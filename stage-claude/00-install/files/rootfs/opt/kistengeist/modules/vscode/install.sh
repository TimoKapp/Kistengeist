# shellcheck shell=bash
# VS Code aus den Paketquellen (Raspberry Pi OS oder Microsoft) und die Erweiterungen
# für Claude Code (Anleitung: https://code.visualstudio.com/docs/setup/linux,
# https://code.claude.com/docs/en/vs-code).

EXTENSIONS="anthropic.claude-code MS-CEINTL.vscode-language-pack-de"
keyring=/usr/share/keyrings/microsoft.gpg
fingerprint=BC528686B50D79E339D3721CEB3E94ADBE1229CF

# Das Paket soll beim Installieren keine zweite Paketquelle anlegen.
if [ "$CP_DRY_RUN" = "1" ]; then
    cp_log "[dry-run] debconf: code code/add-microsoft-repo boolean false"
else
    echo "code code/add-microsoft-repo boolean false" | debconf-set-selections
fi

cp_apt_update
if ! cp_apt_available code || [ "$CP_DRY_RUN" = "1" ]; then
    # Nur eine Quelle für VS Code: eine schon vorhandene bleibt unangetastet,
    # sonst meldet apt widersprüchliche Signed-By-Angaben.
    if ! grep -rqs 'packages.microsoft.com/repos/code' "${CP_ROOT}/etc/apt/sources.list" \
        "${CP_ROOT}/etc/apt/sources.list.d/"; then
        cp_retry curl -fsSLo "${CP_ROOT}/tmp/microsoft.asc" https://packages.microsoft.com/keys/microsoft.asc
        keys="$(gpg --show-keys --with-colons "/tmp/microsoft.asc" 2>/dev/null || true)"
        if [ "$CP_DRY_RUN" != "1" ] && ! grep -q "^fpr:::::::::${fingerprint}:" <<<"$keys"; then
            rm -f /tmp/microsoft.asc
            cp_die "Signaturschlüssel von Microsoft hat nicht den erwarteten Fingerabdruck."
        fi
        cp_run gpg --batch --yes --dearmor -o "${CP_ROOT}${keyring}" "${CP_ROOT}/tmp/microsoft.asc"
        rm -f "${CP_ROOT}/tmp/microsoft.asc"
        cp_write /etc/apt/sources.list.d/vscode.sources <<SOURCES
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: arm64
Signed-By: ${keyring}
SOURCES
        cp_apt_update
    fi
fi
if ! cp_apt_install code; then
    # Eine unbrauchbare Fremdquelle darf nicht liegen bleiben (würde spätere Updates stören).
    rm -f "${CP_ROOT}/etc/apt/sources.list.d/vscode.sources"
    cp_die "VS Code konnte nicht installiert werden."
fi

for ext in $EXTENSIONS; do
    cp_retry runuser -u "$CP_USER" -- env HOME="$(cp_user_home)" code --install-extension "$ext" --force \
        || cp_warn "Erweiterung $ext konnte nicht installiert werden (später in VS Code nachholen)."
done

home="$(cp_user_home)"
# Deutsch und Schlüsselbund (wie Claude/Chrome) – sonst landen Anmeldungen im Klartext.
python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.vscode/argv.json" \
    '{"locale": "de", "password-store": "gnome-libsecret"}'
settings='{"update.mode": "none", "workbench.startupEditor": "none"}'
if [ "$(cp_setting PRIVACY_MINIMAL)" != "no" ]; then
    settings='{"update.mode": "none", "workbench.startupEditor": "none", "telemetry.telemetryLevel": "off"}'
    cp_log "Datensparsam: Telemetrie von VS Code abgeschaltet."
fi
python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.config/Code/User/settings.json" "$settings"
cp_run chown -R "$CP_USER:$CP_USER" "$home/.vscode" "$home/.config/Code"

icon=vscode
[ -f "${CP_ROOT}/usr/share/pixmaps/vscode.png" ] && icon=/usr/share/pixmaps/vscode.png
cp_write /opt/kistengeist/share/applications/kistengeist-vscode.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=VS Code
Comment=Visual Studio Code mit Claude Code im Ordner Projekte
Exec=/opt/kistengeist/bin/kistengeist-launch vscode
Icon=${icon}
Terminal=false
DESKTOP
