#!/bin/bash -e
# Läuft im Image: Rechte setzen, Dienste aktivieren, Benutzer vorbereiten (gemeinsam mit install.sh).

# 01-run.sh kopiert ohne Rechte: deshalb über bash aufrufen.
bash /opt/kistengeist/bin/kistengeist-prepare --image
