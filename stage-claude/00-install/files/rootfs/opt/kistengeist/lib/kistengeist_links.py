"""claude://-Links für Claude Desktop (offizielles Linkformat von Anthropic).

  claude://code/new?folder=<abs. Pfad>&q=<Text>   Claude-Code-Sitzung im Ordner
  claude://cowork/new?file=<abs. Pfad>&q=<Text>   Cowork mit angehängter Datei
  claude://claude.ai/new?q=<Text>                 neuer Chat

Claude Desktop fragt vor der Nutzung eines Ordners immer nach (Sicherheitsabfrage).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from urllib.parse import quote, urlencode

MAX_PROMPT = 14000  # Claude kürzt längere Texte ohnehin


def _query(params: list[tuple[str, str]]) -> str:
    clean = [(k, v) for k, v in params if v]
    return ("?" + urlencode(clean, quote_via=quote)) if clean else ""


def code_link(folder: str | None = None, prompt: str | None = None) -> str:
    if folder and not os.path.isabs(folder):
        raise ValueError("folder muss ein absoluter Pfad sein")
    return "claude://code/new" + _query([("folder", folder or ""), ("q", (prompt or "")[:MAX_PROMPT])])


def cowork_link(files: list[str], prompt: str | None = None) -> str:
    for f in files:
        if not os.path.isabs(f):
            raise ValueError("Dateipfade müssen absolut sein")
    params = [("file", f) for f in files] + [("q", (prompt or "")[:MAX_PROMPT])]
    return "claude://cowork/new" + _query(params)


def chat_link(prompt: str | None = None) -> str:
    return "claude://claude.ai/new" + _query([("q", (prompt or "")[:MAX_PROMPT])])


def cowork_available() -> bool:
    """Cowork braucht auf Linux eine VM (Modul "Cowork"); ohne sie lieber Claude Code nutzen."""
    return os.path.exists("/dev/kvm") and shutil.which("qemu-system-aarch64") is not None


def open_link(url: str) -> None:
    """Öffnet einen claude://-Link direkt über claude-desktop.

    Nicht über xdg-open: dessen Startbefehl ließe den Schalter für den Schlüsselbund
    weg. Läuft Claude schon, reicht die App den Link an das offene Fenster weiter.
    """
    subprocess.Popen(["claude-desktop", "--password-store=gnome-libsecret", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send_file_to_claude(path: str, uploads_dir: str) -> str:
    """Öffnet Claude mit der Datei. Mit Cowork wird sie angehängt, sonst startet eine
    Claude-Code-Sitzung im Upload-Ordner mit vorbereiteter Frage. Liefert den Link."""
    name = os.path.basename(path)
    if cowork_available():
        url = cowork_link([path], f"Sieh dir die Datei „{name}“ an.")
    else:
        ref = f"@{name}" if " " not in name else f"„{name}“"
        url = code_link(uploads_dir, f"Sieh dir die Datei {ref} an und fasse zusammen, was drin steht.")
    open_link(url)
    return url
