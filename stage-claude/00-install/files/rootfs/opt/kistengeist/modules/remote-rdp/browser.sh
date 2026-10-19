# shellcheck shell=bash
# Fernzugriff im Browser mit Selkies (https://github.com/selkies-project/selkies, MPL-2.0):
# Desktop, Ton und Mikrofon über https://kistengeist.local:8443 (nur Heimnetz, Passwort = Anmeldepasswort).
#  Modus "both": Selkies zeigt die Sitzung am Monitor (:0, ohne Größenänderung).
#  Modus "rdp":  ohne Monitor läuft die Sitzung auf einem virtuellen Bildschirm (Xvfb :0),
#                dessen Größe sich dem Browserfenster anpasst.

SELKIES_VERSION=2.0.0
SELKIES_SHA256=d2153526afc104c42257f73c4a43b60c224fa275b0b7d291631bd1849949fa97
SELKIES_URL="https://github.com/selkies-project/selkies/releases/download/${SELKIES_VERSION}/selkies-${SELKIES_VERSION}-debiantrixie-arm64.deb"

mode="$(cp_mode)"
home="$(cp_user_home)"

cp_apt_install_nr pipewire pipewire-bin pipewire-pulse wireplumber pulseaudio-utils ssl-cert curl \
    x11-utils dbus-user-session
if [ "$mode" = "rdp" ]; then
    cp_apt_install_nr xvfb xauth
fi

deb="${CP_ROOT}/tmp/selkies.deb"
cp_retry curl -fsSLo "$deb" "$SELKIES_URL" || cp_die "Selkies konnte nicht geladen werden."
if [ "$CP_DRY_RUN" != "1" ]; then
    echo "${SELKIES_SHA256}  ${deb}" | sha256sum -c - >>"$CP_LOG" 2>&1 \
        || cp_die "Selkies-Paket hat nicht die erwartete Prüfsumme."
fi
cp_apt_install "$deb"
rm -f "$deb"

# HTTPS mit eigenem Zertifikat für diesen Pi (der Browser warnt einmal). Nur neu erzeugen, wenn
# es fehlt oder nicht auf diesen Namen lautet – sonst müssten Browser die Warnung erneut bestätigen.
cert=/etc/ssl/certs/ssl-cert-snakeoil.pem
if [ "$CP_DRY_RUN" = "1" ] || ! openssl x509 -noout -subject -in "$cert" 2>/dev/null | grep -q "CN *= *$(hostname)$"; then
    cp_run make-ssl-cert generate-default-snakeoil --force-overwrite
fi
cp_run usermod -aG ssl-cert "$CP_USER"

# Einstellungen (anpassbar): JPEG ist auf dem Pi 4 sparsamer als H.264 per CPU.
resize=true
[ "$mode" = "both" ] && resize=false   # echten Monitor nicht umschalten
printf 'ENCODER=jpeg\nFRAMERATE=30\nRESIZE=%s\n' "$resize" | cp_write /etc/kistengeist/selkies.conf

# Passwort für den Browser-Zugang = Anmeldepasswort (nur für den Benutzer lesbar).
secret="${CP_SECRET_FILE:-}"
[ -n "$secret" ] && [ -s "$secret" ] || cp_die "Kein Passwort für den Browser-Zugang übergeben."
install -d -m 0700 "$home/.config/kistengeist"
python3 - "$secret" "$home/.config/kistengeist/selkies.env" <<'PY'
import os, sys
pw = open(sys.argv[1], encoding="utf-8").readline().rstrip("\n")
esc = pw.replace("\\", "\\\\").replace('"', '\\"')
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write(f'SELKIES_BASIC_AUTH_PASSWORD="{esc}"\n')
PY
cp_run chown -R "$CP_USER:$CP_USER" "$home/.config/kistengeist"

# systemd-Benutzerdienste (laufen dank „linger“ ab dem Start, auch ohne Anmeldung).
cp_write /etc/systemd/user/kistengeist-selkies.service <<'UNIT'
[Unit]
Description=Kistengeist: Desktop im Browser (Selkies)
ConditionPathExists=/etc/kistengeist/installed
Wants=pipewire.socket pipewire-pulse.socket wireplumber.service
After=pipewire-pulse.socket wireplumber.service kistengeist-desktop.service

[Service]
Environment=DISPLAY=:0
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus
EnvironmentFile=%h/.config/kistengeist/selkies.env
ExecStart=/opt/kistengeist/bin/kistengeist-selkies
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
UNIT
wants="$home/.config/systemd/user/default.target.wants"
mkdir -p "$wants"
ln -sfn /etc/systemd/user/kistengeist-selkies.service "$wants/kistengeist-selkies.service"

if [ "$mode" = "rdp" ]; then
    cp_write /etc/systemd/user/kistengeist-xvfb.service <<'UNIT'
[Unit]
Description=Kistengeist: virtueller Bildschirm (ohne Monitor)
ConditionPathExists=/etc/kistengeist/installed

[Service]
# Zugriffsschutz: nur Prozesse mit dem Cookie aus ~/.Xauthority dürfen auf den Bildschirm.
ExecStartPre=/bin/sh -c 'rm -f %h/.Xauthority && xauth -q -f %h/.Xauthority add :0 . "$$(mcookie)"'
ExecStart=/usr/bin/Xvfb :0 -screen 0 1920x1080x24 -nolisten tcp -auth %h/.Xauthority +extension RANDR
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
UNIT
    cp_write /etc/systemd/user/kistengeist-desktop.service <<'UNIT'
[Unit]
Description=Kistengeist: Oberfläche auf dem virtuellen Bildschirm
ConditionPathExists=/etc/kistengeist/installed
Requires=kistengeist-xvfb.service
Wants=dbus.socket
After=kistengeist-xvfb.service pipewire-pulse.socket dbus.socket

[Service]
Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority
# Gemeinsamer Sitzungsbus mit den systemd-Diensten (Schlüsselbund, PipeWire), kein privater Bus.
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus
ExecStartPre=/bin/sh -c 'for i in $(seq 1 30); do xdpyinfo >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
ExecStart=/opt/kistengeist/bin/kistengeist-session
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
    ln -sfn /etc/systemd/user/kistengeist-xvfb.service "$wants/kistengeist-xvfb.service"
    ln -sfn /etc/systemd/user/kistengeist-desktop.service "$wants/kistengeist-desktop.service"
fi
cp_run chown -R "$CP_USER:$CP_USER" "$home/.config/systemd"

# Benutzerdienste schon beim Start (ohne Anmeldung) – entspricht „loginctl enable-linger“.
mkdir -p "${CP_ROOT}/var/lib/systemd/linger"
touch "${CP_ROOT}/var/lib/systemd/linger/${CP_USER}"
cp_log "Desktop im Browser eingerichtet: https://kistengeist.local:8443 (Modus ${mode})."
