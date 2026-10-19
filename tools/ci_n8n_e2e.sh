#!/bin/bash
# Echter n8n-Test in der CI (arm64-Runner mit Docker, wie der Pi 4):
#  1. n8n-Dateien mit dem echten Modul erzeugen (Installer-Probelauf, Internet-Modus DynDNS)
#  2. Besitzerkonto mit echtem bcrypt-Hash ergänzen, n8n starten
#  3. prüfen: Konto angelegt, Anmeldung klappt, nach Entfernen der Konto-Variablen weiterhin,
#     Sicherung und Firewall-Regel funktionieren
set -euo pipefail
repo="$(pwd)"
home="$repo/stage-claude/00-install/files/rootfs/opt/kistengeist"
root="$(mktemp -d)"
email=ci@example.org
pw=CiTest123

mkdir -p "$root/etc/kistengeist" "$root/run/kistengeist" "$root/tmp" "$root/etc/ufw" "$root/etc/xrdp" "$root/etc/pam.d"
printf '[Globals]\nport=3389\n\n[Xorg]\nname=Xorg\nlib=libxup.so\n' >"$root/etc/xrdp/xrdp.ini"
printf '@include common-auth\n' >"$root/etc/pam.d/xrdp-sesman"
printf 'ENABLED=no\n' >"$root/etc/ufw/ufw.conf"
cat >"$root/etc/kistengeist/setup.conf" <<CONF
MODE="rdp"
AUTOLOGIN="no"
MODULES="webserver n8n"
TIMEZONE="Europe/Berlin"
KEYMAP="de"
LOCALE="de_DE.UTF-8"
PRIVACY_MINIMAL="yes"
NET_ACCESS="dyndns"
DDNS_PROVIDER="ipv64"
DDNS_HOST="citest.ipv64.net"
CONF
echo "VERSION=ci" >"$root/etc/kistengeist/legal-accepted"
echo '{"token": "citest-token-0000"}' >"$root/etc/kistengeist/ddns.json"
secrets="$(mktemp)"
printf '{"firstName":"CI","lastName":"Test","email":"%s","password":"%s","license":""}' "$email" "$pw" >"$secrets"
cp "$secrets" "$root/run/kistengeist/n8n.json"

echo "== 1. Installer-Probelauf"
CP_ROOT="$root" CP_DRY_RUN=1 CP_HOME_DIR="$home" bash "$home/bin/kistengeist-install" >/dev/null
test -f "$root/srv/n8n/docker-compose.yml" && test -f "$root/srv/n8n/n8n.env"

echo "== 2. n8n mit Besitzerkonto starten"
sudo rm -rf /srv/n8n && sudo mkdir -p /srv/n8n
sudo cp -r "$root/srv/n8n/." /srv/n8n/
sudo chown -R 1000:1000 /srv/n8n/data /srv/n8n/backup
owner="$(python3 "$home/lib/kistengeist_n8n.py" owner-env "$secrets")"
printf '%s\n' "# kistengeist-owner-begin" "$owner" "# kistengeist-owner-end" | sudo tee -a /srv/n8n/n8n.env >/dev/null
cd /srv/n8n
sudo docker compose pull --quiet
sudo docker compose up -d

login() {
    curl -fsS -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:5678/rest/login \
        -H 'Content-Type: application/json' \
        -d "{\"emailOrLdapLoginId\":\"$email\",\"password\":\"$pw\"}"
}

echo "== 3. Konto und Anmeldung"
python3 "$home/lib/kistengeist_n8n.py" owner-check
login

echo "== 4. Konto-Variablen entfernen (wie das Modul), Neustart, erneut anmelden"
sudo sed -i '/^# kistengeist-owner-begin$/,/^# kistengeist-owner-end$/d' /srv/n8n/n8n.env
if sudo grep -q OWNER /srv/n8n/n8n.env; then echo "Konto-Variablen nicht entfernt"; exit 1; fi
sudo docker compose up -d
sleep 5
python3 "$home/lib/kistengeist_n8n.py" owner-check
login

echo "== 5. Sicherung (leer wie nach der Installation, dann mit einem Workflow) und Firewall"
sudo bash "$home/bin/kistengeist-n8n" backup
cat >/tmp/wf.json <<'WF'
{"name":"CI-Test","nodes":[{"parameters":{},"name":"Start","type":"n8n-nodes-base.manualTrigger","typeVersion":1,"position":[0,0]}],"connections":{},"settings":{}}
WF
sudo docker compose cp /tmp/wf.json n8n:/tmp/wf.json
sudo docker compose exec -T n8n n8n import:workflow --input=/tmp/wf.json
sudo bash "$home/bin/kistengeist-n8n" backup
sudo ls -la /srv/n8n/backup/
sudo sh -c 'test -s /srv/n8n/backup/*/workflows.json' 
sudo bash "$home/bin/kistengeist-n8n" firewall
sudo iptables -S DOCKER-USER | grep -q KISTENGEIST-N8N
sudo bash "$home/bin/kistengeist-n8n" firewall   # zweimal: darf keine doppelte Regel erzeugen
[ "$(sudo iptables -S DOCKER-USER | grep -c KISTENGEIST-N8N)" = 1 ]
sudo docker compose logs --tail 30 n8n
echo "n8n-Test bestanden."
