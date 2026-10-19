# shellcheck shell=bash
# Zugangsdaten und Ports in ~/Zugangsdaten.txt (0600), optional Kopie auf den USB-Stick.
# Geheimnisse liegen nur im RAM (/run/kistengeist) und werden danach gelöscht.

home="$(cp_user_home)"
out="$home/Zugangsdaten.txt"
usb_args=()
if [ "$(cp_setting ACCESS_FILE_USB)" = "yes" ] && cp_module_selected usb-stick; then
    ls /mnt/usb-stick >/dev/null 2>&1 || true
    if [ "$CP_DRY_RUN" = "1" ] || mountpoint -q /mnt/usb-stick; then
        mkdir -p "${CP_ROOT}/mnt/usb-stick"
        usb_args=(--usb "${CP_ROOT}/mnt/usb-stick")
    else
        cp_warn "USB-Stick nicht eingehängt – keine Kopie der Zugangsdaten auf dem Stick."
    fi
fi
CP_ROOT="$CP_ROOT" python3 "${CP_HOME_DIR}/lib/kistengeist_access.py" write --out "$out" "${usb_args[@]}" \
    --rdp-out "$home/Kistengeist.rdp" \
    || cp_die "Zugangsdaten-Datei konnte nicht geschrieben werden."
cp_run chown "$CP_USER:$CP_USER" "$out"
[ -f "$home/Kistengeist.rdp" ] && cp_run chown "$CP_USER:$CP_USER" "$home/Kistengeist.rdp"
cp_log "Zugangsdaten und Ports: $out${usb_args[1]:+ (Kopie auf dem USB-Stick)}"
rm -f "${CP_ROOT}/run/kistengeist/account.secret" "${CP_ROOT}/run/kistengeist/n8n.json" "${CP_ROOT}/run/kistengeist/browser.secret"
