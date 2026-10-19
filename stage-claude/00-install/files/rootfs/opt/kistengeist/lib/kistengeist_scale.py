#!/usr/bin/env python3
"""Schriftgröße/Skalierung der Claude-Oberfläche (100–200 %).

Gespeichert in ~/.config/kistengeist/scale.conf (SCALE=200). Wirkt über
  - ~/.Xresources: Xft.dpi = 96·f (Claude Desktop, Chrome, VS Code, GTK lesen das), Mauszeiger
  - Umgebung XCURSOR_THEME/XCURSOR_SIZE (kistengeist-session)
  - tint2-Leiste: Höhe, Symbole, Abstände und Schriften mal f (kistengeist-autostart)

Aufruf:
  kistengeist_scale.py get              → aktueller Wert (leer, wenn noch nie gewählt)
  kistengeist_scale.py set 150          → speichern und ~/.Xresources anpassen
  kistengeist_scale.py env              → export-Zeilen für die Sitzung
  kistengeist_scale.py tint2 <vorlage>  → skalierte tint2rc auf stdout
"""

from __future__ import annotations

import os
import re
import sys

SCALES = (100, 125, 150, 175, 200)
CURSOR_THEME = "Adwaita"
# tint2-Schlüssel, deren Zahlen (Pixel) mitwachsen; Prozentangaben bleiben.
TINT2_PIXEL_KEYS = {
    "panel_size", "panel_padding", "launcher_padding", "launcher_icon_size", "taskbar_padding",
    "task_maximum_size", "task_padding", "systray_padding", "systray_icon_size", "clock_padding",
    "tooltip_padding",
}
TINT2_FONT_KEYS = {"task_font", "time1_font", "time2_font"}


def conf_path(home: str | None = None) -> str:
    return os.path.join(home or os.path.expanduser("~"), ".config", "kistengeist", "scale.conf")


def read_scale(home: str | None = None) -> int | None:
    try:
        with open(conf_path(home), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("SCALE="):
                    value = int(line.split("=", 1)[1].strip().strip('"'))
                    return value if value in SCALES else None
    except (OSError, ValueError):
        pass
    return None


def factor(scale: int | None) -> float:
    return (scale or 100) / 100


def write_scale(scale: int, home: str | None = None) -> None:
    if scale not in SCALES:
        raise ValueError(f"Erlaubt: {SCALES}")
    path = conf_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"SCALE={scale}\n")


def xresources(text: str, scale: int) -> str:
    """Setzt Xft.dpi und Mauszeiger, alle übrigen Zeilen bleiben."""
    f = factor(scale)
    wanted = {"Xft.dpi": str(round(96 * f)), "Xcursor.theme": CURSOR_THEME, "Xcursor.size": str(round(24 * f))}
    lines = [ln for ln in text.splitlines() if ln.split(":", 1)[0].strip() not in wanted]
    lines += [f"{k}: {v}" for k, v in wanted.items()]
    return "\n".join(lines).strip() + "\n"


def tint2(template: str, scale: int | None) -> str:
    f = factor(scale)
    if f == 1:
        return template
    out = []
    for line in template.splitlines():
        key, sep, value = line.partition("=")
        k = key.strip()
        if sep and k in TINT2_PIXEL_KEYS:
            value = re.sub(r"(?<![\d.%])(\d+)(?![\d%])", lambda m: str(round(int(m.group(1)) * f)), value)
            line = f"{key}={value}"
        elif sep and k in TINT2_FONT_KEYS:
            value = re.sub(r"(\d+(?:\.\d+)?)\s*$", lambda m: f"{float(m.group(1)) * f:g}", value)
            line = f"{key}={value}"
        out.append(line)
    return "\n".join(out) + "\n"


def env_lines(scale: int | None) -> str:
    return f"export XCURSOR_THEME={CURSOR_THEME}\nexport XCURSOR_SIZE={round(24 * factor(scale))}\n"


def main(argv: list[str]) -> int:
    if argv == ["get"]:
        print(read_scale() or "")
        return 0
    if len(argv) == 2 and argv[0] == "set":
        scale = int(argv[1])
        write_scale(scale)
        xr = os.path.expanduser("~/.Xresources")
        try:
            with open(xr, encoding="utf-8") as fh:
                old = fh.read()
        except OSError:
            old = ""
        with open(xr, "w", encoding="utf-8") as fh:
            fh.write(xresources(old, scale))
        return 0
    if argv == ["env"]:
        sys.stdout.write(env_lines(read_scale()))
        return 0
    if len(argv) == 2 and argv[0] == "tint2":
        with open(argv[1], encoding="utf-8") as fh:
            sys.stdout.write(tint2(fh.read(), read_scale()))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
