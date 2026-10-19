# Projektstand Kistengeist

> Produktname seit 19.10.2026 **Kistengeist** (vorher Arbeitsname „Claude-Pi-OS“; geändert wegen der
> Markenregeln von Raspberry Pi Ltd und Anthropic). Hervorgegangen aus der Variante mit
> **Fernzugriff: Browser oder RDP**. Geplantes öffentliches Repo: `TimoKapp/kistengeist`.

Stand: 17.10.2026 · Übergabedokument, damit jederzeit (auch in einer neuen Claude-Sitzung)
weitergebaut werden kann. Bei jeder größeren Änderung aktualisieren.

## Ziel

Eigenes, schlankes OS für den Raspberry Pi, das direkt in **Claude Desktop** startet und dauerhaft
stromsparend online bleibt. Daneben nur das Nötigste: Browser (Chrome), Dateien/USB,
Speicherverwaltung, Ausschalten. Erweiterbar über Module, MCP und Plugins.

## Getroffene Entscheidungen

| Thema | Entscheidung | Grund |
| --- | --- | --- |
| Basis | Raspberry Pi OS Lite (Debian 13 „Trixie“, arm64) über pi-gen | Eigenes OS ohne Linux wäre inkompatibel (kein Claude, kein Chrome, keine Treiber) |
| Claude | Offizielle Claude-Desktop-Linux-Beta (apt-Repo von Anthropic) | Kein Nachbau nötig/erlaubt |
| Browser | Google Chrome arm64 (Fallback Chromium) | Erweiterungen, „Claude in Chrome“ |
| Grafik | X11 + Openbox + tint2, LightDM | Claude-Hotkeys unter X11, RDP-Spiegelung mit x11vnc |
| Zugang | Wählbar: nur Bildschirm / nur RDP / beides | Wunsch des Nutzers |
| „Beides“ | RDP spiegelt den lokalen Bildschirm (xrdp → x11vnc, nur localhost) | Claude/Chrome dürfen nicht doppelt laufen; Autologin dort Pflicht |
| Einrichtung | Web-Assistent beim ersten Start (statt RDP vor der Installation) | Funktioniert ohne Monitor, vom Handy |
| Installation | Programme werden beim Setup aus dem Internet geladen | Wunsch „Linux bei Installation laden“, kleines Image |
| Zielgerät | Raspberry Pi 4, 8 GB | Vorhandenes Gerät; Pi 5 später |
| Auslieferung | `.img.xz` als Release-Datei für Raspberry Pi Imager („Eigenes Image“) | Artefakt-ZIP von GitHub ist doppelt gepackt und für Imager unbrauchbar (Rückmeldung des Nutzers) |
| Repo | `TimoKapp/kistengeist`, öffentlich geplant | Wunsch des Nutzers (19.10.2026) |
| Name | Kistengeist; Hostname `kistengeist`, Pfade `/opt/kistengeist`, Dienste `kistengeist-*` | Keine fremden Marken im Namen; Benutzer bleibt `claude` |
| Zweiter Weg | Ein-Befehl-Installer `install.sh` auf Raspberry Pi OS Lite | Wunsch „mit einer Batch“; gleiche Vorbereitung wie das Image (`bin/kistengeist-prepare`) |

## Was fertig ist

- pi-gen-Stufe `stage-claude/` (läuft nach stage2), Benutzer `claude` mit gesperrtem Passwort
- Setup-Assistent (`wizard/server.py` + `static/`): Netzwerkstatus, WLAN-Hotspot-Fallback
  („Kistengeist-Setup“, Passwort = Einrichtungscode), Zugangsart, Module, Passwort, Region, Fortschritt, Neustart
- Tty1-Anzeige mit Adresse und QR-Code während der Einrichtung
- Modularer Installer (`bin/kistengeist-install`) mit 26 Modulen (Tabelle im README)
- Claude-Oberfläche: Claude im Vollbild mit Neustart bei Absturz, Leiste mit
  Claude · Code · Terminal · VS Code · Browser · Dateien · Upload · Handy · Speicher · Ausschalten
- **Code-Knopf**: öffnet Claude Code im Code-Bereich von Claude Desktop (`claude://code/new`, Ordner `~/Projekte`)
- **Upload-Knopf**: Fenster mit QR-Code; Webserver (Port 8765, Schlüssel im Link, nur solange Fenster offen,
  30 Min. Leerlauf) nimmt Dateien nach `~/Uploads` an; „An Claude senden“ per `claude://`-Link
  (`lib/kistengeist_upload.py`, `lib/kistengeist_links.py`, `lib/upload_page.html`, `bin/kistengeist-upload`)
- **Handy wie in der Original-App**: Knopf „Handy“ (`bin/kistengeist-mobile`); Remote-Control-Dauerdienst
  (`kistengeist-remote.service`, Benutzerdienst mit Linger, Ordner `~/Projekte`), Push-Einstellungen,
  `remoteControlAtStartup`; Cowork-Modul (für Dispatch) jetzt standardmäßig an
- **Rechtliches vor der Installation**: Seite im Assistenten mit KI-Hinweis, Datenschutz,
  Verantwortung, Sicherheit, Lizenzen, Haftung; 4 Pflicht-Häkchen, Server lehnt Installation ohne
  Bestätigung ab, Nachweis in `/etc/kistengeist/legal-accepted` (nur Version + Zeit).
  Quelle: `share/legal/legal.json` → `RECHTLICHES.md` per `tools/make_legal_md.py` (Test prüft Gleichstand).
  Im Betrieb: Ausschalten-Menü → „Rechtliches und Datenschutz“. Option „Datensparsam“.
- Rechtstexte von zweiter KI geprüft (Haftung nach §§ 521/524/599/600 BGB, Kontoweitergabe/Minderjährige,
  Datenflüsse inkl. Claude in Chrome, NTP, cloud-init; Abschnitt „Daten löschen“); Raspberry Pi Connect
  wird aus dem Image entfernt; Installer bricht ohne Bestätigungsnachweis ab
- **Terminal-Panel** (Modul `terminal-panel`, Knopf „Terminal“, Super+T): tmux-Sitzung `kistengeist`
  (`tmux -L kistengeist`, Konfig `share/tmux/kistengeist.conf`) in xterm, daneben Tk-Befehlsliste
  (`bin/kistengeist-panel`, `lib/kistengeist_commands.py`, Standardliste `share/commands/standard.json`,
  eigene in `~/.config/kistengeist/commands.json`); Ansicht geteilt/unten per wmctrl (`lib/kistengeist_panel.py`).
  Übergabe aus Claude Desktop: Super+Enter (Markierung), Zwischenablage, oder MCP-Server
  `lib/kistengeist_terminal_mcp.py` (angemeldet in `~/.config/Claude/claude_desktop_config.json` und `~/.claude.json`)
- **Graphify** (Modul `graphify`): `graphifyy[pdf]==0.9.91` per pipx als Benutzer (`~/.local/bin/graphify`), Skill via
  `graphify install --platform claude` nach `~/.claude/skills/graphify`; CI baut echt einen Graphen (`graphify update`, ohne LLM).
  Skill mit `disable-model-invocation: true` (nur auf /graphify). Offen: Updates (Version fest; nach Python-
  Wechsel `pipx reinstall-all`), Abhängigkeiten nicht festgeschrieben (numpy, tree-sitter frisch von PyPI).
- **VS Code** (Modul `vscode`, Knopf „VS Code“, Super+V): Microsoft-apt-Repo, Erweiterungen
  `anthropic.claude-code` und deutsches Sprachpaket, Schlüsselbund, Telemetrie aus bei „Datensparsam“
- **USB-Stick** (Modul `usb-stick`, Seite im Assistenten): `lib/kistengeist_usb.py` (nur USB-Bus, nie Systemlaufwerk,
  stabile by-id-Pfade), exFAT/MBR Typ 7, fstab per UUID mit `nofail,x-systemd.automount`, `/mnt/usb-stick` → `~/USB-Stick`
- **Webserver** (Modul `webserver`): Caddy (Debian 2.6.2), `:8080` Startseite, DynDNS mit Anbieterwahl ipv64.net (Standard),
  dynv6, No-IP, DuckDNS (`lib/kistengeist_ddns.py`, `bin/kistengeist-ddns`, Timer 5 Min., meldet nur bei IP-Wechsel bzw.
  täglich wegen Tageslimits/No-IP-Sperren; Zugang `/etc/kistengeist/ddns.json`; CI spricht alle vier APIs echt mit
  falschen Zugangsdaten an) + Let's Encrypt. deSEC nicht dabei (dedyn.io-Neuanmeldung seit 21.09.2026 gesperrt), oder Tailscale Funnel; Caddy während Setup maskiert (Port 80)
- **n8n** (Modul `n8n`): `/srv/n8n` (compose, `n8n.env` 0600, `data/`, `backup/`), `kistengeist-n8n.service`,
  Timer `kistengeist-n8n-update` (wöchentlich) und `-backup` (täglich → USB), Besitzerkonto per `/rest/owner/setup`
  (`lib/kistengeist_n8n.py`), MCP `…/mcp-server/http` in `~/.claude.json`, `N8N_MCP_MANAGED_BY_ENV`
- **Zugangsdaten** (Modul `zugangsdaten`): `lib/kistengeist_access.py` → `~/Zugangsdaten.txt` (0600), optional USB-Kopie;
  Geheimnisse nur in `/run/kistengeist` (account.secret, n8n.json, tailscale.key), danach gelöscht
- **Desktop im Browser** (Modul remote-rdp, `REMOTE=browser`, `modules/remote-rdp/browser.sh`): Selkies 2.0.0
  (arm64-.deb von GitHub, SHA256 geprüft), `bin/kistengeist-selkies` (HTTPS 8443, Basic-Auth, JPEG 30 fps),
  `bin/kistengeist-selkies-audio` (beim Verbinden Ton→Browser, Browser-Mikrofon als Standard; beim Trennen zurück, nach Selkies-Aufräumen nachgezogen; Protokoll `$XDG_RUNTIME_DIR/kistengeist-audio.log`),
  systemd-Benutzerdienste mit linger: `kistengeist-selkies`; ohne Monitor zusätzlich `kistengeist-xvfb` +
  `kistengeist-desktop` (Xvfb :0, Größe folgt dem Browser). CI-Job „Desktop im Browser echt testen“ installiert das
  Modul und verbindet einen echten Chromium-Client mit simuliertem Mikrofon.
- Speicherverwaltung (Tk): Belegung, Cache leeren, Paket/Journal aufräumen, USB auswerfen, Warnung ab 90 %
- Build per GitHub Actions (`.github/workflows/build.yml`), Tests + Shellcheck + Ruff
- Zwei unabhängige KI-Reviews (System/Pi und Sicherheit) durchgeführt und umgesetzt

## Windows-Installer (Hauptweg seit 19.10.2026)

- `windows/Kistengeist-Installer.cmd` (Batch-Kopf + PowerShell): Adminrechte, Raspberry Pi Imager ≥ 2.0.11
  (sonst `imager_latest.exe` laden, Authenticode „Raspberry Pi“ prüfen, still installieren), Raspberry Pi OS
  Lite arm64 über `raspios_lite_arm64_latest` + `.sha256`, Datenträgerwahl (USB/SD/MMC, nicht System),
  Bestätigung „JA“, optional WLAN; schreibt per `rpi-imager --cli --cloudinit-userdata/--cloudinit-networkconfig`.
- cloud-init: Hostname, Zeitzone, Tastatur, Benutzer `claude` (gesperrt), Einrichtungscode nach
  `/etc/kistengeist/setup-code`, Dienst `kistengeist-firstboot` lädt `install.sh` (main bzw. im Release fest)
  mit Wiederholungen und startet ihn mit `KG_START_CONSOLE=1`.
- CI: Windows-Runner schreibt echt auf eine VHDX und prüft die Boot-Partition; Debian 13 prüft user-data
  mit `cloud-init schema`, network-config mit `netplan generate`, Erststart-Skript mit Shellcheck.
- Noch offen: Test auf echter Hardware (Pi 4 + Windows 10/11, SmartScreen/Smart App Control; unsigniert).

## Einrichtungscode

- Pro Gerät zufällig (10 Zeichen, ohne verwechselbare Zeichen), `/etc/kistengeist/setup-code` (0600),
  erzeugt von `bin/kistengeist-setupcode` bzw. dem Assistenten (gleiche Sperrdatei); Vorrang hat ein Code
  vom Windows-Werkzeug. Schützt alle `/api/*` außer `info` (Header `X-Setup-Code`, Sperre nach 10 Fehlern
  für 10 Minuten) und ist das Passwort des Einrichtungs-WLANs. Anzeige auf tty1 mit QR-Code.

## Ein-Befehl-Installer

- `install.sh` (Repo-Wurzel): prüft root, arm64, Debian 13, Pi 4/400/5, Lite (kein lightdm/gdm3/sddm),
  6 GB frei, Port 80 frei, nicht schon eingerichtet; lädt das Quellarchiv (main: codeload; Release:
  eigenes `kistengeist-src-<ver>.tar.gz` mit fester Prüfsumme), kopiert das Rootfs-Overlay, ruft
  `kistengeist-prepare --live` (wie das Image, aber ohne rpi-connect zu entfernen und ohne vorhandenen
  Benutzer `claude` zu sperren), setzt den Gerätenamen, startet den Assistenten auf Port 80.
- CI-Job „Ein-Befehl-Installer testen“: systemd-Container, Schutzprüfungen, falsche Prüfsumme,
  Einrichtung über `bash < install.sh`, Assistent antwortet, zweiter Lauf, Sperre nach Einrichtung.

## Letzter erfolgreicher Build

- Unter neuem Namen noch keiner (Stand 19.10.2026). Letzter Image-Build unter altem Namen: dev-c4fd75c.

**Status: auf echter Hardware noch nicht getestet.** Testliste siehe README.

## So geht es weiter

### Neues Image bauen
- GitHub → Actions → „Prüfen und Image bauen“ → *Run workflow* (Dauer ca. 7 Minuten)
- Oder Release: Tag `vX.Y.Z` pushen → ZIP erscheint unter Releases

### Lokal prüfen (vor jedem Push)
```bash
pytest -q          # 140 Tests, inkl. Probelauf des Installers für alle Zugangsarten
ruff check .
shellcheck -x -S warning $(grep -rlE '^#!/bin/bash|shell=bash' stage-claude)   # läuft auch in CI
```

### Neues Modul hinzufügen
1. Ordner `stage-claude/00-install/files/rootfs/opt/kistengeist/modules/<name>/`
2. `module.conf` (NAME, DESCRIPTION, GROUP, ORDER, DEFAULT, REQUIRED, DEPENDS, MODES, NOTE)
3. `install.sh` – nur Helfer aus `lib/common.sh` nutzen (`cp_apt_install`, `cp_write`, `cp_run` …),
   damit der Probelauf (`CP_DRY_RUN=1`) in den Tests funktioniert
4. Test in `tests/test_install_dryrun.py` ergänzen

### Fehlersuche auf dem Pi
- Installationsprotokoll: `/var/log/kistengeist/install.log`
- Einstellungen: `/etc/kistengeist/setup.conf` (ohne Passwörter)
- Einrichtung wiederholen: `/etc/kistengeist/installed` löschen,
  `systemctl enable --now kistengeist-setup kistengeist-console`

## Offene Punkte

| Priorität | Punkt |
| --- | --- |
| hoch | Erster Hardwaretest auf dem Pi 4 (Testliste im README) und Fehler einsammeln |
| hoch | Prüfen, ob Claude-Anmeldung nach Neustart erhalten bleibt (Schlüsselbund + `--password-store=gnome-libsecret`) |
| mittel | Leistung von Claude + Chrome auf dem Pi 4 bewerten (ggf. GPU-Flags) |
| mittel | Setup-Assistent ist bis zum Abschluss ohne Anmeldung im LAN erreichbar (bewusst, siehe README); optional Setup-Code am Bildschirm |
| mittel | RDP-Spiegelung („beides“) nutzt nur 8 Zeichen des Passworts (VNC-Grenze) |
| hoch | Terminal-Panel testen: Fensteranordnung mit Claude-Fensterklasse, MCP-Werkzeug im Chat von Claude Desktop (Linux-Pfad der claude_desktop_config.json ist nur aus der Community belegt) |
| mittel | VS Code auf dem Pi 4: Leistung/RAM neben Claude und Chrome |
| hoch | Browser-Zugang auf dem Pi 4: Bildrate/CPU (JPEG, 30 fps), Claude Desktop auf Xvfb (Software-Rendering), Mikrofon in Chrome/Edge/Firefox nach Zertifikatswarnung |
| hoch | USB-Formatierung auf echter Hardware testen (verschiedene Sticks, Stick beim Booten gesteckt/nicht gesteckt) |
| hoch | n8n auf dem Pi: Start, Besitzerkonto per `/rest/owner/setup` (interner Endpunkt), MCP mit Claude, Backup-Export |
| hoch | DynDNS (ipv64, dynv6, No-IP, DuckDNS) mit echten Konten + Let's Encrypt und Tailscale Funnel am echten Anschluss testen (DS-Lite!); Menünamen der Anleitungen am Original prüfen |
| mittel | Docker veröffentlicht 5678 im Modus „nur Heimnetz“ an ufw vorbei; n8n Python-Code-Nodes brauchen externen Runner (nicht eingerichtet); n8n 3.0 steht bevor (Breaking Changes) |
| hoch | Remote Control auf dem Pi testen (Dienst, Gerätekarte in der App, Push) |
| hoch | Cowork-VM/Dispatch auf dem Pi 4 testen (RAM-Bedarf, /dev/kvm, vhost_vsock) |
| hoch | Prüfen, ob `claude://`-Links auf dem Pi ankommen (URL-Handler von claude-desktop registriert?) |
| mittel | Claude-Code-Link nimmt laut Anthropic noch keine Dateien an; „An Claude senden“ nutzt daher Ordner + vorbereitete Frage (mit Cowork: echter Anhang) |
| niedrig | Cowork-Modul auf dem Pi ungetestet (KVM/vhost_vsock) |
| mittel | Projektname „Kistengeist“ nutzt die Marke „Claude“ – vor einer Veröffentlichung umbenennen (z. B. „Pi-KI-Station für Claude“); Icon ist bereits neutral (blaues π), Akzentfarbe des Assistenten ähnelt noch Anthropic |
| mittel | Lizenz für das eigene Repo festlegen (derzeit keine) |
| später | Pi 5 (eigenes Image, 16-KB-Kernel prüfen, NVMe) |
| später | Eigenes Logo/Bootbild, Update-Mechanismus für Kistengeist selbst |

## Erkenntnisse aus dem Bau

- **Lehre:** Immer zuerst gründlich recherchieren, was die originale Claude-Desktop-App kann
  (Handy-Steuerung wurde anfangs übersehen). Regel steht in `CLAUDE.md`.

- Die GitHub-Anbindung der Claude-Sitzung kann keine Repos anlegen → Repo manuell anlegen, dann `add_repo`.
- `increase-runner-disk-size` von pi-gen-action bricht auf ARM-Runnern ab → ausgeschaltet; Platz reicht.
- **Hardwaretest RDP (dev-79fc30f):** Linksklick kam nicht an – Openbox-Bindung „Left“ im Kontext Frame
  verschluckt Klicks (nur Client-Kontext gibt sie weiter). Entfernt; doubleClickTime 600, GTK-Doppelklick 800 ms.
  Neu: Schriftgröße (lib/kistengeist_scale.py, bin/kistengeist-scale), Beige-Hintergrund/Leiste, Ton+Mikro über RDP
  (pipewire-module-xrdp, Kanäle rdpsnd/drdynvc). Medientasten kamen als d/c/b an (xrdp 0.10.1 verliert E0,
  Issue #1725): fertige Kistengeist.rdp mit keyboardhook:i:0, audiomode 0, audiocapturemode 1 (Assistent, ~, USB).
  Offen: xrdp aus trixie-backports (0.10.6.1) auf dem Pi testen, ob es den E0-Fehler behebt. Testphasen-Wrapper in ~/.local/bin werden nach kistengeist-alt verschoben.
- **Hardwaretest 17.10.:** n8n scheiterte mit „docker: Kommando nicht gefunden“ – in Debian 13 ist `docker-cli`
  bei `docker.io` nur empfohlen. Behoben; neuer CI-Job „Pakete in Debian 13 (arm64)“ installiert alle Modulpakete
  ohne Empfehlungen und prüft die aufgerufenen Befehle.
- Shellcheck stolpert über ein unquotiertes Argument `done` → quoten.
- Der GitHub-Artefakt-Download ist selbst eine ZIP – Imager kann ihn nicht schreiben. Deshalb wird jedes Image als
  (Vorab-)Release mit direkt ladbarer `.img.xz` veröffentlicht; der Build prüft das Image (Boot-Dateien, Dienste, Assistent).
