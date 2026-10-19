"""Terminal-Panel: Befehlsliste, tmux-Übergabe, MCP-Server und Fensteranordnung."""

import io
import json

import kistengeist_commands as commands
import kistengeist_panel as panel
import kistengeist_terminal as terminal
import kistengeist_terminal_mcp as mcp
import pytest
from conftest import CP_HOME

STANDARD = f"{CP_HOME}/share/commands/standard.json"


def test_standard_list_is_valid():
    entries = commands.load_standard(STANDARD)
    assert len(entries) >= 40
    cmds = [e["command"] for e in entries]
    assert len(cmds) == len(set(cmds))
    assert all(e["description"] for e in entries)
    for needed in ("/clear", "/compact", "/model", "/review", "/remote-control", "/mcp"):
        assert needed in cmds


def test_user_commands_add_replace_remove(tmp_path):
    path = str(tmp_path / "c.json")
    commands.add_user("git log --oneline", "Verlauf", "", path=path)
    commands.add_user("git log --oneline", "Verlauf kurz", "Git", path=path)
    entries = commands.load_user(path)
    assert entries == [{"command": "git log --oneline", "description": "Verlauf kurz",
                        "category": "Git", "source": "eigene"}]
    assert commands.remove_user("git log --oneline", path=path)
    assert not commands.remove_user("gibt es nicht", path=path)
    with pytest.raises(ValueError):
        commands.add_user("   ", path=path)


def test_broken_user_file_is_ignored(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{kaputt")
    assert commands.load_user(str(p)) == []


def test_scan_claude_commands_and_skills(tmp_path):
    cdir = tmp_path / ".claude" / "commands" / "git"
    cdir.mkdir(parents=True)
    (cdir / "push.md").write_text("---\ndescription: Änderungen pushen\n---\nMach es\n")
    (tmp_path / ".claude" / "commands" / "notiz.md").write_text("# Notiz anlegen\nText\n")
    sdir = tmp_path / ".claude" / "skills" / "bericht"
    sdir.mkdir(parents=True)
    (sdir / "SKILL.md").write_text("---\nname: bericht\ndescription: \"Bericht schreiben\"\n---\n")
    found = {e["command"]: e for e in commands.scan_claude(str(tmp_path))}
    assert found["/git:push"]["description"] == "Änderungen pushen"
    assert found["/notiz"]["description"] == "Notiz anlegen"
    assert found["/bericht"]["category"] == "Skills"


def test_all_commands_user_overrides_and_search(tmp_path):
    commands.add_user("/clear", "Mein Text", "Eigene", path=commands.user_file(str(tmp_path)))
    entries = commands.all_commands(str(tmp_path), STANDARD)
    clear = [e for e in entries if e["command"] == "/clear"]
    assert len(clear) == 1 and clear[0]["source"] == "eigene"
    assert [e["command"] for e in commands.search(entries, "kontext voll")] == ["/context"]
    assert all(e["category"] == "Code prüfen" for e in commands.search(entries, "", "Code prüfen"))


class FakeRun:
    def __init__(self, has_session=True, foreground=b"2.1.290\n"):
        self.calls = []
        self.has_session = has_session
        self.fg = foreground

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw.get("input")))

        class R:
            returncode = 0
            stdout = b""
        if "has-session" in cmd:
            R.returncode = 0 if self.has_session else 1
        if "new-session" in cmd:
            self.has_session = True
        if "display-message" in cmd:
            R.stdout = self.fg
        return R


def no_sleep(_s):
    pass


def test_clean_text_strips_escape_sequences():
    assert terminal.clean_text("a\x1b[201~b\r\nc\td\x07") == "a[201~b\nc\td"


def test_send_text_uses_bracketed_paste(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    run = FakeRun()
    msg = terminal.send_text("Hallo\nWelt", submit=False, run=run, sleep=no_sleep)
    assert "nicht abgeschickt" in msg
    cmds = [c for c, _ in run.calls]
    assert all(c[:3] == ["tmux", "-L", "kistengeist"] for c in cmds)
    load = next((c, i) for c, i in run.calls if "load-buffer" in c)
    assert load[1] == b"Hallo\nWelt"
    paste = next(c for c in cmds if "paste-buffer" in c)
    assert "-p" in paste and "=kistengeist:" in paste
    assert not any("send-keys" in c for c in cmds)


def test_send_text_submit_and_new_session(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "kistengeist").mkdir(parents=True)
    (tmp_path / ".config" / "kistengeist" / "display.env").write_text("DISPLAY=:0\nLANG=de_DE.UTF-8\n")
    run = FakeRun(has_session=False)
    terminal.send_text("/clear", submit=True, run=run, sleep=no_sleep)
    cmds = [c for c, _ in run.calls]
    new = next(c for c in cmds if "new-session" in c)
    assert "DISPLAY=:0" in new and "LANG=de_DE.UTF-8" in new and "KISTENGEIST_TERMINAL=1" in new
    assert cmds[-1][-1] == "Enter"
    with pytest.raises(ValueError):
        terminal.send_text("\x1b\x07  ", run=run)


def test_no_submit_into_plain_shell(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    run = FakeRun(foreground=b"bash\n")
    with pytest.raises(ValueError):
        terminal.send_text("!rm -rf x", submit=True, run=run, sleep=no_sleep)
    assert not any("paste-buffer" in c for c, _ in run.calls)
    assert "Shell" in terminal.send_text("ls", run=run, sleep=no_sleep)


def test_new_session_waits_until_claude_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    run = FakeRun(has_session=False, foreground=b"bash\n")
    with pytest.raises(ValueError, match="nicht bereit"):
        terminal.send_text("x", run=run, sleep=no_sleep)


def rpc(lines):
    out = io.StringIO()
    mcp.serve(io.StringIO("\n".join(json.dumps(m) for m in lines) + "\n"), out)
    return [json.loads(x) for x in out.getvalue().splitlines()]


def test_mcp_initialize_list_and_unknown():
    replies = rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "gibtsnicht"},
    ])
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert {t["name"] for t in replies[1]["result"]["tools"]} == {"send_to_terminal", "list_commands", "add_command"}
    assert replies[2]["error"]["code"] == -32601


def test_mcp_send_calls_terminal(monkeypatch):
    sent = []
    monkeypatch.setattr(mcp.terminal, "send_text", lambda t, submit: sent.append((t, submit)) or "ok")
    monkeypatch.setattr(mcp.terminal, "show_panel", lambda: None)
    monkeypatch.delenv("TMUX", raising=False)
    r = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "send_to_terminal", "arguments": {"text": "/review", "submit": True}}}])[0]
    assert sent == [("/review", False)] and r["result"]["isError"] is False


def test_mcp_refuses_sending_to_itself(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/kistengeist,123,0")
    monkeypatch.delenv("KISTENGEIST_TERMINAL", raising=False)
    r = rpc([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "send_to_terminal", "arguments": {"text": "x"}}}])[0]
    assert r["result"]["isError"] is True


def test_mcp_survives_bad_input(monkeypatch):
    monkeypatch.delenv("KISTENGEIST_TERMINAL", raising=False)
    replies = rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": []},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "gibtsnicht"}},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    ])
    assert replies[0]["error"]["code"] == -32602
    assert replies[1]["error"]["code"] == -32602
    assert replies[2]["result"] == {}


def test_trailing_space_kept_and_hidden_skills(tmp_path):
    entry = commands.add_user("/rename ", "Umbenennen", path=str(tmp_path / "c.json"))
    assert entry["command"] == "/rename "
    sdir = tmp_path / ".claude" / "skills" / "intern"
    sdir.mkdir(parents=True)
    (sdir / "SKILL.md").write_text("---\nname: intern\nuser-invocable: false\n---\n")
    assert commands.scan_claude(str(tmp_path)) == []


def test_mcp_add_and_list(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(commands, "STANDARD_FILE", STANDARD)
    monkeypatch.setattr(commands.all_commands, "__defaults__", (None, STANDARD))
    replies = rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "add_command", "arguments": {"command": "!htop", "description": "Prozesse"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "list_commands", "arguments": {"query": "prozesse"}}},
    ])
    assert "!htop" in replies[1]["result"]["content"][0]["text"]


def test_panel_layout_and_parsing(tmp_path):
    wa = panel.parse_workarea("0  * DG: 1920x1080  VP: 0,0  WA: 0,0 1920x1036  N/A\n")
    assert wa == (0, 0, 1920, 1036)
    split = panel.layout("geteilt", wa)
    assert split["claude"][2] + split["term"][2] == 1920
    assert split["term"][3] + split["liste"][3] == 1036
    bottom = panel.layout("unten", wa)
    assert "claude" not in bottom and bottom["term"][1] + bottom["term"][3] == 1036
    wins = panel.parse_windows(
        "0x01  0 claude.Claude  pi  Claude\n"
        "0x02  0 kistengeist-term.Kistengeist-term  pi  Claude Code\n"
        "0x03  0 kistengeist-panel.Kistengeist-panel  pi  Befehle\n"
        "0x04  0 code.Code  pi  VS Code\n")
    assert panel.find_claude(wins) == ["0x01"]
    assert panel.find(wins, panel.TERM_CLASS) == ["0x02"]
    cfg = str(tmp_path / "p.json")
    assert panel.read_mode(cfg) == "geteilt"
    panel.save_mode("unten", cfg)
    assert panel.read_mode(cfg) == "unten"
