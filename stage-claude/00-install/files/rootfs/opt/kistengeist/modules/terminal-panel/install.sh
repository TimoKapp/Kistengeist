# shellcheck shell=bash
# Terminal-Panel: tmux-Sitzung „kistengeist“ mit Claude Code, Befehlsliste (Tk) und lokaler
# MCP-Server, über den Claude Desktop Text ans Terminal übergibt.

cp_apt_install_nr tmux xterm xclip wmctrl python3-tk

cp_write /opt/kistengeist/share/applications/kistengeist-terminal.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Terminal
Comment=Claude Code im Terminal ein- oder ausblenden, mit Befehlsliste
Exec=/opt/kistengeist/bin/kistengeist-launch terminal
Icon=/opt/kistengeist/share/icons/kistengeist-terminal.svg
Terminal=false
DESKTOP

# MCP-Server anmelden: Chat von Claude Desktop (claude_desktop_config.json) sowie
# Code-Bereich und CLI (~/.claude.json, Benutzerebene). Im Panel-Terminal selbst sperrt
# der Server das Senden an sich selbst.
home="$(cp_user_home)"
server='{"command": "python3", "args": ["/opt/kistengeist/lib/kistengeist_terminal_mcp.py"]}'
mkdir -p "$home/.config/Claude"
python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.config/Claude/claude_desktop_config.json" \
    "{\"mcpServers\": {\"kistengeist-terminal\": ${server}}}"
python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.claude.json" \
    "{\"mcpServers\": {\"kistengeist-terminal\": {\"type\": \"stdio\", ${server:1}}}"
cp_run chown -R "$CP_USER:$CP_USER" "$home/.config/Claude"
cp_run chown "$CP_USER:$CP_USER" "$home/.claude.json"
cp_log "MCP-Server kistengeist-terminal für Claude Desktop und Claude Code angemeldet."
