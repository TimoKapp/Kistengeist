# shellcheck shell=bash
# Grundsystem: Updates, Sprache, Zeitzone, X11-Basis, Schlüsselbund.

timezone="$(cp_setting TIMEZONE)"
keymap="$(cp_setting KEYMAP)"
locale="$(cp_setting LOCALE)"

cp_ensure_time
cp_apt_update
cp_retry apt-get "${APT_OPTS[@]}" -y -o Dpkg::Options::=--force-confdef \
    -o Dpkg::Options::=--force-confold full-upgrade

if command -v raspi-config >/dev/null 2>&1 || [ "$CP_DRY_RUN" = "1" ]; then
    [ -n "$locale" ] && cp_run raspi-config nonint do_change_locale "$locale"
    [ -n "$timezone" ] && cp_run raspi-config nonint do_change_timezone "$timezone"
    [ -n "$keymap" ] && cp_run raspi-config nonint do_configure_keyboard "$keymap"
else
    cp_warn "raspi-config fehlt – Sprache/Zeitzone/Tastatur bleiben unverändert."
fi

# X11 statt Wayland: Claude Desktop unterstützt seine Tastenkürzel unter X11
# vollständig, und RDP-Spiegelung (x11vnc) funktioniert nur mit X11.
cp_apt_install_nr \
    ca-certificates curl gnupg \
    xserver-xorg xinit x11-xserver-utils x11-utils \
    openbox tint2 dbus-x11 \
    gnome-keyring libpam-gnome-keyring libsecret-1-0 \
    zenity python3-tk xdg-utils \
    fonts-dejavu fonts-noto-color-emoji adwaita-icon-theme \
    libgl1-mesa-dri libegl-mesa0 libgbm1 \
    at-spi2-core

# Grafiktreiber des Pi 4 (vc4) als primäre Anzeige festlegen; ohne diese Datei
# wählt Xorg je nach Start die 3D-Einheit (v3d) und der Bildschirm bleibt schwarz.
cp_write /etc/X11/xorg.conf.d/99-vc4.conf <<'EOF'
Section "OutputClass"
    Identifier "vc4"
    MatchDriver "vc4"
    Driver "modesetting"
    Option "PrimaryGPU" "true"
EndSection
EOF
