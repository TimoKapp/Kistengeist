#!/usr/bin/env python3
"""Setup-Assistent von Kistengeist.

Kleiner Webserver (nur Python-Standardbibliothek), der beim ersten Start auf
Port 80 läuft. Im Browser eines anderen Geräts wählt man Zugangsart, Module,
Passwort und Region; danach startet er den Installer und zeigt den Fortschritt.
"""

from __future__ import annotations

import hmac
import ipaddress
import secrets
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import kistengeist_access as access  # noqa: E402
import kistengeist_ddns as ddns  # noqa: E402
import kistengeist_legal as legal  # noqa: E402
import kistengeist_n8n as n8n  # noqa: E402
import kistengeist_usb as usb  # noqa: E402
import modules as modlib  # noqa: E402

HOME = os.environ.get("CP_HOME_DIR", "/opt/kistengeist")
ROOT = os.environ.get("CP_ROOT", "")
ETC = ROOT + "/etc/kistengeist"
RUN = ROOT + "/run/kistengeist"
LOG = ROOT + "/var/log/kistengeist/install.log"
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
USER = os.environ.get("CP_USER", "claude")
TEST_MODE = os.environ.get("CP_TEST_MODE") == "1"

MAX_BODY = 16 * 1024

TIMEZONES = [
    "Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "Europe/Amsterdam", "Europe/Brussels",
    "Europe/Luxembourg", "Europe/Paris", "Europe/London", "Europe/Rome", "Europe/Madrid",
    "Europe/Warsaw", "Europe/Prague", "UTC",
]
KEYMAPS = {"de": "Deutsch", "ch": "Schweiz", "at": "Österreich (wie Deutsch)",
           "us": "Englisch (US)", "gb": "Englisch (UK)"}
LOCALES = {"de_DE.UTF-8": "Deutsch (Deutschland)", "de_AT.UTF-8": "Deutsch (Österreich)",
           "de_CH.UTF-8": "Deutsch (Schweiz)", "en_US.UTF-8": "English (US)", "en_GB.UTF-8": "English (UK)"}
# raspi-config kennt kein eigenes "at"-Layout; Österreich nutzt das deutsche.
KEYMAP_TO_LAYOUT = {"at": "de"}

NET_ACCESS = ("lan", "dyndns", "tailscale")
TAILSCALE_RE = re.compile(r"^tskey-[A-Za-z0-9_-]{10,200}$")
LICENSE_RE = re.compile(r"^[A-Za-z0-9_-]{8,200}$")
NAME_RE = re.compile(r"^[^\x00-\x1f<>\"'`$\\]{1,50}$")

MIN_PASSWORD = 8
MAX_PASSWORD = 128

_install_lock = threading.Lock()


class ValidationError(ValueError):
    pass


# ---------------------------------------------------------------- Zustand

def read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def setup_value(key: str) -> str:
    try:
        with open(ETC + "/setup.conf", encoding="utf-8") as fh:
            return modlib.parse_conf(fh.read()).get(key, "")
    except OSError:
        return ""


def setup_mode() -> str:
    return setup_value("MODE")


def install_status() -> dict:
    status = _install_status()
    status["mode"] = setup_mode()
    status["remote"] = setup_value("REMOTE")
    return status


def _install_status() -> dict:
    if os.path.exists(ETC + "/installed"):
        return {"state": "done", "step": 1, "total": 1, "module": "", "title": "Fertig", "error": ""}
    status = read_json(RUN + "/status.json")
    if not status:
        return {"state": "idle", "step": 0, "total": 0, "module": "", "title": "", "error": ""}
    # Läuft angeblich, aber der Installer ist weg (z. B. Absturz): als Fehler melden.
    if status.get("state") == "running" and not installer_alive() and time.time() - status.get("updated", 0) > 30:
        status["state"] = "failed"
        status["error"] = "Der Installer wurde unerwartet beendet. Details im Protokoll."
    return status


def installer_alive() -> bool:
    if TEST_MODE:
        return True
    result = subprocess.run(["systemctl", "is-active", "--quiet", "kistengeist-install.service"], check=False)
    return result.returncode == 0


def log_tail(lines: int = 60) -> list[str]:
    try:
        with open(LOG, encoding="utf-8", errors="replace") as fh:
            return [line.rstrip("\n") for line in fh.readlines()[-lines:]]
    except OSError:
        return []


def local_ips() -> list[str]:
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        return []
    ips = []
    for token in out.split():
        try:
            if ipaddress.ip_address(token).version == 4:
                ips.append(token)
        except ValueError:
            continue
    return ips


def online() -> bool:
    if TEST_MODE:
        return os.environ.get("CP_TEST_ONLINE", "1") == "1"
    try:
        socket.create_connection(("downloads.claude.ai", 443), timeout=5).close()
        return True
    except OSError:
        return False


def network_info() -> dict:
    return {
        "online": online(),
        "ips": local_ips(),
        "hostname": socket.gethostname(),
        "hotspot": os.path.exists(RUN + "/hotspot"),
        "wifi": read_json(RUN + "/wifi.json") or [],
    }


def version() -> str:
    try:
        with open(HOME + "/VERSION", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "dev"


def usb_sticks() -> list[dict]:
    if TEST_MODE:
        return json.loads(os.environ.get("CP_TEST_USB", "[]"))
    return usb.list_sticks()


def usb_info() -> list[dict]:
    """USB-Sticks für die Auswahlseite (mit lesbaren Größen)."""
    out = []
    for stick in usb_sticks():
        parts = [f"{p['fstype'] or 'unformatiert'} {p['label']}".strip() for p in stick["partitions"]]
        out.append({**stick, "sizeText": usb.human_size(stick["size"]),
                    "content": ", ".join(parts) or "leer/unformatiert"})
    return out


# ---------------------------------------------------------------- Prüfung

def legal_info() -> dict:
    """Rechtliche Hinweise für die Seite; Absätze als sicher erzeugtes HTML."""
    data = legal.load()
    return {
        "version": legal.version(data),
        "title": data["title"],
        "updated": data["updated"],
        "intro": legal.inline_html(data["intro"]),
        "sections": [{"id": s["id"], "title": s["title"], "paragraphs": [legal.inline_html(p) for p in s["body"]]}
                     for s in data["sections"]],
        "confirmations": data["confirmations"],
    }


def validate(payload: dict, modules: dict[str, modlib.Module]) -> dict:
    # Ohne aktive Bestätigung der rechtlichen Hinweise wird nichts installiert.
    if not legal.accepted(legal.load(), payload.get("legal")):
        raise ValidationError("Bitte zuerst die rechtlichen Hinweise lesen und alle Punkte bestätigen.")

    mode = payload.get("mode")
    if mode not in modlib.MODES:
        raise ValidationError("Bitte eine Zugangsart wählen.")

    selected = payload.get("modules", [])
    if not isinstance(selected, list) or not all(isinstance(m, str) for m in selected):
        raise ValidationError("Ungültige Modulauswahl.")
    try:
        plan = modlib.plan(modules, mode, selected)
    except modlib.PlanError as exc:
        raise ValidationError(str(exc)) from exc

    password = payload.get("password", "")
    if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise ValidationError(f"Das Passwort muss {MIN_PASSWORD} bis {MAX_PASSWORD} Zeichen lang sein.")
    if any(ch in password for ch in "\n\r\0"):
        raise ValidationError("Das Passwort enthält ungültige Zeichen.")

    timezone = payload.get("timezone", "Europe/Berlin")
    keymap = payload.get("keymap", "de")
    locale = payload.get("locale", "de_DE.UTF-8")
    if timezone not in TIMEZONES or keymap not in KEYMAPS or locale not in LOCALES:
        raise ValidationError("Ungültige Region.")

    usb_cfg = {"device": "", "format": False, "label": usb.DEFAULT_LABEL}
    if "usb-stick" in plan:
        raw = payload.get("usb") or {}
        if not isinstance(raw, dict):
            raise ValidationError("Ungültige Angaben zum USB-Stick.")
        device = raw.get("device") or ""
        if device and (not isinstance(device, str)
                       or not re.fullmatch(r"/dev/disk/by-id/usb-[A-Za-z0-9._:-]+", device)):
            raise ValidationError("Ungültiger USB-Stick.")
        if device:
            stick = next((s for s in usb_sticks() if s["id"] == device), None)
            if stick is None:
                raise ValidationError("Der gewählte USB-Stick wurde nicht gefunden. Bitte neu suchen.")
            label = raw.get("label") or usb.DEFAULT_LABEL
            if not isinstance(label, str) or not usb.valid_label(label):
                raise ValidationError("Bezeichnung des Sticks: 1–11 Zeichen, nur Buchstaben, Ziffern, - und _.")
            fmt = raw.get("format") is True
            if fmt and raw.get("formatConfirmed") is not True:
                raise ValidationError("Bitte bestätigen, dass alle Daten auf dem Stick gelöscht werden dürfen.")
            if not fmt and not stick["usable"]:
                raise ValidationError("Der Stick hat kein nutzbares Dateisystem – bitte „formatieren“ wählen.")
            usb_cfg = {"device": device, "format": fmt, "label": label}

    inet = validate_internet(payload.get("internet") or {}, plan)

    remote = payload.get("remote", "rdp")
    if remote not in ("rdp", "browser"):
        raise ValidationError("Bitte wählen: Fernzugriff über Browser oder RDP.")
    browser_pw = ""
    if mode != "desktop" and remote == "browser":
        # Eigenes Passwort: das Anmeldepasswort (sudo) wird nirgends gespeichert.
        browser_pw = payload.get("browserPassword", "")
        if not isinstance(browser_pw, str) or not MIN_PASSWORD <= len(browser_pw) <= MAX_PASSWORD:
            raise ValidationError(f"Das Browser-Passwort muss {MIN_PASSWORD} bis {MAX_PASSWORD} Zeichen lang sein.")
        if any(ch in browser_pw for ch in "\n\r\0"):
            raise ValidationError("Das Browser-Passwort enthält ungültige Zeichen.")
        if browser_pw == payload.get("password"):
            raise ValidationError("Bitte für den Browser ein anderes Passwort als das Anmeldepasswort wählen.")
    # "beides": ohne angemeldete Sitzung am Pi gäbe es nichts zu spiegeln. Browser ohne Monitor:
    # die Sitzung läuft dauerhaft im Hintergrund (Anmeldung schützt der Browser-Zugang).
    autologin = (mode == "both" or (mode == "desktop" and payload.get("autologin") is True)
                 or (mode == "rdp" and remote == "browser"))
    # Nur Module, die in dieser Zugangsart vorkommen (Pflichtmodule ergänzt der Plan).
    chosen = [m for m in plan if not modules[m].required]
    return {
        "mode": mode,
        "remote": remote if mode != "desktop" else "",
        "browser_password": browser_pw,
        "modules": chosen,
        "plan": plan,
        "password": password,
        "timezone": timezone,
        "keymap": KEYMAP_TO_LAYOUT.get(keymap, keymap),
        "locale": locale,
        "autologin": autologin,
        # Datensparsam: Fehlerberichte und Umfragen von Claude Code aus (Standard an).
        "privacy_minimal": payload.get("privacy_minimal", True) is not False,
        "usb": usb_cfg,
        "internet": inet,
    }


def validate_internet(raw: dict, plan: list[str]) -> dict:
    """Webserver/Erreichbarkeit, n8n-Konto und Zugangsdaten-Datei."""
    if not isinstance(raw, dict):
        raise ValidationError("Ungültige Angaben zu Internet und n8n.")
    out: dict = {"net": "lan", "provider": "", "host": "", "ddns_secret": None, "email": "", "ipv6_only": False,
                 "tailscale_key": "", "n8n": None, "file_secrets": raw.get("fileSecrets", True) is not False,
                 "file_usb": raw.get("fileUsb") is True}
    if "webserver" in plan:
        net = raw.get("net", "lan")
        if net not in NET_ACCESS:
            raise ValidationError("Bitte wählen, wie der Pi erreichbar sein soll.")
        out["net"] = net
        email = str(raw.get("acmeEmail") or "").strip()
        if email and not n8n.EMAIL_RE.match(email):
            raise ValidationError("Die E-Mail-Adresse für das Zertifikat ist ungültig.")
        out["email"] = email
        if net == "dyndns":
            provider, host, secret = ddns_input(raw)
            out.update(provider=provider, host=host, ddns_secret=secret, ipv6_only=raw.get("ipv6Only") is True)
        elif net == "tailscale":
            key = str(raw.get("tailscaleKey") or "").strip()
            if key and not TAILSCALE_RE.match(key):
                raise ValidationError("Der Tailscale-Schlüssel beginnt mit „tskey-“.")
            out["tailscale_key"] = key
    if "n8n" in plan:
        n = raw.get("n8n") or {}
        if not isinstance(n, dict):
            raise ValidationError("Ungültige Angaben zum n8n-Konto.")
        first, last = str(n.get("firstName") or "").strip(), str(n.get("lastName") or "").strip()
        email, pw = str(n.get("email") or "").strip(), n.get("password", "")
        license_key = str(n.get("license") or "").strip()
        if not NAME_RE.match(first) or not NAME_RE.match(last):
            raise ValidationError("Bitte Vor- und Nachnamen für das n8n-Konto angeben.")
        if not n8n.EMAIL_RE.match(email):
            raise ValidationError("Bitte eine gültige E-Mail-Adresse für das n8n-Konto angeben.")
        problem = n8n.password_problem(pw)
        if problem:
            raise ValidationError(problem)
        if license_key and not LICENSE_RE.match(license_key):
            raise ValidationError("Der n8n-Lizenzschlüssel enthält ungültige Zeichen.")
        out["n8n"] = {"firstName": first, "lastName": last, "email": email, "password": pw, "license": license_key}
    return out


def setup_conf(cfg: dict) -> str:
    usb_cfg = cfg.get("usb") or {"device": "", "format": False, "label": usb.DEFAULT_LABEL}
    inet = cfg.get("internet") or {}
    return (
        "# Von der Einrichtung erzeugt. Enthält keine Passwörter.\n"
        f'MODE="{cfg["mode"]}"\n'
        f'REMOTE="{cfg.get("remote", "")}"\n'
        f'AUTOLOGIN="{"yes" if cfg["autologin"] else "no"}"\n'
        f'MODULES="{" ".join(cfg["modules"])}"\n'
        f'TIMEZONE="{cfg["timezone"]}"\n'
        f'KEYMAP="{cfg["keymap"]}"\n'
        f'LOCALE="{cfg["locale"]}"\n'
        f'PRIVACY_MINIMAL="{"yes" if cfg.get("privacy_minimal", True) else "no"}"\n'
        f'USB_DEVICE="{usb_cfg["device"]}"\n'
        f'USB_FORMAT="{"yes" if usb_cfg["format"] else "no"}"\n'
        f'USB_LABEL="{usb_cfg["label"]}"\n'
        f'NET_ACCESS="{inet.get("net", "lan")}"\n'
        f'DDNS_PROVIDER="{inet.get("provider", "")}"\n'
        f'DDNS_HOST="{inet.get("host", "")}"\n'
        f'DDNS_IPV6_ONLY="{"yes" if inet.get("ipv6_only") else "no"}"\n'
        f'ACME_EMAIL="{inet.get("email", "")}"\n'
        f'ACCESS_FILE_SECRETS="{"yes" if inet.get("file_secrets", True) else "no"}"\n'
        f'ACCESS_FILE_USB="{"yes" if inet.get("file_usb") else "no"}"\n'
    )


# ---------------------------------------------------------------- Aktionen

def write_private(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)  # auch wenn die Datei schon mit anderen Rechten existierte
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)


def set_password(password: str) -> None:
    if TEST_MODE:
        return
    result = subprocess.run(["chpasswd"], input=f"{USER}:{password}\n", text=True,
                            capture_output=True, check=False)
    if result.returncode != 0:
        raise ValidationError("Das Passwort konnte nicht gesetzt werden.")


def start_installer(cfg: dict) -> None:
    os.makedirs(ETC, exist_ok=True)
    os.makedirs(RUN, exist_ok=True)
    with open(ETC + "/setup.conf", "w", encoding="utf-8") as fh:
        fh.write(setup_conf(cfg))
    # Nachweis der Bestätigung: nur Version und Zeitpunkt, keine personenbezogenen Daten.
    data = legal.load()
    with open(ETC + "/legal-accepted", "w", encoding="utf-8") as fh:
        fh.write(legal.record(data, time.strftime("%Y-%m-%dT%H:%M:%S%z"), ntp_synced()))
    # Kopie des bestätigten Textes, damit er später nachvollziehbar bleibt.
    with open(ETC + "/legal-accepted.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    if cfg.get("remote") == "browser":
        # Nur im RAM (/run), der Installer löscht die Datei nach Gebrauch.
        write_private(RUN + "/secret", cfg["browser_password"] + "\n")
    elif cfg["mode"] == "both":
        # Nur im RAM (/run), der Installer löscht die Datei nach Gebrauch (VNC-Spiegelung).
        write_private(RUN + "/secret", cfg["password"] + "\n")
    if (cfg.get("browser_password") and "zugangsdaten" in cfg["plan"]
            and (cfg.get("internet") or {}).get("file_secrets", True)):
        write_private(RUN + "/browser.secret", cfg["browser_password"] + "\n")
    inet = cfg.get("internet") or {}
    # Für die Zugangsdaten-Datei (nur wenn gewählt) und das n8n-Konto: ebenfalls nur im RAM.
    if inet.get("file_secrets", True) and "zugangsdaten" in cfg["plan"]:
        write_private(RUN + "/account.secret", cfg["password"] + "\n")
    if inet.get("n8n"):
        write_private(RUN + "/n8n.json", json.dumps(inet["n8n"], ensure_ascii=False))
    if inet.get("tailscale_key"):
        write_private(RUN + "/tailscale.key", inet["tailscale_key"] + "\n")
    if inet.get("ddns_secret"):
        # Dauerhaft nötig (Aktualisierung bei jeder neuen IP); nur für root lesbar.
        write_private(ETC + "/ddns.json", json.dumps(inet["ddns_secret"]))
    with open(RUN + "/status.json", "w", encoding="utf-8") as fh:
        json.dump({"state": "running", "step": 0, "total": len(cfg["plan"]), "module": "",
                   "title": "Start", "error": "", "updated": int(time.time())}, fh)
    if TEST_MODE:
        return
    subprocess.run(["systemctl", "reset-failed", "kistengeist-install.service"],
                   check=False, capture_output=True)
    subprocess.run(
        ["systemd-run", "--unit=kistengeist-install", "--collect",
         "--description=Kistengeist Installation", HOME + "/bin/kistengeist-install"],
        check=True, capture_output=True,
    )


def sync_clock_from_browser(client_ms: object) -> bool:
    """Pi ohne Echtzeituhr: ist die Zeit nicht per NTP gestellt und weicht sie deutlich von der
    Zeit des Browsers ab, wird sie übernommen (sonst scheitern apt und HTTPS)."""
    if TEST_MODE or not isinstance(client_ms, int | float) or ntp_synced() == "yes":
        return False
    client = client_ms / 1000
    if client < 1.7e9 or abs(client - time.time()) < 300:  # unplausibel oder schon passend
        return False
    return subprocess.run(["date", "-s", f"@{int(client)}"], capture_output=True, check=False).returncode == 0


def ntp_synced() -> str:
    if TEST_MODE:
        return "test"
    try:
        out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                             capture_output=True, text=True, timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unbekannt"
    return out or "unbekannt"


def ddns_input(raw: dict) -> tuple[str, str, dict]:
    """Anbieter, vollständige Adresse und Zugang aus den Eingaben des Assistenten."""
    provider = str(raw.get("provider") or "")
    try:
        host = ddns.normalize_host(provider, raw.get("host"))
        secret = ddns.normalize_secret(provider, raw.get("token"), raw.get("user"), raw.get("password"))
    except ddns.DdnsError as exc:
        raise ValidationError(str(exc)) from exc
    return provider, host, secret


def ddns_test(provider: str, host: str, secret: dict, ipv6_only: bool = False) -> dict:
    """Meldet die Adresse einmal echt beim Anbieter (zählt dort wie eine normale Aktualisierung)."""
    if TEST_MODE:
        bad = secret.get("token") == "00000000-0000-0000-0000-000000000000" or secret.get("password") == "falsch"
        return {"ok": not bad, "ip": "203.0.113.7", "host": host, "detail": "test"}
    _state, result, message = ddns.run_update(provider, host, secret, ipv6_only, {}, force=True)
    return {"ok": result == "ok", "ip": _state.get("ipv4") or _state.get("ipv6") or "", "host": host,
            "detail": "" if result == "ok" else message}


def mark_failed(message: str) -> None:
    try:
        with open(RUN + "/status.json", "w", encoding="utf-8") as fh:
            json.dump({"state": "failed", "step": 0, "total": 0, "module": "", "title": "",
                       "error": message, "updated": int(time.time())}, fh)
    except OSError:
        pass


def connect_wifi(ssid: str, password: str) -> None:
    """Wechselt vom Einrichtungs-Hotspot ins eigene WLAN (läuft im Hintergrund)."""
    def worker() -> None:
        time.sleep(2)  # Antwort an den Browser noch ausliefern
        subprocess.run([HOME + "/bin/kistengeist-hotspot", "connect", ssid, password],
                       check=False, capture_output=True)
    if not TEST_MODE:
        threading.Thread(target=worker, daemon=True).start()


def reboot() -> None:
    if TEST_MODE:
        return
    threading.Thread(target=lambda: (time.sleep(3), subprocess.run(["systemctl", "reboot"], check=False)),
                     daemon=True).start()


# ---------------------------------------------------------------- Einrichtungscode

# Ohne verwechselbare Zeichen (0/O, 1/I/L); 10 Zeichen ≈ 50 Bit, zugleich WPA2-Passwort des Setup-WLANs.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_RE = re.compile(r"^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{10}$")
BOOT_CODE_FILE = ROOT + "/boot/firmware/kistengeist-code.txt"
MAX_CODE_FAILS = 10
CODE_LOCK_SECONDS = 600
_code_fails: dict[str, list[float]] = {}
_code_lock = threading.Lock()


def setup_code() -> str:
    """Pro Gerät zufälliger Code; auch kistengeist-setupcode nutzt dieselbe Datei."""
    path = ETC + "/setup-code"
    os.makedirs(ETC, exist_ok=True)
    import fcntl
    with open(path + ".lock", "w") as lock:  # gleiche Sperre wie bin/kistengeist-setupcode
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _setup_code_locked(path)


def _setup_code_locked(path: str) -> str:
    try:
        code = open(path, encoding="utf-8").read().strip()
        if CODE_RE.match(code):
            return code
    except OSError:
        pass
    code = ""
    try:  # vom Windows-Werkzeug vorgegeben (Boot-Partition, auch am PC lesbar)
        code = open(BOOT_CODE_FILE, encoding="utf-8").read().strip().upper()
    except OSError:
        pass
    if not CODE_RE.match(code):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
    write_private(path, code + "\n")
    return code


def code_ok(given: str | None, client: str) -> bool | None:
    """True/False; None = zu viele Fehlversuche (vorübergehend gesperrt)."""
    now = time.time()
    with _code_lock:
        fails = [t for t in _code_fails.get(client, []) if now - t < CODE_LOCK_SECONDS]
        _code_fails[client] = fails
        if len(fails) >= MAX_CODE_FAILS:
            return None
        ok = hmac.compare_digest((given or "").strip().upper().encode(), setup_code().encode())
        if not ok:
            fails.append(now)
        return ok


# ---------------------------------------------------------------- HTTP

def host_allowed(host_header: str | None) -> bool:
    """Schutz gegen DNS-Rebinding: nur IP-Adressen und der eigene Gerätename."""
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    name = socket.gethostname().lower()
    return host in {"localhost", name, name + ".local", name + ".lan", name + ".home", name + ".fritz.box"}


class Handler(BaseHTTPRequestHandler):
    server_version = "KistengeistSetup"
    modules_dir = HOME + "/modules"

    def log_message(self, fmt: str, *args) -> None:  # leiser als Standard
        sys.stderr.write("setup: " + (fmt % args) + "\n")

    # Antworten
    def send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"ok": False, "error": message}, status)

    def send_static(self, name: str, ctype: str) -> None:
        try:
            with open(os.path.join(STATIC, name), "rb") as fh:
                body = fh.read()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict | None:
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self.send_error_json("Erwarte JSON.", 415)
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.send_error_json("Anfrage zu groß.", 413)
            return None
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self.send_error_json("Ungültiges JSON.")
            return None
        if not isinstance(data, dict):
            self.send_error_json("Ungültiges JSON.")
            return None
        return data

    def guard(self, path: str = "") -> bool:
        if not host_allowed(self.headers.get("Host")):
            self.send_error_json("Unbekannter Hostname. Bitte die IP-Adresse oder kistengeist.local verwenden.", 403)
            return False
        # Alles außer Startseite, Skripten und Grundinfo nur mit dem Einrichtungscode (steht am
        # Bildschirm des Pi, im Windows-Werkzeug bzw. am Ende von install.sh).
        if path in ("/", "/index.html", "/app.js", "/style.css", "/api/info"):
            return True
        given = self.headers.get("X-Setup-Code")
        if given is None and "?" in self.path:
            from urllib.parse import parse_qs
            given = (parse_qs(self.path.split("?", 1)[1]).get("code") or [None])[0]
        ok = code_ok(given, self.client_address[0])
        if ok is None:
            self.send_error_json("Zu viele falsche Codes. Bitte 10 Minuten warten.", 429)
            return False
        if not ok:
            self.send_error_json("Einrichtungscode fehlt oder ist falsch.", 401)
            return False
        return True

    # Routen
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not self.guard(path):
            return
        if path in ("/", "/index.html"):
            self.send_static("index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self.send_static("app.js", "text/javascript; charset=utf-8")
        elif path == "/style.css":
            self.send_static("style.css", "text/css; charset=utf-8")
        elif path == "/api/info":
            self.api_info()
        elif path == "/kistengeist.rdp":
            body = access.rdp_file(socket.gethostname() + ".local", USER).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-rdp")
            self.send_header("Content-Disposition", 'attachment; filename="Kistengeist.rdp"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/ports":
            self.api_ports()
        elif path == "/api/usb":
            self.send_json({"sticks": usb_info()})
        elif path == "/api/status":
            self.send_json({"status": install_status(), "log": log_tail()})
        else:
            self.send_error_json("Nicht gefunden.", 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not self.guard(path):
            return
        data = self.read_json_body()
        if data is None:
            return
        if path == "/api/code":
            self.send_json({"ok": True})          # guard() hat den Code schon geprüft
        elif path == "/api/install":
            self.api_install(data)
        elif path == "/api/ddns-test":
            self.api_ddns_test(data)
        elif path == "/api/wifi":
            self.api_wifi(data)
        elif path == "/api/reboot":
            if install_status()["state"] != "done":
                self.send_error_json("Die Installation ist noch nicht fertig.", 409)
                return
            self.send_json({"ok": True})
            reboot()
        else:
            self.send_error_json("Nicht gefunden.", 404)

    def api_info(self) -> None:
        try:
            modules = modlib.load_modules(self.modules_dir)
        except modlib.PlanError as exc:
            self.send_error_json(str(exc), 500)
            return
        self.send_json({
            "version": version(),
            "user": USER,
            "modules": modlib.module_list(modules),
            "network": network_info(),
            "status": install_status(),
            "timezones": TIMEZONES,
            "keymaps": KEYMAPS,
            "locales": LOCALES,
            "minPassword": MIN_PASSWORD,
            "legal": legal_info(),
        })

    def api_install(self, data: dict) -> None:
        with _install_lock:
            state = install_status()["state"]
            if state in ("running", "done"):
                self.send_error_json("Die Installation läuft bereits oder ist abgeschlossen.", 409)
                return
            try:
                cfg = validate(data, modlib.load_modules(self.modules_dir))
            except (ValidationError, modlib.PlanError) as exc:
                self.send_error_json(str(exc))
                return
            if not online():
                self.send_error_json("Keine Internetverbindung. Bitte zuerst Netzwerk verbinden.", 409)
                return
            sync_clock_from_browser(data.get("clientTime"))
            try:
                set_password(cfg["password"])
                start_installer(cfg)
            except ValidationError as exc:
                self.send_error_json(str(exc), 500)
                return
            except (OSError, subprocess.CalledProcessError) as exc:
                mark_failed(f"Installer konnte nicht gestartet werden: {exc}")
                self.send_error_json(f"Installer konnte nicht gestartet werden: {exc}", 500)
                return
        self.send_json({"ok": True, "plan": cfg["plan"]})

    def api_ddns_test(self, data: dict) -> None:
        """Prüft Adresse und Zugang direkt beim Anbieter (trägt dabei die aktuelle IP ein)."""
        try:
            provider, host, secret = ddns_input(data)
        except ValidationError as exc:
            self.send_error_json(str(exc))
            return
        self.send_json(ddns_test(provider, host, secret, data.get("ipv6Only") is True))

    def api_ports(self) -> None:
        """Portliste für die Fertig-Seite (ohne Geheimnisse)."""
        cfg = modlib.parse_conf(open(ETC + "/setup.conf", encoding="utf-8").read()) \
            if os.path.exists(ETC + "/setup.conf") else {}
        self.send_json({"ports": access.ports(cfg, read_json(ETC + "/access.json") or {}),
                        "access": read_json(ETC + "/access.json") or {}})

    def api_wifi(self, data: dict) -> None:
        ssid = data.get("ssid", "")
        password = data.get("password", "")
        if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32:
            self.send_error_json("Bitte ein WLAN auswählen.")
            return
        if not os.path.exists(RUN + "/hotspot"):
            self.send_error_json("WLAN lässt sich hier nur im Einrichtungs-WLAN ändern.", 409)
            return
        hex_psk = re.fullmatch(r"[0-9a-fA-F]{64}", password or "") is not None
        if not isinstance(password, str) or (password and not hex_psk and not 8 <= len(password) <= 63) \
                or re.search(r"[\r\n\0]", password + ssid):
            self.send_error_json("Das WLAN-Passwort muss 8 bis 63 Zeichen lang sein.")
            return
        self.send_json({"ok": True})
        connect_wifi(ssid, password)


def main() -> int:
    port = int(os.environ.get("CP_SETUP_PORT", "80"))
    setup_code()  # früh anlegen: Bildschirmanzeige und Setup-WLAN lesen dieselbe Datei
    server = ThreadingHTTPServer(("", port), Handler)
    server.daemon_threads = True
    print(f"Setup-Assistent läuft auf Port {port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
