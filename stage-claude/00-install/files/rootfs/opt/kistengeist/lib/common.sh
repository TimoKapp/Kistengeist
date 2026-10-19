# shellcheck shell=bash
# Gemeinsame Hilfsfunktionen für Installer und Module von Kistengeist.
#
# Umgebungsvariablen:
#   CP_ROOT     Präfix für alle Dateipfade (leer auf dem Pi, ein Testordner in Tests)
#   CP_DRY_RUN  1 = Befehle nur protokollieren, nicht ausführen (für Tests)
#   CP_LOG      Logdatei (Standard: /var/log/kistengeist/install.log)

CP_ROOT="${CP_ROOT:-}"
CP_DRY_RUN="${CP_DRY_RUN:-0}"
CP_HOME_DIR="${CP_HOME_DIR:-/opt/kistengeist}"
CP_ETC="${CP_ROOT}/etc/kistengeist"
CP_USER="${CP_USER:-claude}"
CP_LOG="${CP_LOG:-${CP_ROOT}/var/log/kistengeist/install.log}"

export DEBIAN_FRONTEND=noninteractive

cp_log() {
    local msg
    msg="$(date '+%Y-%m-%d %H:%M:%S') $*"
    mkdir -p "$(dirname "$CP_LOG")"
    printf '%s\n' "$msg" >>"$CP_LOG"
    printf '%s\n' "$msg"
}

cp_warn() { cp_log "WARNUNG: $*"; }

cp_die() {
    cp_log "FEHLER: $*"
    exit 1
}

# Führt einen Befehl aus (oder protokolliert ihn im Testmodus).
cp_run() {
    if [ "$CP_DRY_RUN" = "1" ]; then
        cp_log "[dry-run] $*"
        return 0
    fi
    cp_log "+ $*"
    "$@" >>"$CP_LOG" 2>&1
}

# Wie cp_run, aber als Sitzungsbenutzer.
cp_run_as_user() {
    if [ "$CP_DRY_RUN" = "1" ]; then
        cp_log "[dry-run] (als $CP_USER) $*"
        return 0
    fi
    cp_log "+ (als $CP_USER) $*"
    runuser -u "$CP_USER" -- env HOME="$(cp_user_home)" "$@" >>"$CP_LOG" 2>&1
}

cp_user_home() {
    if [ "$CP_DRY_RUN" = "1" ]; then
        printf '%s/home/%s' "$CP_ROOT" "$CP_USER"
        return
    fi
    getent passwd "$CP_USER" | cut -d: -f6
}

# Schreibt stdin in eine Datei unterhalb von CP_ROOT.
#   cp_write /etc/foo.conf [modus]
cp_write() {
    local target="${CP_ROOT}$1" mode="${2:-0644}"
    mkdir -p "$(dirname "$target")"
    cat >"$target"
    chmod "$mode" "$target"
    cp_log "Datei geschrieben: $1"
}

# Wiederholt einen Befehl bei Netzwerkfehlern (3 Versuche).
cp_retry() {
    local n=1
    until cp_run "$@"; do
        if [ "$n" -ge 3 ]; then
            return 1
        fi
        cp_warn "Versuch $n fehlgeschlagen, neuer Versuch in $((n * 10)) s: $*"
        [ "$CP_DRY_RUN" = "1" ] || sleep $((n * 10))
        n=$((n + 1))
    done
}

APT_OPTS=(-o DPkg::Lock::Timeout=600)

# Eine kurz nicht erreichbare oder falsch signierte Fremdquelle darf nicht jedes spätere Modul
# abbrechen: Fehler beim Aktualisieren werden gemeldet; fehlt dadurch ein Paket, scheitert erst
# dessen Installation (mit klarer Meldung).
cp_apt_update() {
    cp_retry apt-get "${APT_OPTS[@]}" update || cp_warn "apt-get update meldete Fehler (siehe Protokoll) – fahre fort."
}

# Uhrzeit sicherstellen: der Pi hat keine Echtzeituhr. Ohne richtige Zeit scheitern apt
# ("Release file is not valid yet") und HTTPS. Erst auf NTP warten, sonst die Zeit aus dem
# Date-Kopf eines HTTP-Servers übernehmen (auch wenn NTP/UDP 123 gesperrt ist).
cp_ensure_time() {
    [ "$CP_DRY_RUN" = "1" ] && { cp_log "[dry-run] Uhrzeit prüfen"; return 0; }
    local i synced
    for i in $(seq 1 30); do
        synced="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)"
        [ "$synced" = "yes" ] && { cp_log "Uhrzeit per NTP synchronisiert."; return 0; }
        [ "$i" = 1 ] && cp_log "Warte auf Zeitsynchronisierung (NTP) …"
        sleep 3
    done
    local http_date
    http_date="$(curl -sI --max-time 15 http://deb.debian.org/ 2>/dev/null | tr -d '\r' | sed -n 's/^[Dd]ate: //p' | head -n 1)"
    if [ -n "$http_date" ] && date -s "$http_date" >/dev/null 2>&1; then
        cp_log "Uhrzeit aus dem Internet übernommen: $(date)"
    else
        cp_warn "Uhrzeit konnte nicht geprüft werden (aktuell: $(date))."
    fi
}

cp_apt_install() {
    cp_retry apt-get "${APT_OPTS[@]}" install -y -o Dpkg::Options::=--force-confdef \
        -o Dpkg::Options::=--force-confold "$@"
}

cp_apt_install_nr() {
    cp_apt_install --no-install-recommends "$@"
}

# Prüft, ob ein Paket in den Paketquellen existiert.
cp_apt_available() {
    if [ "$CP_DRY_RUN" = "1" ]; then
        return 0
    fi
    apt-cache show "$1" >/dev/null 2>&1
}

cp_enable() {
    cp_run systemctl enable "$@"
}

cp_disable() {
    cp_run systemctl disable "$@"
}

# Liest einen Wert aus /etc/kistengeist/setup.conf.
cp_setting() {
    local key="$1" file="${CP_ETC}/setup.conf"
    [ -f "$file" ] || return 0
    sed -n "s/^${key}=//p" "$file" | tail -n 1 | tr -d '"'
}

cp_module_selected() {
    case " $(cp_setting MODULES) " in
        *" $1 "*) return 0 ;;
    esac
    return 1
}

cp_mode() { cp_setting MODE; }

cp_mode_has_local() {
    case "$(cp_mode)" in desktop | both) return 0 ;; esac
    return 1
}

cp_mode_has_rdp() {
    case "$(cp_mode)" in rdp | both) return 0 ;; esac
    return 1
}
