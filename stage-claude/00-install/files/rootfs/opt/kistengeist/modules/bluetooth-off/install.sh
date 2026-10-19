# shellcheck shell=bash
# Bluetooth per Device-Tree abschalten (wirkt nach dem Neustart).

config="${CP_ROOT}/boot/firmware/config.txt"
if [ -f "$config" ]; then
    if ! grep -q '^dtoverlay=disable-bt' "$config"; then
        printf '\n[all]\n# Kistengeist: Bluetooth aus\ndtoverlay=disable-bt\n' >>"$config"
        cp_log "Bluetooth in config.txt abgeschaltet."
    fi
else
    cp_warn "config.txt nicht gefunden – Bluetooth bleibt an."
fi
cp_disable hciuart.service bluetooth.service || true
