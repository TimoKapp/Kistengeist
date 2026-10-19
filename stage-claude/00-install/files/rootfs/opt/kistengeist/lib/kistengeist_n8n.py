#!/usr/bin/env python3
"""Hilfen für das n8n-Modul: Besitzerkonto anlegen und Eingaben prüfen.

Aufruf:
  kistengeist_n8n.py owner-env /run/kistengeist/n8n.json   → Zeilen für die env-Datei (bcrypt-Hash)
  kistengeist_n8n.py owner-check [--url http://127.0.0.1:5678]

Das Besitzerkonto entsteht über die dokumentierten Variablen N8N_INSTANCE_OWNER_* (ab n8n 2.17,
https://docs.n8n.io/deploy/host-n8n/configure-n8n/manage-settings-using-environment-variables.md):
es existiert damit schon beim ersten Start. Das Passwort steht nur als bcrypt-Hash in der Datei.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request

# Bewusst eng: der Wert landet auch in der Caddy-Konfiguration und in setup.conf.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def password_problem(pw: str) -> str:
    """Passwortregeln von n8n: 8–64 Zeichen, mindestens eine Ziffer und ein Großbuchstabe."""
    if not isinstance(pw, str) or not 8 <= len(pw) <= 64:
        return "Das n8n-Passwort muss 8 bis 64 Zeichen lang sein."
    if not re.search(r"\d", pw):
        return "Das n8n-Passwort braucht mindestens eine Ziffer."
    if not re.search(r"[A-ZÄÖÜ]", pw):
        return "Das n8n-Passwort braucht mindestens einen Großbuchstaben."
    if any(c in pw for c in "\r\n\0"):
        return "Das n8n-Passwort enthält ungültige Zeichen."
    return ""


def owner_env(data: dict, hasher=None) -> str:
    """Zeilen für n8n.env; Werte werden geprüft, damit nichts in die Datei eingeschleust wird."""
    if hasher is None:
        import bcrypt

        def hasher(pw: str) -> str:
            return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(10)).decode()
    email, first, last = data["email"], data["firstName"], data["lastName"]
    if not EMAIL_RE.match(email) or password_problem(data["password"]):
        raise ValueError("Ungültige Kontodaten.")
    for value in (first, last):
        # Keine Zeichen, die die env-Datei (docker compose: $-Ersetzung, Anführungszeichen) stören.
        if not value or any(c in value for c in "\r\n\0$'`\"\\"):
            raise ValueError("Ungültiger Name.")
    return "\n".join([
        "N8N_INSTANCE_OWNER_MANAGED_BY_ENV=true",
        f"N8N_INSTANCE_OWNER_EMAIL={email}",
        f"N8N_INSTANCE_OWNER_FIRST_NAME={first}",
        f"N8N_INSTANCE_OWNER_LAST_NAME={last}",
        # Einfache Anführungszeichen: docker compose ersetzt sonst die $-Teile des bcrypt-Hashes.
        f"N8N_INSTANCE_OWNER_PASSWORD_HASH='{hasher(data['password'])}'",
    ])


def owner_ready(url: str, opener=urllib.request.urlopen, sleep=time.sleep) -> bool:
    """Wartet, bis n8n bereit ist, und prüft, dass keine Ersteinrichtung mehr offen ist."""
    if not wait_healthy(url, sleep=sleep, opener=opener):
        return False
    try:
        with opener(url + "/rest/settings", timeout=10) as res:
            data = json.loads(res.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError):
        return False
    um = (data.get("data") or data).get("userManagement") or {}
    return um.get("showSetupOnFirstLoad") is False


def wait_healthy(url: str, timeout: float = 900.0, sleep=time.sleep, opener=urllib.request.urlopen) -> bool:
    waited = 0.0
    while waited < timeout:
        try:
            # readiness: erst nach den Datenbank-Migrationen bereit
            with opener(url + "/healthz/readiness", timeout=5) as res:
                if res.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        sleep(3)
        waited += 3
    return False


def setup_owner(data: dict, url: str, opener=urllib.request.urlopen, sleep=time.sleep) -> str:
    if not wait_healthy(url, sleep=sleep, opener=opener):
        raise RuntimeError("n8n antwortet nicht.")
    body = json.dumps({"email": data["email"], "firstName": data["firstName"],
                       "lastName": data["lastName"], "password": data["password"]}).encode()
    req = urllib.request.Request(url + "/rest/owner/setup", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with opener(req, timeout=30) as res:
            if res.status != 200:
                raise RuntimeError(f"HTTP {res.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"n8n lehnt ab: HTTP {exc.code}") from exc
    return "ok"


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "owner-env":
        with open(argv[1], encoding="utf-8") as fh:
            try:
                print(owner_env(json.load(fh)))
            except (ValueError, KeyError) as exc:
                print(f"Fehler: {exc}", file=sys.stderr)
                return 1
        return 0
    if argv[:1] == ["owner-check"]:
        url = argv[2] if len(argv) >= 3 and argv[1] == "--url" else "http://127.0.0.1:5678"
        if owner_ready(url):
            print("Besitzerkonto vorhanden.")
            return 0
        print("Fehler: n8n nicht bereit oder Besitzerkonto fehlt.", file=sys.stderr)
        return 1
    if len(argv) >= 2 and argv[0] == "setup-owner":
        url = argv[3] if len(argv) >= 4 and argv[2] == "--url" else "http://127.0.0.1:5678"
        with open(argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
        try:
            setup_owner(data, url)
        except (RuntimeError, KeyError, OSError) as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 1
        print("Besitzerkonto angelegt.")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
