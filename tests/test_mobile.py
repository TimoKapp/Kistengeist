import json

import kistengeist_mobile as mobile
import json_merge


def test_parse_auth_logged_in():
    st = mobile.parse_auth(0, json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "x@example.org"}))
    assert st.logged_in and st.account == "x@example.org" and "Angemeldet als" in st.text


def test_parse_auth_logged_out():
    st = mobile.parse_auth(1, json.dumps({"authMethod": "none"}))
    assert not st.logged_in and "nicht angemeldet" in st.text


def test_parse_auth_api_key_warns():
    st = mobile.parse_auth(0, json.dumps({"authMethod": "api_key"}))
    assert st.logged_in and "claude.ai-Abo" in st.text


def test_parse_auth_garbage():
    assert not mobile.parse_auth(1, "kein json").logged_in


def test_json_merge_keeps_user_values(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"model": "opus", "projects": {"/a": {"x": 1}}}))
    extra = {"remoteControlAtStartup": True, "projects": {"/b": {"hasTrustDialogAccepted": True}}}
    json_merge.merge_file(str(f), extra)
    data = json.loads(f.read_text())
    assert data["model"] == "opus" and data["remoteControlAtStartup"] is True
    assert data["projects"] == {"/a": {"x": 1}, "/b": {"hasTrustDialogAccepted": True}}


def test_json_merge_broken_file_backed_up(tmp_path):
    f = tmp_path / "s.json"
    f.write_text("{kaputt")
    json_merge.merge_file(str(f), {"a": 1})
    assert json.loads(f.read_text()) == {"a": 1}
    assert (tmp_path / "s.json.bak").read_text() == "{kaputt"


def test_strip_ansi():
    assert mobile.strip_ansi("\x1b[2K\x1b[1;32mbereit\x1b[0m\r\n") == "bereit\n"


def test_toggles_roundtrip(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"model": "opus", "remoteControlAtStartup": True}))
    assert mobile.read_toggles(str(f)) == {"remoteControlAtStartup": True, "agentPushNotifEnabled": False,
                                           "inputNeededNotifEnabled": False}
    mobile.set_toggle("agentPushNotifEnabled", True, str(f))
    data = json.loads(f.read_text())
    assert data["agentPushNotifEnabled"] is True and data["model"] == "opus"


def test_json_merge_private_mode(tmp_path):
    import os

    new = tmp_path / "neu.json"
    json_merge.merge_file(str(new), {"a": 1})
    assert oct(os.stat(new).st_mode & 0o777) == "0o600"
    old = tmp_path / "alt.json"
    old.write_text("{}")
    os.chmod(old, 0o640)
    json_merge.merge_file(str(old), {"a": 1})
    assert oct(os.stat(old).st_mode & 0o777) == "0o640"
