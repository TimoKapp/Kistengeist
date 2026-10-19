# shellcheck shell=bash
# Speicherkarte schonen: Protokolle begrenzen, Auslagerung in komprimiertem RAM.

cp_write /etc/systemd/journald.conf.d/50-kistengeist.conf <<'CONF'
[Journal]
SystemMaxUse=64M
RuntimeMaxUse=32M
MaxRetentionSec=2week
CONF

# Raspberry Pi OS (Trixie) bringt eigenes zram mit (rpi-swap). Nur wenn kein
# zram-Swap aktiv ist, wird zram-tools ergänzt; ein Swap-File wird abgeschaltet.
if [ "$CP_DRY_RUN" = "1" ] || ! grep -q '^/dev/zram' /proc/swaps 2>/dev/null; then
    if [ "$CP_DRY_RUN" = "1" ] || ! dpkg -s rpi-swap >/dev/null 2>&1; then
        cp_apt_install_nr zram-tools
        cp_write /etc/default/zramswap <<'CONF'
ALGO=zstd
PERCENT=50
PRIORITY=100
CONF
        cp_enable zramswap.service
        if [ "$CP_DRY_RUN" = "1" ] || dpkg -s dphys-swapfile >/dev/null 2>&1; then
            cp_disable dphys-swapfile.service || true
        fi
    fi
fi
