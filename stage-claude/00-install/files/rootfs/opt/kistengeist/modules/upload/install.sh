# shellcheck shell=bash
# Upload übers Netzwerk: Fenster mit QR-Code, kleiner Webserver (Port 8765)
# läuft nur, solange das Fenster offen ist.

cp_apt_install_nr python3-tk qrencode wmctrl

cp_write /opt/kistengeist/share/applications/kistengeist-upload.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Upload
Comment=Dateien vom PC oder Handy empfangen
Exec=/opt/kistengeist/bin/kistengeist-launch upload
Icon=document-send
Terminal=false
DESKTOP
