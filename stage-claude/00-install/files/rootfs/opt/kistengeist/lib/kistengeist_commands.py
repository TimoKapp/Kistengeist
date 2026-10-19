"""Befehlsliste für das Terminal-Panel: Standardbefehle, eigene Einträge und
die eigenen Befehle/Skills aus ~/.claude (wie sie Claude Code selbst anbietet).

Ein Eintrag ist ein dict: {"command": "/clear", "description": "…", "category": "…",
"source": "standard" | "eigene" | "claude"}.
"""

from __future__ import annotations

import json
import os

STANDARD_FILE = "/opt/kistengeist/share/commands/standard.json"
USER_CATEGORY = "Eigene Befehle"
MAX_COMMAND = 4000
MAX_DESCRIPTION = 300


def user_file(home: str | None = None) -> str:
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".config", "kistengeist", "commands.json")


def _clean(entry: object, source: str) -> dict | None:
    if not isinstance(entry, dict):
        return None
    # Leerzeichen am Ende bleibt erhalten (z. B. „/rename “ – danach folgt der Name).
    command = str(entry.get("command", "")).lstrip().rstrip("\r\n")
    if not command.strip():
        return None
    return {
        "command": command[:MAX_COMMAND],
        "description": " ".join(str(entry.get("description", "")).split())[:MAX_DESCRIPTION],
        "category": str(entry.get("category") or USER_CATEGORY).strip() or USER_CATEGORY,
        "source": source,
    }


def _load_list(path: str, source: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    items = data.get("commands", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [e for e in (_clean(i, source) for i in items) if e]


def load_standard(path: str = STANDARD_FILE) -> list[dict]:
    return _load_list(path, "standard")


def load_user(path: str | None = None) -> list[dict]:
    return _load_list(path or user_file(), "eigene")


def _save_user(path: str, entries: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"commands": [{k: e[k] for k in ("command", "description", "category")} for e in entries]}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def add_user(command: str, description: str = "", category: str = "", path: str | None = None) -> dict:
    """Fügt einen eigenen Befehl hinzu (gleicher Befehl wird ersetzt)."""
    path = path or user_file()
    entry = _clean({"command": command, "description": description, "category": category}, "eigene")
    if entry is None:
        raise ValueError("Der Befehl darf nicht leer sein.")
    entries = [e for e in load_user(path) if e["command"] != entry["command"]]
    entries.append(entry)
    _save_user(path, entries)
    return entry


def remove_user(command: str, path: str | None = None) -> bool:
    path = path or user_file()
    entries = load_user(path)
    kept = [e for e in entries if e["command"] != command]
    if len(kept) == len(entries):
        return False
    _save_user(path, kept)
    return True


def _frontmatter(path: str) -> dict:
    """Liest einfache Schlüssel aus dem YAML-Kopf einer Markdown-Datei (ohne YAML-Bibliothek)."""
    out: dict = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(20000)
    except OSError:
        return out
    lines = text.splitlines()
    body = lines
    if lines and lines[0].strip() == "---":
        body = []
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body = lines[i + 1:]
                break
            key, sep, value = line.partition(":")
            if sep and key and not key.startswith((" ", "\t")):
                out[key.strip()] = value.strip().strip("\"'")
    if "description" not in out or not out["description"]:
        first = next((b.strip().lstrip("#").strip() for b in body if b.strip()), "")
        out["description"] = first
    return out


def scan_claude(home: str | None = None) -> list[dict]:
    """Eigene Slash-Befehle (~/.claude/commands) und Skills (~/.claude/skills) des Nutzers."""
    home = home or os.path.expanduser("~")
    found: list[dict] = []
    cmd_dir = os.path.join(home, ".claude", "commands")
    if os.path.isdir(cmd_dir):
        for dirpath, _dirs, files in os.walk(cmd_dir):
            for name in sorted(files):
                if not name.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), cmd_dir)[:-3]
                meta = _frontmatter(os.path.join(dirpath, name))
                found.append({"command": "/" + rel.replace(os.sep, ":"),
                              "description": meta.get("description", ""),
                              "category": "Eigene Claude-Befehle", "source": "claude"})
    skill_dir = os.path.join(home, ".claude", "skills")
    if os.path.isdir(skill_dir):
        for name in sorted(os.listdir(skill_dir)):
            skill = os.path.join(skill_dir, name, "SKILL.md")
            if os.path.isfile(skill):
                meta = _frontmatter(skill)
                if meta.get("user-invocable", "").lower() == "false":
                    continue  # nur für Claude selbst, nicht per /name aufrufbar
                found.append({"command": "/" + (meta.get("name") or name),
                              "description": meta.get("description", ""),
                              "category": "Skills", "source": "claude"})
    return [e for e in (_clean(f, f["source"]) for f in found) if e]


def all_commands(home: str | None = None, standard_path: str = STANDARD_FILE) -> list[dict]:
    """Alle Einträge; eigene Einträge überschreiben gleichnamige Standardbefehle."""
    merged: dict[str, dict] = {}
    for entry in load_standard(standard_path) + scan_claude(home) + load_user(user_file(home)):
        merged[entry["command"]] = entry
    return list(merged.values())


def categories(entries: list[dict]) -> list[str]:
    seen: list[str] = []
    for e in entries:
        if e["category"] not in seen:
            seen.append(e["category"])
    return seen


def search(entries: list[dict], query: str = "", category: str = "") -> list[dict]:
    words = query.lower().split()
    out = []
    for e in entries:
        if category and e["category"] != category:
            continue
        hay = f"{e['command']} {e['description']} {e['category']}".lower()
        if all(w in hay for w in words):
            out.append(e)
    return out
