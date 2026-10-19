# shellcheck shell=bash
# SSH-Server aktivieren (in Raspberry Pi OS Lite bereits installiert).

cp_apt_install_nr openssh-server
cp_enable ssh.service
