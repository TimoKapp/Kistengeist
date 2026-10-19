# shellcheck shell=bash
# Google Chrome (offizielles arm64-Paket seit Mitte 2026), sonst Chromium.

browser=""

if cp_retry curl -fsSLo "${CP_ROOT}/tmp/google-linux-key.pub" https://dl.google.com/linux/linux_signing_key.pub; then
    # Gleiche Ablage wie Googles eigenes Paket, damit dessen Paketquellen-Pflege
    # keine doppelten oder widersprüchlichen Einträge erzeugt.
    cp_run install -d -m 0755 "${CP_ROOT}/etc/apt/trusted.gpg.d"
    cp_run gpg --batch --yes --dearmor -o "${CP_ROOT}/etc/apt/trusted.gpg.d/google-chrome.gpg" \
        "${CP_ROOT}/tmp/google-linux-key.pub"
    cp_write /etc/apt/sources.list.d/google-chrome.list <<'EOF'
### THIS FILE IS AUTOMATICALLY CONFIGURED ###
deb [arch=arm64] https://dl.google.com/linux/chrome/deb/ stable main
EOF
    cp_apt_update || cp_warn "Paketliste von Google nicht erreichbar."
    if cp_apt_available google-chrome-stable && cp_apt_install google-chrome-stable; then
        browser="google-chrome-stable"
    fi
fi
rm -f "${CP_ROOT}/tmp/google-linux-key.pub"

# Neuere Chrome-Pakete legen ihre Quelle selbst als google-chrome.sources an: dann die eigene
# (ältere) Liste samt Schlüssel entfernen, damit es keine doppelte Quelle gibt.
if [ -f "${CP_ROOT}/etc/apt/sources.list.d/google-chrome.sources" ]; then
    rm -f "${CP_ROOT}/etc/apt/sources.list.d/google-chrome.list" "${CP_ROOT}/etc/apt/trusted.gpg.d/google-chrome.gpg"
fi

if [ -z "$browser" ]; then
    cp_warn "Google Chrome für arm64 nicht verfügbar – installiere Chromium."
    rm -f "${CP_ROOT}/etc/apt/sources.list.d/google-chrome.list"
    cp_apt_update
    cp_apt_install chromium
    browser="chromium"
fi

printf '%s\n' "$browser" | cp_write /etc/kistengeist/browser

cp_write /opt/kistengeist/share/applications/kistengeist-browser.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Browser
Exec=/opt/kistengeist/bin/kistengeist-launch browser
Icon=$([ "$browser" = chromium ] && echo chromium || echo google-chrome)
Terminal=false
EOF

# Browser als Standard für Links (z. B. Anmeldung bei Claude).
cp_run update-alternatives --set x-www-browser "$(command -v "$browser" 2>/dev/null || echo "/usr/bin/$browser")" || true
