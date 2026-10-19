#!/usr/bin/env python3
"""Lokaler MCP-Server (stdio) „kistengeist-terminal“: Claude Desktop kann damit Text an das
Claude-Code-Terminal des Pi übergeben und die Befehlsliste lesen/ergänzen.

Beispiel im Chat: „Schick das ans Terminal“ → Werkzeug send_to_terminal.
Nur Standardbibliothek; Nachrichten als JSON-RPC 2.0, eine pro Zeile (MCP-stdio-Transport).
Daten verlassen den Pi über diesen Server nicht.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kistengeist_commands as commands  # noqa: E402
import kistengeist_terminal as terminal  # noqa: E402

SERVER_INFO = {"name": "kistengeist-terminal", "version": "1.0.0"}
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

TOOLS = [
    {
        "name": "send_to_terminal",
        "description": ("Fügt Text oder einen Befehl in das Claude-Code-Terminal des Raspberry Pi ein "
                        "(tmux-Sitzung „kistengeist“, Ordner ~/Projekte) und blendet das Terminal ein. "
                        "Es wird bewusst NICHT abgeschickt: der Nutzer prüft den Text und drückt selbst Enter."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text, Aufgabe oder Slash-Befehl (z. B. /review)."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_commands",
        "description": "Listet die Befehle der Terminal-Befehlsliste (mit kurzer Erklärung), optional gefiltert.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Suchbegriff (optional)."}},
        },
    },
    {
        "name": "add_command",
        "description": "Nimmt einen neuen Eintrag in die Befehlsliste des Terminal-Panels auf.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Der Befehl bzw. Text, der eingefügt werden soll."},
                "description": {"type": "string", "description": "Knappe Erklärung auf Deutsch."},
                "category": {"type": "string", "description": "Kategorie (Standard: Eigene Befehle)."},
            },
            "required": ["command"],
        },
    },
]


def inside_own_terminal() -> bool:
    """True, wenn dieser Server von Claude Code IM Panel-Terminal gestartet wurde – dann
    würde Claude Text an sich selbst schicken."""
    return bool(os.environ.get(terminal.MARKER)) or f"/{terminal.SOCKET}," in os.environ.get("TMUX", "")


class InvalidParams(Exception):
    pass


def call_tool(name: str, args: dict) -> tuple[str, bool]:
    if name == "send_to_terminal":
        if inside_own_terminal():
            return "Dieses Terminal ist selbst das Ziel – Senden an sich selbst ist gesperrt.", True
        text = args.get("text")
        if not isinstance(text, str):
            return "Parameter „text“ fehlt.", True
        # Nie abschicken: Enter könnte einen offenen Rückfragedialog bestätigen oder „!befehl“
        # ausführen – das entscheidet immer der Mensch am Terminal.
        msg = terminal.send_text(text, submit=False)
        terminal.show_panel()
        return msg, False
    if name == "list_commands":
        found = commands.search(commands.all_commands(), str(args.get("query") or ""))
        lines = [f"{e['command']} – {e['description']} [{e['category']}]" for e in found]
        return "\n".join(lines) or "Keine passenden Befehle.", False
    if name == "add_command":
        entry = commands.add_user(str(args.get("command") or ""), str(args.get("description") or ""),
                                  str(args.get("category") or ""))
        return f"Aufgenommen: {entry['command']} ({entry['category']})", False
    raise InvalidParams(f"Unbekanntes Werkzeug: {name}")


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")
    if mid is None:  # Benachrichtigung (z. B. notifications/initialized)
        return None
    params = msg.get("params")
    params = {} if params is None else params
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "params muss ein Objekt sein"}}
    if method == "initialize":
        asked = params.get("protocolVersion")
        result = {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                  "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO,
                  "instructions": "Werkzeuge für das Claude-Code-Terminal des Raspberry Pi (Kistengeist)."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        args = params.get("arguments") or {}
        try:
            text, is_error = call_tool(str(params.get("name")), args if isinstance(args, dict) else {})
        except InvalidParams as exc:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": str(exc)}}
        except Exception as exc:  # Fehler als Werkzeug-Ergebnis melden, Server läuft weiter
            text, is_error = f"Fehler: {exc}", True
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unbekannt: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Ungültiges JSON"}}
        else:
            try:
                reply = handle(msg) if isinstance(msg, dict) else None
            except Exception as exc:  # nie den Server beenden
                mid = msg.get("id") if isinstance(msg, dict) else None
                reply = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(exc)}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()
