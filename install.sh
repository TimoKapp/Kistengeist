#!/bin/bash
# Kistengeist – Installation mit einem Befehl auf Raspberry Pi OS Lite (64-bit, Debian 13 „Trixie“).
#
#   curl -fsSL https://raw.githubusercontent.com/TimoKapp/kistengeist/main/install.sh | sudo bash
#
# Lädt Kistengeist von GitHub, richtet den Setup-Assistenten ein und startet ihn. Alles Weitere
# (Claude Desktop, Browser, Module) wählst und installierst du danach im Browser unter
# http://kistengeist.local – genau wie beim fertigen Image.
#
# Einstellungen (Umgebungsvariablen, alle optional):
#   KG_REF=<tag|branch>        Version (Standard: main; die Datei aus einem Release ist darauf festgelegt)
#   KG_SHA256=<prüfsumme>      Prüfsumme des Quellarchivs (im Release-Installer gesetzt)
#   KG_KEEP_HOSTNAME=1         Gerätenamen nicht auf „kistengeist“ ändern
#   KG_SOURCE=<ordner>         Quellen aus einem lokalen Ordner statt von GitHub (Entwicklung/Tests)
#   KG_ARCHIVE_URL=<url>       Quellarchiv von anderer Adresse (Spiegel/Tests; mit KG_SHA256 prüfen)
#   KG_ALLOW_ANY_HW=1          auch ohne Raspberry Pi 4/5 (nur Tests)
#   KG_MIN_FREE_MB=<mb>        nötiger freier Speicher (Standard 6144)
#   KG_START_CONSOLE=1         Einrichtungsanzeige (Adresse, Code, QR) sofort auf dem Bildschirm zeigen
#                              (setzt das Windows-Werkzeug beim ersten Start; nicht bei Anmeldung an tty1)
#
# Raspberry Pi is a trademark of Raspberry Pi Ltd. Claude is a trademark of Anthropic, PBC.
# Kistengeist ist ein unabhängiges Projekt und nicht mit diesen Unternehmen verbunden.

# Arbeitsordner global, damit die Aufräum-Falle ihn auch nach dem Ende von main() noch kennt.
KG_WORK=""
cleanup() { [ -z "$KG_WORK" ] || rm -rf "$KG_WORK"; }

# Alles steckt in main(), damit bei „curl | bash“ nichts halb Geladenes ausgeführt wird.
main() {
    set -euo pipefail
    local repo="${KG_REPO:-TimoKapp/kistengeist}"
    local ref="${KG_REF:-main}"
    local sha="${KG_SHA256:-}"
    local log=/var/log/kistengeist/install-script.log

    say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
    die() { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

    # --- Voraussetzungen ---------------------------------------------------------------------
    [ "$(id -u)" = 0 ] || die "Bitte mit sudo starten:  curl -fsSL … | sudo bash"
    [ "$(uname -m)" = aarch64 ] || die "Nur 64-bit-Systeme (arm64). Bitte Raspberry Pi OS Lite (64-bit) verwenden."
    # shellcheck disable=SC1091
    . /etc/os-release
    [ "${ID:-}" = debian ] && [ "${VERSION_CODENAME:-}" = trixie ] \
        || die "Nur Raspberry Pi OS Lite auf Basis von Debian 13 (Trixie) wird unterstützt (gefunden: ${PRETTY_NAME:-unbekannt})."
    local model=""
    [ -r /proc/device-tree/model ] && model="$(tr -d '\0' </proc/device-tree/model)"
    case "$model" in
        "Raspberry Pi 4"*|"Raspberry Pi 5"*) ;;   # auch Pi 400
        *) [ "${KG_ALLOW_ANY_HW:-}" = 1 ] || die "Unterstützt: Raspberry Pi 4/400/5 (gefunden: ${model:-unbekannt})." ;;
    esac
    [ ! -e /etc/kistengeist/installed ] || die "Kistengeist ist hier bereits eingerichtet."
    for dm in lightdm gdm3 sddm; do
        if dpkg-query -W -f='${Status}' "$dm" 2>/dev/null | grep -q 'ok installed'; then
            die "Hier ist eine Desktop-Version installiert ($dm). Bitte Raspberry Pi OS Lite (64-bit) frisch aufspielen."
        fi
    done
    local free_kb
    free_kb="$(df --output=avail -k / | tail -n 1)"
    local min_mb="${KG_MIN_FREE_MB:-6144}"
    [ "$free_kb" -ge $((min_mb * 1024)) ] \
        || die "Zu wenig freier Speicher (mindestens $((min_mb / 1024)) GB nötig, frei: $((free_kb / 1024)) MB)."
    # Ein früherer Lauf hat den Assistenten evtl. schon gestartet: der darf Port 80 belegen.
    systemctl stop kistengeist-setup.service 2>/dev/null || true
    if ss -Hltn 'sport = :80' 2>/dev/null | grep -q .; then
        die "Port 80 ist belegt (läuft schon ein Webserver?). Der Setup-Assistent braucht diesen Port."
    fi

    mkdir -p /var/log/kistengeist
    exec > >(tee -a "$log") 2>&1
    say "Kistengeist wird eingerichtet ($(date '+%d.%m.%Y %H:%M'), Version $ref)"

    # --- Uhrzeit (der Pi hat keine Echtzeituhr) und erster Start ---------------------------------
    if command -v cloud-init >/dev/null; then
        say "Warte, bis die Ersteinrichtung von Raspberry Pi OS fertig ist"
        cloud-init status --wait >/dev/null 2>&1 || true
    fi
    local _
    for _ in $(seq 1 30); do
        [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = yes ] && break
        sleep 2
    done
    if [ "$(date +%Y)" -lt 2026 ]; then
        local web_date
        web_date="$(curl -sI --max-time 10 https://github.com | sed -n 's/^[Dd]ate: //p' | tr -d '\r' || true)"
        [ -n "$web_date" ] && date -s "$web_date" >/dev/null 2>&1 || true
    fi

    # --- Grundpakete (wie im Image) -----------------------------------------------------------
    export DEBIAN_FRONTEND=noninteractive
    local apt_opts=(-o DPkg::Lock::Timeout=600)
    say "Paketlisten aktualisieren"
    apt-get "${apt_opts[@]}" update
    say "Grundpakete installieren"
    apt-get "${apt_opts[@]}" install -y --no-install-recommends python3 qrencode avahi-daemon network-manager curl gnupg \
        ca-certificates dnsmasq-base polkitd tar

    # --- Quellen holen --------------------------------------------------------------------------
    local work src
    work="$(mktemp -d /tmp/kistengeist.XXXXXX)"
    KG_WORK="$work"
    trap cleanup EXIT
    if [ -n "${KG_SOURCE:-}" ]; then
        src="$KG_SOURCE"
        [ -d "$src/stage-claude/00-install/files/rootfs" ] || die "KG_SOURCE ist kein Kistengeist-Ordner: $src"
    else
        say "Kistengeist ($ref) von GitHub laden"
        curl -fsSL --retry 3 -o "$work/src.tar.gz" "${KG_ARCHIVE_URL:-https://codeload.github.com/${repo}/tar.gz/${ref}}" \
            || die "Download fehlgeschlagen (Internet? Gibt es die Version $ref?)."
        if [ -n "$sha" ]; then
            echo "$sha  $work/src.tar.gz" | sha256sum -c --quiet - || die "Prüfsumme stimmt nicht – Abbruch."
        fi
        mkdir "$work/src"
        tar -xzf "$work/src.tar.gz" -C "$work/src" --strip-components=1
        src="$work/src"
    fi
    local rootfs="$src/stage-claude/00-install/files/rootfs"
    [ -f "$rootfs/opt/kistengeist/bin/kistengeist-prepare" ] || die "Quellen unvollständig."

    # --- Dateien und Vorbereitung (wie im Image) ----------------------------------------------
    say "Dateien kopieren"
    # Alte Programmdateien ersetzen statt überlagern (Einstellungen liegen in /etc/kistengeist).
    rm -rf /opt/kistengeist
    cp -R --no-preserve=mode,ownership "$rootfs/." /
    find /opt/kistengeist -name __pycache__ -prune -exec rm -rf {} +
    if [ -f "$src/VERSION" ]; then
        cp "$src/VERSION" /opt/kistengeist/VERSION
    else
        echo "$ref" >/opt/kistengeist/VERSION
    fi
    say "System vorbereiten"
    bash /opt/kistengeist/bin/kistengeist-prepare --live
    systemctl daemon-reload

    if [ "${KG_KEEP_HOSTNAME:-}" != 1 ] && [ "$(hostname)" != kistengeist ]; then
        say "Gerätename: kistengeist (Adresse http://kistengeist.local)"
        local old
        old="$(hostname)"
        hostnamectl set-hostname kistengeist 2>/dev/null || echo kistengeist >/etc/hostname
        hostname kistengeist 2>/dev/null || true
        # cloud-init (Raspberry Pi Imager) würde den alten Namen beim nächsten Start zurückschreiben.
        if [ -d /etc/cloud/cloud.cfg.d ]; then
            printf 'preserve_hostname: true\nmanage_etc_hosts: false\n' >/etc/cloud/cloud.cfg.d/99-kistengeist.cfg
        fi
        if grep -q '^127\.0\.1\.1' /etc/hosts; then
            sed -i "s/^127\.0\.1\.1.*/127.0.1.1\tkistengeist/" /etc/hosts
        else
            printf '127.0.1.1\tkistengeist\n' >>/etc/hosts
        fi
        echo "(vorher: $old)"
        systemctl restart avahi-daemon.service 2>/dev/null || true
    fi

    # Ohne WLAN-Land bleibt WLAN gesperrt und das Einrichtungs-WLAN könnte nicht starten.
    if command -v raspi-config >/dev/null && [ -z "$(raspi-config nonint get_wifi_country 2>/dev/null || true)" ]; then
        raspi-config nonint do_wifi_country DE >/dev/null 2>&1 || true
    fi
    # Wer per SSH installiert, soll SSH auch nach der Einrichtung behalten (Firewall-Modul).
    if systemctl is-enabled ssh.service >/dev/null 2>&1; then
        touch /etc/kistengeist/keep-ssh
    fi

    # --- Setup-Assistent starten ----------------------------------------------------------------
    say "Setup-Assistent starten"
    systemctl start avahi-daemon.service 2>/dev/null || true
    systemctl start kistengeist-setup.service
    local ok=""
    for _ in $(seq 1 30); do
        if curl -fs -o /dev/null http://127.0.0.1/; then ok=1; break; fi
        sleep 1
    done
    [ -n "$ok" ] || die "Setup-Assistent antwortet nicht (Protokoll: journalctl -u kistengeist-setup)."

    if [ "${KG_START_CONSOLE:-}" = 1 ]; then
        systemctl start kistengeist-console.service 2>/dev/null || true
    fi

    local ips code
    ips="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' | head -n 2 | sed 's|^|http://|' | tr '\n' ' ' || true)"
    code="$(/opt/kistengeist/bin/kistengeist-setupcode)"
    echo
    say "Fertig vorbereitet. Öffne jetzt auf PC oder Handy im selben Netz:"
    echo "      http://$(hostname).local    ${ips}"
    echo "    Einrichtungscode: $code"
    echo "    Dort wählst du Module, Passwort und Region; danach startet der Pi neu."
    echo "    Protokoll: $log"
}

main "$@"
