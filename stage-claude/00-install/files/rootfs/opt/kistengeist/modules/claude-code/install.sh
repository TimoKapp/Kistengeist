# shellcheck shell=bash
# Claude Code (CLI) über den offiziellen Installer für den Sitzungsbenutzer.
# Wird für die Browser-Steuerung über "Claude in Chrome" gebraucht.

installer="${CP_ROOT}/tmp/claude-code-install.sh"
cp_retry curl -fsSLo "$installer" https://claude.ai/install.sh
cp_run chmod 0755 "$installer"
cp_run_as_user bash "$installer"
rm -f "$installer"

home="$(cp_user_home)"
profile="${home}/.profile"
if [ -f "$profile" ] && ! grep -q '.local/bin' "$profile"; then
    printf '\n# Claude Code\nexport PATH="$HOME/.local/bin:$PATH"\n' >>"$profile"
fi

# Datensparsam (Einrichtung, Standard an): Fehlerberichte und Umfragen von Claude Code aus.
# Bewusst NICHT DISABLE_TELEMETRY/CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: das schaltet laut
# Anthropic auch die Feature-Flags ab und macht Remote Control unbrauchbar.
if [ "$(cp_setting PRIVACY_MINIMAL)" != "no" ]; then
    mkdir -p "$home/.claude"
    python3 "${CP_HOME_DIR}/lib/json_merge.py" "$home/.claude/settings.json" \
        '{"env": {"DISABLE_ERROR_REPORTING": "1", "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "1"}}'
    cp_run chown -R "$CP_USER:$CP_USER" "$home/.claude"
    cp_log "Datensparsam: Fehlerberichte und Umfragen von Claude Code abgeschaltet."
fi
