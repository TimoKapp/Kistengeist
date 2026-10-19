# shellcheck shell=bash
# Claude-Oberfläche: Benutzergruppen und Schlüsselbund.

for group in video render audio input plugdev netdev; do
    if [ "$CP_DRY_RUN" = "1" ] || getent group "$group" >/dev/null; then
        cp_run usermod -aG "$group" "$CP_USER"
    fi
done

home="$(cp_user_home)"

# Openbox, tint2 & Co. lesen ihre Konfiguration aus /opt/kistengeist/share;
# im Benutzerordner wird nur das Nötigste angelegt.
cp_run install -d -o "$CP_USER" -g "$CP_USER" -m 0700 \
    "$home/.config" "$home/.config/kistengeist" "$home/.local" "$home/.local/share" \
    "$home/Projekte" "$home/Uploads"

# Doppelklick-Zeit und -Abstand großzügig (RDP-Verzögerung, hohe Auflösung).
for v in 3.0 4.0; do
    mkdir -p "$home/.config/gtk-$v"
    [ -f "$home/.config/gtk-$v/settings.ini" ] && continue   # eigene Einstellungen bleiben
    printf '[Settings]\ngtk-double-click-time=800\ngtk-double-click-distance=12\ngtk-cursor-theme-name=Adwaita\n' \
        | cp_write "${home#"${CP_ROOT}"}/.config/gtk-$v/settings.ini"
done
cp_run chown -R "$CP_USER:$CP_USER" "$home/.config/gtk-3.0" "$home/.config/gtk-4.0"

if [ "$(cp_setting AUTOLOGIN)" = "yes" ]; then
    # Bei automatischer Anmeldung gibt es kein Passwort, das den Schlüsselbund
    # entsperrt. Die Sitzung legt ihn deshalb ohne Passwort an (siehe
    # kistengeist-session). Claude speichert dort seine Anmeldung.
    cp_log "Automatische Anmeldung: Schlüsselbund wird ohne Passwort angelegt."
fi

# Ausschalten/Neustarten aus der Leiste auch in RDP-Sitzungen erlauben.
cp_write /etc/polkit-1/rules.d/50-kistengeist-power.rules <<RULES
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.login1.reboot" ||
         action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
         action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.power-off-multiple-sessions") &&
        subject.user == "${CP_USER}") {
        return polkit.Result.YES;
    }
});
RULES
