import http.client
import os
import threading
from urllib.parse import quote

import pytest

import kistengeist_links as links
import kistengeist_upload as up


@pytest.mark.parametrize("raw,expected", [
    ("foto.jpg", "foto.jpg"),
    ("../../etc/passwd", "passwd"),
    ("C:\\Users\\x\\bericht.pdf", "bericht.pdf"),
    (".bashrc", "bashrc"),
    ("..", "datei"),
    ("", "datei"),
    ("a\x00b\nc.txt", "abc.txt"),
    ('wei<rd>:na|me?.txt', "weirdname.txt"),
])
def test_sanitize(raw, expected):
    assert up.sanitize_name(raw) == expected


def test_sanitize_long_name_keeps_extension():
    name = up.sanitize_name("x" * 400 + ".pdf")
    assert name.endswith(".pdf") and len(name.encode()) <= up.MAX_NAME


def test_unique_path(tmp_path):
    (tmp_path / "a.txt").write_text("1")
    (tmp_path / "a (2).txt").write_text("2")
    assert up.unique_path(str(tmp_path), "a.txt").endswith("a (3).txt")
    assert up.unique_path(str(tmp_path), "neu").endswith("neu")


@pytest.fixture()
def server(tmp_path):
    received, sent = [], []
    srv = up.UploadServer(str(tmp_path / "Uploads"), port=0, host="127.0.0.1",
                          on_file=received.append, on_send=sent.append)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, received, sent
    srv.shutdown()
    srv.server_close()


def put(srv, body, name="test.txt", token=None, send=False, length=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    headers = {"X-Upload-Token": srv.token if token is None else token,
               "X-File-Name": quote(name), "X-Send-To-Claude": "1" if send else "0",
               "Content-Length": str(len(body) if length is None else length)}
    conn.request("PUT", "/upload", body=body, headers=headers)
    res = conn.getresponse()
    return res.status, res.read().decode()


def test_upload_stores_file(server):
    srv, received, sent = server
    status, body = put(srv, b"hallo welt", name="Notiz ä.txt", send=True)
    assert status == 200, body
    path = os.path.join(srv.directory, "Notiz ä.txt")
    assert open(path, "rb").read() == b"hallo welt"
    assert received == [path] and sent == [path]
    assert not any(n.endswith(".part") for n in os.listdir(srv.directory))


def test_wrong_token_rejected(server):
    srv, received, _ = server
    status, _ = put(srv, b"x", token="falsch")
    assert status == 403 and received == []
    status, _ = put(srv, b"x", token="")
    assert status == 403


def test_traversal_name_stays_in_folder(server):
    srv, _, _ = server
    status, _ = put(srv, b"x", name="../../boese.sh")
    assert status == 200
    assert os.listdir(srv.directory) == ["boese.sh"]


def test_duplicate_names(server):
    srv, _, _ = server
    put(srv, b"1", name="a.txt")
    put(srv, b"2", name="a.txt")
    assert sorted(os.listdir(srv.directory)) == ["a (2).txt", "a.txt"]


def test_too_large_rejected(server):
    srv, _, _ = server
    status, body = put(srv, b"", length=up.MAX_FILE + 1)
    assert status == 413 and "groß" in body


def test_page_needs_token(server):
    srv, _, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    conn.request("GET", "/")
    assert conn.getresponse().status == 403
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    conn.request("GET", "/?t=" + srv.token)
    res = conn.getresponse()
    assert res.status == 200 and "An Kistengeist senden" in res.read().decode()


def test_expired_access(server):
    srv, _, _ = server
    srv.idle_timeout = -1
    status, _ = put(srv, b"x")
    assert status == 410


def test_links():
    assert links.code_link("/home/claude/Projekte") == "claude://code/new?folder=%2Fhome%2Fclaude%2FProjekte"
    url = links.code_link("/home/claude/Uploads", "Sieh dir @a b.pdf an")
    assert url.startswith("claude://code/new?folder=") and "&q=Sieh%20dir%20%40a%20b.pdf%20an" in url
    assert links.cowork_link(["/a/x.pdf", "/a/y.png"]).count("file=") == 2
    assert links.chat_link() == "claude://claude.ai/new"
    with pytest.raises(ValueError):
        links.code_link("relativ/pfad")


def test_stale_part_files_removed(tmp_path):
    d = tmp_path / "Uploads"
    d.mkdir()
    (d / ".upload-abc.part").write_text("rest")
    (d / "behalten.txt").write_text("x")
    srv = up.UploadServer(str(d), port=0, host="127.0.0.1")
    srv.server_close()
    assert os.listdir(d) == ["behalten.txt"]


def test_same_name_parallel_does_not_collide(server):
    srv, _, _ = server
    results = []
    threads = [threading.Thread(target=lambda: results.append(put(srv, b"x" * 200_000, name="IMG.jpg")[0]))
               for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * 4
    assert sorted(os.listdir(srv.directory)) == ["IMG (2).jpg", "IMG (3).jpg", "IMG (4).jpg", "IMG.jpg"]


def test_info_endpoint(server):
    import json

    srv, _, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    conn.request("GET", "/api/info", headers={"X-Upload-Token": srv.token})
    data = json.loads(conn.getresponse().read())
    assert data["ok"] and data["max_file"] == up.MAX_FILE and data["free"] >= 0


def test_write_error_returns_507(server, monkeypatch):
    srv, _, _ = server

    def broken(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(up.tempfile, "mkstemp", broken)
    status, body = put(srv, b"x")
    assert status == 507 and "Speicher" in body
    assert srv.reserved == 0


def test_send_error_does_not_break_upload(tmp_path):
    def boom(_path):
        raise FileNotFoundError("claude-desktop fehlt")

    srv = up.UploadServer(str(tmp_path / "U"), port=0, host="127.0.0.1", on_send=boom)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, _ = put(srv, b"x", send=True)
        assert status == 200
    finally:
        srv.shutdown()
        srv.server_close()


def test_renew_changes_token(server):
    srv, _, _ = server
    old = srv.token
    srv.idle_timeout = -1
    assert srv.expired()
    srv.idle_timeout = 60
    srv.renew()
    assert srv.token != old and not srv.expired()
    assert put(srv, b"x", token=old)[0] == 403
