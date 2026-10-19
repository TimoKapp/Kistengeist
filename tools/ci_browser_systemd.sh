#!/bin/bash
# Browser-Zugang mit echtem systemd (PID 1) in Debian 13 arm64: Linger, Benutzerdienste in der
# richtigen Reihenfolge, EnvironmentFile mit Sonderzeichen-Passwort, Oberfläche (Openbox, Leiste) im Dienst.
set -euo pipefail
cat >/tmp/Dockerfile <<'DOCKER'
FROM debian:trixie
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends systemd systemd-sysv dbus \
    dbus-user-session sudo python3 curl ca-certificates openbox tint2 gnome-keyring x11-xserver-utils \
    zenity dbus-x11 procps >/dev/null
CMD ["/sbin/init"]
DOCKER
docker build -q -t cpi-systemd /tmp
docker run -d --name cpi --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    -v "$PWD:/repo" cpi-systemd >/dev/null
sleep 5
docker exec cpi bash /repo/tools/ci_browser_systemd_inner.sh
