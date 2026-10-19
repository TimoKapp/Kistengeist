#!/usr/bin/env python3
"""USB-Stick für Kistengeist finden und prüfen (Setup-Assistent und Modul „usb-stick“).

Sicherheitsregel: Nur Laufwerke am USB-Bus kommen in Frage, und nie das Laufwerk, von dem
das System läuft (Speicherkarte oder – bei USB-Boot – der Boot-Stick).

Aufruf (für install.sh):
  kistengeist_usb.py check <by-id-pfad>     → gibt den Gerätepfad aus (/dev/sda) oder Fehler
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

BY_ID = "/dev/disk/by-id"
MOUNTPOINT = "/mnt/usb-stick"
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,11}$")  # exFAT erlaubt 11 Zeichen; bewusst ohne Sonderzeichen
DEFAULT_LABEL = "KISTENGEIST"
LSBLK_COLS = "NAME,PATH,SIZE,MODEL,VENDOR,SERIAL,TRAN,RM,HOTPLUG,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,PKNAME"


def _run(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout if res.returncode == 0 else ""


def lsblk_json() -> dict:
    try:
        return json.loads(_run(["lsblk", "-J", "-b", "-o", LSBLK_COLS]) or "{}")
    except ValueError:
        return {}


def disk_of(dev_name: str, sys_block: str = "/sys/class/block") -> str:
    """Ganzes Laufwerk zu einer Partition (mmcblk0p2 → mmcblk0, sda1 → sda) über sysfs."""
    path = os.path.join(sys_block, dev_name)
    if os.path.exists(os.path.join(path, "partition")):
        return os.path.basename(os.path.dirname(os.path.realpath(path)))
    return dev_name


def system_disks() -> set[str]:
    """Laufwerke (z. B. mmcblk0 oder sda), auf denen / oder /boot/firmware liegen."""
    disks = set()
    for mnt in ("/", "/boot/firmware"):
        src = _run(["findmnt", "-n", "-o", "SOURCE", mnt]).strip()
        if not src:
            continue
        parent = _run(["lsblk", "-n", "-d", "-o", "PKNAME", src]).strip().splitlines()
        name = parent[0].strip() if parent and parent[0].strip() else disk_of(os.path.basename(src))
        disks.add(name)
    return disks


def by_id_links(by_id_dir: str = BY_ID) -> dict[str, str]:
    """Gerätename → stabiler Pfad unter /dev/disk/by-id (nur ganze USB-Laufwerke)."""
    links: dict[str, str] = {}
    try:
        names = sorted(os.listdir(by_id_dir))
    except OSError:
        return links
    for name in names:
        if not name.startswith("usb-") or "-part" in name:
            continue
        path = os.path.join(by_id_dir, name)
        links.setdefault(os.path.basename(os.path.realpath(path)), path)
    return links


def _mounts(dev: dict) -> list[str]:
    return [m for m in (dev.get("mountpoints") or []) if m]


def candidates(tree: dict, system: set[str], links: dict[str, str]) -> list[dict]:
    """USB-Laufwerke, die als Datenstick taugen (ohne Systemlaufwerk)."""
    out = []
    for disk in tree.get("blockdevices", []):
        if disk.get("type") != "disk" or disk.get("tran") != "usb" or disk.get("name") in system:
            continue
        if disk.get("name") not in links:
            continue  # ohne stabilen Pfad kein sicheres Formatieren
        parts = [p for p in disk.get("children", []) or [] if p.get("type") == "part"]
        fs = [{"name": p["name"], "fstype": p.get("fstype") or "", "label": p.get("label") or "",
               "size": int(p.get("size") or 0), "mounts": _mounts(p)} for p in parts]
        if not parts and disk.get("fstype"):
            fs = [{"name": disk["name"], "fstype": disk["fstype"], "label": disk.get("label") or "",
                   "size": int(disk.get("size") or 0), "mounts": _mounts(disk)}]
        name = " ".join(x for x in ((disk.get("vendor") or "").strip(), (disk.get("model") or "").strip()) if x)
        out.append({
            "id": links[disk["name"]],
            "device": "/dev/" + disk["name"],
            "name": name or "USB-Laufwerk",
            "size": int(disk.get("size") or 0),
            "partitions": fs,
            "usable": any(f["fstype"] in ("exfat", "vfat", "ntfs", "ext4") for f in fs),
        })
    return out


def list_sticks() -> list[dict]:
    system = system_disks()
    if not system:
        return []  # Systemlaufwerk unbekannt: lieber nichts anbieten als das falsche
    return candidates(lsblk_json(), system, by_id_links())


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1000
    return str(n)


def valid_label(label: str) -> bool:
    return bool(LABEL_RE.match(label))


def check(stable_id: str) -> str:
    """Prüft einen by-id-Pfad unmittelbar vor dem Formatieren; liefert /dev/sdX."""
    if not stable_id.startswith(BY_ID + "/usb-") or "-part" in stable_id or ".." in stable_id:
        raise ValueError("Kein gültiger USB-Laufwerkspfad.")
    for stick in list_sticks():
        if stick["id"] == stable_id:
            return stick["device"]
    raise ValueError("Der gewählte USB-Stick ist nicht (mehr) angeschlossen oder ist das Systemlaufwerk.")


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "check":
        try:
            print(check(argv[1]))
            return 0
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    if argv == ["list"]:
        print(json.dumps(list_sticks(), ensure_ascii=False, indent=1))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
