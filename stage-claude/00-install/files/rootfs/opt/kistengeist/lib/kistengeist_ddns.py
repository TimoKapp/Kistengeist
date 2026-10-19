#!/usr/bin/env python3
"""Dynamische Adresse (DynDNS) für den Pi – mehrere kostenlose Anbieter mit Update-API.

Anbieter (Stand Oktober 2026, jeweils offizielle Update-API):
  ipv64   https://ipv64.net/dyndns_updater_api    Token, gratis 3 Adressen, Tageslimit für Updates
  dynv6   https://dynv6.com/docs/apis             Token, gratis, ohne bekanntes Limit
  noip    https://www.noip.com/integrate/request  DDNS-Key (Benutzer + Passwort), gratis 1 Adresse,
                                                  alle 30 Tage per E-Mail bestätigen
  duckdns https://www.duckdns.org/spec.jsp        Token, gratis 5 Adressen

Damit Tageslimits (ipv64) und Sperren wegen „nochg“-Flut (No-IP) nicht greifen, meldet der Pi
nur, wenn sich seine öffentliche Adresse geändert hat – und sonst einmal täglich.

Einstellungen: /etc/kistengeist/setup.conf (DDNS_PROVIDER, DDNS_HOST, DDNS_IPV6_ONLY),
Zugang: /etc/kistengeist/ddns.json (nur root), Zustand: /var/lib/kistengeist/ddns-state.json.

Aufruf: kistengeist_ddns.py [--force]
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ETC = os.environ.get("CP_ETC", "/etc/kistengeist")
STATE = os.environ.get("CP_DDNS_STATE", "/var/lib/kistengeist/ddns-state.json")
STATUS = os.environ.get("CP_DDNS_STATUS", "/run/kistengeist/ddns.status")
USER_AGENT = "Kistengeist kistengeist-ddns/Linux-1.0 kistengeist@users.noreply.github.com"
REFRESH = 24 * 3600          # auch ohne Änderung einmal täglich melden
RETRY_UNKNOWN_IP = 3600      # eigene IPv4 nicht ermittelbar: höchstens stündlich blind melden …
RETRY_UNKNOWN_IP_NOIP = 12 * 3600  # … bei No-IP seltener (Sperre bei vielen „nochg“)

PROVIDERS: dict[str, dict] = {
    "ipv64": {
        "label": "ipv64.net",
        "site": "https://ipv64.net",
        "auth": "token",
        "domains": ("ipv64.net", "ipv64.de", "any64.de", "api64.de", "dns64.de", "dyndns64.de", "dynipv6.de",
                    "eth64.de", "home64.de", "iot64.de", "lan64.de", "nas64.de", "root64.de", "route64.de",
                    "srv64.de", "tcp64.de", "udp64.de", "vpn64.de", "wan64.de"),
    },
    "dynv6": {
        "label": "dynv6",
        "site": "https://dynv6.com",
        "auth": "token",
        "domains": ("dynv6.net", "dns.army", "dns.navy", "v6.army", "v6.navy", "v6.rocks"),
    },
    "noip": {
        "label": "No-IP",
        "site": "https://www.noip.com",
        "auth": "basic",
        # No-IP bietet über 30 Gratis-Domains (ddns.net, hopto.org, zapto.org …) – jede ist erlaubt.
        "domains": (),
    },
    "duckdns": {
        "label": "DuckDNS",
        "site": "https://www.duckdns.org",
        "auth": "token",
        "domains": ("duckdns.org",),
    },
}

LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{8,200}$")
DUCK_TOKEN_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
USER_RE = re.compile(r"^[^\s:]{1,128}$")


class DdnsError(ValueError):
    pass


# ------------------------------------------------------------------ Eingaben prüfen

def normalize_host(provider: str, raw: object) -> str:
    """Vollständiger Name, z. B. „MeinPi“ (DuckDNS) → meinpi.duckdns.org."""
    if provider not in PROVIDERS:
        raise DdnsError("Bitte einen DynDNS-Anbieter wählen.")
    host = str(raw or "").strip().lower()
    host = re.sub(r"^[a-z]+://", "", host).split("/")[0].strip(".")
    if provider == "duckdns" and "." not in host:
        host += ".duckdns.org"
    labels = host.split(".")
    if len(labels) < 3 or not all(LABEL_RE.match(x) for x in labels) or len(host) > 253:
        raise DdnsError("Bitte die vollständige Adresse eingeben, z. B. " + example(provider) + ".")
    domains = PROVIDERS[provider]["domains"]
    if domains and ".".join(labels[1:]) not in domains:
        raise DdnsError(f"Die Adresse muss auf eine Domain von {PROVIDERS[provider]['label']} enden, z. B. "
                        + example(provider) + ".")
    return host


def example(provider: str) -> str:
    return {"ipv64": "meinpi.ipv64.net", "dynv6": "meinpi.dynv6.net", "noip": "meinpi.ddns.net",
            "duckdns": "meinpi.duckdns.org"}.get(provider, "meinpi.example.net")


def normalize_secret(provider: str, token: object = "", user: object = "", password: object = "") -> dict:
    if provider not in PROVIDERS:
        raise DdnsError("Bitte einen DynDNS-Anbieter wählen.")
    if PROVIDERS[provider]["auth"] == "basic":
        u, p = str(user or "").strip(), str(password or "")
        if not USER_RE.match(u):
            raise DdnsError("Bitte den Benutzernamen des DDNS-Keys von No-IP einfügen.")
        if not p or len(p) > 128 or any(ord(c) < 32 for c in p):
            raise DdnsError("Bitte das Passwort des DDNS-Keys von No-IP einfügen.")
        return {"user": u, "password": p}
    t = str(token or "").strip()
    if provider == "duckdns":
        t = t.lower()
        if not DUCK_TOKEN_RE.match(t):
            raise DdnsError("Der DuckDNS-Token hat nicht das erwartete Format (xxxxxxxx-xxxx-…).")
    elif not TOKEN_RE.match(t):
        raise DdnsError(f"Bitte den Token von {PROVIDERS[provider]['label']} vollständig einfügen.")
    return {"token": t}


# ------------------------------------------------------------------ Anfragen

def build_request(provider: str, host: str, secret: dict, ipv4: str | None, ipv6: str | None,
                  v6only: bool = False, clear: bool = False) -> tuple[str, dict]:
    """URL und Kopfzeilen für eine Aktualisierung. ipv4=None: der Anbieter nimmt die Absenderadresse."""
    headers = {"User-Agent": USER_AGENT}
    if provider == "ipv64":
        base = "https://ipv64.net/nic/update"
        q = {"domain": host, "output": "min"}
        if ipv4 and not v6only:
            q["ip"] = ipv4
        if ipv6:
            q["ip6"] = ipv6
        headers["Authorization"] = "Bearer " + secret["token"]
        return base + "?" + urllib.parse.urlencode(q), headers
    if provider == "dynv6":
        if v6only:
            q = {"zone": host, "token": secret["token"], "ipv4": "-", "ipv6": ipv6 or "auto"}
            return "https://dynv6.com/api/update?" + urllib.parse.urlencode(q), headers
        q = {"zone": host, "token": secret["token"], "ipv4": ipv4 or "auto"}
        if ipv6:
            q["ipv6"] = ipv6
        return "https://ipv4.dynv6.com/api/update?" + urllib.parse.urlencode(q), headers
    if provider == "noip":
        q = {"hostname": host}
        if v6only:
            if ipv6:
                q["myipv6"] = ipv6
        elif ipv4:
            q["myip"] = ipv4 + ("," + ipv6 if ipv6 else "")
        elif ipv6:
            q["myipv6"] = ipv6
        cred = base64.b64encode(f"{secret['user']}:{secret['password']}".encode()).decode()
        headers["Authorization"] = "Basic " + cred
        return "https://dynupdate.no-ip.com/nic/update?" + urllib.parse.urlencode(q), headers
    if provider == "duckdns":
        q = {"domains": host.removesuffix(".duckdns.org"), "token": secret["token"], "verbose": "true"}
        if clear:
            q["clear"] = "true"
        else:
            if not v6only:
                q["ip"] = ipv4 or ""
            # Mit ipv6= schaltet DuckDNS die IPv4-Erkennung ab – ohne eigene IPv4 also weglassen.
            if ipv6 and (ipv4 or v6only):
                q["ipv6"] = ipv6
        return "https://www.duckdns.org/update?" + urllib.parse.urlencode(q), headers
    raise DdnsError(f"Unbekannter Anbieter: {provider}")


def parse_response(provider: str, status: int, body: str) -> tuple[str, str]:
    """→ (ok | fatal | retry, Meldung). fatal: erst nach geänderten Zugangsdaten erneut versuchen."""
    text = body.strip()
    first = text.splitlines()[0].strip() if text else ""
    low = first.lower()
    if provider == "ipv64":
        if status == 200 and low.split()[:1] in (["good"], ["nochg"]):
            return "ok", first
        if status == 401 or "badauth" in low:
            return "fatal", ("ipv64 lehnt den Token ab (Token oder Adresse prüfen; nach mehreren Fehlversuchen "
                             "sperrt ipv64 den Token 10 Minuten).")
        if status in (400, 403, 404, 409):
            return "fatal", f"ipv64 lehnt die Aktualisierung ab ({first or status}) – Adresse im Konto prüfen."
        if status == 429 or "overcommited" in low:
            return "retry", "ipv64: Tageslimit für Aktualisierungen erreicht – nächster Versuch später."
        return "retry", f"ipv64 meldet: {first or status}"
    if provider == "dynv6":
        if status == 200:
            return "ok", first or "aktualisiert"
        if status in (401, 403, 404):
            return "fatal", "dynv6 lehnt Token oder Adresse ab (Token und Zone prüfen)."
        return "retry", f"dynv6 meldet: {first or status}"
    if provider == "noip":
        word = low.split()[0] if low else ""
        if word in ("good", "nochg"):
            return "ok", first
        if word in ("nohost", "badauth", "badagent", "!donator", "abuse"):
            reason = {"nohost": "Adresse gibt es im Konto nicht", "badauth": "Benutzer/Passwort falsch",
                      "abuse": "Adresse wegen Missbrauchs gesperrt", "!donator": "Funktion nur im Bezahltarif",
                      "badagent": "Programm abgelehnt"}[word]
            return "fatal", f"No-IP: {reason} ({word})."
        return "retry", f"No-IP meldet: {first or status} – nächster Versuch frühestens in 30 Minuten."
    if provider == "duckdns":
        if status == 200 and first == "OK":
            return "ok", "OK"
        if first == "KO":
            return "fatal", "DuckDNS meldet KO – Name oder Token stimmen nicht."
        return "retry", f"DuckDNS meldet: {first or status}"
    return "fatal", "Unbekannter Anbieter."


def http_get(url: str, headers: dict, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4000).decode("utf-8", "replace") if exc.fp else ""


# ------------------------------------------------------------------ eigene Adressen

def public_ipv4(get=http_get) -> str | None:
    for url in ("https://api.ipify.org", "https://ipv4.icanhazip.com"):
        try:
            status, body = get(url, {"User-Agent": USER_AGENT}, 10)
            ip = ipaddress.ip_address(body.strip())
        except (OSError, ValueError):
            continue
        if status == 200 and ip.version == 4 and ip.is_global:
            return str(ip)
    return None


def local_ipv6(ip_output: str | None = None) -> str | None:
    """Stabile globale IPv6 des Pi (keine temporäre Datenschutzadresse, keine Docker-/VPN-Netze)."""
    if ip_output is None:
        try:
            ip_output = subprocess.run(["ip", "-6", "-o", "addr", "show", "scope", "global", "-temporary",
                                        "-deprecated"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
    for line in ip_output.splitlines():
        parts = line.split()
        if len(parts) < 4 or re.match(r"^(docker|br-|veth|tailscale)", parts[1]):
            continue
        addr = parts[3].split("/")[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.version == 6 and ip.is_global:
            return str(ip)
    return None


# ------------------------------------------------------------------ Ablauf

def fingerprint(provider: str, host: str, secret: dict, v6only: bool) -> str:
    raw = json.dumps([provider, host, secret, v6only], sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def run_update(provider: str, host: str, secret: dict, v6only: bool, state: dict, *, force: bool = False,
               now: float | None = None, get=http_get, ipv4: str | None = None, ipv6: str | None = None,
               detect: bool = True) -> tuple[dict, str, str]:
    """Eine Runde. → (neuer Zustand, Ergebnis ok|skip|fatal|retry|blocked, Meldung)."""
    now = time.time() if now is None else now
    fp = fingerprint(provider, host, secret, v6only)
    if state.get("fp") != fp:
        state = {"fp": fp}
    if not force:
        if state.get("blocked"):
            return state, "blocked", state["blocked"]
        if now < state.get("retry_after", 0):
            return state, "skip", "wartet (Anbieter bat um Pause)"
    if detect:
        ipv4 = None if v6only else public_ipv4(get)
        ipv6 = local_ipv6()
    if v6only and not ipv6:
        return state, "retry", "Keine globale IPv6-Adresse gefunden (DS-Lite-Einstellung)."
    if not force and "time" in state:
        age = now - state["time"]
        same = state.get("ipv4") == ipv4 and state.get("ipv6") == ipv6
        reported = ipv6 if v6only else ipv4
        if same and reported is not None and age < REFRESH:
            return state, "skip", "unverändert"
        blind = RETRY_UNKNOWN_IP_NOIP if provider == "noip" else RETRY_UNKNOWN_IP
        if reported is None and same and age < blind:
            return state, "skip", "eigene Adresse unbekannt – nächster Versuch später"
    if provider == "duckdns" and v6only and not state.get("cleared"):
        # DS-Lite: alte (unerreichbare) IPv4 einmalig löschen.
        url, headers = build_request(provider, host, secret, None, None, v6only, clear=True)
        try:
            status, body = get(url, headers, 20)
        except OSError as exc:
            return state, "retry", f"{PROVIDERS[provider]['label']} nicht erreichbar: {exc}"
        if parse_response(provider, status, body)[0] == "ok":
            state["cleared"] = True
    url, headers = build_request(provider, host, secret, ipv4, ipv6, v6only)
    try:
        status, body = get(url, headers, 20)
    except OSError as exc:
        return state, "retry", f"{PROVIDERS[provider]['label']} nicht erreichbar: {exc}"
    result, message = parse_response(provider, status, body)
    if result == "ok":
        state.update(ipv4=ipv4, ipv6=ipv6, time=now, retry_after=0, blocked="")
    elif result == "fatal":
        state["blocked"] = message
    else:
        pause = 3 * 3600 if "Tageslimit" in message else 1800
        state["retry_after"] = now + pause
    return state, result, message


def read_conf(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.strip().partition("=")
                if sep:
                    out[key] = value.strip().strip('"')
    except OSError:
        pass
    return out


def load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path: str, data: dict, mode: int = 0o600) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    os.fchmod(fd, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def main(argv: list[str]) -> int:
    force = "--force" in argv
    cfg = read_conf(os.path.join(ETC, "setup.conf"))
    provider, host = cfg.get("DDNS_PROVIDER", ""), cfg.get("DDNS_HOST", "")
    secret = load_json(os.path.join(ETC, "ddns.json"))
    if provider not in PROVIDERS or not host or not secret:
        print("DynDNS nicht eingerichtet.", file=sys.stderr)
        return 0
    state, result, message = run_update(provider, host, secret, cfg.get("DDNS_IPV6_ONLY") == "yes",
                                        load_json(STATE), force=force)
    save_json(STATE, state)
    line = (f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {PROVIDERS[provider]['label']} {host}: {result} – {message}"
            f" (IPv4 {state.get('ipv4') or '–'}, IPv6 {state.get('ipv6') or '–'})")
    try:
        os.makedirs(os.path.dirname(STATUS), exist_ok=True)
        with open(STATUS, "w", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, file=sys.stderr if result in ("fatal", "blocked", "retry") else sys.stdout)
    return 0 if result in ("ok", "skip") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
