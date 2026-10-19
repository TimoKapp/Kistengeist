#!/usr/bin/env python3
"""Führt JSON-Einstellungen zusammen, ohne vorhandene Werte des Nutzers zu verlieren.

Aufruf: json_merge.py <datei> '<json-objekt>'
Objekte werden rekursiv gemischt; die neuen Werte gewinnen. Fehlt die Datei oder ist sie
kaputt, wird sie neu angelegt (eine kaputte Datei wird als .bak gesichert).
"""

from __future__ import annotations

import json
import os
import sys


def merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def merge_file(path: str, extra: dict) -> dict:
    data: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            os.replace(path, path + ".bak")
    data = merge(data, extra)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Rechte der bestehenden Datei übernehmen, sonst privat (Claude-Dateien enthalten Kontodaten).
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o600
    tmp = path + ".tmp"
    # Läuft auch als root im Home des Nutzers: keinem vorbereiteten Symlink folgen.
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    os.fchmod(fd, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
    return data


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    merge_file(argv[1], json.loads(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
