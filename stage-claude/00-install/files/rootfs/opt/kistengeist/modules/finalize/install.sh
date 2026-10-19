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

# Einrichtungs-WLAN dauerhaft entfernen.
cp_run nmcli connection delete kistengeist-setup || true
rm -f "${CP_ROOT}/run/kistengeist/hotspot"

# Einrichtungsgeheimnisse entfernen: Code (der laufende Assistent kennt ihn bis zum Neustart) und –
# beim Windows-Werkzeug – Code und WLAN-Passwort auf der Boot-Partition, die jeder an jedem PC lesen
# kann. Vorher cloud-init abschalten, damit die geschwärzten Dateien nie wieder angewendet werden;
# das WLAN läuft über die von cloud-init angelegte Netplan-Datei weiter.
rm -f "${CP_ROOT}/etc/kistengeist/setup-code" "${CP_ROOT}/etc/kistengeist/setup-code.lock" \
    "${CP_ROOT}/boot/firmware/kistengeist-code.txt"
fw="${CP_ROOT}/boot/firmware"
if [ -f "$fw/user-data" ] && grep -q 'kistengeist-firstboot' "$fw/user-data"; then
    mkdir -p "${CP_ROOT}/etc/cloud"
    touch "${CP_ROOT}/etc/cloud/cloud-init.disabled"
    sed -i -E '/^ *- path: \/etc\/kistengeist\/setup-code/,/^ *- path:/{/^ +[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{10} *$/d}' \
        "$fw/user-data"
    if [ -f "$fw/network-config" ]; then
        if grep -rqs 'access-points' "${CP_ROOT}/etc/netplan/" || ! grep -q 'access-points' "$fw/network-config"; then
            sed -i -E 's/^( *password:).*/\1 "entfernt"/' "$fw/network-config"
        else
            cp_warn "WLAN-Daten bleiben auf der Boot-Partition (keine Netplan-Kopie gefunden)."
        fi
    fi
    cp_log "Einrichtungscode und WLAN-Passwort von der Boot-Partition entfernt."
fi

version="$(cat "${CP_ROOT}/opt/kistengeist/VERSION" 2>/dev/null || echo unbekannt)"
printf 'INSTALLED_AT=%s\nVERSION=%s\n' "$(date -Iseconds)" "$version" \
    | cp_write /etc/kistengeist/installed
