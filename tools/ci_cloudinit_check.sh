#!/bin/bash
# Prüft die vom Windows-Werkzeug (über den Imager) geschriebenen Ersteinrichtungsdateien mit den
# echten Werkzeugen von Debian 13: cloud-init-Schema, Netplan, Shellcheck des Erststart-Skripts.
set -euo pipefail
dir="${1:?Ordner mit user-data/network-config}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends cloud-init netplan.io python3-yaml shellcheck >/dev/null
fail=0
err() { echo "::error::$1"; fail=1; }
head -n 1 "$dir/user-data" | grep -q '^#cloud-config' || err "user-data ohne #cloud-config"
cloud-init schema -c "$dir/user-data" --annotate || err "cloud-init-Schema meldet Fehler"
mkdir -p /etc/netplan
install -m 600 "$dir/network-config" /etc/netplan/50-kistengeist.yaml
netplan generate || err "Netplan lehnt network-config ab"
python3 - "$dir/user-data" <<'PY' || fail=1
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
files = {f["path"]: f for f in d["write_files"]}
assert d["hostname"] == "kistengeist"
assert d["user"]["name"] == "claude" and d["user"]["lock_passwd"] is True
assert files["/etc/kistengeist/setup-code"]["permissions"] == "0600"
open("/tmp/firstboot.sh", "w").write(files["/usr/local/sbin/kistengeist-firstboot"]["content"])
open("/tmp/firstboot.service", "w").write(files["/etc/systemd/system/kistengeist-firstboot.service"]["content"])
assert ["systemctl", "start", "--no-block", "kistengeist-firstboot.service"] in d["runcmd"]
print("user-data: Inhalt in Ordnung")
PY
shellcheck -S warning /tmp/firstboot.sh || err "Erststart-Skript"
grep -q 'install.sh' /tmp/firstboot.sh || err "Erststart-Skript lädt install.sh nicht"
[ "$fail" = 0 ] && echo "Ersteinrichtung: alle Prüfungen bestanden." || exit 1
