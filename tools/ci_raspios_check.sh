#!/bin/bash
# Prüft das aktuelle offizielle Raspberry Pi OS Lite (64-bit), das das Windows-Werkzeug lädt:
# Prüfsumme, Ersteinrichtung per cloud-init (os_list init_format und cloud-init im Image).
# Stellt Raspberry Pi die Ersteinrichtung um, fällt das hier auf statt erst beim Kunden.
set -euo pipefail
fail=0
err() { echo "::error::$1"; fail=1; }
url="$(curl -sSLI -o /dev/null -w '%{url_effective}' https://downloads.raspberrypi.com/raspios_lite_arm64_latest)"
echo "Aktuell: $url"
[[ "$url" == https://downloads.raspberrypi.com/*.img.xz ]] || { err "unerwartete Adresse"; exit 1; }
curl -fsSL -o /tmp/os.img.xz "$url"
expected="$(curl -fsSL "$url.sha256" | awk '{print $1}')"
echo "$expected  /tmp/os.img.xz" | sha256sum -c - || err "Prüfsumme stimmt nicht"
curl -fsSL https://downloads.raspberrypi.com/os_list_imagingutility_v4.json -o /tmp/os_list.json
python3 - <<'PY' || err "os_list: Lite 64-bit nicht mit cloud-init"
import json
def walk(items):
    for o in items:
        yield o
        yield from walk(o.get("subitems", []))
lite = [o for o in walk(json.load(open("/tmp/os_list.json"))["os_list"]) if "raspios_lite_arm64" in o.get("url", "")]
print([(o["name"], o.get("init_format")) for o in lite])
assert lite and all(str(o.get("init_format", "")).startswith("cloudinit") for o in lite)
PY
xz -dc /tmp/os.img.xz > /tmp/os.img
loop="$(sudo losetup -fP --show /tmp/os.img)"
sudo mkdir -p /mnt/r /mnt/b
sudo mount -o ro "${loop}p2" /mnt/r
sudo mount -o ro "${loop}p1" /mnt/b
[ -x /mnt/r/usr/bin/cloud-init ] || err "cloud-init fehlt im Image"
ls /mnt/r/etc/cloud/cloud.cfg.d/ || true
grep -rqs 'NoCloud' /mnt/r/etc/cloud/ || err "NoCloud-Datenquelle nicht konfiguriert"
[ -x /mnt/r/usr/bin/curl ] || err "curl fehlt im Image (Erststart braucht es)"
[ -f /mnt/b/cmdline.txt ] || err "cmdline.txt fehlt"
echo "Image-Größe entpackt: $(du -h /tmp/os.img | cut -f1)"
sudo umount /mnt/r /mnt/b
sudo losetup -d "$loop"
rm -f /tmp/os.img /tmp/os.img.xz
[ "$fail" = 0 ] && echo "Raspberry Pi OS Lite: Ersteinrichtung per cloud-init bestätigt." || exit 1
