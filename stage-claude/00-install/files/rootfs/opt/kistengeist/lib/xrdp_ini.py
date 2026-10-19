#!/usr/bin/env python3
"""Passt /etc/xrdp/xrdp.ini für Kistengeist an.

Entfernt alle mitgelieferten Sitzungsarten (Abschnitte mit "lib=") und hängt
genau eine Kistengeist-Sitzung an. Globale Abschnitte bleiben unverändert.

Aufruf: xrdp_ini.py <original-xrdp.ini> <rdp|both>   (Ergebnis auf stdout)
"""

from __future__ import annotations

import sys

SESSIONS = {
    # Eigene Sitzung je Anmeldung (xorgxrdp).
    "rdp": """[Kistengeist]
name=Kistengeist
lib=libxup.so
username=ask
password=ask
ip=127.0.0.1
port=-1
code=20
""",
    # Spiegelt den Bildschirm am Pi (x11vnc lauscht nur auf 127.0.0.1).
    "both": """[Kistengeist-Bildschirm]
name=Kistengeist (Bildschirm am Pi)
lib=libvnc.so
username=na
password=ask
ip=127.0.0.1
port=5900
""",
}


def split_sections(text: str) -> list[tuple[str | None, list[str]]]:
    """Teilt die Datei in (Abschnittsname, Zeilen)-Blöcke."""
    blocks: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            blocks.append((stripped[1:-1], [line]))
        else:
            blocks[-1][1].append(line)
    return blocks


def is_session(lines: list[str]) -> bool:
    return any(line.strip().startswith("lib=") for line in lines)


# Ton zum Arbeitsplatz (rdpsnd) und Mikrofon vom Arbeitsplatz (über dynamische Kanäle).
CHANNELS = {"rdpsnd": "true", "drdynvc": "true"}


def ensure_channels(name: str | None, lines: list[str]) -> list[str]:
    if name != "Channels":
        return lines
    out, seen = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in CHANNELS and "=" in line:
            out.append(f"{key}={CHANNELS[key]}")
            seen.add(key)
        else:
            out.append(line)
    out[1:1] = [f"{k}={v}" for k, v in CHANNELS.items() if k not in seen]
    return out


def rewrite(text: str, mode: str) -> str:
    if mode not in SESSIONS:
        raise ValueError(f"Unbekannter Modus: {mode}")
    kept: list[str] = []
    blocks = split_sections(text)
    if not any(name == "Channels" for name, _ in blocks):
        blocks.append(("Channels", ["[Channels]"]))
    for name, lines in blocks:
        if name is not None and is_session(lines):
            continue
        kept.extend(ensure_channels(name, lines))
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept) + "\n\n" + SESSIONS[mode]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        sys.stdout.write(rewrite(fh.read(), argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
