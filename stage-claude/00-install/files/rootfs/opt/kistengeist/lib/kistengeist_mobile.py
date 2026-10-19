"""Zustand der Handy-Anbindung (Remote Control und Dispatch), ohne Oberfläche."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

SERVICE = "kistengeist-remote.service"
SETTINGS = os.path.expanduser("~/.claude/settings.json")
# Einstellungen, die die Original-App über /config bzw. Desktop-Einstellungen anbietet.
TOGGLES = {
    "remoteControlAtStartup": "Neue Code-Sitzungen automatisch mit dem Handy verbinden",
    "agentPushNotifEnabled": "Push, wenn Claude es für sinnvoll hält (z. B. Aufgabe fertig)",
    "inputNeededNotifEnabled": "Push, wenn Claude auf dich wartet (Fragen, Freigaben)",
}
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\r")
APP_URL = "https://claude.ai/mobile"  # führt aufs Handy in den passenden App-Store


@dataclass
class AuthState:
    installed: bool
    logged_in: bool
    method: str = ""
    account: str = ""

    @property
    def text(self) -> str:
        if not self.installed:
            return "Claude Code ist nicht installiert (Modul „Claude Code“)."
        if not self.logged_in:
            return "Claude Code ist nicht angemeldet."
        if self.method and self.method != "claude.ai":
            return f"Angemeldet per {self.method} – Remote Control braucht ein claude.ai-Abo."
        return "Angemeldet" + (f" als {self.account}" if self.account else "") + "."


def claude_bin() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    local = os.path.expanduser("~/.local/bin/claude")
    return local if os.access(local, os.X_OK) else None


def parse_auth(returncode: int, output: str) -> AuthState:
    """Wertet `claude auth status` aus (JSON; Exit 0 = angemeldet)."""
    method, account = "", ""
    try:
        data = json.loads(output)
        if isinstance(data, dict):
            method = str(data.get("authMethod") or "")
            nested = data.get("account") if isinstance(data.get("account"), dict) else {}
            account = str(data.get("email") or nested.get("email") or "")
    except ValueError:
        pass
    logged_in = returncode == 0 and method != "none"
    return AuthState(True, logged_in, "" if method == "none" else method, account)


def auth_state() -> AuthState:
    binary = claude_bin()
    if not binary:
        return AuthState(False, False)
    try:
        res = subprocess.run([binary, "auth", "status"], capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return AuthState(True, False)
    return parse_auth(res.returncode, res.stdout)


def service_state() -> str:
    """'active', 'activating', 'inactive', 'failed' … laut systemd."""
    try:
        res = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                             capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unbekannt"
    return res.stdout.strip() or "unbekannt"


def service_log(lines: int = 30) -> str:
    try:
        res = subprocess.run(["journalctl", "--user", "-u", SERVICE, "-n", str(lines), "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return strip_ansi(res.stdout)


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def restart_service() -> None:
    # --no-block: die Oberfläche wartet nicht, bis der alte Prozess beendet ist.
    subprocess.run(["systemctl", "--user", "--no-block", "restart", SERVICE], check=False, capture_output=True)


def read_toggles(path: str = SETTINGS) -> dict[str, bool]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    return {key: data.get(key) is True for key in TOGGLES}


def set_toggle(key: str, value: bool, path: str = SETTINGS) -> None:
    import json_merge

    if key not in TOGGLES:
        raise KeyError(key)
    json_merge.merge_file(path, {key: bool(value)})


def desktop_running() -> bool:
    return subprocess.call(["pgrep", "-u", str(os.getuid()), "-f", "claude-desktop"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def cowork_ready() -> tuple[bool, str]:
    """Kann Cowork (und damit Dispatch) auf diesem Pi laufen?"""
    if not os.path.exists("/dev/kvm"):
        return False, "Keine Virtualisierung (/dev/kvm fehlt)."
    if not shutil.which("qemu-system-aarch64"):
        return False, "QEMU fehlt – Modul „Cowork und Dispatch“ installieren."
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        return False, "Kein Zugriff auf /dev/kvm – einmal ab- und wieder anmelden."
    return True, "Bereit. Dispatch in Claude unter Cowork einrichten."
