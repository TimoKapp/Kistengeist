# shellcheck shell=bash
# Handy-Steuerung wie in der Original-App (Remote Control von Claude Code):
#  - Dauerdienst "claude remote-control" (Server-Modus) im Ordner ~/Projekte: der Pi
#    erscheint in der Claude-App unter Code als Gerät, Sitzungen lassen sich vom Handy starten
#  - remoteControlAtStartup: Code-Sitzungen in Claude Desktop verbinden sich automatisch
#  - Push-Nachrichten aufs Handy (wenn Claude fertig ist oder eine Entscheidung braucht)

home="$(cp_user_home)"

cp_apt_install_nr lxterminal

# Einstellungen von Claude Code (bestehende Werte bleiben erhalten).
cp_run install -d -o "$CP_USER" -g "$CP_USER" -m 0700 "$home/.claude"
mkdir -p "$home/.claude"  # nur für den Probelauf nötig (dort ist cp_run ohne Wirkung)
python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.claude/settings.json" \
    '{"remoteControlAtStartup": true, "agentPushNotifEnabled": true, "inputNeededNotifEnabled": true}'
# Der Arbeitsordner gilt als vertrauenswürdig, damit der Dienst ohne Rückfrage startet.
python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.claude.json" \
    "{\"projects\": {\"${home#"$CP_ROOT"}/Projekte\": {\"hasTrustDialogAccepted\": true}}}"
cp_log "Claude-Code-Einstellungen für Remote Control und Push gesetzt."

# Benutzerdienst, global abgelegt und für den Sitzungsbenutzer aktiviert.
cp_write /etc/systemd/user/kistengeist-remote.service <<'UNIT'
[Unit]
Description=Kistengeist Handy-Steuerung (Claude Code Remote Control)

[Service]
Type=simple
WorkingDirectory=%h
ExecStart=/opt/kistengeist/bin/kistengeist-remote
Restart=always
RestartSec=30
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
UNIT
mkdir -p "$home/.config/systemd/user/default.target.wants"
ln -sf /etc/systemd/user/kistengeist-remote.service \
    "$home/.config/systemd/user/default.target.wants/kistengeist-remote.service"
cp_run chown -R "$CP_USER:$CP_USER" "$home/.claude" "$home/.claude.json" "$home/.config/systemd"

# Läuft auch ohne Anmeldung am Bildschirm (wichtig für "nur RDP" und Dauerbetrieb).
cp_run loginctl enable-linger "$CP_USER" || {
    mkdir -p "${CP_ROOT}/var/lib/systemd/linger"
    touch "${CP_ROOT}/var/lib/systemd/linger/${CP_USER}"
}

cp_write /opt/kistengeist/share/applications/kistengeist-mobile.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Handy
Comment=Claude vom Handy steuern (Remote Control und Dispatch)
Exec=/opt/kistengeist/bin/kistengeist-launch mobile
Icon=phone
Terminal=false
DESKTOP
