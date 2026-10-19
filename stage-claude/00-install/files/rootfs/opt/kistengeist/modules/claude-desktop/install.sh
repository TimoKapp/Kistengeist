# shellcheck shell=bash
# Claude Desktop aus dem offiziellen Anthropic-Paketarchiv
# (Anleitung: https://code.claude.com/docs/en/desktop-linux).

keyring=/usr/share/keyrings/claude-desktop-archive-keyring.asc
fingerprint=31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE

cp_retry curl -fsSLo "${CP_ROOT}${keyring}" https://downloads.claude.ai/claude-desktop/key.asc

if [ "$CP_DRY_RUN" != "1" ]; then
    keys="$(gpg --show-keys --with-colons "$keyring" 2>/dev/null || true)"
    if ! grep -q "^fpr:::::::::${fingerprint}:" <<<"$keys"; then
        rm -f "$keyring"
        cp_die "Signaturschlüssel von Anthropic hat nicht den erwarteten Fingerabdruck."
    fi
    cp_log "Signaturschlüssel geprüft ($fingerprint)."
fi

cp_write /etc/apt/sources.list.d/claude-desktop.list <<EOF
deb [arch=amd64,arm64 signed-by=${keyring}] https://downloads.claude.ai/claude-desktop/apt/stable stable main
EOF

cp_apt_update
# Ohne empfohlene Pakete: die schweren QEMU-Pakete für Cowork kommen nur mit dem Cowork-Modul.
cp_apt_install_nr claude-desktop

# Startsymbol für die Leiste mit dem Icon aus dem Paket anlegen.
icon="claude-desktop"
if [ "$CP_DRY_RUN" != "1" ]; then
    desktop_file="$(dpkg -L claude-desktop 2>/dev/null | grep '/applications/.*\.desktop$' | head -n 1 || true)"
    if [ -n "$desktop_file" ]; then
        found="$(sed -n 's/^Icon=//p' "$desktop_file" | head -n 1)"
        [ -n "$found" ] && icon="$found"
    fi
fi

# Zweites Startsymbol: Claude Code in der Oberfläche von Claude Desktop.
cp_write /opt/kistengeist/share/applications/kistengeist-code.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Code
Comment=Claude Code im Ordner Projekte
Exec=/opt/kistengeist/bin/kistengeist-launch code
Icon=utilities-terminal
Terminal=false
EOF

cp_write /opt/kistengeist/share/applications/kistengeist-claude.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Claude
Exec=/opt/kistengeist/bin/kistengeist-launch claude
Icon=${icon}
Terminal=false
EOF
