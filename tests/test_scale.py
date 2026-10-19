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
