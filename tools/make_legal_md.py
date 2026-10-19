#!/usr/bin/env python3
"""Erzeugt RECHTLICHES.md im Repo aus share/legal/legal.json (einzige Quelle der Texte)."""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "stage-claude/00-install/files/rootfs/opt/kistengeist/lib"))
import kistengeist_legal as legal  # noqa: E402

TARGET = os.path.join(REPO, "RECHTLICHES.md")

if __name__ == "__main__":
    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(legal.to_markdown(legal.load()))
    print(TARGET)
