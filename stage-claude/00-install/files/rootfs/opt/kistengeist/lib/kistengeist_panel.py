"""Fensteranordnung für das Terminal-Panel (über wmctrl).

Zwei Ansichten:
  geteilt – Claude links (58 %), rechts Terminal (oben) und Befehlsliste (unten)
  unten   – Claude bleibt im Vollbild, Terminal und Liste liegen eingeblendet im unteren Teil
"""

from __future__ import annotations

import json
import os
import re
import subprocess

MODES = {"geteilt": "Geteilt", "unten": "Eingeblendet unten"}
PANEL_CLASS = "Kistengeist-panel"
TERM_CLASS = "Kistengeist-term"
SPLIT_RATIO = 0.58
BOTTOM_RATIO = 0.45
TERM_RATIO = 0.62


def config_file(home: str | None = None) -> str:
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".config", "kistengeist", "panel.json")


def read_mode(path: str | None = None) -> str:
    try:
        with open(path or config_file(), encoding="utf-8") as fh:
            mode = json.load(fh).get("mode")
    except (OSError, ValueError, AttributeError):
        mode = None
    return mode if mode in MODES else "geteilt"


def save_mode(mode: str, path: str | None = None) -> None:
    if mode not in MODES:
        raise ValueError(mode)
    path = path or config_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"mode": mode}, fh)


def parse_workarea(wmctrl_d: str, fallback: tuple[int, int] = (1920, 1080)) -> tuple[int, int, int, int]:
    """Arbeitsfläche (ohne Leiste) aus „wmctrl -d“: x, y, Breite, Höhe."""
    for line in wmctrl_d.splitlines():
        if " * " not in line:
            continue
        m = re.search(r"WA:\s*(\d+),(\d+)\s+(\d+)x(\d+)", line)
        if m:
            return tuple(int(v) for v in m.groups())  # type: ignore[return-value]
    return (0, 0, *fallback)


def parse_windows(wmctrl_lx: str) -> list[tuple[str, str]]:
    """Fensterliste aus „wmctrl -lx“: [(fenster-id, wm_class)]."""
    out = []
    for line in wmctrl_lx.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3:
            out.append((parts[0], parts[2]))
    return out


def find(windows: list[tuple[str, str]], cls: str) -> list[str]:
    return [wid for wid, wc in windows if wc.split(".")[-1] == cls]


def find_claude(windows: list[tuple[str, str]]) -> list[str]:
    """Fenster von Claude Desktop (Electron-Klasse enthält „claude“, nicht unsere Werkzeuge)."""
    return [wid for wid, wc in windows
            if "claude" in wc.lower() and "kistengeist" not in wc.lower()]


def layout(mode: str, wa: tuple[int, int, int, int]) -> dict[str, tuple[int, int, int, int]]:
    """Rechtecke (x, y, b, h) für claude (nur bei „geteilt“), term und liste."""
    x, y, w, h = wa
    if mode == "unten":
        ph = int(h * BOTTOM_RATIO)
        py = y + h - ph
        tw = int(w * TERM_RATIO)
        return {"term": (x, py, tw, ph), "liste": (x + tw, py, w - tw, ph)}
    cw = int(w * SPLIT_RATIO)
    th = int(h * TERM_RATIO)
    return {"claude": (x, y, cw, h), "term": (x + cw, y, w - cw, th),
            "liste": (x + cw, y + th, w - cw, h - th)}


def _wm(*args: str, run=subprocess.run) -> str:
    try:
        res = run(["wmctrl", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout if res.returncode == 0 else ""


def _place(wid: str, rect: tuple[int, int, int, int], above: bool, run) -> None:
    _wm("-i", "-r", wid, "-b", "remove,maximized_vert,maximized_horz", run=run)
    _wm("-i", "-r", wid, "-e", "0,{},{},{},{}".format(*rect), run=run)
    _wm("-i", "-r", wid, "-b", ("add" if above else "remove") + ",above", run=run)


def apply(mode: str, run=subprocess.run) -> bool:
    """Ordnet die Fenster an. False, wenn Terminal oder Liste noch nicht sichtbar sind."""
    windows = parse_windows(_wm("-lx", run=run))
    terms, lists = find(windows, TERM_CLASS), find(windows, PANEL_CLASS)
    if not terms or not lists:
        return False
    rects = layout(mode, parse_workarea(_wm("-d", run=run)))
    above = mode == "unten"
    for wid in find_claude(windows):
        if "claude" in rects:
            _place(wid, rects["claude"], False, run)
        else:
            _wm("-i", "-r", wid, "-b", "add,maximized_vert,maximized_horz", run=run)
    _place(terms[0], rects["term"], above, run)
    _place(lists[0], rects["liste"], above, run)
    return True


def restore_claude(run=subprocess.run) -> None:
    """Claude wieder im Vollbild (beim Schließen des Panels)."""
    for wid in find_claude(parse_windows(_wm("-lx", run=run))):
        _wm("-i", "-r", wid, "-b", "add,maximized_vert,maximized_horz", run=run)


def panel_open(run=subprocess.run) -> bool:
    return bool(find(parse_windows(_wm("-lx", run=run)), PANEL_CLASS))


def close_windows(cls: str, run=subprocess.run) -> None:
    for wid in find(parse_windows(_wm("-lx", run=run)), cls):
        _wm("-i", "-c", wid, run=run)


def activate(cls: str, run=subprocess.run) -> None:
    for wid in find(parse_windows(_wm("-lx", run=run)), cls):
        _wm("-i", "-a", wid, run=run)
