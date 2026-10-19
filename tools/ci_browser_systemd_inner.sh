#!/bin/bash
set -uo pipefail
fail=0
err() { echo "::error::$1"; fail=1; }
cp -r /repo/stage-claude/00-install/files/rootfs/opt/kistengeist /opt/kistengeist
useradd -m -s /bin/bash claude
uid="$(id -u claude)"
mkdir -p /etc/kistengeist /run/kistengeist
printf 'MODE="rdp"\nREMOTE="browser"\nAUTOLOGIN="yes"\nMODULES=""\n' >/etc/kistengeist/setup.conf
pw='Ab"c\d$e#Ü1x`y'
printf '%s\n' "$pw" >/run/kistengeist/secret
echo "== Modul echt ausführen"
CP_HOME_DIR=/opt/kistengeist CP_SECRET_FILE=/run/kistengeist/secret bash -eu -o pipefail -c \
    '. "$1"; cd "$(dirname "$2")"; . "$2"' _ /opt/kistengeist/lib/common.sh /opt/kistengeist/modules/remote-rdp/install.sh \
    || { tail -30 /var/log/kistengeist/install.log; exit 1; }
touch /etc/kistengeist/installed
# Schriftgrößen-Dialog bei der ersten Anmeldung im Test überspringen
mkdir -p /home/claude/.config/kistengeist && echo SCALE=100 >/home/claude/.config/kistengeist/scale.conf
chown -R claude:claude /home/claude
echo "== Benutzer-Manager starten (wie beim Booten mit linger)"
loginctl enable-linger claude 2>/dev/null || systemctl start "user@${uid}.service"
for _ in $(seq 1 90); do
    runuser -u claude -- env XDG_RUNTIME_DIR="/run/user/$uid" systemctl --user is-active -q kistengeist-selkies.service && break
    sleep 2
done
sleep 20
us() { runuser -u claude -- env XDG_RUNTIME_DIR="/run/user/$uid" systemctl --user "$@"; }
for u in kistengeist-xvfb kistengeist-desktop kistengeist-selkies pipewire-pulse.socket; do
    state="$(us is-active "$u" 2>/dev/null)"
    echo "$u: $state"
    [ "$state" = active ] || err "$u nicht aktiv"
done
us status --no-pager kistengeist-selkies | tail -15 || true
code() { curl -sk -o /dev/null -w '%{http_code}' "$@" https://127.0.0.1:8443/; }
c1="$(code)"; c2="$(code -u "claude:$pw")"; c3="$(code -u claude:falsch)"
echo "ohne: $c1  richtig: $c2  falsch: $c3"
[ "$c1" = 401 ] || err "ohne Passwort nicht gesperrt"
[ "$c3" = 401 ] || err "falsches Passwort nicht abgelehnt"
case "$c2" in 200 | 302) ;; *) err "Passwort mit Sonderzeichen wird nicht angenommen ($c2)" ;; esac
pgrep -u claude -x openbox >/dev/null || err "Openbox läuft nicht im Dienst"
pgrep -u claude -x tint2 >/dev/null || err "Leiste (tint2) läuft nicht im Dienst"
[ "$(stat -c %a /home/claude/.Xauthority 2>/dev/null)" = 600 ] || err ".Xauthority fehlt oder falsche Rechte"
DISPLAY=:0 XAUTHORITY=/nonexistent xdpyinfo >/dev/null 2>&1 && err "Xvfb ohne Zugriffsschutz"
[ "$fail" = 0 ] && echo "systemd-Kette: alle Prüfungen bestanden." || { us status --no-pager | tail -40; exit 1; }
