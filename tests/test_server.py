import http.client
import json
import os
import socket
import threading
from http.server import ThreadingHTTPServer

import pytest
from conftest import MODULES_DIR


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("CP_TEST_MODE", "1")
    import importlib

    import server as srv

    importlib.reload(srv)
    monkeypatch.setattr(srv, "ETC", str(tmp_path / "etc"))
    monkeypatch.setattr(srv, "RUN", str(tmp_path / "run"))
    monkeypatch.setattr(srv, "LOG", str(tmp_path / "install.log"))
    (tmp_path / "etc").mkdir(exist_ok=True)
    (tmp_path / "etc" / "setup-code").write_text(CODE + "\n")
    srv.Handler.modules_dir = MODULES_DIR
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield srv, httpd.server_address[1], tmp_path
    httpd.shutdown()


CODE = "TESTCQDE23"


def request(port, method, path, body=None, host=None, ctype="application/json", code=CODE):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if code is not None:
        headers["X-Setup-Code"] = code
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = ctype
    conn.request(method, path, body=data, headers=headers)
    res = conn.getresponse()
    raw = res.read()
    try:
        return res.status, json.loads(raw)
    except ValueError:
        return res.status, raw.decode()


import kistengeist_legal as legal  # noqa: E402

_L = legal.load()
LEGAL_OK = {"version": legal.version(_L), "checks": {cid: True for cid in legal.confirmation_ids(_L)}}

GOOD = {"legal": LEGAL_OK, "mode": "both", "modules": ["chrome", "claude-in-chrome", "storage"],
        "password": "geheim123", "autologin": True,
        "locale": "de_DE.UTF-8", "keymap": "at", "timezone": "Europe/Vienna"}


def test_info(server):
    _srv, port, _ = server
    status, data = request(port, "GET", "/api/info")
    assert status == 200
    assert data["status"]["state"] == "idle"
    assert any(m["id"] == "claude-desktop" and m["required"] for m in data["modules"])


def test_static_page(server):
    _srv, port, _ = server
    status, body = request(port, "GET", "/")
    assert status == 200 and "Kistengeist" in body


def test_dns_rebinding_blocked(server):
    _srv, port, _ = server
    status, _ = request(port, "GET", "/api/info", host="evil.example.com")
    assert status == 403
    status, _ = request(port, "GET", "/api/info", host=f"{socket.gethostname()}.local")
    assert status == 200


def test_requires_json(server):
    _srv, port, _ = server
    status, _ = request(port, "POST", "/api/install", GOOD, ctype="text/plain")
    assert status == 415


@pytest.mark.parametrize("change,message", [
    ({"mode": "kiosk"}, "Zugangsart"),
    ({"password": "kurz"}, "Passwort"),
    ({"password": "zeile\nzwei1234"}, "ungültige"),
    ({"modules": ["gibt-es-nicht"]}, "Unbekannte"),
    ({"timezone": "Mars/Olymp"}, "Region"),
])
def test_validation(server, change, message):
    _srv, port, _ = server
    status, data = request(port, "POST", "/api/install", {**GOOD, **change})
    assert status == 400 and message in data["error"]


def test_install_requires_legal(server):
    _srv, port, tmp = server
    status, data = request(port, "POST", "/api/install", {**GOOD, "legal": None})
    assert status == 400 and "rechtlichen Hinweise" in data["error"]
    partial = {"version": LEGAL_OK["version"], "checks": {**LEGAL_OK["checks"], "age": False}}
    status, _ = request(port, "POST", "/api/install", {**GOOD, "legal": partial})
    assert status == 400
    assert not (tmp / "etc" / "setup.conf").exists()


def test_info_contains_legal(server):
    _srv, port, _ = server
    _, data = request(port, "GET", "/api/info")
    assert data["legal"]["version"] == LEGAL_OK["version"]
    assert len(data["legal"]["confirmations"]) == 4


def test_install_flow(server):
    _srv, port, tmp = server
    status, data = request(port, "POST", "/api/install", GOOD)
    assert status == 200, data
    assert data["plan"][-1] == "finalize" and "chrome" in data["plan"]

    conf = (tmp / "etc" / "setup.conf").read_text()
    assert 'MODE="both"' in conf and 'AUTOLOGIN="yes"' in conf
    assert 'KEYMAP="de"' in conf  # Österreich nutzt das deutsche Layout
    assert "geheim" not in conf
    assert 'PRIVACY_MINIMAL="yes"' in conf
    accepted = (tmp / "etc" / "legal-accepted").read_text()
    assert f"VERSION={LEGAL_OK['version']}" in accepted and "NTP_SYNC=" in accepted
    assert (tmp / "etc" / "legal-accepted.json").exists()
    secret = tmp / "run" / "secret"
    assert secret.read_text().strip() == "geheim123"
    assert oct(os.stat(secret).st_mode & 0o777) == "0o600"

    status, _ = request(port, "POST", "/api/install", GOOD)
    assert status == 409  # läuft bereits

    status, data = request(port, "GET", "/api/status")
    assert data["status"]["state"] == "running"


def test_autologin_rules(server):
    _srv, port, tmp = server
    request(port, "POST", "/api/install", {**GOOD, "mode": "both", "autologin": False})
    assert 'AUTOLOGIN="yes"' in (tmp / "etc" / "setup.conf").read_text()  # bei "beides" Pflicht
    _, data = request(port, "GET", "/api/status")
    assert data["status"]["mode"] == "both"


def test_autologin_string_is_not_true(server):
    _srv, port, tmp = server
    request(port, "POST", "/api/install", {**GOOD, "mode": "desktop", "autologin": "false"})
    assert 'AUTOLOGIN="no"' in (tmp / "etc" / "setup.conf").read_text()


def test_rdp_mode_disables_autologin_and_secret(server):
    _srv, port, tmp = server
    status, _ = request(port, "POST", "/api/install", {**GOOD, "mode": "rdp"})
    assert status == 200
    conf = (tmp / "etc" / "setup.conf").read_text()
    assert 'AUTOLOGIN="no"' in conf
    assert not (tmp / "run" / "secret").exists()


def test_offline_install_refused(server, monkeypatch):
    _srv, port, _ = server
    monkeypatch.setenv("CP_TEST_ONLINE", "0")
    status, data = request(port, "POST", "/api/install", GOOD)
    assert status == 409 and "Internet" in data["error"]


def test_reboot_only_when_done(server):
    _srv, port, tmp = server
    status, _ = request(port, "POST", "/api/reboot", {})
    assert status == 409
    (tmp / "etc").mkdir(exist_ok=True)
    (tmp / "etc" / "installed").write_text("x")
    status, _ = request(port, "POST", "/api/reboot", {})
    assert status == 200


def test_wifi_only_in_hotspot_mode(server):
    _srv, port, _ = server
    assert request(port, "POST", "/api/wifi", {"ssid": "Heim", "password": "langgenug"})[0] == 409


def test_wifi_validation(server):
    _srv, port, tmp = server
    (tmp / "run").mkdir(exist_ok=True)
    (tmp / "run" / "hotspot").write_text("")
    assert request(port, "POST", "/api/wifi", {"ssid": "Heim", "password": "z" * 64})[0] == 400
    assert request(port, "POST", "/api/wifi", {"ssid": "Heim", "password": "ab12" * 16})[0] == 200
    assert request(port, "POST", "/api/wifi", {"ssid": "", "password": ""})[0] == 400
    assert request(port, "POST", "/api/wifi", {"ssid": "Heim", "password": "kurz"})[0] == 400
    assert request(port, "POST", "/api/wifi", {"ssid": "Heim", "password": "langgenug"})[0] == 200


def test_setup_code_required(server):
    _srv, port, _tmp = server
    assert request(port, "GET", "/api/info", code=None)[0] == 200          # Grundinfo frei
    assert request(port, "GET", "/", code=None)[0] == 200
    for method, path in (("GET", "/api/status"), ("GET", "/api/usb"), ("POST", "/api/install"),
                         ("POST", "/api/wifi"), ("POST", "/api/ddns-test"), ("POST", "/api/reboot")):
        status, data = request(port, method, path, {} if method == "POST" else None, code=None)
        assert status == 401, (path, status, data)
    assert request(port, "POST", "/api/code", {}, code="testcqde23")[0] == 200   # Groß/Klein egal
    assert request(port, "GET", f"/kistengeist.rdp?code={CODE}", code=None)[0] == 200


def test_setup_code_lockout(server):
    _srv, port, _tmp = server
    for _ in range(10):
        assert request(port, "POST", "/api/code", {}, code="FALSCHFALS")[0] == 401
    assert request(port, "POST", "/api/code", {}, code="FALSCHFALS")[0] == 429
    assert request(port, "POST", "/api/code", {})[0] == 429                    # auch der richtige, 10 Minuten


def test_setup_code_generated_and_from_boot(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv, "ETC", str(tmp_path / "etc"))
    monkeypatch.setattr(srv, "BOOT_CODE_FILE", str(tmp_path / "kistengeist-code.txt"))
    (tmp_path / "kistengeist-code.txt").write_text("k7m2q9xapr\n")
    assert srv.setup_code() == "K7M2Q9XAPR"
    assert oct((tmp_path / "etc" / "setup-code").stat().st_mode & 0o777) == "0o600"
    (tmp_path / "etc" / "setup-code").unlink()
    (tmp_path / "kistengeist-code.txt").write_text("zu-kurz")
    code = srv.setup_code()
    assert srv.CODE_RE.match(code) and code == srv.setup_code()
