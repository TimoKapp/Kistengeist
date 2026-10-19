"""Zugangsdaten-Datei, USB-Erkennung und n8n-Hilfen."""

import io
import json
import urllib.error

import kistengeist_access as access
import kistengeist_n8n as n8n
import kistengeist_usb as usb
import pytest

CFG = {"MODE": "both", "MODULES": "webserver n8n ssh upload zugangsdaten", "NET_ACCESS": "dyndns",
       "DDNS_PROVIDER": "ipv64", "DDNS_HOST": "meinpi.ipv64.net", "ACCESS_FILE_SECRETS": "yes"}
ACCESS = {"public_url": "https://meinpi.ipv64.net", "n8n_url": "https://meinpi.ipv64.net",
          "n8n_mcp_url": "https://meinpi.ipv64.net/mcp-server/http", "n8n_owner": "ok"}
NET = {"hostname": "kistengeist", "ipv4": ["192.168.178.20 (eth0)"], "ipv6": [], "mac": "dc:a6:32:00:00:01 (eth0)"}
SECRETS = {"account": "Systempw1", "ddns": {"token": "tok-en"},
           "n8n": {"email": "t@example.org", "password": "N8nGeheim1"}}


def test_ports_forward_only_web():
    ports = access.ports(CFG, ACCESS)
    fwd = sorted(p["port"] for p in ports if p["forward"])
    assert fwd == ["443", "80"]
    by_port = {p["port"]: p for p in ports}
    assert not by_port["3389"]["forward"] and "NIE" in by_port["3389"]["note"]
    assert not by_port["22"]["forward"] and not by_port["5678"]["forward"]


def test_ports_lan_and_tailscale_need_no_forwarding():
    for net in ("lan", "tailscale"):
        assert not [p for p in access.ports({**CFG, "NET_ACCESS": net}, ACCESS) if p["forward"]]


def test_render_with_and_without_secrets():
    text = access.render(CFG, ACCESS, SECRETS, NET, "claude", "17.10.2026 12:00")
    for needle in ("192.168.178.20", "dc:a6:32", "Systempw1", "N8nGeheim1", "tok-en", "meinpi.ipv64.net",
                   "ipv64.net + Portfreigabe", "FREIGEBEN", "Portfreigaben", "/mcp-server/http"):
        assert needle in text
    hidden = access.render({**CFG, "ACCESS_FILE_SECRETS": "no"}, ACCESS, SECRETS, NET, "claude", "x")
    assert "Systempw1" not in hidden and "N8nGeheim1" not in hidden and "tok-en" not in hidden
    assert "t@example.org" in hidden  # Anmeldename bleibt


def test_render_noip_key_and_hint():
    cfg = {**CFG, "DDNS_PROVIDER": "noip", "DDNS_HOST": "meinpi.ddns.net"}
    text = access.render(cfg, ACCESS, {**SECRETS, "ddns": {"user": "keyuser", "password": "KeyPw#1"}}, NET,
                         "claude", "x")
    assert "keyuser" in text and "KeyPw#1" in text and "30 Tage" in text and "No-IP" in text


def test_write_private(tmp_path):
    out = tmp_path / "Z.txt"
    access.write_private(str(out), "x")
    assert oct(out.stat().st_mode & 0o777) == "0o600"


LSBLK = {"blockdevices": [
    {"name": "mmcblk0", "type": "disk", "tran": None, "size": 64e9, "children": [
        {"name": "mmcblk0p2", "type": "part", "fstype": "ext4", "mountpoints": ["/"]}]},
    {"name": "sda", "type": "disk", "tran": "usb", "vendor": "SanDisk ", "model": "Ultra", "size": 32e9,
     "children": [{"name": "sda1", "type": "part", "fstype": "vfat", "label": "STICK", "size": 32e9,
                   "mountpoints": [None]}]},
    {"name": "sdb", "type": "disk", "tran": "usb", "vendor": "Boot", "model": "SSD", "size": 256e9,
     "children": [{"name": "sdb2", "type": "part", "fstype": "ext4", "mountpoints": ["/"]}]},
    {"name": "sdc", "type": "disk", "tran": "usb", "vendor": "Neu", "model": "", "size": 16e9, "children": []},
]}


def test_usb_candidates_exclude_system_and_unstable():
    links = {"sda": "/dev/disk/by-id/usb-SanDisk_Ultra-0:0", "sdb": "/dev/disk/by-id/usb-Boot_SSD-0:0",
             "sdc": "/dev/disk/by-id/usb-Neu-0:0"}
    found = usb.candidates(LSBLK, {"mmcblk0", "sdb"}, links)
    assert [s["device"] for s in found] == ["/dev/sda", "/dev/sdc"]
    assert found[0]["usable"] and not found[1]["usable"]
    assert found[0]["name"] == "SanDisk Ultra"
    assert usb.candidates(LSBLK, set(), {}) == []  # ohne by-id-Pfad nichts


def test_usb_by_id_links(tmp_path):
    (tmp_path / "sda").write_text("")
    (tmp_path / "usb-X-0:0").symlink_to(tmp_path / "sda")
    (tmp_path / "usb-X-0:0-part1").symlink_to(tmp_path / "sda")
    assert usb.by_id_links(str(tmp_path)) == {"sda": str(tmp_path / "usb-X-0:0")}


def test_usb_check_rejects_bad_paths():
    for bad in ("/dev/sda", "/dev/disk/by-id/usb-X-part1", "/dev/disk/by-id/usb-../../sda"):
        with pytest.raises(ValueError):
            usb.check(bad)
    assert usb.valid_label("KISTENGEIST") and not usb.valid_label("ZU-LANGER-NAME") and not usb.valid_label("a b")


def test_n8n_password_rules():
    assert n8n.password_problem("Geheim123") == ""
    assert "Ziffer" in n8n.password_problem("Geheimnis")
    assert "Großbuchstaben" in n8n.password_problem("geheim123")
    assert "8 bis 64" in n8n.password_problem("G1")


class FakeRes(io.BytesIO):
    def __init__(self, status=200):
        super().__init__(b"{}")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_n8n_setup_owner_waits_and_posts():
    calls = []

    def opener(req, timeout=0):
        url = req if isinstance(req, str) else req.full_url
        calls.append(url)
        if url.endswith("/healthz/readiness") and len(calls) < 3:
            raise urllib.error.URLError("noch nicht")
        if not isinstance(req, str):
            assert json.loads(req.data)["email"] == "t@example.org"
        return FakeRes()

    data = {"email": "t@example.org", "firstName": "T", "lastName": "X", "password": "Geheim123"}
    assert n8n.setup_owner(data, "http://n8n", opener=opener, sleep=lambda s: None) == "ok"
    assert calls[-1] == "http://n8n/rest/owner/setup"


def test_n8n_setup_owner_reports_rejection():
    def opener(req, timeout=0):
        if isinstance(req, str):
            return FakeRes()
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, None)
    with pytest.raises(RuntimeError, match="400"):
        n8n.setup_owner({"email": "a@b.de", "firstName": "a", "lastName": "b", "password": "x"}, "http://n",
                        opener=opener, sleep=lambda s: None)


def test_owner_env_quotes_hash_and_rejects_injection():
    data = {"email": "t@example.org", "firstName": "Timo", "lastName": "Test", "password": "Geheim123"}
    env = n8n.owner_env(data, hasher=lambda pw: "$2b$10$abc")
    assert "N8N_INSTANCE_OWNER_MANAGED_BY_ENV=true" in env
    assert "N8N_INSTANCE_OWNER_PASSWORD_HASH='$2b$10$abc'" in env
    assert "Geheim123" not in env
    for bad in ({"firstName": "a$b"}, {"lastName": "x\nN8N_X=1"}, {"email": "a b@c.de"}, {"password": "kurz"}):
        with pytest.raises(ValueError):
            n8n.owner_env({**data, **bad}, hasher=lambda pw: "h")


def test_owner_ready_checks_setup_flag():
    def opener_for(flag):
        def opener(req, timeout=0):
            res = FakeRes()
            if str(req).endswith("/rest/settings"):
                res = FakeRes()
                res.write(json.dumps({"data": {"userManagement": {"showSetupOnFirstLoad": flag}}}).encode())
                res.seek(0)
            return res
        return opener
    assert n8n.owner_ready("http://n", opener=opener_for(False), sleep=lambda s: None)
    assert not n8n.owner_ready("http://n", opener=opener_for(True), sleep=lambda s: None)


def test_disk_of_partition(tmp_path):
    disk = tmp_path / "devices" / "mmcblk0"
    (disk / "mmcblk0p2").mkdir(parents=True)
    (disk / "mmcblk0p2" / "partition").write_text("2")
    block = tmp_path / "block"
    block.mkdir()
    (block / "mmcblk0p2").symlink_to(disk / "mmcblk0p2")
    (block / "mmcblk0").symlink_to(disk)
    assert usb.disk_of("mmcblk0p2", str(block)) == "mmcblk0"
    assert usb.disk_of("mmcblk0", str(block)) == "mmcblk0"


def test_list_sticks_empty_without_known_system_disk(monkeypatch):
    monkeypatch.setattr(usb, "system_disks", lambda: set())
    assert usb.list_sticks() == []


def test_rdp_file_keeps_media_keys_and_audio_local():
    rdp = access.rdp_file("kistengeist.local")
    assert rdp.endswith("\r\n") and "full address:s:kistengeist.local" in rdp
    assert "audiomode:i:0" in rdp and "audiocapturemode:i:1" in rdp and "keyboardhook:i:0" in rdp
    assert "password" not in rdp.lower()


def test_ports_browser_remote():
    cfg = {**CFG, "REMOTE": "browser"}
    by_port = {p["port"]: p for p in access.ports(cfg, ACCESS)}
    assert "8443" in by_port and not by_port["8443"]["forward"] and "3389" not in by_port
    text = access.render(cfg, ACCESS, SECRETS, NET, "claude", "x")
    assert "https://kistengeist.local:8443" in text
