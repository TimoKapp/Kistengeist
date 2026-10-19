#!/bin/bash -e
# Kopiert die Kistengeist-Dateien ins Image (ohne Besitzer des Build-Rechners).

# Ohne Rechte des Build-Rechners kopieren: bestehende Ordner wie /etc behalten
# ihre Rechte, neue Dateien bekommen Standardrechte (02-run-chroot.sh setzt den Rest).
find files/rootfs -name __pycache__ -prune -exec rm -rf {} +
cp -R --no-preserve=mode,ownership files/rootfs/. "${ROOTFS_DIR}/"

if [ ! -f "${ROOTFS_DIR}/opt/kistengeist/VERSION" ]; then
	echo "dev" > "${ROOTFS_DIR}/opt/kistengeist/VERSION"
fi
