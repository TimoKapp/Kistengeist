#!/bin/bash
# Läuft im systemd-Container (siehe ci_installer.sh).
set -uo pipefail
fail=0
err() { echo "::error::$1"; fail=1; }
cd /srv && (python3 -m http.server 8000 >/tmp/http.log 2>&1 &) && sleep 1
url=http://127.0.0.1:8000/kg-src.tar.gz
sha="$(sha256sum /srv/kg-src.tar.gz | cut -d' ' -f1)"
export KG_MIN_FREE_MB=1024

echo "== 1. Schutzprüfungen"
out="$(bash /repo/install.sh 2>&1)"; rc=$?
{ [ $rc != 0 ] && grep -q "Raspberry Pi 4" <<<"$out"; } || err "ohne Raspberry Pi nicht abgelehnt: $out"
useradd -m tester
out="$(sudo -u tester bash /repo/install.sh 2>&1)"; rc=$?
{ [ $rc != 0 ] && grep -q "sudo" <<<"$out"; } || err "ohne root nicht abgelehnt: $out"
out="$(KG_ALLOW_ANY_HW=1 KG_ARCHIVE_URL=$url KG_SHA256=0000 bash /repo/install.sh 2>&1)"; rc=$?
{ [ $rc != 0 ] && grep -q "Prüfsumme" <<<"$out"; } || err "falsche Prüfsumme nicht abgelehnt"
[ ! -d /opt/kistengeist ] || err "nach Prüfsummenfehler wurden trotzdem Dateien kopiert"

echo "== 2. Installation wie mit curl | sudo bash"
KG_ALLOW_ANY_HW=1 KG_ARCHIVE_URL=$url KG_SHA256=$sha bash < /repo/install.sh || err "install.sh scheitert"
for u in kistengeist-setup kistengeist-console kistengeist-hotspot avahi-daemon; do
    systemctl is-enabled "$u.service" >/dev/null 2>&1 || err "$u nicht aktiviert"
done
systemctl is-active kistengeist-setup.service >/dev/null || err "Setup-Assistent läuft nicht"
code="$(curl -s -o /tmp/index.html -w '%{http_code}' http://127.0.0.1/)"
[ "$code" = 200 ] || err "Setup-Assistent antwortet nicht (HTTP $code)"
grep -q Kistengeist /tmp/index.html || err "Startseite ohne Kistengeist"
curl -fs http://127.0.0.1/api/info | python3 -c 'import json,sys; json.load(sys.stdin)' || err "/api/info liefert kein JSON"
id claude >/dev/null || err "Benutzer claude fehlt"
passwd -S claude | grep -q ' L ' || err "Passwort von claude nicht gesperrt"
[ "$(cat /etc/hostname)" = kistengeist ] || err "Gerätename nicht gesetzt"
grep -q '127.0.1.1.*kistengeist' /etc/hosts || err "/etc/hosts ohne kistengeist"
[ "$(systemctl get-default)" = multi-user.target ] || err "Standardziel nicht multi-user"
[ -x /opt/kistengeist/bin/kistengeist-install ] || err "Installer-Programm nicht ausführbar"
[ "$(stat -c %U /opt/kistengeist/wizard/server.py)" = root ] || err "Dateien gehören nicht root"
[ -s /var/log/kistengeist/install-script.log ] || err "Protokoll fehlt"
compgen -G '/tmp/kistengeist.*' >/dev/null && err "Arbeitsordner nicht aufgeräumt"

echo "== 3. Zweiter Lauf (z. B. nach Abbruch) und Sperre nach fertiger Einrichtung"
systemctl stop kistengeist-setup.service
KG_ALLOW_ANY_HW=1 KG_ARCHIVE_URL=$url KG_SHA256=$sha bash /repo/install.sh >/tmp/run2.log 2>&1 || { tail -20 /tmp/run2.log; err "zweiter Lauf scheitert"; }
touch /etc/kistengeist/installed
out="$(KG_ALLOW_ANY_HW=1 bash /repo/install.sh 2>&1)"; rc=$?
{ [ $rc != 0 ] && grep -q "bereits eingerichtet" <<<"$out"; } || err "zweite Einrichtung nicht verhindert"

[ "$fail" = 0 ] && echo "Ein-Befehl-Installer: alle Prüfungen bestanden." || { journalctl -u kistengeist-setup --no-pager | tail -30; exit 1; }
