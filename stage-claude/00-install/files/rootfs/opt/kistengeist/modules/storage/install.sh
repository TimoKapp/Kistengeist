# shellcheck shell=bash
# Speicherverwaltung: App, Warnung bei vollem Speicher, Aufräum-Helfer.

cp_apt_install_nr python3-tk udisks2

# Der Helfer darf nur fest definierte Aufräumaktionen als root ausführen.
cp_write /etc/sudoers.d/kistengeist-storage 0440 <<SUDO
${CP_USER} ALL=(root) NOPASSWD: /opt/kistengeist/bin/kistengeist-storage-helper
SUDO
if [ "$CP_DRY_RUN" != "1" ]; then
    visudo -cf /etc/sudoers.d/kistengeist-storage >/dev/null || {
        rm -f /etc/sudoers.d/kistengeist-storage
        cp_die "sudoers-Datei ungültig."
    }
fi

cp_write /opt/kistengeist/share/applications/kistengeist-storage.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Speicher
Exec=/opt/kistengeist/bin/kistengeist-launch storage
Icon=drive-harddisk
Terminal=false
DESKTOP
