#!/bin/bash
# Baut das Image lokal mit pi-gen in Docker (Linux-Rechner mit Docker nötig).
# Einfacher: GitHub Actions baut es automatisch (siehe README).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
work="${here}/pi-gen"

if [ ! -d "$work" ]; then
    git clone --depth 1 --branch arm64 https://github.com/RPi-Distro/pi-gen.git "$work"
fi

version="$(git -C "$here" describe --tags --always 2>/dev/null || echo dev)"
echo "$version" >"${here}/stage-claude/00-install/files/rootfs/opt/kistengeist/VERSION"

# Zufälliges Passwort nur für den Bau; der Benutzer wird im Image gesperrt
# und erhält sein Passwort im Setup-Assistenten.
pw="$(openssl rand -hex 24)"

rm -rf "${work}/stage-claude"
cp -R "${here}/stage-claude" "${work}/stage-claude"
touch "${work}/stage2/SKIP_IMAGES"

cat >"${work}/config" <<CONF
IMG_NAME=kistengeist
RELEASE=trixie
STAGE_LIST="stage0 stage1 stage2 stage-claude"
TARGET_HOSTNAME=kistengeist
FIRST_USER_NAME=claude
FIRST_USER_PASS=${pw}
DISABLE_FIRST_BOOT_USER_RENAME=1
ENABLE_SSH=0
LOCALE_DEFAULT=de_DE.UTF-8
KEYBOARD_KEYMAP=de
KEYBOARD_LAYOUT="German"
TIMEZONE_DEFAULT=Europe/Berlin
WPA_COUNTRY=DE
DEPLOY_COMPRESSION=zip
CONF

cd "$work"
./build-docker.sh
echo "Fertig. Image liegt in ${work}/deploy/"
