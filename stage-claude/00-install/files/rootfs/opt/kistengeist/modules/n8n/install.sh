# shellcheck shell=bash
# n8n per Docker Compose (Debian-Pakete docker.io/docker-compose). Port 5678 nur lokal bzw. im
# Heimnetz; von außen nur über Caddy (HTTPS) oder Tailscale Funnel. Quellen:
# https://docs.n8n.io/deploy/host-n8n/install-options/install-with-docker.md, …/deployment.md,
# https://docs.n8n.io/connect/connect-to-n8n-mcp-server.md

# docker-cli (Befehl "docker") ist bei docker.io in Debian 13 nur empfohlen, nicht abhängig.
cp_apt_install_nr docker.io docker-cli docker-compose python3-bcrypt iptables ca-certificates
if [ "$CP_DRY_RUN" != "1" ]; then
    command -v docker >/dev/null || cp_die "Docker-Befehl fehlt nach der Installation."
    docker compose version >>"$CP_LOG" 2>&1 || cp_die "docker compose fehlt nach der Installation."
fi
cp_enable docker.service
cp_run systemctl start docker.service

net="$(cp_setting NET_ACCESS)"
net="${net:-lan}"
tz="$(cp_setting TIMEZONE)"
tz="${tz:-Europe/Berlin}"
public_url="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("public_url",""))' \
    "${CP_ETC}/access.json" 2>/dev/null || true)"
dir=/srv/n8n
mkdir -p "${CP_ROOT}${dir}/data" "${CP_ROOT}${dir}/backup"
cp_run chown 1000:1000 "${CP_ROOT}${dir}/data" "${CP_ROOT}${dir}/backup"
chmod 0700 "${CP_ROOT}${dir}/data"

if [ -n "$public_url" ]; then
    host="${public_url#https://}"
    bind="127.0.0.1:5678:5678"
    url_env="N8N_HOST=${host}
N8N_PROTOCOL=https
N8N_WEBHOOK_URL=${public_url}/
N8N_EDITOR_BASE_URL=${public_url}/
N8N_PROXY_HOPS=1
N8N_SECURE_COOKIE=true"
    local_url="http://127.0.0.1:5678"
else
    # Nur Heimnetz: ohne HTTPS, daher ohne „Secure“-Cookie (sonst ist keine Anmeldung möglich).
    bind="5678:5678"
    url_env="N8N_HOST=kistengeist.local
N8N_PROTOCOL=http
N8N_WEBHOOK_URL=http://kistengeist.local:5678/
N8N_EDITOR_BASE_URL=http://kistengeist.local:5678/
N8N_SECURE_COOKIE=false"
    local_url="http://kistengeist.local:5678"
fi

privacy=""
if [ "$(cp_setting PRIVACY_MINIMAL)" != "no" ]; then
    # Versionshinweise bleiben bewusst an: darüber kommen Sicherheitswarnungen.
    privacy="N8N_DIAGNOSTICS_ENABLED=false
N8N_PERSONALIZATION_ENABLED=false
N8N_HIRING_BANNER_ENABLED=false"
fi

license=""
owner_env=""
secrets="${CP_ROOT}/run/kistengeist/n8n.json"
if [ -s "$secrets" ]; then
    license="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("license",""))' "$secrets")"
    # Besitzerkonto über die dokumentierten Variablen (ab n8n 2.17): existiert schon beim ersten
    # Start, es gibt also kein Zeitfenster, in dem ein Fremder das Konto anlegen könnte.
    # Nach dem ersten Start werden die Zeilen wieder entfernt; die Werte bleiben in n8n erhalten.
    if [ "$CP_DRY_RUN" = "1" ]; then
        owner_env="N8N_INSTANCE_OWNER_MANAGED_BY_ENV=true
N8N_INSTANCE_OWNER_PASSWORD_HASH='\$2b\$10\$dryrun'"
    else
        owner_env="$(python3 "${CP_HOME_DIR}/lib/kistengeist_n8n.py" owner-env "$secrets")" \
            || cp_die "Besitzerkonto für n8n konnte nicht vorbereitet werden."
    fi
fi

{
    echo "# Von Kistengeist erzeugt. Enthält ggf. den Lizenzschlüssel – nur für root lesbar."
    echo "$url_env"
    echo "N8N_PORT=5678"
    echo "NODE_ENV=production"
    echo "GENERIC_TIMEZONE=${tz}"
    echo "TZ=${tz}"
    echo "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true"
    # MCP-Zugang für Claude (Einstellungen > Instance-level MCP), ab n8n 2.20.
    echo "N8N_MCP_MANAGED_BY_ENV=true"
    echo "N8N_MCP_ACCESS_ENABLED=true"
    [ -n "$privacy" ] && echo "$privacy"
    [ -n "$license" ] && echo "N8N_LICENSE_ACTIVATION_KEY=${license}"
    if [ -n "$owner_env" ]; then
        echo "# kistengeist-owner-begin"
        echo "$owner_env"
        echo "# kistengeist-owner-end"
    fi
    true
} | cp_write "${dir}/n8n.env" 0600

cp_write "${dir}/docker-compose.yml" <<YAML
# Von Kistengeist erzeugt (Modul n8n).
services:
  n8n:
    image: docker.io/n8nio/n8n:stable
    restart: unless-stopped
    ports:
      - "${bind}"
    env_file: n8n.env
    volumes:
      - ./data:/home/node/.n8n
      - ./backup:/home/node/backup
YAML

cp_write /etc/systemd/system/kistengeist-n8n.service <<'UNIT'
[Unit]
Description=Kistengeist: n8n (Docker Compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/n8n
ExecStart=/usr/bin/docker compose up -d --remove-orphans
# Docker veröffentlicht Ports an ufw vorbei: 5678 nur aus privaten Netzen zulassen.
ExecStartPost=/opt/kistengeist/bin/kistengeist-n8n firewall
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
UNIT
for job in update backup; do
    if [ "$job" = update ]; then when="Mon *-*-* 04:30:00"; text="Sicherheitsupdates (wöchentlich)"; else when="*-*-* 03:15:00"; text="Sicherung (täglich)"; fi
    cp_write "/etc/systemd/system/kistengeist-n8n-${job}.service" <<UNIT
[Unit]
Description=Kistengeist: n8n ${text}
Requires=docker.service
After=docker.service kistengeist-n8n.service

[Service]
Type=oneshot
ExecStart=/opt/kistengeist/bin/kistengeist-n8n ${job}
UNIT
    cp_write "/etc/systemd/system/kistengeist-n8n-${job}.timer" <<UNIT
[Unit]
Description=Kistengeist: n8n ${text}

[Timer]
OnCalendar=${when}
Persistent=true
RandomizedDelaySec=20min

[Install]
WantedBy=timers.target
UNIT
done
cp_run systemctl daemon-reload
cp_enable kistengeist-n8n.service kistengeist-n8n-update.timer kistengeist-n8n-backup.timer

cp_retry docker compose -f "${dir}/docker-compose.yml" pull --quiet || cp_die "n8n-Image konnte nicht geladen werden."
cp_run systemctl start kistengeist-n8n.service || cp_die "n8n startet nicht (Protokoll: docker compose logs)."

# Besitzerkonto prüfen und die Zeilen danach aus der env-Datei entfernen.
owner=skipped
if [ -n "$owner_env" ]; then
    if [ "$CP_DRY_RUN" = "1" ]; then
        cp_log "[dry-run] n8n: auf Bereitschaft warten, Besitzerkonto prüfen"
        owner=ok
    elif python3 "${CP_HOME_DIR}/lib/kistengeist_n8n.py" owner-check >>"$CP_LOG" 2>&1; then
        owner=ok
        cp_log "n8n-Besitzerkonto angelegt."
    else
        owner=failed
    fi
    sed -i '/^# kistengeist-owner-begin$/,/^# kistengeist-owner-end$/d' "${CP_ROOT}${dir}/n8n.env"
    cp_run systemctl restart kistengeist-n8n.service || true
fi
if [ "$owner" = failed ]; then
    if [ "$net" != lan ]; then
        # Ohne Konto dürfte jeder aus dem Internet das Besitzerkonto anlegen: n8n nicht starten.
        cp_run systemctl disable --now kistengeist-n8n.service || true
        cp_warn "n8n-Besitzerkonto fehlt – n8n wurde aus Sicherheitsgründen gestoppt. Einrichtung wiederholen."
    else
        cp_warn "n8n-Besitzerkonto fehlt – beim ersten Öffnen im Heimnetz selbst anlegen."
    fi
fi

# MCP-Server von n8n bei Claude Code anmelden (Anmeldung danach in Claude Code mit /mcp).
mcp_url="${public_url:-http://localhost:5678}/mcp-server/http"
home="$(cp_user_home)"
python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.claude.json" \
    "{\"mcpServers\": {\"n8n\": {\"type\": \"http\", \"url\": \"${mcp_url}\"}}}"
cp_run chown "$CP_USER:$CP_USER" "$home/.claude.json"

n8n_url="${public_url:-$local_url}"
# Direkter Zugang im Heimnetz nur im Modus „lan“ (sonst ist 5678 nur auf dem Pi selbst offen).
lan_url=""
[ "$net" = lan ] && lan_url="http://kistengeist.local:5678"
python3 "${CP_HOME_DIR}/lib/json_merge.py" "${CP_ETC}/access.json" \
    "{\"n8n_url\": \"${n8n_url}\", \"n8n_local_url\": \"${lan_url}\", \"n8n_mcp_url\": \"${mcp_url}\", \"n8n_owner\": \"${owner}\"}"
chmod 0644 "${CP_ETC}/access.json"

cp_write /opt/kistengeist/share/applications/kistengeist-n8n.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=n8n
Comment=Automatisierungen mit n8n öffnen
Exec=/opt/kistengeist/bin/kistengeist-launch n8n
Icon=/opt/kistengeist/share/icons/kistengeist-n8n.svg
Terminal=false
DESKTOP
