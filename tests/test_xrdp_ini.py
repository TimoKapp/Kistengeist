import pytest

import xrdp_ini

SAMPLE = """[Globals]
port=3389
security_layer=negotiate

[Logging]
LogFile=xrdp.log

[Channels]
rdpdr=true

; Sitzungsarten
[Xorg]
name=Xorg
lib=libxup.so
username=ask
password=ask
code=20

[Xvnc]
name=Xvnc
lib=libvnc.so
username=ask
password=ask
port=-1

;[Local-Xorg]
;lib=libxup.so
"""


def test_rdp_mode_keeps_globals_and_replaces_sessions():
    out = xrdp_ini.rewrite(SAMPLE, "rdp")
    assert "[Globals]" in out and "security_layer=negotiate" in out
    assert "[Channels]" in out
    assert "[Xorg]" not in out and "[Xvnc]" not in out
    assert out.count("lib=") == 1  # nur unsere Sitzung
    assert "[Kistengeist]" in out and "lib=libxup.so" in out


def test_both_mode_mirrors_local_screen():
    out = xrdp_ini.rewrite(SAMPLE, "both")
    assert "[Kistengeist-Bildschirm]" in out
    assert "lib=libvnc.so" in out and "port=5900" in out and "ip=127.0.0.1" in out


def test_unknown_mode():
    with pytest.raises(ValueError):
        xrdp_ini.rewrite(SAMPLE, "desktop")
