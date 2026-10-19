#!/usr/bin/env python3
"""Das Claude-Code-Terminal von Kistengeist: eine tmux-Sitzung „kistengeist“ mit Claude Code.

Die Sitzung läuft unabhängig vom Fenster weiter (Panel schließen beendet nichts). Texte werden
per „bracketed paste“ eingefügt: Claude Code nimmt sie wie eingefügten Text an, mehrzeilig, ohne
sie Zeichen für Zeichen als Tasten zu deuten. Abgeschickt wird nur auf Wunsch (Enter).

Aufruf (für Tastenkürzel):
  kistengeist_terminal.py send --selection primary|clipboard [--submit]
  kistengeist_terminal.py send --text "…" [--submit]
  kistengeist_terminal.py ensure
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

SOCKET = "kistengeist"          # eigener tmux-Server (tmux -L kistengeist)
SESSION = "kistengeist"
TARGET = "=kistengeist:"        # „=“: nur exakt diese Sitzung („:“ = deren aktives Fenster)
MARKER = "KISTENGEIST_TERMINAL"  # in der Sitzung gesetzt; der MCP-Server erkennt daran sich selbst
SHELLS = ("bash", "sh", "dash", "tmux", "")
CONF = "/opt/kistengeist/share/tmux/kistengeist.conf"
MAX_TEXT = 100_000
# Steuerzeichen außer Tab und Zeilenumbruch entfernen: verhindert u. a., dass ein Text die
# Einfügeklammer (ESC[201~) schließt und danach als Tastendruck wirkt.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def display_file() -> str:
    return os.path.join(os.path.expanduser("~"), ".config", "kistengeist", "display.env")


def session_env() -> dict[str, str]:
    """Grafik- und Sprachumgebung der laufenden Oberfläche. Claude Desktop startet MCP-Server
    mit stark reduzierter Umgebung (ohne DISPLAY und LANG); kistengeist-autostart legt die Werte
    deshalb in display.env ab."""
    env: dict[str, str] = {}
    try:
        with open(display_file(), encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.strip().partition("=")
                if sep and key in ("DISPLAY", "XAUTHORITY", "LANG"):
                    env[key] = value
    except OSError:
        pass
    for key in ("DISPLAY", "XAUTHORITY", "LANG"):
        if os.environ.get(key):
            env.setdefault(key, os.environ[key])
    if "UTF-8" not in env.get("LANG", "").upper().replace("UTF8", "UTF-8"):
        env["LANG"] = "C.UTF-8"
    return env


def proc_env() -> dict[str, str]:
    """Umgebung für tmux-Aufrufe (tmux braucht eine UTF-8-Locale für Umlaute)."""
    return {**os.environ, **session_env()}


def tmux_cmd(*args: str) -> list[str]:
    cmd = ["tmux", "-L", SOCKET]
    if os.path.exists(CONF):
        cmd += ["-f", CONF]
    return cmd + list(args)


def workdir() -> str:
    path = os.path.join(os.path.expanduser("~"), "Projekte")
    os.makedirs(path, exist_ok=True)
    return path


# In der Sitzung: Claude Code starten; nach /exit bleibt eine Shell offen.
SHELL_CMD = ("bash -lc 'command -v claude >/dev/null && claude; "
             "echo; echo \"Claude Code beendet. Neu starten: claude\"; exec bash -l'")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    return text[:MAX_TEXT]


def _env_args() -> list[str]:
    args = ["-e", f"{MARKER}=1"]
    for key, value in session_env().items():
        args += ["-e", f"{key}={value}"]
    return args


def running(run=subprocess.run) -> bool:
    return run(tmux_cmd("has-session", "-t", "=" + SESSION), capture_output=True, env=proc_env()).returncode == 0


def ensure_session(run=subprocess.run) -> bool:
    """Startet die Sitzung, falls nötig. Gibt True zurück, wenn sie neu gestartet wurde."""
    if running(run):
        return False
    try:
        run(tmux_cmd("new-session", "-d", "-s", SESSION, "-c", workdir(), "-x", "160", "-y", "45",
                     *_env_args(), SHELL_CMD), check=True, capture_output=True, env=proc_env())
    except subprocess.CalledProcessError:
        if not running(run):  # sonst hat das Terminalfenster sie gerade gleichzeitig angelegt
            raise
    return True


def attach_command() -> list[str]:
    """Befehl für das Terminalfenster: an die Sitzung anhängen (oder sie anlegen)."""
    return tmux_cmd("new-session", "-A", "-s", SESSION, "-c", workdir(), *_env_args(), SHELL_CMD)


def foreground(run=subprocess.run) -> str:
    """Name des Vordergrundprozesses im Terminal („bash“ = Claude Code läuft nicht)."""
    res = run(tmux_cmd("display-message", "-p", "-t", TARGET, "#{pane_current_command}"),
              capture_output=True, env=proc_env())
    out = res.stdout.decode(errors="replace") if isinstance(res.stdout, bytes) else (res.stdout or "")
    return out.strip() if res.returncode == 0 else ""


def claude_active(run=subprocess.run) -> bool:
    # Die native Installation heißt im Prozessnamen wie ihre Version (z. B. 2.1.290), daher
    # „läuft nicht“ = Shell im Vordergrund.
    return foreground(run) not in SHELLS


def wait_ready(run=subprocess.run, timeout: float = 30.0, settle: float = 3.0, sleep=time.sleep) -> bool:
    """Wartet nach dem Start, bis Claude Code im Vordergrund läuft (Pi 4 braucht dafür etwas)."""
    waited = 0.0
    while waited < timeout:
        if claude_active(run):
            sleep(settle)  # Oberfläche aufbauen lassen, bevor eingefügt wird
            return True
        sleep(0.5)
        waited += 0.5
    return False


def send_text(text: str, submit: bool = False, run=subprocess.run, sleep=time.sleep) -> str:
    """Fügt Text in die Eingabe von Claude Code ein. Rückgabe: kurze Meldung."""
    text = clean_text(text)
    if not text.strip():
        raise ValueError("Kein Text zum Senden.")
    if ensure_session(run) and not wait_ready(run, sleep=sleep):
        raise ValueError("Claude Code ist noch nicht bereit – bitte gleich noch einmal versuchen.")
    active = claude_active(run)
    if submit and not active:
        # In der Shell würde Enter den Text direkt als Befehl ausführen.
        raise ValueError("Claude Code läuft im Terminal nicht (nur Shell) – nichts abgeschickt.")
    buf = f"kistengeist-send-{os.getpid()}-{time.monotonic_ns()}"
    env = proc_env()
    run(tmux_cmd("load-buffer", "-b", buf, "-"), input=text.encode(), check=True, capture_output=True, env=env)
    run(tmux_cmd("paste-buffer", "-p", "-d", "-b", buf, "-t", TARGET), check=True, capture_output=True, env=env)
    if submit:
        sleep(0.2)
        run(tmux_cmd("send-keys", "-t", TARGET, "Enter"), check=True, capture_output=True, env=env)
        return "Text an Claude Code gesendet und abgeschickt."
    if not active:
        return "Text in die Shell eingefügt (Claude Code läuft gerade nicht; Start mit: claude)."
    return "Text in Claude Code eingefügt (noch nicht abgeschickt)."


def read_selection(which: str, run=subprocess.run) -> str:
    try:
        res = run(["xclip", "-o", "-selection", which], capture_output=True, timeout=3,
                  env={**os.environ, **session_env()})
    except (OSError, subprocess.SubprocessError):
        return ""
    return res.stdout.decode("utf-8", errors="replace") if res.returncode == 0 else ""


def show_panel() -> None:
    """Blendet das Panel ein (ohne es bei offenem Panel zu schließen)."""
    env = {**os.environ, **session_env()}
    if env.get("DISPLAY"):
        subprocess.Popen(["/opt/kistengeist/bin/kistengeist-panel", "--show"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Claude-Code-Terminal von Kistengeist")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    src = s.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--selection", choices=["primary", "clipboard"])
    s.add_argument("--submit", action="store_true")
    sub.add_parser("ensure")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "ensure":
            ensure_session()
            return 0
        text = args.text if args.text is not None else read_selection(args.selection)
        print(send_text(text, args.submit))
        show_panel()
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
