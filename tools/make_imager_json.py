#!/usr/bin/env python3
"""Erzeugt die Repository-Datei für Raspberry Pi Imager.

Damit erscheint Kistengeist in Raspberry Pi Imager (Einstellungen →
eigenes Repository / --repo URL); Imager lädt das Image dann selbst herunter.

Aufruf:
  make_imager_json.py --image kistengeist.zip --url https://…/kistengeist.zip \
      --version v0.1.0 --out kistengeist-imager.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import lzma
import os
import sys
import zipfile

CHUNK = 4 * 1024 * 1024


def extracted_stats(path: str) -> tuple[int, str]:
    """Größe und SHA-256 des entpackten Images (so verlangt es Imager)."""
    digest, size = hashlib.sha256(), 0
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            images = [n for n in zf.namelist() if n.endswith(".img")]
            if len(images) != 1:
                raise ValueError(f"ZIP muss genau ein .img enthalten, gefunden: {images}")
            with zf.open(images[0]) as fh:
                while chunk := fh.read(CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
        return size, digest.hexdigest()
    opener = lzma.open if path.endswith(".xz") else open
    with opener(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def build(image: str, url: str, version: str, release_date: str) -> dict:
    extract_size, extract_sha = extracted_stats(image)
    return {
        "os_list": [
            {
                "name": f"Kistengeist {version}",
                "description": "Bootet direkt in Claude Desktop. Setup-Assistent im Browser lädt "
                               "Claude, Chrome und gewählte Module bei der Installation.",
                "icon": "https://raw.githubusercontent.com/TimoKapp/kistengeist/main/imager/icon.png",
                "url": url,
                "extract_size": extract_size,
                "extract_sha256": extract_sha,
                "image_download_size": os.path.getsize(image),
                "image_download_sha256": file_sha256(image),
                "release_date": release_date,
                "init_format": "cloudinit-rpi",
                "devices": ["pi4-64bit"],
                "website": "https://github.com/TimoKapp/kistengeist",
            }
        ]
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    data = build(args.image, args.url, args.version, args.date)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
