# shellcheck shell=bash
# Anmeldung und Sitzung am angeschlossenen Bildschirm (LightDM).

cp_apt_install_nr lightdm lightdm-gtk-greeter

autologin=""
if [ "$(cp_setting AUTOLOGIN)" = "yes" ]; then
    autologin="autologin-user=${CP_USER}
autologin-user-timeout=0
autologin-session=kistengeist"
fi

cp_write /etc/lightdm/lightdm.conf.d/50-kistengeist.conf <<EOF
# Von Kistengeist erzeugt.
[Seat:*]
user-session=kistengeist
greeter-session=lightdm-gtk-greeter
greeter-hide-users=false
${autologin}
EOF

cp_write /etc/lightdm/lightdm-gtk-greeter.conf <<'EOF'
[greeter]
background=#1f1e1d
theme-name=Adwaita-dark
clock-format=%A, %d. %B  %H:%M
EOF

cp_run systemctl set-default graphical.target
cp_enable lightdm.service
