"""Setup-Assistent: USB-Stick, Internet/Webserver, n8n-Konto und Zugangsdaten."""

import json
import os

from test_server import GOOD, request, server  # noqa: F401

STICK = {"id": "/dev/disk/by-id/usb-SanDisk_Ultra_123-0:0", "device": "/dev/sda", "name": "SanDisk Ultra",
         "size": 32_000_000_000, "partitions": [{"name": "sda1", "fstype": "vfat", "label": "STICK",
                                                 "size": 32_000_000_000, "mounts": []}], "usable": True}

N8N = {"firstName": "Timo", "lastName": "Test", "email": "t@example.org", "password": "Geheim123", "license": ""}
INET = {"net": "dyndns", "provider": "ipv64", "host": "https://MeinPi.ipv64.net/", "token": "AbCdEf1234567890xyz",
        "ipv6Only": False, "acmeEmail": "", "n8n": N8N, "fileSecrets": True, "fileUsb": True}


def payload(**extra):
    p = {**GOOD, "modules": ["usb-stick", "webserver", "n8n", "zugangsdaten"],
         "usb": {"device": STICK["id"], "format": True, "formatConfirmed": True, "label": "KISTENGEIST"},
         "internet": INET}
    p.update(extra)
    return p


def test_usb_list(server, monkeypatch):  # noqa: F811
    srv, port, _ = server
    monkeypatch.setenv("CP_TEST_USB", json.dumps([STICK]))
    status, data = request(port, "GET", "/api/usb")
    assert status == 200 and data["sticks"][0]["sizeText"] == "32,0 GB"
    assert "vfat" in data["sticks"][0]["content"]


def test_install_with_server_n8n_usb(server, monkeypatch):  # noqa: F811
    srv, port, tmp = server
    monkeypatch.setenv("CP_TEST_USB", json.dumps([STICK]))
    status, data = request(port, "POST", "/api/install", payload())
    assert status == 200, data
    conf = (tmp / "etc" / "setup.conf").read_text()
    for line in ('USB_DEVICE="/dev/disk/by-id/usb-SanDisk_Ultra_123-0:0"', 'USB_FORMAT="yes"', 'NET_ACCESS="dyndns"',
                 'DDNS_PROVIDER="ipv64"', 'DDNS_HOST="meinpi.ipv64.net"',
                 'ACCESS_FILE_SECRETS="yes"', 'ACCESS_FILE_USB="yes"'):
        assert line in conf
    # Keine Geheimnisse in setup.conf
    assert "Geheim123" not in conf and "AbCdEf" not in conf and "t@example.org" not in conf
    token = tmp / "etc" / "ddns.json"
    assert json.loads(token.read_text()) == {"token": INET["token"]}
    assert oct(os.stat(token).st_mode & 0o777) == "0o600"
    n8n = json.loads((tmp / "run" / "n8n.json").read_text())
    assert n8n["password"] == "Geheim123"
    assert oct(os.stat(tmp / "run" / "n8n.json").st_mode & 0o777) == "0o600"
    assert (tmp / "run" / "account.secret").read_text().strip() == GOOD["password"]


def test_validation_errors(server, monkeypatch):  # noqa: F811
    srv, port, _ = server
    monkeypatch.setenv("CP_TEST_USB", json.dumps([STICK]))
    cases = [
        ({"usb": {"device": STICK["id"], "format": True, "formatConfirmed": False}}, "gelöscht"),
        ({"usb": {"device": "/dev/disk/by-id/usb-gibtsnicht", "format": False}}, "nicht gefunden"),
        ({"usb": {"device": "/dev/sda; rm", "format": False}}, "Ungültiger"),
        ({"internet": {**INET, "token": "kurz"}}, "Token"),
        ({"internet": {**INET, "host": "meinpi.example.com"}}, "ipv64.net"),
        ({"internet": {**INET, "provider": "duckdns", "host": "meinpi", "token": "falsch"}}, "DuckDNS-Token"),
        ({"internet": {**INET, "provider": "noip", "host": "meinpi.ddns.net"}}, "DDNS-Key"),
        ({"internet": {**INET, "provider": "desec"}}, "Anbieter"),
        ({"internet": {**INET, "n8n": {**N8N, "password": "geheim123"}}}, "Großbuchstaben"),
        ({"internet": {**INET, "n8n": {**N8N, "email": "keine-mail"}}}, "E-Mail"),
        ({"internet": {**INET, "net": "tailscale", "tailscaleKey": "abc"}}, "tskey"),
    ]
    for extra, needle in cases:
        status, data = request(port, "POST", "/api/install", payload(**extra))
        assert status == 400 and needle in data["error"], (extra, data)


def test_no_secret_file_when_deselected(server, monkeypatch):  # noqa: F811
    srv, port, tmp = server
    monkeypatch.setenv("CP_TEST_USB", "[]")
    p = payload(modules=["webserver", "zugangsdaten"], internet={"net": "lan", "fileSecrets": False})
    status, data = request(port, "POST", "/api/install", p)
    assert status == 200, data
    assert not (tmp / "run" / "account.secret").exists()
    assert not (tmp / "etc" / "ddns.json").exists()
    assert 'NET_ACCESS="lan"' in (tmp / "etc" / "setup.conf").read_text()


def test_ddns_test_endpoint(server):  # noqa: F811
    _srv, port, _ = server
    for body, host in (
        ({"provider": "ipv64", "host": "meinpi.home64.de", "token": INET["token"]}, "meinpi.home64.de"),
        ({"provider": "dynv6", "host": "meinpi.dynv6.net", "token": "dynv6tokenABC"}, "meinpi.dynv6.net"),
        ({"provider": "noip", "host": "meinpi.ddns.net", "user": "keyuser", "password": "Pw:#1"}, "meinpi.ddns.net"),
        ({"provider": "duckdns", "host": "MeinPi", "token": "a1b2c3d4-0000-1111-2222-333344445555"},
         "meinpi.duckdns.org"),
    ):
        status, data = request(port, "POST", "/api/ddns-test", body)
        assert status == 200 and data["ok"] and data["host"] == host, (body, data)
    status, data = request(port, "POST", "/api/ddns-test",
                           {"provider": "noip", "host": "meinpi.ddns.net", "user": "u", "password": "falsch"})
    assert status == 200 and not data["ok"]
    status, data = request(port, "POST", "/api/ddns-test", {"provider": "ipv64", "host": "x y", "token": "1"})
    assert status == 400


def test_rdp_download(server):  # noqa: F811
    _srv, port, _ = server
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", "/kistengeist.rdp", headers={"Host": f"127.0.0.1:{port}"})
    res = conn.getresponse()
    body = res.read().decode()
    assert res.status == 200 and "attachment" in res.getheader("Content-Disposition")
    assert "audiocapturemode:i:1" in body


def test_remote_browser_choice(server, monkeypatch):  # noqa: F811
    _srv, port, tmp = server
    monkeypatch.setenv("CP_TEST_USB", "[]")
    p = {**GOOD, "mode": "rdp", "modules": [], "remote": "browser", "browserPassword": "AnderesPw123"}
    status, data = request(port, "POST", "/api/install", {**p, "browserPassword": GOOD["password"]})
    assert status == 400, data                                          # muss sich vom Login unterscheiden
    status, data = request(port, "POST", "/api/install", p)
    assert status == 200, data
    conf = (tmp / "etc" / "setup.conf").read_text()
    assert 'REMOTE="browser"' in conf and 'AUTOLOGIN="yes"' in conf   # Sitzung läuft ohne Monitor
    assert (tmp / "run" / "secret").read_text().strip() == "AnderesPw123"  # Passwort für den Browser-Zugang
    status, data = request(port, "POST", "/api/install", {**p, "remote": "vnc"})
    assert status in (400, 409)
