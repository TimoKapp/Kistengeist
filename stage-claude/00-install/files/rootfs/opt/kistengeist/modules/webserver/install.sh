# shellcheck shell=bash
# Webserver Caddy (Debian-Paket) mit Startseite im Heimnetz (Port 8080) und – je nach Wahl –
# Internet-Zugang: eigene DynDNS-Adresse (ipv64, dynv6, No-IP oder DuckDNS) + automatisches HTTPS
# (Ports 80/443 am Router freigeben) oder Tailscale Funnel (kein Router nötig).
# Anleitung: https://caddyserver.com/docs/automatic-https, lib/kistengeist_ddns.py,
# https://tailscale.com/kb/1223/funnel

net="$(cp_setting NET_ACCESS)"
net="${net:-lan}"
domain="$(cp_setting DDNS_HOST)"
email="$(cp_setting ACME_EMAIL)"
with_n8n=no
cp_module_selected n8n && with_n8n=yes

# Während der Einrichtung belegt der Assistent Port 80: Caddy erst nach dem Neustart starten –
# und nur, wenn die Installation fertig ist (sonst stritte Caddy nach einem Abbruch mit dem
# Assistenten um Port 80).
cp_run systemctl mask caddy.service
cp_apt_install_nr caddy curl
cp_run systemctl unmask caddy.service
cp_write /etc/systemd/system/caddy.service.d/kistengeist.conf <<'UNIT'
[Unit]
ConditionPathExists=/etc/kistengeist/installed
UNIT
cp_run systemctl daemon-reload
cp_enable caddy.service

public_url=""
case "$net" in
    dyndns)
        [ -n "$domain" ] || cp_die "DynDNS gewählt, aber keine Adresse angegeben."
        public_url="https://${domain}"
        ;;
    tailscale)
        # Offizielle Paketquelle von Tailscale (https://tailscale.com/download/linux/debian-trixie).
        cp_retry curl -fsSLo "${CP_ROOT}/usr/share/keyrings/tailscale-archive-keyring.gpg" \
            https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg
        cp_retry curl -fsSLo "${CP_ROOT}/etc/apt/sources.list.d/tailscale.list" \
            https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list
        cp_apt_update
        cp_apt_install_nr tailscale
        cp_enable tailscaled.service
        cp_run systemctl start tailscaled.service
        keyfile="${CP_ROOT}/run/kistengeist/tailscale.key"
        if [ -s "$keyfile" ]; then
            if [ "$CP_DRY_RUN" = "1" ]; then
                cp_log "[dry-run] tailscale up --auth-key=*** --hostname=kistengeist"
            else
                # Ohne --timeout wartet tailscale up bei falschem Schlüssel unbegrenzt.
                tailscale up --timeout=90s --auth-key="file:${keyfile}" --hostname=kistengeist >>"$CP_LOG" 2>&1 \
                    || cp_warn "Tailscale-Anmeldung fehlgeschlagen (Schlüssel prüfen; später: sudo tailscale up)."
            fi
            rm -f "$keyfile"
        else
            cp_warn 'Kein Tailscale-Schlüssel - später mit "sudo tailscale up" anmelden.'
        fi
        target=8080
        [ "$with_n8n" = yes ] && target=5678
        # Ist Funnel im Tailnet noch nicht erlaubt, wartet der Befehl auf eine Freigabe im Browser.
        cp_run timeout 60 tailscale funnel --bg "$target" \
            || cp_warn "Funnel nicht aktiv: in der Tailscale-Verwaltung HTTPS und Funnel erlauben, dann: sudo tailscale funnel --bg $target"
        if [ "$CP_DRY_RUN" = "1" ]; then
            public_url="https://kistengeist.example.ts.net"
        else
            dns="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
            [ -n "$dns" ] && public_url="https://${dns}"
        fi
        ;;
esac

# Caddyfile
site_body="	root * /srv/kistengeist-web
	file_server"
if [ "$with_n8n" = yes ]; then
    site_body="	reverse_proxy 127.0.0.1:5678"
fi
{
    echo "# Von Kistengeist erzeugt (Modul webserver)."
    if [ -n "$email" ]; then
        printf '{\n\temail %s\n}\n\n' "$email"
    fi
    if [ "$net" = dyndns ]; then
        printf '%s {\n\tencode zstd gzip\n%s\n}\n\n' "$domain" "$site_body"
    fi
    printf ':8080 {\n\troot * /srv/kistengeist-web\n\tfile_server\n}\n'
} | cp_write /etc/caddy/Caddyfile
if [ "$CP_DRY_RUN" != "1" ]; then
    caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile >>"$CP_LOG" 2>&1 \
        || cp_die "Caddyfile ungültig."
fi

# Startseite (Heimnetz)
links='<a class="card" href="/"><strong>Startseite</strong><br>Diese Seite</a>'
if [ "$with_n8n" = yes ]; then
    n8n_link="${public_url:-http://kistengeist.local:5678}"
    links="<a class=\"card\" href=\"${n8n_link}\"><strong>n8n</strong><br>Automatisierungen – ${n8n_link}</a>"
fi
mkdir -p "${CP_ROOT}/srv/kistengeist-web"
if [ ! -f "${CP_ROOT}/srv/kistengeist-web/index.html" ] || grep -q 'Kistengeist</title>' "${CP_ROOT}/srv/kistengeist-web/index.html"; then
    sed "s#@LINKS@#${links//&/\\&}#" "${CP_HOME_DIR}/share/web/index.html.in" \
        | cp_write /srv/kistengeist-web/index.html
fi

# DynDNS: alle 5 Minuten prüfen, gemeldet wird nur bei geänderter Adresse (Tageslimits der Anbieter).
if [ "$net" = dyndns ]; then
    secret_file="${CP_ETC}/ddns.json"
    [ -s "$secret_file" ] || cp_die "Zugangsdaten für den DynDNS-Anbieter fehlen."
    chmod 0600 "$secret_file"
    cp_write /etc/systemd/system/kistengeist-ddns.service <<'UNIT'
[Unit]
Description=Kistengeist: DynDNS-Adresse aktualisieren
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/kistengeist/bin/kistengeist-ddns
UNIT
    cp_write /etc/systemd/system/kistengeist-ddns.timer <<'UNIT'
[Unit]
Description=Kistengeist: DynDNS-Adresse alle 5 Minuten prüfen

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
UNIT
    cp_run systemctl daemon-reload
    cp_enable kistengeist-ddns.timer
    cp_run /opt/kistengeist/bin/kistengeist-ddns --force || cp_warn "DynDNS-Aktualisierung fehlgeschlagen (Zugangsdaten/Adresse prüfen: kistengeist-ddns status)."
fi

mkdir -p "${CP_ETC}"
python3 "${CP_HOME_DIR}/lib/json_merge.py" "${CP_ETC}/access.json" \
    "{\"net_access\": \"${net}\", \"public_url\": \"${public_url}\", \"home_url\": \"http://kistengeist.local:8080\"}"
chmod 0644 "${CP_ETC}/access.json"
cp_log "Webserver eingerichtet (${net}${public_url:+, $public_url})."
