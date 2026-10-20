# shellcheck shell=bash
# Fernzugriff per RDP (xrdp).
#
#  Modus "rdp":  eigene RDP-Sitzung (xorgxrdp), Anmeldung mit Benutzer + Passwort.
#                Die Sitzung läuft nach dem Trennen weiter; beim nächsten
#                Verbinden geht es dort weiter.
#  Modus "both": RDP zeigt denselben Bildschirm wie am Pi (Spiegelung über
#                x11vnc, nur lokal erreichbar). So laufen Claude und Chrome
#                nie doppelt, was ihre Profile beschädigen könnte.

mode="$(cp_mode)"
home="$(cp_user_home)"

# Fernzugriff im Browser statt RDP (Auswahl im Assistenten).
if [ "$(cp_setting REMOTE)" = "browser" ]; then
    # shellcheck source=browser.sh
    . ./browser.sh
    return 0
fi

cp_apt_install_nr xrdp xorgxrdp
# Ton und Mikrofon des RDP-Arbeitsplatzes (Sprachausgabe/-eingabe von Claude):
# PipeWire mit dem xrdp-Modul (xrdp-sink/xrdp-source).
cp_apt_install_nr pipewire pipewire-bin pipewire-pulse wireplumber pipewire-module-xrdp pulseaudio-utils
if [ "$mode" = "both" ]; then
    # tigervnc-tools liefert vncpasswd, das das Passwort über stdin liest
    # (nicht über die Befehlszeile, wo es in der Prozessliste sichtbar wäre).
    cp_apt_install_nr x11vnc tigervnc-tools
fi

xrdp_ini="${CP_ROOT}/etc/xrdp/xrdp.ini"
if [ -f "$xrdp_ini" ]; then
    [ -f "${xrdp_ini}.kistengeist.orig" ] || cp "$xrdp_ini" "${xrdp_ini}.kistengeist.orig"
    # Alle mitgelieferten Sitzungsarten entfernen; Globals, Logging usw. bleiben.
    python3 "${CP_HOME_DIR}/lib/xrdp_ini.py" "${xrdp_ini}.kistengeist.orig" "$mode" >"$xrdp_ini"
    cp_log "xrdp.ini für Modus $mode angepasst."
else
    cp_warn "xrdp.ini nicht gefunden – Standardkonfiguration bleibt."
fi

if [ "$mode" = "rdp" ]; then
    # Debians xorgxrdp nutzt glamor über /dev/dri/renderD128; auf dem Pi (vc4/v3d) ergibt das
    # einen schwarzen Bildschirm. Ohne DRM-Gerät rendert xorgxrdp in Software (zuverlässig).
    xorgconf="${CP_ROOT}/etc/X11/xrdp/xorg.conf"
    if [ -f "$xorgconf" ]; then
        sed -i 's|Option "DRMDevice" ".*"|Option "DRMDevice" ""|' "$xorgconf"
        cp_log "xrdp: DRMDevice abgeschaltet (Software-Rendering)."
    fi

    # Jede RDP-Anmeldung startet die Kistengeist-Oberfläche.
    startwm="${CP_ROOT}/etc/xrdp/startwm.sh"
    if [ -f "$startwm" ] && [ ! -f "${startwm}.kistengeist.orig" ]; then
        cp "$startwm" "${startwm}.kistengeist.orig"
    fi
    cp_write /etc/xrdp/startwm.sh 0755 <<'EOF'
#!/bin/sh
# Von Kistengeist erzeugt: startet die Kistengeist-Oberfläche in der RDP-Sitzung.
if [ -r /etc/profile ]; then
    . /etc/profile
fi
# Über Debians Xsession, damit dieselben Xsession.d-Skripte laufen wie lokal.
exec /etc/X11/Xsession /opt/kistengeist/bin/kistengeist-session
EOF
fi

if [ "$mode" = "both" ]; then
    # VNC-Passwort für die lokale Spiegelung aus dem Setup-Passwort erzeugen.
    # Das Klartext-Passwort liegt nur kurz im RAM (/run) und wird danach gelöscht.
    secret="${CP_SECRET_FILE:-}"
    if [ -n "$secret" ] && [ -s "$secret" ]; then
        if [ "$CP_DRY_RUN" = "1" ]; then
            cp_log "[dry-run] vncpasswd -f > $home/.config/kistengeist/vnc.passwd"
        else
            install -d -o "$CP_USER" -g "$CP_USER" -m 0700 "$home/.config/kistengeist"
            head -n 1 "$secret" | vncpasswd -f >"$home/.config/kistengeist/vnc.passwd" \
                || cp_die "VNC-Passwort konnte nicht erzeugt werden."
            [ -s "$home/.config/kistengeist/vnc.passwd" ] || cp_die "VNC-Passwortdatei ist leer."
            chown "$CP_USER:$CP_USER" "$home/.config/kistengeist/vnc.passwd"
            chmod 0600 "$home/.config/kistengeist/vnc.passwd"
            cp_log "VNC-Passwort für die Spiegelung angelegt."
        fi
    else
        cp_die "Kein Passwort für die RDP-Spiegelung übergeben."
    fi
fi

# Schlüsselbund bei RDP-Anmeldung entsperren, damit Claude angemeldet bleibt.
pam_file="${CP_ROOT}/etc/pam.d/xrdp-sesman"
if [ -f "$pam_file" ] && ! grep -q pam_gnome_keyring "$pam_file"; then
    printf '%s\n' \
        "# Kistengeist: Schlüsselbund entsperren" \
        "-auth optional pam_gnome_keyring.so" \
        "-session optional pam_gnome_keyring.so auto_start" >>"$pam_file"
    cp_log "PAM für xrdp um gnome-keyring ergänzt."
fi

# Unterdrückt die bekannte Passwortabfrage "color managed device" in RDP-Sitzungen.
cp_write /etc/polkit-1/rules.d/45-kistengeist-colord.rules <<'EOF'
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.color-manager.") === 0 &&
        subject.isInGroup("users")) {
        return polkit.Result.YES;
    }
});
EOF

cp_run usermod -aG users "$CP_USER"
cp_enable xrdp.service
