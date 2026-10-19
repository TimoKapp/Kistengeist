# shellcheck shell=bash
# Firewall (ufw). Regeln werden jetzt gesetzt, aktiv ab dem Neustart – so
# bleibt der Setup-Assistent bis zum Ende erreichbar.

cp_apt_install_nr ufw

cp_run ufw --force reset
cp_run ufw default deny incoming
cp_run ufw default allow outgoing
cp_run ufw allow 5353/udp comment 'mDNS (kistengeist.local)'
if cp_mode_has_rdp && [ "$(cp_setting REMOTE)" = "browser" ]; then
    # Desktop im Browser nur aus dem Heimnetz.
    for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7 fe80::/10; do
        cp_run ufw allow from "$net" to any port 8443 proto tcp comment 'Desktop im Browser (nur Heimnetz)'
    done
elif cp_mode_has_rdp; then
    # RDP nur aus dem Heimnetz (von außen: VPN, z. B. Tailscale).
    for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7 fe80::/10; do
        cp_run ufw allow from "$net" to any port 3389 proto tcp comment 'RDP (nur Heimnetz)'
    done
fi
if cp_module_selected upload; then
    # Nur offen, solange am Pi das Upload-Fenster läuft (sonst lauscht dort niemand).
    for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
        cp_run ufw allow from "$net" to any port 8765 proto tcp comment 'Kistengeist Upload (nur Heimnetz)'
    done
fi
if cp_module_selected webserver; then
    for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7 fe80::/10; do
        cp_run ufw allow from "$net" to any port 8080 proto tcp comment 'Kistengeist Startseite (nur Heimnetz)'
    done
    if [ "$(cp_setting NET_ACCESS)" = "dyndns" ]; then
        # Öffentlich: Caddy holt damit das HTTPS-Zertifikat und liefert die Seite aus.
        cp_run ufw allow 80/tcp comment 'Webserver HTTP (Zertifikat, Umleitung)'
        cp_run ufw allow 443/tcp comment 'Webserver HTTPS'
    fi
fi
if cp_module_selected n8n && [ "$(cp_setting NET_ACCESS)" = "lan" ]; then
    # IPv4 veröffentlicht Docker an ufw vorbei (dafür sorgt kistengeist-n8n firewall);
    # IPv6 läuft über docker-proxy und damit durch ufw.
    for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7 fe80::/10; do
        cp_run ufw allow from "$net" to any port 5678 proto tcp comment 'n8n (nur Heimnetz)'
    done
fi
# SSH nur aus dem Heimnetz – auch, wenn per SSH installiert wurde (install.sh legt keep-ssh an),
# damit sich niemand mit der Einrichtung selbst aussperrt.
if cp_module_selected ssh || [ -e "${CP_ROOT}/etc/kistengeist/keep-ssh" ]; then
    for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 fc00::/7 fe80::/10; do
        cp_run ufw allow from "$net" to any port 22 proto tcp comment 'SSH (nur Heimnetz)'
    done
fi

conf="${CP_ROOT}/etc/ufw/ufw.conf"
if [ -f "$conf" ]; then
    sed -i 's/^ENABLED=.*/ENABLED=yes/' "$conf"
else
    printf 'ENABLED=yes\n' | cp_write /etc/ufw/ufw.conf
fi
cp_enable ufw.service
