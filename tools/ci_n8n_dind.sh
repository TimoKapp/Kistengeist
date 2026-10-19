#!/bin/bash
# n8n-Test mit denselben Docker-Paketen wie auf dem Pi (Debian 13: docker.io 26, compose 2.26):
# läuft in einem privilegierten debian:trixie-Container mit eigenem dockerd.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends docker.io docker-cli docker-compose python3 python3-bcrypt \
    curl iptables ca-certificates sudo procps
dockerd >/tmp/dockerd.log 2>&1 &
for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 1; done
docker info >/dev/null || { cat /tmp/dockerd.log; exit 1; }
docker version --format 'Docker {{.Server.Version}}'
docker compose version
bash tools/ci_n8n_e2e.sh
