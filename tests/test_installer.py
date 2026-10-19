"""Ein-Befehl-Installer install.sh: Aufbau, der bei „curl | sudo bash“ sicher ist (echter Lauf: CI)."""

import os
import re
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "install.sh")


def text():
    return open(SCRIPT, encoding="utf-8").read()


def test_syntax_and_executable():
    subprocess.run(["bash", "-n", SCRIPT], check=True)
    assert os.access(SCRIPT, os.X_OK)


def test_runs_only_when_fully_downloaded():
    lines = [ln for ln in text().splitlines() if ln.strip()]
    assert lines[-1] == 'main "$@"'
    # außerhalb von main() nur Kommentare, Shebang und die Funktion selbst
    body = text().split("main() {", 1)[0]
    allowed = ('KG_WORK=""', 'cleanup() { [ -z "$KG_WORK" ] || rm -rf "$KG_WORK"; }')
    assert all(ln.startswith("#") or not ln.strip() or ln in allowed for ln in body.splitlines())


def test_no_interactive_reads_and_all_options_documented():
    src = text()
    assert not re.search(r"^\s*read\b", src, re.M)          # stdin ist bei curl | bash das Skript selbst
    used = set(re.findall(r"\$\{?(KG_[A-Z0-9_]+)", src))
    documented = set(re.findall(r"^#\s+(KG_[A-Z0-9_]+)=", src, re.M))
    assert used - {"KG_REPO", "KG_WORK"} <= documented, used - documented


def test_prepare_shared_with_image():
    chroot = open(os.path.join(REPO, "stage-claude/00-install/02-run-chroot.sh"), encoding="utf-8").read()
    assert "kistengeist-prepare --image" in chroot
    assert "kistengeist-prepare --live" in text()
    prep = open(os.path.join(REPO, "stage-claude/00-install/files/rootfs/opt/kistengeist/bin/kistengeist-prepare"),
                encoding="utf-8").read()
    # rpi-connect nur im Image entfernen (laufendes System: niemanden aussperren)
    assert prep.index('if [ "$mode" = --image ]; then\n    # Raspberry Pi Connect') > 0
