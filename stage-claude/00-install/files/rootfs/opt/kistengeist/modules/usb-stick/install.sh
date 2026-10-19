# shellcheck shell=bash
# USB-Stick als Datenspeicher: optional mit exFAT formatieren (MBR, Typ 0x07 – lesbar unter
# Windows/macOS), per UUID in /etc/fstab eintragen, Ordner ~/USB-Stick verlinken.

# sfdisk steckt in Debian 13 im eigenen Paket fdisk (vom CI-Paketcheck gefunden).
cp_apt_install_nr exfatprogs ntfs-3g parted fdisk util-linux udev

stick="$(cp_setting USB_DEVICE)"
label="$(cp_setting USB_LABEL)"
label="${label:-KISTENGEIST}"
mnt=/mnt/usb-stick
home="$(cp_user_home)"

if [ -z "$stick" ]; then
    cp_warn "Kein USB-Stick gewählt – Modul übersprungen (später: Einrichtung wiederholen)."
    return 0
fi

if [ "$CP_DRY_RUN" = "1" ]; then
    dev=/dev/sdx
    part=/dev/sdx1
    cp_log "[dry-run] USB-Stick $stick → $dev"
else
    # Unmittelbar vor dem Zugriff erneut prüfen: USB-Bus, nicht das Systemlaufwerk.
    dev="$(python3 "${CP_HOME_DIR}/lib/kistengeist_usb.py" check "$stick")" \
        || cp_die "USB-Stick nicht gefunden oder nicht zulässig: $stick"
fi

if [ "$(cp_setting USB_FORMAT)" = "yes" ]; then
    cp_log "Formatiere $dev mit exFAT (Bezeichnung $label) – alle Daten auf dem Stick werden gelöscht."
    if [ "$CP_DRY_RUN" != "1" ]; then
        # Eingehängte Partitionen (z. B. von udisks oder einem früheren Lauf) zuerst lösen.
        systemctl stop 'mnt-usb\x2dstick.automount' 'mnt-usb\x2dstick.mount' 2>/dev/null || true
        for p in $(lsblk -nrpo NAME "$dev" | tail -n +2); do
            umount "$p" 2>/dev/null || true
        done
    fi
    cp_run wipefs -a "$dev"
    # Eine Partition über den ganzen Stick, MBR-Typ 07 (exFAT/NTFS) für Windows.
    if [ "$CP_DRY_RUN" = "1" ]; then
        cp_log "[dry-run] sfdisk $dev (label: dos, type=7)"
    else
        printf 'label: dos\ntype=7\n' | sfdisk --wipe always --wipe-partitions always "$dev" >>"$CP_LOG" 2>&1 \
            || cp_die "Partitionieren von $dev fehlgeschlagen."
        cp_run partprobe "$dev" || true
        cp_run udevadm settle
        part="$(lsblk -nrpo NAME,TYPE "$dev" | awk '$2 == "part" {print $1; exit}')"
        [ -n "$part" ] || cp_die "Neue Partition auf $dev nicht gefunden."
    fi
    cp_run mkfs.exfat -L "$label" "$part" || cp_die "Formatieren fehlgeschlagen."
    cp_run udevadm settle || true
    # Nur einmal formatieren: ein erneuter Installer-Lauf darf den Stick (mit Sicherungen) nicht löschen.
    sed -i 's/^USB_FORMAT=.*/USB_FORMAT="no"/' "${CP_ETC}/setup.conf"
elif [ "$CP_DRY_RUN" != "1" ]; then
    # Vorhandenes Dateisystem verwenden: erste Partition mit bekanntem Typ (oder der ganze Stick).
    part="$(lsblk -nrpo NAME,FSTYPE "$dev" | awk '$2 ~ /^(exfat|vfat|ntfs|ext4)$/ {print $1; exit}')"
    [ -n "$part" ] || cp_die "Auf dem Stick ist kein nutzbares Dateisystem – bitte formatieren lassen."
fi

if [ "$CP_DRY_RUN" = "1" ]; then
    uuid=DRYRUN-UUID
    fstype=exfat
else
    # blkid endet mit Code 2, wenn es nichts findet – dann soll die klare Meldung kommen.
    uuid="$(blkid -s UUID -o value "$part" || true)"
    fstype="$(blkid -s TYPE -o value "$part" || true)"
    [ -n "$uuid" ] || cp_die "Keine UUID für $part."
fi

uid="$(id -u "$CP_USER" 2>/dev/null || echo 1000)"
gid="$(id -g "$CP_USER" 2>/dev/null || echo 1000)"
# nofail + automount: der Pi startet auch ohne Stick; der Stick wird beim ersten Zugriff eingehängt.
common="nofail,x-systemd.automount,x-systemd.device-timeout=10s,noatime"
case "$fstype" in
    exfat | vfat) opts="${common},uid=${uid},gid=${gid},umask=0022" ;;
    ntfs) fstype=ntfs3; opts="${common},uid=${uid},gid=${gid},umask=0022" ;;
    *) opts="$common" ;;
esac

fstab="${CP_ROOT}/etc/fstab"
touch "$fstab"
sed -i '/# kistengeist usb-stick$/d' "$fstab"
printf 'UUID=%s %s %s %s 0 0 # kistengeist usb-stick\n' "$uuid" "$mnt" "$fstype" "$opts" >>"$fstab"
cp_log "fstab: UUID=$uuid → $mnt ($fstype)"
mkdir -p "${CP_ROOT}${mnt}"
printf 'MOUNT=%s\nUUID=%s\nFSTYPE=%s\nLABEL=%s\n' "$mnt" "$uuid" "$fstype" "$label" \
    | cp_write /etc/kistengeist/usb.conf

cp_run systemctl daemon-reload
cp_run mount "$mnt" || cp_warn "Stick konnte gerade nicht eingehängt werden – nach dem Neustart erneut."
if [ "$CP_DRY_RUN" = "1" ] || mountpoint -q "$mnt"; then
    for d in Austausch Sicherungen; do
        cp_run mkdir -p "${CP_ROOT}${mnt}/$d"
    done
    if [ "$fstype" = "ext4" ]; then
        cp_run chown "$CP_USER:$CP_USER" "${CP_ROOT}${mnt}" "${CP_ROOT}${mnt}/Austausch" "${CP_ROOT}${mnt}/Sicherungen"
    fi
fi
mkdir -p "$home"
ln -sfn "$mnt" "$home/USB-Stick"
cp_run chown -h "$CP_USER:$CP_USER" "$home/USB-Stick"
