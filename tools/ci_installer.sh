#!/bin/bash
# Ein-Befehl-Installer (install.sh) echt in Debian 13 arm64 mit systemd als PID 1 testen:
# Schutzprüfungen, Download mit Prüfsumme (falsche Prüfsumme muss abbrechen), Einrichtung,
# Setup-Assistent antwortet auf Port 80, zweiter Lauf funktioniert ebenfalls.
set -euo pipefail
cat >/tmp/Dockerfile <<'DOCKER'
FROM debian:trixie
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends systemd systemd-sysv dbus \
    sudo python3 curl ca-certificates iproute2 procps >/dev/null
CMD ["/sbin/init"]
DOCKER
docker build -q -t kg-installer /tmp
git archive --format=tar.gz --prefix=kistengeist-test/ -o /tmp/kg-src.tar.gz HEAD
docker run -d --name kg --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    -v "$PWD:/repo:ro" -v /tmp/kg-src.tar.gz:/srv/kg-src.tar.gz:ro kg-installer >/dev/null
sleep 5
docker exec kg bash /repo/tools/ci_installer_inner.sh
