# shellcheck shell=bash
# Erweiterung "Claude in Chrome" per Richtlinie vorinstallieren.
# Erweiterungs-ID laut Anthropic-Doku / Chrome Web Store.

ext_id=fcoeoabgfenejglbffodgkkbkcdhcgfn

policy="$(cat <<EOF
{
  "ExtensionSettings": {
    "${ext_id}": {
      "installation_mode": "normal_installed",
      "update_url": "https://clients2.google.com/service/update2/crx"
    }
  }
}
EOF
)"

# Pfade für Chrome und Chromium; nur der installierte Browser liest seinen.
printf '%s\n' "$policy" | cp_write /etc/opt/chrome/policies/managed/kistengeist.json
printf '%s\n' "$policy" | cp_write /etc/chromium/policies/managed/kistengeist.json
