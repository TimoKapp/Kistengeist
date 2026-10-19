# shellcheck shell=bash
# Dateimanager und automatisches Einbinden von USB-Sticks.

cp_apt_install_nr pcmanfm udisks2 udiskie gvfs

# Erlaubt dem Sitzungsbenutzer das Ein- und Aushängen von USB-Sticks auch in
# RDP-Sitzungen (dort gilt die Sitzung für polkit nicht als "aktiv").
cp_write /etc/polkit-1/rules.d/50-kistengeist-udisks.rules <<RULES
polkit.addRule(function(action, subject) {
    var allowed = [
        "org.freedesktop.udisks2.filesystem-mount",
        "org.freedesktop.udisks2.filesystem-mount-other-seat",
        "org.freedesktop.udisks2.filesystem-unmount-others",
        "org.freedesktop.udisks2.eject-media",
        "org.freedesktop.udisks2.eject-media-other-seat",
        "org.freedesktop.udisks2.power-off-drive",
        "org.freedesktop.udisks2.power-off-drive-other-seat"
    ];
    if (allowed.indexOf(action.id) >= 0 && subject.user == "${CP_USER}") {
        return polkit.Result.YES;
    }
});
RULES

cp_write /opt/kistengeist/share/applications/kistengeist-files.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Dateien
Exec=/opt/kistengeist/bin/kistengeist-launch files
Icon=system-file-manager
Terminal=false
DESKTOP
