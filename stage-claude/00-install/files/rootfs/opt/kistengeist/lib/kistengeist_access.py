#!/usr/bin/env python3
"""Zugangsdaten-Datei von Kistengeist: Adressen, Ports (mit Hinweis, was am Router freigegeben
werden muss) und – wenn bei der Einrichtung gewählt – die Anmeldedaten.

Aufruf (Modul „zugangsdaten“):
  kistengeist_access.py write --out ~/Zugangsdaten.txt [--usb /mnt/usb-stick] [--secrets-dir /run/kistengeist]
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time

ETC = os.environ.get("CP_ROOT", "") + "/etc/kistengeist"


# Anbieter-Name und Kontoseite für die Zugangsdaten-Datei (Gegenstück zu kistengeist_ddns.PROVIDERS).
DDNS_LABELS = {"ipv64": ("ipv64.net", "https://ipv64.net"), "dynv6": ("dynv6", "https://dynv6.com"),
               "noip": ("No-IP", "https://www.noip.com"), "duckdns": ("DuckDNS", "https://www.duckdns.org")}


def read_conf(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def rdp_file(host: str, user: str = "claude") -> str:
    """Fertige Verbindungsdatei für die Windows-Remotedesktopverbindung (Doppelklick genügt):
    Ton auf diesem Computer, Mikrofon von diesem Computer, Windows-Tastenkombinationen und
    Medientasten bleiben am Arbeitsplatz (xrdp 0.10.1 verliert bei Medientasten das E0-Kennzeichen,
    sie kämen sonst als d/c/b an), Zwischenablage, Auflösung passt sich dem Fenster an."""
    lines = [
        f"full address:s:{host}",
        f"username:s:{user}",
        "audiomode:i:0",
        "audiocapturemode:i:1",
        "keyboardhook:i:0",
        "redirectclipboard:i:1",
        "screen mode id:i:2",
        "dynamic resolution:i:1",
        "smart sizing:i:1",
        "prompt for credentials:i:1",
        "session bpp:i:32",
        "connection type:i:7",
        "networkautodetect:i:1",
        "bandwidthautodetect:i:1",
    ]
    return "\r\n".join(lines) + "\r\n"


def ports(cfg: dict[str, str], access: dict | None = None) -> list[dict]:
    """Alle Ports, die der Pi je nach Auswahl bereitstellt. forward=True: am Router freigeben."""
    access = access or {}
    mods = cfg.get("MODULES", "").split()
    mode = cfg.get("MODE", "")
    net = cfg.get("NET_ACCESS", "lan")
    out: list[dict] = []

    def add(port: str, proto: str, service: str, forward: bool, note: str) -> None:
        out.append({"port": port, "proto": proto, "service": service, "forward": forward, "note": note})

    if "webserver" in mods:
        if net == "dyndns":
            add("80", "TCP", "Webserver (Caddy) – HTTP, nötig für das HTTPS-Zertifikat", True,
                "leitet automatisch auf HTTPS um")
            add("443", "TCP", "Webserver (Caddy) – HTTPS" + (" mit n8n" if "n8n" in mods else ""), True,
                access.get("public_url", ""))
        elif net == "tailscale":
            add("–", "–", "Tailscale Funnel (Internet ohne Portfreigabe)", False,
                "keine Router-Freigabe nötig: " + access.get("public_url", "Adresse siehe oben"))
        add("8080", "TCP", "Startseite des Pi im Heimnetz", False, "nur im Heimnetz")
    if "n8n" in mods:
        add("5678", "TCP", "n8n (direkt)", False,
            "nur im Heimnetz" if net == "lan" else "nur auf dem Pi selbst; von außen über HTTPS")
    if mode in ("rdp", "both") and cfg.get("REMOTE") == "browser":
        add("8443", "TCP", "Desktop im Browser (https://kistengeist.local:8443)", False,
            "NIE am Router freigeben – nur im Heimnetz")
    elif mode in ("rdp", "both"):
        add("3389", "TCP", "Remotedesktop (RDP)", False, "NIE am Router freigeben – stattdessen VPN nutzen")
    if "ssh" in mods:
        add("22", "TCP", "SSH", False, "NIE am Router freigeben")
    if "upload" in mods:
        add("8765", "TCP", "Upload-Fenster", False, "nur im Heimnetz, nur solange das Fenster offen ist")
    add("5353", "UDP", "Gerätename kistengeist.local (mDNS)", False, "nur im Heimnetz")
    return out


def network() -> dict:
    def run(cmd: list[str]) -> str:
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            return ""
    v4, v6, mac = [], [], ""
    for line in run(["ip", "-o", "addr", "show", "scope", "global"]).splitlines():
        parts = line.split()
        skip = parts[1:2] and (parts[1] in ("docker0", "lo") or parts[1].startswith(("br-", "veth", "tailscale")))
        if len(parts) > 3 and not skip:
            addr = parts[3].split("/")[0]
            if parts[2] == "inet":
                v4.append(f"{addr} ({parts[1]})")
            elif parts[2] == "inet6" and "temporary" not in line:
                v6.append(f"{addr} ({parts[1]})")
    for dev in ("eth0", "wlan0"):
        mac_dev = read_text(f"/sys/class/net/{dev}/address")
        if mac_dev and read_text(f"/sys/class/net/{dev}/operstate") == "up":
            mac = f"{mac_dev} ({dev})"
            break
    return {"hostname": socket.gethostname(), "ipv4": v4, "ipv6": v6, "mac": mac}


def render(cfg: dict[str, str], access: dict, secrets: dict, net: dict, user: str, now: str) -> str:
    with_secrets = cfg.get("ACCESS_FILE_SECRETS", "no") == "yes"
    mods = cfg.get("MODULES", "").split()
    host = net.get("hostname") or "kistengeist"
    L: list[str] = []
    line = L.append

    def hidden(value: str) -> str:
        if not value:
            return "(nicht angegeben)"
        return value if with_secrets else "(nicht gespeichert – bei der Einrichtung abgewählt)"

    line("KISTENGEIST – ZUGANGSDATEN UND PORTS")
    line("=" * 60)
    line(f"Erstellt: {now}")
    line("Diese Datei enthält Zugangsdaten. Sicher aufbewahren, nicht weitergeben, nicht ins Internet hochladen.")
    line("")
    line("1. GERÄT IM HEIMNETZ")
    line("-" * 60)
    line(f"Name:          {host}  (im Browser: http://{host}.local)")
    line(f"IPv4:          {', '.join(net.get('ipv4') or []) or 'unbekannt'}")
    line(f"IPv6:          {', '.join(net.get('ipv6') or []) or 'keine'}")
    line(f"MAC-Adresse:   {net.get('mac') or 'unbekannt'}")
    line("Tipp: Im Router dem Pi immer dieselbe IPv4-Adresse geben (FRITZ!Box: Heimnetz > Netzwerk >")
    line("      Gerät bearbeiten > „IPv4-Adresse dauerhaft zuweisen“), sonst laufen Portfreigaben ins Leere.")
    line("")
    via = "Browser" if cfg.get("REMOTE") == "browser" else "RDP"
    line(f"2. ANMELDUNG AM PI (Bildschirm, {via}" + (", SSH" if "ssh" in mods else "") + ")")
    line("-" * 60)
    line(f"Benutzer:      {user}")
    line(f"Passwort:      {hidden(secrets.get('account', ''))}")
    if cfg.get("REMOTE") == "browser" and cfg.get("MODE") in ("rdp", "both"):
        line(f"Im Browser:    https://{host}.local:8443  (Benutzer {user}; beim ersten Öffnen die")
        line("               Zertifikatswarnung einmal bestätigen)")
        line(f"Browser-Passw.: {hidden(secrets.get('browser', ''))}")
    line("")
    if "webserver" in mods:
        line("3. WEBSERVER UND ERREICHBARKEIT AUS DEM INTERNET")
        line("-" * 60)
        net_access = cfg.get("NET_ACCESS", "lan")
        provider = DDNS_LABELS.get(cfg.get("DDNS_PROVIDER", ""), ("DynDNS", ""))
        label = {"lan": "nur im Heimnetz", "dyndns": f"{provider[0]} + Portfreigabe am Router",
                 "tailscale": "Tailscale Funnel (ohne Portfreigabe)"}.get(net_access, net_access)
        line(f"Art:           {label}")
        line(f"Startseite:    http://{host}.local:8080 (Heimnetz)")
        if access.get("public_url"):
            line(f"Internet:      {access['public_url']}")
        if net_access == "dyndns":
            dd = secrets.get("ddns") or {}
            line(f"DynDNS:        {cfg.get('DDNS_HOST', '')}  (Anbieter {provider[0]}, Konto: {provider[1]})")
            if "user" in dd:
                line(f"DDNS-Key:      Benutzer {hidden(dd.get('user', ''))}")
                line(f"               Passwort {hidden(dd.get('password', ''))}")
            else:
                line(f"DynDNS-Token:  {hidden(dd.get('token', ''))}")
            if cfg.get("DDNS_PROVIDER") == "noip":
                line("               No-IP (gratis): Adresse alle 30 Tage per Link in der E-Mail")
                line("               von No-IP bestätigen, sonst wird sie abgeschaltet.")
            line("Prüfen:        kistengeist-ddns status  (im Terminal des Pi)")
            if cfg.get("DDNS_IPV6_ONLY") == "yes":
                line("               DS-Lite: nur IPv6 eingetragen – von außen nur über IPv6 erreichbar.")
        line("")
    if "n8n" in mods:
        n8n = secrets.get("n8n", {}) or {}
        line("4. N8N (AUTOMATISIERUNG)")
        line("-" * 60)
        if access.get("n8n_url"):
            line(f"Adresse:       {access['n8n_url']}")
        if access.get("n8n_local_url"):
            line(f"Im Heimnetz:   {access['n8n_local_url']}")
        elif access.get("n8n_url"):
            line("Im Heimnetz:   über die Adresse oben (n8n ist nur über HTTPS erreichbar)")
        line(f"E-Mail:        {n8n.get('email') or '(selbst beim ersten Öffnen anlegen)'}")
        line(f"Passwort:      {hidden(n8n.get('password', ''))}")
        if access.get("n8n_owner") == "failed":
            line("               Konto konnte nicht automatisch angelegt werden – beim ersten Öffnen selbst anlegen.")
        mcp = access.get("n8n_mcp_url") or "(Adresse siehe n8n > Einstellungen > Instance-level MCP)"
        line("MCP für Claude: " + mcp)
        line("Daten:         /srv/n8n/data – Sicherung täglich nach /srv/n8n/backup und (ohne Schlüssel)")
        line("               auf den USB-Stick. Der Schlüssel für die gespeicherten Zugangsdaten liegt in")
        line("               /srv/n8n/data/config – für eine Wiederherstellung getrennt und sicher aufbewahren.")
        line("")
    line("5. PORTS")
    line("-" * 60)
    line(f"{'Port':<6}{'Prot.':<6}{'Router':<14}Dienst / Hinweis")
    for p in ports(cfg, access):
        flag = "FREIGEBEN" if p["forward"] else "nicht freig."
        note = f" – {p['note']}" if p["note"] else ""
        line(f"{p['port']:<6}{p['proto']:<6}{flag:<14}{p['service']}{note}")
    forwards = [p for p in ports(cfg, access) if p["forward"]]
    line("")
    line("6. PORTFREIGABE AM ROUTER")
    line("-" * 60)
    if not forwards:
        line("Keine Portfreigabe nötig.")
    else:
        line("Am Router freigeben (Ziel: dieser Pi, IPv4 und – wenn vorhanden – IPv6):")
        for p in forwards:
            line(f"  • {p['proto']} {p['port']} → {host} Port {p['port']}")
        line("")
        line("FRITZ!Box:")
        line("  1. http://fritz.box öffnen und anmelden.")
        line("  2. Internet > Freigaben > Portfreigaben > „Gerät für Freigaben hinzufügen“.")
        line(f"  3. Gerät „{host}“ wählen (oder seine IPv4-Adresse eingeben).")
        line("  4. „Neue Freigabe“ > „Portfreigabe“ > Anwendung „Andere Anwendung“, Protokoll TCP.")
        line("  5. Port an Gerät, bis Port und „Port extern gewünscht (IPv4)“: jeweils 80 – dann OK.")
        line("  6. Dasselbe für 443. Wenn angeboten: IPv6-Freigabe für das Gerät ebenfalls aktivieren.")
        line("  7. „Übernehmen“.")
        line("DS-Lite prüfen: Internet > Online-Monitor > Verbindungsdetails. Steht dort keine öffentliche")
        line("  IPv4-Adresse (oder eine aus 100.64.x.x bzw. 192.0.0.x), ist der Pi über IPv4 nicht erreichbar –")
        line("  dann nur IPv6 nutzen oder bei der Einrichtung „Tailscale Funnel“ wählen.")
    line("")
    line("7. SICHERHEIT")
    line("-" * 60)
    line("• Nur 80/443 freigeben, niemals RDP (3389), SSH (22) oder n8n (5678) direkt.")
    line("• n8n regelmäßig aktualisieren (geschieht wöchentlich automatisch). Starke Passwörter verwenden,")
    line("  in n8n die Zwei-Faktor-Anmeldung einschalten (Einstellungen > Persönlich).")
    line("• Diese Datei nach dem Abschreiben der Passwörter am besten löschen oder sicher verwahren.")
    return "\n".join(L) + "\n"


def write_private(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--out", required=True)
    w.add_argument("--usb", default="")
    w.add_argument("--secrets-dir", default=os.environ.get("CP_ROOT", "") + "/run/kistengeist")
    w.add_argument("--user", default=os.environ.get("CP_USER", "claude"))
    w.add_argument("--rdp-out", default="")
    args = ap.parse_args(argv)
    cfg = read_conf(ETC + "/setup.conf")
    access = read_json(ETC + "/access.json")
    secrets = {"account": read_text(os.path.join(args.secrets_dir, "account.secret")),
               "browser": read_text(os.path.join(args.secrets_dir, "browser.secret")),
               "ddns": read_json(ETC + "/ddns.json"),
               "n8n": read_json(os.path.join(args.secrets_dir, "n8n.json"))}
    text = render(cfg, access, secrets, network(), args.user, time.strftime("%d.%m.%Y %H:%M"))
    write_private(args.out, text)
    if args.usb:
        write_private(os.path.join(args.usb, "Zugangsdaten.txt"), text.replace("\n", "\r\n"))
    if args.rdp_out and cfg.get("MODE") in ("rdp", "both") and cfg.get("REMOTE") != "browser":
        # Verbindungsdatei (enthält kein Passwort): im Benutzerordner und – falls eingebunden – auf dem Stick.
        rdp = rdp_file(f"{socket.gethostname()}.local", args.user)
        for target in [args.rdp_out] + ([os.path.join(args.usb, "Kistengeist.rdp")] if args.usb else []):
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(rdp)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
