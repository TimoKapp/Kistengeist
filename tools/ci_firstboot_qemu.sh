#!/bin/bash
# Echter Erststart wie beim Kunden: das aktuelle Raspberry Pi OS Lite (64-bit) mit den Dateien,
# die der Raspberry Pi Imager im Windows-Test auf die Karte geschrieben hat (user-data,
# network-config, meta-data, cmdline.txt), in QEMU starten. Erfolgreich, wenn danach der
# Setup-Assistent von außen erreichbar ist und den Einrichtungscode verlangt.
#
# Abweichungen vom echten Pi (nur, weil QEMU keinen Pi 4 mit Netzwerk nachbilden kann):
# Debian-Kernel statt Pi-Kernel (Maschine „virt“, Gerätebaum mit Modellname „Raspberry Pi 4“),
# Partition vorab vergrößert, Installer und Quellen dieses Commits über einen lokalen Server.
#
#   tools/ci_firstboot_qemu.sh <ordner mit user-data, network-config, meta-data, cmdline.txt>
set -euo pipefail
art="$(cd "$1" && pwd)"
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="${RUNNER_TEMP:-/tmp}/kg-qemu"
mkdir -p "$work"
cd "$work"
log() { echo "::group::$*"; }
end() { echo "::endgroup::"; }

for f in user-data network-config meta-data cmdline.txt; do
    [ -s "$art/$f" ] || { echo "::error::$f fehlt im Imager-Ergebnis"; exit 1; }
done

log "Werkzeuge"
sudo apt-get update -qq
sudo apt-get install -y -qq qemu-system-arm qemu-utils device-tree-compiler parted e2fsprogs zstd >/dev/null
end

log "Raspberry Pi OS Lite (64-bit), aktuell"
url="$(curl -sSLI -o /dev/null -w '%{url_effective}' https://downloads.raspberrypi.com/raspios_lite_arm64_latest)"
echo "$url"
curl -fsSL -o os.img.xz "$url"
echo "$(curl -fsSL "$url.sha256" | awk '{print $1}')  os.img.xz" | sha256sum -c -
xz -d -f os.img.xz
end

log "Debian-Kernel und busybox (arm64)"
curl -fsSL -o Packages.xz https://deb.debian.org/debian/dists/trixie/main/binary-arm64/Packages.xz
python3 - <<'PY' >debs.txt
import lzma, re
pkgs = {}
for block in lzma.open("Packages.xz", "rt").read().split("\n\n"):
    f = dict(re.findall(r"^([A-Za-z-]+): (.*)$", block, re.M))
    if "Package" in f:
        pkgs[f["Package"]] = f
kern = sorted(p for p in pkgs if re.fullmatch(r"linux-image-\d[\d.]*[^ ]*-arm64", p) and "-rt-" not in p and "-cloud-" not in p)
print(pkgs[kern[-1]]["Filename"])
print(pkgs["busybox-static"]["Filename"])
PY
cat debs.txt
rm -rf kdeb bb
mkdir kdeb bb
curl -fsSL -o kernel.deb "https://deb.debian.org/debian/$(sed -n 1p debs.txt)"
curl -fsSL -o busybox.deb "https://deb.debian.org/debian/$(sed -n 2p debs.txt)"
dpkg-deb -x kernel.deb kdeb
dpkg-deb -x busybox.deb bb
moddir="$(find kdeb/usr/lib/modules kdeb/lib/modules -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -n 1 || true)"
[ -n "$moddir" ] || { echo "::error::Kernel-Module nicht gefunden"; exit 1; }
kver="$(basename "$moddir")"
echo "Kernel $kver"
# vmlinuz ist bei Debian ein EFI-zboot- oder gzip-Abbild: für -kernel das rohe Image auspacken.
python3 - "kdeb/boot/vmlinuz-$kver" Image <<'PY'
import gzip, struct, subprocess, sys
data = open(sys.argv[1], "rb").read()
if data[:2] == b"MZ" and data[4:8] == b"zimg":
    off, size = struct.unpack_from("<II", data, 8)
    payload, kind = data[off:off + size], data[24:32].rstrip(b"\0")
    data = gzip.decompress(payload) if kind == b"gzip" else \
        subprocess.run(["zstd", "-d", "-c"], input=payload, capture_output=True, check=True).stdout
elif data[:2] == b"\x1f\x8b":
    data = gzip.decompress(data)
open(sys.argv[2], "wb").write(data)
PY
end

log "Kleines initramfs (virtio-Platte, ext4)"
depmod -b "$(dirname "$(dirname "$(dirname "$moddir")")")" "$kver" 2>/dev/null \
    || depmod -b "$(dirname "$(dirname "$moddir")")" "$kver"
rm -rf initrd
mkdir -p initrd/bin initrd/mods initrd/dev initrd/proc initrd/sys initrd/root
bbin="$(find bb/usr/bin bb/bin -maxdepth 1 -name busybox -type f 2>/dev/null | head -n 1 || true)"
file "$bbin" | grep -q 'ARM aarch64' || { echo "::error::busybox (arm64) nicht gefunden: $bbin"; exit 1; }
install -m 0755 "$bbin" initrd/bin/busybox
python3 - "$moddir" initrd/mods <<'PY' >initrd/mods/order
import lzma, os, re, shutil, subprocess, sys
moddir, out = sys.argv[1:]
deps = {}
for line in open(os.path.join(moddir, "modules.dep")):
    mod, _, rest = line.partition(":")
    deps[mod] = rest.split()
name = {re.sub(r"\.ko(\.xz|\.zst)?$", "", os.path.basename(m)).replace("-", "_"): m for m in deps}
order, seen = [], set()
def add(m):
    if m in seen:
        return
    seen.add(m)
    for d in deps[m]:
        add(d)
    order.append(m)
for want in ("virtio_pci", "virtio_blk", "ext4", "crc32c_generic"):
    if want in name:
        add(name[want])
for m in order:
    src, dst = os.path.join(moddir, m), os.path.join(out, os.path.basename(m))
    if m.endswith(".xz"):
        open(dst[:-3], "wb").write(lzma.open(src).read()); dst = dst[:-3]
    elif m.endswith(".zst"):
        open(dst[:-4], "wb").write(subprocess.run(["zstd", "-d", "-c", src], capture_output=True, check=True).stdout)
        dst = dst[:-4]
    else:
        shutil.copy(src, dst)
    print(os.path.basename(dst))
PY
cat initrd/mods/order
cat >initrd/init <<'EOF'
#!/bin/busybox sh
/bin/busybox --install -s /bin
mount -t proc proc /proc; mount -t sysfs sys /sys; mount -t devtmpfs dev /dev
for m in $(cat /mods/order); do insmod /mods/$m 2>/dev/null; done
for _ in $(seq 1 50); do [ -b /dev/vda2 ] && break; sleep 0.2; done
mount -o rw /dev/vda2 /root || { echo "Wurzelpartition fehlt"; exec sh; }
umount /proc /sys; mount --move /dev /root/dev 2>/dev/null || umount /dev
exec switch_root /root /sbin/init
EOF
chmod +x initrd/init
(cd initrd && find . | cpio -o -H newc --quiet | gzip -1) >initrd.img
end

log "Karte vorbereiten: Imager-Dateien, Kernel-Module, Partition vergrößern"
truncate -s 16G os.img
sudo parted -s os.img resizepart 2 100%
loop="$(sudo losetup -fP --show os.img)"
sudo e2fsck -fy "${loop}p2" >/dev/null || true
sudo resize2fs "${loop}p2" >/dev/null
sudo mkdir -p mnt/boot mnt/root
sudo mount "${loop}p1" mnt/boot
sudo mount "${loop}p2" mnt/root
# Installer und Quellen dieses Commits lokal anbieten (wie im Release festgelegt).
mkdir -p srv
git -C "$repo" archive --format=tar.gz --prefix=kistengeist/ -o "$work/srv/src.tar.gz" HEAD
# shellcheck disable=SC2016  # bewusst wörtlich: wird erst im Installer ausgewertet
pin=': "${KG_REF:=ci}" "${KG_ARCHIVE_URL:=http://10.0.2.2:8000/src.tar.gz}" "${KG_SHA256:=@SHA@}"'
sed "1a ${pin/@SHA@/$(sha256sum srv/src.tar.gz | cut -d' ' -f1)}" "$repo/install.sh" >srv/install.sh
sed -E 's#^( *url=")[^"]*(")#\1http://10.0.2.2:8000/install.sh\2#' "$art/user-data" >user-data
grep -q 'url="http://10.0.2.2:8000/install.sh"' user-data || { echo "::error::Installer-Adresse nicht gefunden"; exit 1; }
sudo cp user-data "$art/network-config" "$art/meta-data" "$art/cmdline.txt" mnt/boot/
echo "cmdline.txt (vom Imager): $(cat "$art/cmdline.txt")"
echo "--- user-data (vom Imager)"; cat user-data; echo
code="$(python3 - user-data <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
print([f for f in doc["write_files"] if f["path"] == "/etc/kistengeist/setup-code"][0]["content"].strip())
PY
)"
[ "${#code}" = 10 ] || { echo "::error::Einrichtungscode nicht in user-data"; exit 1; }
sudo mkdir -p "mnt/root/usr/lib/modules"
sudo cp -a "$moddir" "mnt/root/usr/lib/modules/"
sudo umount mnt/boot mnt/root
sudo losetup -d "$loop"
end

# Kernel-Kommandozeile: die des Imagers, nur Konsole/Wurzel auf die virtuelle Maschine angepasst.
append="console=ttyAMA0 root=/dev/vda2 rw net.ifnames=0"
read -ra imager_args <"$art/cmdline.txt" || true   # ohne Zeilenende am Dateiende
for a in "${imager_args[@]}"; do
    case "$a" in console=*|root=*|init=*|quiet|splash|plymouth.*) ;; *) append="$append $a" ;; esac
done
echo "Kernel-Kommandozeile: $append"

qemu=(qemu-system-aarch64 -M virt -cpu cortex-a72 -smp 4 -m 4096 -accel "tcg,thread=multi")
"${qemu[@]}" -machine dumpdtb=virt.dtb >/dev/null 2>&1
dtc -q -I dtb -O dts virt.dtb | sed 's/model = "linux,dummy-virt"/model = "Raspberry Pi 4 Model B Rev 1.5"/' >virt.dts
grep -q 'Raspberry Pi 4' virt.dts
dtc -q -I dts -O dtb -o pi.dtb virt.dts

(cd srv && python3 -m http.server 8000 --bind 127.0.0.1 >../http.log 2>&1) &
srvpid=$!

log "Start (Ausgabe der seriellen Konsole: serial.log)"
"${qemu[@]}" -dtb pi.dtb -kernel Image -initrd initrd.img -append "$append" \
    -drive file=os.img,format=raw,if=virtio \
    -netdev user,id=n0,hostfwd=tcp:127.0.0.1:8080-:80 -device virtio-net-pci,netdev=n0 \
    -display none -serial file:serial.log -monitor none &
qpid=$!
end

ok=""
start=$SECONDS
while [ $((SECONDS - start)) -lt 5400 ]; do
    kill -0 "$qpid" 2>/dev/null || { echo "::error::QEMU wurde beendet"; break; }
    grep -q 'Kernel panic' serial.log && { echo "::error::Kernel panic"; break; }
    if curl -fs -o /dev/null --max-time 10 http://127.0.0.1:8080/api/info; then ok=1; break; fi
    sleep 30
    echo "$(( (SECONDS - start) / 60 )) min: $(tail -n 1 serial.log | tr -cd '[:print:]' | cut -c1-150)"
done

fail=0
if [ -n "$ok" ]; then
    echo "Setup-Assistent nach $(( (SECONDS - start) / 60 )) Minuten erreichbar."
    page="$(curl -fsS http://127.0.0.1:8080/ || true)"
    [[ "$page" == *code-gate* ]] || { echo "::error::Startseite unvollständig"; fail=1; }
    st="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/status)"
    [ "$st" = 401 ] || [ "$st" = 403 ] || { echo "::error::/api/status ohne Code: $st"; fail=1; }
    st="$(curl -s -o /dev/null -w '%{http_code}' -H "X-Setup-Code: $code" http://127.0.0.1:8080/api/status)"
    [ "$st" = 200 ] || { echo "::error::/api/status mit Code: $st"; fail=1; }
else
    echo "::error::Setup-Assistent nach dem Erststart nicht erreichbar"
    fail=1
fi

kill "$qpid" "$srvpid" 2>/dev/null || true
wait "$qpid" 2>/dev/null || true
log "Protokolle aus der Karte"
loop="$(sudo losetup -fP --show os.img)"
sudo mount -o ro "${loop}p2" mnt/root
for f in var/log/kistengeist-firstboot.log var/log/kistengeist/install-script.log var/log/cloud-init-output.log; do
    echo "--- /$f"; sudo tail -n 60 "mnt/root/$f" 2>/dev/null || echo "(fehlt)"
done
sudo cat mnt/root/etc/hostname 2>/dev/null || true
sudo umount mnt/root
sudo losetup -d "$loop"
echo "--- serial.log (Ende)"; tail -n 80 serial.log | tr -cd '[:print:]\n'
end
[ "$fail" = 0 ] && echo "Erststart wie beim Kunden: Setup-Assistent erreichbar und geschützt." || exit 1
