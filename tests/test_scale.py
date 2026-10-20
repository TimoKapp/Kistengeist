"""Schriftgröße: Xresources, tint2-Skalierung, Speichern; xrdp-Tonkanäle."""

import kistengeist_scale as scale
import pytest
import xrdp_ini
from conftest import CP_HOME

TINT2 = open(f"{CP_HOME}/share/tint2/tint2rc.in", encoding="utf-8").read()


def test_xresources_replaces_and_keeps_other_lines():
    old = "XTerm*faceSize: 12\nXft.dpi: 192\nXcursor.size: 48\n"
    new = scale.xresources(old, 150)
    assert "XTerm*faceSize: 12" in new
    assert "Xft.dpi: 144" in new and "Xcursor.size: 36" in new and "Xcursor.theme: Adwaita" in new
    assert new.count("Xft.dpi") == 1


def test_tint2_scaled_at_200_percent():
    out = scale.tint2(TINT2, 200)
    assert "panel_size = 100% 88" in out          # Höhe verdoppelt, Breite bleibt 100 %
    assert "launcher_icon_size = 64" in out
    assert "systray_icon_size = 44" in out
    assert "task_maximum_size = 440 72" in out
    assert "panel_padding = 16 8 16" in out
    assert "task_font = Sans 22" in out
    assert "#e6dccb" in out                      # Farben unverändert
    assert scale.tint2(TINT2, 100) == TINT2


def test_scale_conf_roundtrip(tmp_path):
    assert scale.read_scale(str(tmp_path)) is None
    scale.write_scale(200, str(tmp_path))
    assert scale.read_scale(str(tmp_path)) == 200
    assert "XCURSOR_SIZE=48" in scale.env_lines(200)
    with pytest.raises(ValueError):
        scale.write_scale(130, str(tmp_path))


def test_beige_colors_in_template():
    assert "background_color = #e6dccb 100" in TINT2
    assert "task_font_color = #3d3a36" in TINT2


def test_openbox_has_no_left_frame_binding():
    rc = open(f"{CP_HOME}/share/openbox/rc.xml", encoding="utf-8").read()
    import re
    frame = re.search(r'<context name="Frame">(.*?)</context>', rc, re.S)
    assert frame is None or 'button="Left"' not in frame.group(1)   # verschluckte sonst jeden Linksklick
    assert '<context name="Close">' in rc and '<context name="Titlebar">' in rc
    assert "<doubleClickTime>600</doubleClickTime>" in rc


def test_xrdp_sound_channels_enabled():
    out = xrdp_ini.rewrite("[Globals]\nport=3389\n[Channels]\nrdpsnd=false\n", "rdp")
    assert "rdpsnd=true" in out and "drdynvc=true" in out and "rdpsnd=false" not in out
    out2 = xrdp_ini.rewrite("[Globals]\nport=3389\n", "rdp")
    assert "[Channels]" in out2 and "rdpsnd=true" in out2


def _run_script(tmp_path, name, args, stubs, check=True):
    """Skript aus bin/ mit Stub-Programmen ausführen; /opt/kistengeist zeigt auf den Quellbaum."""
    import os
    import subprocess
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    for prog, body in stubs.items():
        p = stub_dir / prog
        p.write_text(f'#!/bin/bash\necho "{prog} $* XCURSOR_SIZE=$XCURSOR_SIZE" >>"{log}"\n{body}\n')
        p.chmod(0o755)
    src = open(f"{CP_HOME}/bin/{name}", encoding="utf-8").read().replace("/opt/kistengeist", CP_HOME)
    script = tmp_path / name
    script.write_text(src)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {**os.environ, "HOME": str(home), "PATH": f"{stub_dir}:{os.environ['PATH']}", "XCURSOR_SIZE": "24"}
    subprocess.run(["bash", str(script), *args], env=env, check=check, timeout=30)
    return log.read_text() if log.exists() else ""


def test_scale_change_resizes_cursor_at_once(tmp_path):
    calls = _run_script(tmp_path, "kistengeist-scale", [], {
        "zenity": 'case "$*" in *--list*) echo "150 %";; *) exit 1;; esac',
        "xrdb": "", "xsetroot": "", "dbus-update-activation-environment": "", "tint2": "", "pkill": "",
    })
    assert "xsetroot -cursor_name left_ptr XCURSOR_SIZE=36" in calls
    assert "Xcursor.size: 36" in (tmp_path / "home/.Xresources").read_text()
    assert "Claude Desktop jetzt neu starten?" in calls and "Mauszeiger" in calls


def test_launch_uses_current_cursor_and_scale(tmp_path):
    (tmp_path / "home/.config/kistengeist").mkdir(parents=True)
    (tmp_path / "home/.config/kistengeist/scale.conf").write_text("SCALE=200\n")
    calls = _run_script(tmp_path, "kistengeist-launch", ["claude"], {"claude-desktop": ""})
    assert "--force-device-scale-factor=2.00" in calls and "XCURSOR_SIZE=48" in calls


def test_claude_loop_rereads_scale_before_each_start(tmp_path):
    conf = tmp_path / "home/.config/kistengeist/scale.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("SCALE=100\n")
    # Erster Start: Größe auf 150 % ändern; die Pause danach beendet die Schleife.
    calls = _run_script(tmp_path, "kistengeist-launch", ["claude-loop"], {
        "claude-desktop": f'[ -f "{tmp_path}/once" ] || {{ touch "{tmp_path}/once"; echo SCALE=150 >"{conf}"; }}',
        "sleep": f'[ -f "{tmp_path}/twice" ] && kill $PPID; touch "{tmp_path}/twice"',
    }, check=False)
    starts = [ln for ln in calls.splitlines() if ln.startswith("claude-desktop")]
    assert len(starts) == 2
    assert "XCURSOR_SIZE=24" in starts[0] and "scale-factor" not in starts[0]
    assert "XCURSOR_SIZE=36" in starts[1] and "--force-device-scale-factor=1.50" in starts[1]
