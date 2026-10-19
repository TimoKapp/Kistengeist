# shellcheck shell=bash
# Energiesparen: Die Sitzung schaltet den Bildschirm nach 10 Minuten ab
# (siehe kistengeist-autostart, liest SCREEN_OFF_SECONDS).

printf 'SCREEN_OFF_SECONDS=600\n' | cp_write /etc/kistengeist/energy.conf
