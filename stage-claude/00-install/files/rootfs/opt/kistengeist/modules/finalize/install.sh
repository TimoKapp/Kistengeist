# shellcheck shell=bash
# Abschluss: Einrichtungsmodus beenden, Standardziel setzen.

if cp_mode_has_local; then
    cp_run systemctl set-default graphical.target
else
    cp_run systemctl set-default multi-user.target
fi

# Setup-Dienste beim nächsten Start nicht mehr ausführen (sie prüfen zusätzlich
# auf /etc/kistengeist/installed).
cp_disable kistengeist-setup.service kistengeist-console.service kistengeist-hotspot.service || true

# Einrichtungs-WLAN (festes Passwort) dauerhaft entfernen.
cp_run nmcli connection delete kistengeist-setup || true
rm -f "${CP_ROOT}/run/kistengeist/hotspot"

version="$(cat "${CP_ROOT}/opt/kistengeist/VERSION" 2>/dev/null || echo unbekannt)"
printf 'INSTALLED_AT=%s\nVERSION=%s\n' "$(date -Iseconds)" "$version" \
    | cp_write /etc/kistengeist/installed
