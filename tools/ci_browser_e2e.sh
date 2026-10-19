#!/bin/bash
# Desktop im Browser – echter Test in debian:trixie (arm64) wie auf dem Pi:
#  1. Modul remote-rdp mit REMOTE=browser, MODE=rdp ECHT ausführen (Selkies laden, Prüfsumme, Dienste)
#  2. virtuellen Bildschirm + PipeWire wie die Benutzerdienste starten, kistengeist-selkies starten
#  3. echter Chromium-Client mit simuliertem Mikrofon verbindet sich
#  4. prüfen: ohne Passwort gesperrt, Größe folgt dem Browser, Ton-Senke und Browser-Mikrofon sind
#     Standard (Hook), nach dem Trennen wieder zurück
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
repo="$(pwd)"
home_dir="$repo/stage-claude/00-install/files/rootfs/opt/kistengeist"
fail=0
err() { echo "::error::$1"; fail=1; }

printf '#!/bin/sh\nexit 101\n' >/usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d
apt-get update -qq
apt-get install -y -qq --no-install-recommends python3 sudo procps curl ca-certificates openbox \
    x11-xserver-utils dbus dbus-x11 chromium >/dev/null
# Wie im Image: Programme unter /opt/kistengeist
mkdir -p /opt && cp -r "$home_dir" /opt/kistengeist
id claude >/dev/null 2>&1 || useradd -m -s /bin/bash claude
mkdir -p /etc/kistengeist /run/kistengeist
printf 'MODE="rdp"\nREMOTE="browser"\nMODULES=""\n' >/etc/kistengeist/setup.conf
# Sonderzeichen prüft ci_browser_systemd.sh; hier zählt der echte Browser-Client
echo 'BrowserTest1' >/run/kistengeist/secret

echo "== 1. Modul echt ausführen"
CP_HOME_DIR=/opt/kistengeist CP_SECRET_FILE=/run/kistengeist/secret bash -eu -o pipefail -c \
    '. "$1"; cd "$(dirname "$2")"; . "$2"' _ /opt/kistengeist/lib/common.sh /opt/kistengeist/modules/remote-rdp/install.sh \
    || { tail -30 /var/log/kistengeist/install.log; exit 1; }
tail -5 /var/log/kistengeist/install.log
for f in /etc/systemd/user/kistengeist-selkies.service /etc/systemd/user/kistengeist-xvfb.service \
         /etc/systemd/user/kistengeist-desktop.service /var/lib/systemd/linger/claude \
         /home/claude/.config/systemd/user/default.target.wants/kistengeist-selkies.service; do
    [ -e "$f" ] || err "fehlt: $f"
done
[ "$(stat -c %a /home/claude/.config/kistengeist/selkies.env)" = 600 ] || err "selkies.env nicht 0600"
command -v selkies >/dev/null || err "selkies fehlt"
id -nG claude | grep -qw ssl-cert || err "claude nicht in ssl-cert"

echo "== 2. Dienste wie systemd starten (als claude)"
# Teil A (als claude, läuft weiter): Bildschirm, Ton, Selkies – wie die Benutzerdienste.
cat >/tmp/svc.sh <<'RUN'
set -u
export XDG_RUNTIME_DIR=/tmp/xdg-claude; mkdir -p -m 700 "$XDG_RUNTIME_DIR"
Xvfb :0 -screen 0 1920x1080x24 -nolisten tcp +extension RANDR >/tmp/xvfb.log 2>&1 &
export DISPLAY=:0
eval "$(dbus-launch --sh-syntax)"
pipewire >/tmp/pw.log 2>&1 & sleep 1; wireplumber >/tmp/wp.log 2>&1 & sleep 1; pipewire-pulse >/tmp/pwp.log 2>&1 & sleep 2
# Wie am Pi (Kopfhörer/HDMI): eine echte Ausgabe als Standard, damit „zurückstellen“ prüfbar ist.
pactl load-module module-null-sink sink_name=lautsprecher >/dev/null && pactl set-default-sink lautsprecher
openbox >/dev/null 2>&1 &
set -a; . "$HOME/.config/kistengeist/selkies.env"; set +a
exec /opt/kistengeist/bin/kistengeist-selkies >/tmp/selkies.log 2>&1
RUN
# Teil B (als claude): Messwerte aus derselben Sitzung
cat >/tmp/probe.sh <<'RUN'
export XDG_RUNTIME_DIR=/tmp/xdg-claude DISPLAY=:0
echo "$1_DIMS=$(xdpyinfo | awk '/dimensions/{print $2}')"
echo "$1_SINK=$(pactl get-default-sink)"
echo "$1_SOURCE=$(pactl get-default-source)"
RUN
sudo -u claude bash /tmp/svc.sh &
for _ in $(seq 1 60); do curl -sk -o /dev/null https://127.0.0.1:8443/ && break; sleep 1; done
sleep 2
{
    sudo -u claude bash /tmp/probe.sh BEFORE
    echo "STATUS_NOAUTH=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/)"
    echo "STATUS_WRONG=$(curl -sk -u claude:falsch -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/)"
} | tee /tmp/out.txt
# Test-Client (nicht Teil des Produkts): Chromium als root wie im Selkies-Probelauf
Xvfb :2 -screen 0 1280x720x24 >/dev/null 2>&1 &
sleep 1
DISPLAY=:2 chromium --no-sandbox --ignore-certificate-errors --use-fake-ui-for-media-stream \
  --use-fake-device-for-media-stream --autoplay-policy=no-user-gesture-required --window-size=1280,720 \
  --user-data-dir=/tmp/chr "https://claude:BrowserTest1@127.0.0.1:8443/" >/tmp/chromium.log 2>&1 &
cpid=$!
sleep 45
sudo -u claude bash /tmp/probe.sh CONN | tee -a /tmp/out.txt
sudo -u claude env XDG_RUNTIME_DIR=/tmp/xdg-claude pactl list short sources
kill "$cpid" || true; sleep 20
sudo -u claude bash /tmp/probe.sh AFTER | tee -a /tmp/out.txt
tail -25 /tmp/selkies.log
echo '== Ton-Umschaltung'; cat /tmp/xdg-claude/kistengeist-audio.log || true
echo '== chromium.log'; tail -15 /tmp/chromium.log
get() { sed -n "s/^$1=//p" /tmp/out.txt | tail -n 1; }

echo "== 3. Auswertung"
[ "$(get STATUS_NOAUTH)" = 401 ] || err "ohne Passwort nicht gesperrt ($(get STATUS_NOAUTH))"
[ "$(get STATUS_WRONG)" = 401 ] || err "falsches Passwort nicht abgelehnt ($(get STATUS_WRONG))"
[ "$(get CONN_DIMS)" != "1920x1080" ] || err "Bildgröße folgt dem Browser nicht"
[ "$(get CONN_SINK)" = output ] || err "Ton geht nicht zum Browser (Standard: $(get CONN_SINK))"
case "$(get CONN_SOURCE)" in *SelkiesVirtualMic) ;; *) err "Browser-Mikrofon nicht Standard ($(get CONN_SOURCE))" ;; esac
[ "$(get BEFORE_SINK)" = lautsprecher ] || err "Test-Lautsprecher nicht Standard ($(get BEFORE_SINK))"
[ "$(get AFTER_SINK)" = "$(get BEFORE_SINK)" ] || err "Ton nach dem Trennen nicht zurückgestellt ($(get AFTER_SINK))"
[ "$(get AFTER_SOURCE)" = "$(get BEFORE_SOURCE)" ] || err "Mikrofon nach dem Trennen nicht zurückgestellt ($(get AFTER_SOURCE))"
[ "$fail" = 0 ] && echo "Desktop im Browser: alle Prüfungen bestanden." || exit 1
