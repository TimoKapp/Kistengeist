#!/usr/bin/env python3
"""Listet alle Debian-Pakete, die die Module per cp_apt_install(_nr) installieren.

Für die CI-Prüfung „Pakete in Debian 13 (arm64)“: so fällt vor dem Hardwaretest auf, wenn ein
Paket fehlt oder ein Befehl nur über eine (nicht installierte) Empfehlung käme.
Pakete aus Fremdquellen (Anthropic, Google, Microsoft, Tailscale) werden ausgelassen.
"""

from __future__ import annotations

import glob
import os
import re
import sys

FOREIGN = {"claude-desktop", "google-chrome-stable", "code", "tailscale"}
CALL = re.compile(r"cp_apt_install(?:_nr)?\s+((?:[^\n]*\\\n)*[^\n]*)")


def packages(modules_dir: str) -> list[str]:
    found: set[str] = set()
    for path in sorted(glob.glob(os.path.join(modules_dir, "*", "install.sh"))):
        text = open(path, encoding="utf-8").read()
        for m in CALL.finditer(text):
            args = m.group(1).replace("\\\n", " ")
            args = args.split(";")[0].split("&&")[0].split("||")[0]
            for word in args.split():
                if word.startswith(("-", "$", '"')) or not re.fullmatch(r"[a-z0-9][a-z0-9.+-]+", word):
                    continue
                found.add(word)
    return sorted(found - FOREIGN)


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "stage-claude/00-install/files/rootfs/opt/kistengeist/modules"
    print("\n".join(packages(base)))
