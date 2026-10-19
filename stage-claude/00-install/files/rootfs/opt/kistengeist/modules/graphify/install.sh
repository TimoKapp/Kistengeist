# shellcheck shell=bash
# Graphify (https://github.com/safishamsi/graphify, PyPI-Paket „graphifyy“): Programm per pipx
# in ~/.local des Sitzungsbenutzers, danach „graphify install“ – legt den Skill unter
# ~/.claude/skills/graphify ab und meldet ihn in ~/.claude/CLAUDE.md an.
# Feste, in der CI (Debian 13 arm64) echt getestete Version; Lizenz Apache-2.0.
GRAPHIFY_VERSION=0.9.91

cp_apt_install_nr pipx python3-venv

home="$(cp_user_home)"
# pipx-Umgebung im Benutzerordner; ~/.local/bin steht durch das Modul claude-code im PATH.
cp_retry runuser -u "$CP_USER" -- env HOME="$home" PIPX_HOME="$home/.local/share/pipx" \
    PIPX_BIN_DIR="$home/.local/bin" pipx install --force "graphifyy[pdf]==${GRAPHIFY_VERSION}" \
    || cp_die "Graphify konnte nicht installiert werden."
cp_run_as_user env PATH="$home/.local/bin:/usr/local/bin:/usr/bin:/bin" "$home/.local/bin/graphify" install \
    --platform claude \
    || cp_die "Graphify-Skill konnte nicht in Claude Code angemeldet werden."
if [ "$CP_DRY_RUN" != "1" ]; then
    [ -s "$home/.claude/skills/graphify/SKILL.md" ] || cp_die "Graphify-Skill fehlt nach der Installation."
    # Nur auf ausdrücklichen Aufruf (/graphify): sonst startet Claude den aufwendigen Lauf bei
    # gewöhnlichen Code-Fragen selbst und verbraucht Kontingent. Bleibt erhalten, weil Graphify
    # den Skill nur bei einem Versionswechsel neu schreibt (Version oben fest).
    skill="$home/.claude/skills/graphify/SKILL.md"
    if head -n 1 "$skill" | grep -q '^---$' && ! grep -q '^disable-model-invocation:' "$skill"; then
        # als Benutzer: sed -i legt die Datei neu an (sonst gehörte sie root)
        runuser -u "$CP_USER" -- sed -i '1a disable-model-invocation: true' "$skill"
    fi
    ver="$(runuser -u "$CP_USER" -- env HOME="$home" "$home/.local/bin/graphify" --version 2>/dev/null | head -n 1 || true)"
    cp_log "Graphify eingerichtet${ver:+ ($ver)}: in Claude Code /graphify eingeben."
fi
