# shellcheck shell=bash
# Automatische Updates für System, Raspberry-Pi-Pakete, Claude und Chrome.

cp_apt_install_nr unattended-upgrades

cp_write /etc/apt/apt.conf.d/52kistengeist-unattended <<'CONF'
// Von Kistengeist erzeugt.
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,codename=${distro_codename},label=Debian";
        "origin=Debian,codename=${distro_codename}-updates,label=Debian";
        "origin=Debian,codename=${distro_codename},label=Debian-Security";
        "origin=Debian,codename=${distro_codename}-security,label=Debian-Security";
        "origin=Raspberry Pi Foundation,codename=${distro_codename}";
        "site=downloads.claude.ai";
        "site=dl.google.com";
};
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
CONF

cp_write /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
