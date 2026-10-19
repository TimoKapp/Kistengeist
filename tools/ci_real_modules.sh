#!/bin/bash
# Läuft in debian:trixie (arm64) wie Raspberry Pi OS Lite: Raspberry-Pi-Paketarchiv einbinden,
# alle Debian-Pakete der Module ohne Empfehlungen installieren und die Module mit Fremdquellen
# (Claude Desktop, Chrome, Claude Code, VS Code, Terminal-Panel, Graphify) ECHT ausführen. Danach Befehle,
# Dateien, Bibliotheken und Paketquellen prüfen.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
repo="$(pwd)"
home="$repo/stage-claude/00-install/files/rootfs/opt/kistengeist"
fail=0
err() { echo "::error::$1"; fail=1; }

printf '#!/bin/sh\nexit 101\n' >/usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d
apt-get update
# Grundausstattung, die Raspberry Pi OS Lite immer mitbringt
apt-get install -y --no-install-recommends ca-certificates curl gnupg python3 sudo systemd udev \
    iproute2 kmod procps util-linux mount debconf

echo "== Raspberry-Pi-Paketarchiv (wie pi-gen stage0)"
# Derselbe Schlüsselbund wie im Image (pi-gen, Zweig arm64); der alte raspberrypi.gpg.key ist
# SHA1-gebunden und wird von apt in Debian 13 seit 02/2026 abgelehnt.
curl -fsSLo /usr/share/keyrings/raspberrypi-archive-keyring.pgp \
    https://raw.githubusercontent.com/RPi-Distro/pi-gen/arm64/stage0/00-configure-apt/files/raspberrypi-archive-keyring.pgp
cat >/etc/apt/sources.list.d/raspi.sources <<'SRC'
Types: deb
URIs: http://archive.raspberrypi.com/debian/
Suites: trixie
Components: main
Signed-By: /usr/share/keyrings/raspberrypi-archive-keyring.pgp
SRC
apt-get update

echo "== Debian-Pakete der Module (ohne Empfehlungen)"
# shellcheck disable=SC2046
apt-get install -y --no-install-recommends $(python3 tools/module_packages.py)

echo "== Module mit Fremdquellen echt ausführen"
id claude >/dev/null 2>&1 || useradd -m -s /bin/bash claude
mkdir -p /etc/kistengeist
printf 'MODE="desktop"\nMODULES="claude-desktop chrome claude-code vscode terminal-panel graphify"\nPRIVACY_MINIMAL="yes"\n' \
    >/etc/kistengeist/setup.conf
for m in claude-desktop chrome claude-code vscode terminal-panel graphify; do
    echo "--- Modul $m"
    CP_HOME_DIR="$home" bash -eu -o pipefail -c '. "$1"; cd "$(dirname "$2")"; . "$2"' _ \
        "$home/lib/common.sh" "$home/modules/$m/install.sh" || err "Modul $m scheitert"
done

echo "== Paketquellen fehlerfrei"
out="$(apt-get update 2>&1)" || err "apt-get update scheitert"
echo "$out" | grep -E '^(W|E):' || true
echo "$out" | grep -q '^E:' && err "apt-get update meldet Fehler"

echo "== Programme und Bibliotheken"
command -v claude-desktop >/dev/null || err "claude-desktop fehlt"
command -v google-chrome-stable >/dev/null || command -v chromium >/dev/null || err "Browser fehlt"
command -v code >/dev/null || err "VS Code fehlt"
runuser -u claude -- bash -lc '"$HOME"/.local/bin/claude --version' || err "Claude Code (CLI) startet nicht"
runuser -u claude -- env HOME=/home/claude code --list-extensions | tee /tmp/ext.txt
grep -qi '^anthropic.claude-code$' /tmp/ext.txt || err "VS-Code-Erweiterung Claude Code fehlt"
# Graphify: Skill angemeldet und echter Graph aus Code (lokale AST-Analyse, ohne LLM)
runuser -u claude -- env HOME=/home/claude /home/claude/.local/bin/graphify --version || err "graphify startet nicht"
[ -s /home/claude/.claude/skills/graphify/SKILL.md ] || err "Graphify-Skill fehlt"
grep -q graphify /home/claude/.claude/CLAUDE.md || err "Graphify nicht in ~/.claude/CLAUDE.md angemeldet"
rm -rf /tmp/gfy && mkdir -p /tmp/gfy && cp "$home"/lib/*.py /tmp/gfy/ && chown -R claude:claude /tmp/gfy
(cd /tmp/gfy && runuser -u claude -- env HOME=/home/claude /home/claude/.local/bin/graphify update /tmp/gfy) \
    || err "graphify update scheitert"
python3 -c "import json,sys; g=json.load(open('/tmp/gfy/graphify-out/graph.json')); n=len(g.get('nodes',[])); print('Graphify-Knoten:', n); sys.exit(n < 20)" \
    || err "Graphify-Graph leer"
for f in graph.html GRAPH_REPORT.md; do [ -s "/tmp/gfy/graphify-out/$f" ] || err "Graphify: $f fehlt"; done
sed -n '1,6p' /home/claude/.claude/skills/graphify/SKILL.md
grep -q '^disable-model-invocation: true' /home/claude/.claude/skills/graphify/SKILL.md || err "Graphify-Skill startet selbstständig"
[ "$(stat -c %U /home/claude/.claude/skills/graphify/SKILL.md)" = claude ] || err "Graphify-Skill gehört nicht claude"
# Electron/Chrome laden mitgelieferte Bibliotheken (z. B. libffmpeg.so) aus dem eigenen Ordner:
# deshalb jeden Ordner als Suchpfad mitgeben, so wie es das Programm selbst tut.
missing_libs="$(dpkg -L claude-desktop google-chrome-stable code 2>/dev/null \
    | while read -r f; do
        [ -f "$f" ] && [ -x "$f" ] || continue
        real="$(readlink -f "$f")"   # /usr/bin/… ist oft nur ein Verweis auf den Programmordner
        LD_LIBRARY_PATH="$(dirname "$real")" ldd "$real" 2>/dev/null | grep 'not found' | sed "s|^|$real: |"
    done | sort -u || true)"
cd_real="$(readlink -f "$(command -v claude-desktop)")"
echo "Claude Desktop: $cd_real"
[ -e "$(dirname "$cd_real")/libffmpeg.so" ] || err "libffmpeg.so fehlt neben $cd_real"
[ -z "$missing_libs" ] || { echo "$missing_libs"; err "Fehlende Bibliotheken (Empfehlungen nötig?)"; }

echo "== Befehle, die die Module aufrufen"
for cmd in docker caddy mkfs.exfat sfdisk wipefs blkid lsblk findmnt partprobe udevadm mountpoint mount umount \
           tmux xterm xclip wmctrl ufw iptables qrencode x11vnc vncpasswd udiskie pcmanfm lxterminal zenity \
           openbox tint2 xsetroot xset gnome-keyring-daemon curl gpg qemu-system-aarch64 unattended-upgrade \
           lightdm xrdp xrdp-sesman sshd runuser dbus-launch dbus-update-activation-environment xdg-open \
           modprobe usermod loginctl timeout debconf-set-selections update-alternatives dm-tool pgrep pkill \
           journalctl ip sha256sum visudo; do
    command -v "$cmd" >/dev/null || err "Befehl fehlt: $cmd"
done
for f in /usr/lib/xorg/Xorg /usr/lib/xorg/modules/drivers/modesetting_drv.so \
         /usr/lib/xorg/modules/drivers/xrdpdev_drv.so /usr/share/xgreeters/lightdm-gtk-greeter.desktop \
         /etc/X11/Xsession /etc/xrdp/xrdp.ini /etc/xrdp/startwm.sh /etc/pam.d/xrdp-sesman \
         /etc/X11/xrdp/xorg.conf /usr/libexec/virtiofsd /usr/share/AAVMF/AAVMF_CODE.fd; do
    [ -e "$f" ] || err "Datei fehlt: $f"
done
# Ton/Mikrofon über RDP: Autostart-Eintrag des xrdp-Moduls und sein Ladeskript
pwx=/etc/xdg/autostart/pipewire-xrdp.desktop
if [ -f "$pwx" ]; then
    loader="$(sed -n 's/^Exec=//p' "$pwx" | head -n 1)"
    echo "pipewire-module-xrdp lädt über: $loader"
    [ -e "${loader%% *}" ] || err "Ladeskript von pipewire-module-xrdp fehlt: $loader"
else
    err "pipewire-xrdp.desktop fehlt (Paket pipewire-module-xrdp)"
fi
command -v pactl >/dev/null || err "pactl fehlt"
command -v pw-cli >/dev/null || err "pw-cli fehlt (Ladeskript von pipewire-module-xrdp)"
command -v pw-metadata >/dev/null || err "pw-metadata fehlt"
grep -q 'DRMDevice' /etc/X11/xrdp/xorg.conf || err "xrdp xorg.conf ohne DRMDevice-Zeile (sed im Modul greift nicht)"
for u in docker caddy ufw lightdm xrdp ssh; do
    [ -e "/usr/lib/systemd/system/$u.service" ] || [ -e "/lib/systemd/system/$u.service" ] || err "Unit fehlt: $u.service"
done
docker compose version
udiskie --version
x11vnc -version >/dev/null 2>&1 || true
[ "$(printf 'abcdef\n' | vncpasswd -f | wc -c)" -gt 0 ] || err "vncpasswd -f liefert nichts"
python3 -c "import tkinter, bcrypt" || err "python3-tk/bcrypt fehlen"
printf ':8080 {\n\troot * /srv\n\tfile_server\n}\n' >/tmp/Caddyfile
caddy validate --adapter caddyfile --config /tmp/Caddyfile || err "caddy validate"

[ "$fail" = 0 ] && echo "Alle Prüfungen bestanden." || exit 1
