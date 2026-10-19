"""Rechtliche Hinweise: Laden, Version, Prüfung der Bestätigung, Ausgabe als HTML/Markdown.

Einzige Quelle der Texte ist share/legal/legal.json. Die Version ist eine Prüfsumme des
Inhalts: Ändert sich ein Text, muss erneut bestätigt werden.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re

LEGAL_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "share", "legal", "legal.json")

_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def load(path: str = LEGAL_FILE) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def version(data: dict) -> str:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def confirmation_ids(data: dict) -> list[str]:
    return [c["id"] for c in data["confirmations"]]


def accepted(data: dict, answer: object) -> bool:
    """Gültig nur mit passender Version und allen Häkchen ausdrücklich auf true."""
    if not confirmation_ids(data):
        return False  # ohne Bestätigungspunkte nie automatisch gültig
    if not isinstance(answer, dict) or answer.get("version") != version(data):
        return False
    checks = answer.get("checks")
    if not isinstance(checks, dict):
        return False
    return all(checks.get(cid) is True for cid in confirmation_ids(data))


def record(data: dict, when: str, ntp_synced: str = "unbekannt") -> str:
    """Inhalt der Nachweisdatei (ohne personenbezogene Daten). Der Pi 4 hat keine Echtzeituhr;
    NTP_SYNC zeigt, ob die Uhrzeit zum Zeitpunkt der Bestätigung schon gestellt war."""
    return (f"VERSION={version(data)}\nSTAND={data['updated']}\nBESTAETIGT_AM={when}\nNTP_SYNC={ntp_synced}\n"
            f"BESTAETIGT={','.join(confirmation_ids(data))}\n")


def inline_html(text: str) -> str:
    """Wandelt **fett** und [Text](https://…) sicher in HTML um (alles andere wird escaped)."""
    out, pos = [], 0
    for m in _LINK.finditer(text):
        out.append(_bold(html.escape(text[pos:m.start()])))
        out.append(f'<a href="{html.escape(m.group(2), quote=True)}" target="_blank" rel="noopener noreferrer">'
                   f"{html.escape(m.group(1))}</a>")
        pos = m.end()
    out.append(_bold(html.escape(text[pos:])))
    return "".join(out)


def _bold(escaped: str) -> str:
    return _BOLD.sub(r"<strong>\1</strong>", escaped)


def to_html(data: dict) -> str:
    parts = [
        "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>{html.escape(data['title'])}</title>",
        "<style>body{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:0 auto;padding:24px 16px;"
        "color:#1f1e1d;background:#f5f4ef}h1{font-size:26px}h2{font-size:18px;margin-top:28px}"
        "a{color:#c96442}@media(prefers-color-scheme:dark){body{color:#f5f4ef;background:#1f1e1d}"
        "a{color:#d97757}}</style></head><body>",
        f"<h1>{html.escape(data['title'])}</h1>",
        f"<p><em>Stand {html.escape(data['updated'])} · Version {version(data)}</em></p>",
        f"<p>{inline_html(data['intro'])}</p>",
    ]
    for sec in data["sections"]:
        parts.append(f"<h2 id=\"{html.escape(sec['id'])}\">{html.escape(sec['title'])}</h2>")
        parts.extend(f"<p>{inline_html(p)}</p>" for p in sec["body"])
    parts.append("</body></html>")
    return "\n".join(parts)


def to_markdown(data: dict) -> str:
    lines = [f"# {data['title']}", "", f"_Stand {data['updated']} · Version {version(data)}_", "",
             data["intro"], ""]
    for sec in data["sections"]:
        lines += [f"## {sec['title']}", ""]
        for p in sec["body"]:
            lines += [p, ""]
    lines += ["## Bestätigung bei der Installation", ""]
    lines += [f"- [ ] {c['text']}" for c in data["confirmations"]]
    return "\n".join(lines) + "\n"
