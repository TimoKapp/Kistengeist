"""Logik der Speicherverwaltung (ohne Oberfläche, damit sie testbar ist)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

# Echte Dateisysteme; Pseudo-Dateisysteme wie proc oder tmpfs werden ausgeblendet.
REAL_FS = {"ext4", "ext3", "ext2", "vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "btrfs", "xfs", "f2fs"}

WARN_PERCENT = 90

# Cache-Ordner, die gefahrlos geleert werden können (relativ zum Benutzerordner).
USER_CACHES = (
    ".cache/google-chrome",
    ".cache/chromium",
    ".cache/thumbnails",
    ".cache/pip",
)


@dataclass
class Mount:
    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    removable: bool

    @property
    def percent(self) -> int:
        # Wie df: reservierte Blöcke von ext4 zählen nicht als verfügbar.
        usable = self.used + self.free
        return round(self.used * 100 / usable) if usable else 0

    @property
    def label(self) -> str:
        if self.mountpoint == "/":
            return "System (Speicherkarte/SSD)"
        if self.mountpoint.startswith("/boot"):
            return "Startpartition"
        if self.removable:
            return f"USB: {os.path.basename(self.mountpoint)}"
        return self.mountpoint


def unescape_mount(path: str) -> str:
    """/proc/mounts kodiert Leerzeichen usw. als Oktalfolgen (z. B. \\040)."""
    out, i = [], 0
    while i < len(path):
        if path[i] == "\\" and i + 3 < len(path) and path[i + 1 : i + 4].isdigit():
            out.append(chr(int(path[i + 1 : i + 4], 8)))
            i += 4
        else:
            out.append(path[i])
            i += 1
    return "".join(out)


def parse_mounts(text: str) -> list[tuple[str, str, str]]:
    result, seen = [], set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mountpoint, fstype = parts[0], unescape_mount(parts[1]), parts[2]
        if fstype not in REAL_FS or mountpoint in seen:
            continue
        seen.add(mountpoint)
        result.append((device, mountpoint, fstype))
    return result


def is_removable(mountpoint: str) -> bool:
    return mountpoint.startswith(("/media/", "/run/media/", "/mnt/"))


def list_mounts(proc_mounts: str = "/proc/mounts") -> list[Mount]:
    with open(proc_mounts, encoding="utf-8") as fh:
        entries = parse_mounts(fh.read())
    mounts = []
    for device, mountpoint, fstype in entries:
        try:
            usage = shutil.disk_usage(mountpoint)
        except OSError:
            continue
        mounts.append(
            Mount(device, mountpoint, fstype, usage.total, usage.used, usage.free, is_removable(mountpoint))
        )
    return mounts


def parse_meminfo(text: str) -> dict[str, int]:
    """Liefert Werte aus /proc/meminfo in Bytes."""
    values = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0]) * 1024
    return values


def memory(meminfo: str = "/proc/meminfo") -> dict[str, int]:
    with open(meminfo, encoding="utf-8") as fh:
        info = parse_meminfo(fh.read())
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    swap_used = swap_total - info.get("SwapFree", 0)
    return {"total": total, "used": total - available, "swap_total": swap_total, "swap_used": swap_used}


def dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                st = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            total += st.st_blocks * 512
    return total


def largest_entries(path: str, limit: int = 10) -> list[tuple[str, int]]:
    """Größte direkte Unterordner/Dateien eines Ordners."""
    sizes = []
    try:
        names = os.listdir(path)
    except OSError:
        return []
    for name in names:
        full = os.path.join(path, name)
        if os.path.islink(full):
            continue
        try:
            size = dir_size(full) if os.path.isdir(full) else os.lstat(full).st_blocks * 512
        except OSError:
            continue
        sizes.append((full, size))
    sizes.sort(key=lambda item: item[1], reverse=True)
    return sizes[:limit]


def cache_dirs(home: str) -> list[str]:
    return [os.path.join(home, rel) for rel in USER_CACHES if os.path.isdir(os.path.join(home, rel))]


def clear_dir_contents(path: str) -> int:
    """Löscht den Inhalt eines Ordners (nicht den Ordner selbst); liefert freigegebene Bytes."""
    freed = dir_size(path)
    for name in os.listdir(path):
        full = os.path.join(path, name)
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full, ignore_errors=True)
            else:
                os.unlink(full)
        except OSError:
            pass
    return freed - dir_size(path)


def warnings(mounts: list[Mount], threshold: int = WARN_PERCENT) -> list[str]:
    return [
        f"{m.label} ist zu {m.percent} % voll ({human(m.free)} frei)."
        for m in mounts
        if m.percent >= threshold and not m.mountpoint.startswith("/boot")
    ]


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return f"{size} B"


def parent_device(device: str, sysfs: str = "/sys/class/block") -> str:
    """Gerät zu einer Partition: /dev/sda1 -> /dev/sda, /dev/mmcblk0p1 -> /dev/mmcblk0.

    Ein Stick ohne Partitionstabelle (/dev/sda) ist sein eigenes Gerät.
    """
    name = os.path.basename(device)
    entry = os.path.join(sysfs, name)
    if os.path.isdir(entry):
        if not os.path.exists(os.path.join(entry, "partition")):
            return device
        return "/dev/" + os.path.basename(os.path.dirname(os.path.realpath(entry)))
    parent = device.rstrip("0123456789")
    if parent.endswith("p") and parent[:-1][-1:].isdigit():
        parent = parent[:-1]
    return parent if parent != device else device
