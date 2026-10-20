# Kistengeist

Ein Windows-Installer für den Raspberry Pi 4, der die Installation von Claude Desktop als One-Klick-Lösung bietet.

Ein schlankes Betriebssystem für den **Raspberry Pi 4 (64-bit, 8 GB empfohlen)**, das direkt in
**Claude Desktop** startet. Unten liegt eine schmale Leiste mit Claude Code, Browser (Google Chrome), Upload,
Dateien, Speicherverwaltung und Ausschalten. Ein klassischer Desktop fehlt absichtlich.

Unter der Haube arbeitet Raspberry Pi OS Lite (Debian 13 „Trixie“) mit dem offiziellen
Pi-Kernel und allen Treibern. Das Image ist klein. Claude, Chrome und alle gewählten
Module lädt der Pi **bei der Installation aus dem Internet**.

> Status: erste Version, **noch nicht auf echter Hardware getestet**. Bitte die
> [Testliste](#testliste-für-den-ersten-start) durchgehen und Fehler als Issue melden.

## So funktioniert es

```
Pi bootet ─► Erster Start? ─ja─► Setup-Assistent im Browser ─► Module installieren ─► Neustart
                 │ nein                                                                 │
                 └──────────────────► Claude Desktop im Vollbild ◄──────────────────────┘
                  Leiste: Claude · Code · Browser · Dateien · Upload · Handy · Speicher · Aus
```

## Installation

Drei Wege führen zum selben Ergebnis:

- **Weg 1 – Windows-Installer (empfohlen):** `Kistengeist-Installer.cmd` aus dem neuesten
  [Release](https://github.com/TimoKapp/kistengeist/releases) laden (nicht die Datei aus dem Quellcode:
  die Release-Fassung ist auf genau diese Version festgelegt und geprüft) und doppelklicken
  (Windows fragt nach Administratorrechten; bei „Der Computer wurde durch Windows geschützt“ →
  „Weitere Informationen“ → „Trotzdem ausführen“). Das Programm
  1. installiert bei Bedarf den offiziellen **Raspberry Pi Imager**,
  2. lädt das offizielle **Raspberry Pi OS Lite (64-bit)** und prüft die Prüfsumme,
  3. fragt nach der Speicherkarte (alle Daten darauf werden gelöscht) und optional nach dem WLAN,
  4. schreibt die Karte und legt fest, dass sich der Pi beim ersten Start **selbst online zu Kistengeist
     umbaut** (lädt `install.sh`),
  5. zeigt den **Einrichtungscode** und speichert ihn als `Kistengeist-Code.txt` auf dem Desktop.

  Karte (mindestens 16 GB) in den Pi, Strom an, nach 5–15 Minuten `http://kistengeist.local` öffnen
  (sonst `http://kistengeist.fritz.box` oder die IP vom Bildschirm des Pi) und den Code eingeben.
  Fortschritt und Fehler (z. B. „Kein Internet“) stehen am Bildschirm des Pi.
  Fragt Windows beim Schreiben „Datenträger formatieren?“: immer **Abbrechen**.
- **Weg 2 – fertiges Image:** mit Raspberry Pi Imager schreiben, Schritte unten.
- **Weg 3 – ein Befehl:** Raspberry Pi OS **Lite (64-bit)** mit Raspberry Pi Imager aufspielen
  (dort Benutzer, WLAN und SSH einstellen), anmelden und eingeben:

  ```
  curl -fsSL https://raw.githubusercontent.com/TimoKapp/kistengeist/main/install.sh | sudo bash
  ```

  Der Befehl prüft das System (Raspberry Pi 4/400/5, Debian 13 „Trixie“, Lite, 6 GB frei, Port 80 frei),
  lädt Kistengeist, nennt den Pi `kistengeist` und startet den Setup-Assistenten. Danach geht es ab
  Schritt 3 weiter. Eine auf eine Version festgelegte Fassung mit Prüfsumme liegt in jedem
  [Release](https://github.com/TimoKapp/kistengeist/releases) als `install.sh`. Protokoll:
  `/var/log/kistengeist/install-script.log`.

### Weg 2 – Image

1. **Image holen** – unter [Releases](https://github.com/TimoKapp/kistengeist/releases) die Datei
   `kistengeist-<version>.img.xz` herunterladen (direkter Download, **nicht** die Artefakt-ZIP aus
   „Actions“ – die packt GitHub in eine zusätzliche ZIP, die Imager nicht schreiben kann).
   In **Raspberry Pi Imager**: Gerät „Raspberry Pi 4“ → Betriebssystem ganz unten
   **„Eigenes Image verwenden“** (Use custom) → die `.img.xz` wählen (nicht entpacken) → Speicherkarte
   wählen. Die Frage nach Anpassungen mit **„Nein“** beantworten (höchstens WLAN eintragen; keinen
   Benutzer anlegen – den richtet der Assistent ein). Schreiben und prüfen lassen.
2. **Pi starten** – am besten mit Netzwerkkabel. Ohne Kabel und ohne WLAN-Daten öffnet der Pi
   nach ca. 90 Sekunden das WLAN **Kistengeist-Setup**. Passwort ist der **Einrichtungscode**, der am
   Bildschirm des Pi steht (mit QR-Code zum Verbinden).
3. **Setup-Assistent öffnen** – auf PC oder Handy im Browser:
   `http://kistengeist.local` oder die IP-Adresse, die am Bildschirm des Pi steht (mit QR-Code).
   Im Hotspot: `http://10.42.0.1`.
4. **Rechtliche Hinweise lesen und bestätigen** (KI-Hinweis, Datenschutz, Mindestalter,
   Haftung – alle Häkchen sind Pflicht; Text auch in [RECHTLICHES.md](RECHTLICHES.md)).
5. Im Assistenten wählen:
   - **Zugangsart**: *Nur Bildschirm*, *Nur RDP* oder *Beides*
   - **Module** (siehe unten)
   - **Passwort** für den Benutzer `claude` und Region
6. **Installieren** – dauert je nach Internet 15–40 Minuten. Danach **Neustart**.
7. Kistengeist öffnet Claude Desktop. Mit deinem Claude-Konto anmelden – fertig.

## Claude Code und Upload

**Code** (Leiste oder Win+K) öffnet Claude Code in der Oberfläche von Claude Desktop – über den
offiziellen Link `claude://code/new` mit dem Arbeitsordner `~/Projekte`. Claude fragt beim ersten
Mal nach, ob der Ordner benutzt werden darf.

**Upload** (Leiste oder Win+U) öffnet ein Fenster mit QR-Code und Adresse. Mit dem Handy scannen
oder die Adresse am PC öffnen, Dateien auswählen – sie landen in `~/Uploads`. Ist „Danach direkt in
Claude öffnen“ angehakt (oder im Fenster „An Claude senden“ gedrückt), öffnet sich Claude mit der
Datei: mit Cowork-Modul als Anhang, sonst als Claude-Code-Sitzung im Upload-Ordner mit vorbereiteter
Frage. Der Zugang gilt nur mit dem Schlüssel im QR-Code, nur solange das Fenster offen ist und
endet nach 30 Minuten ohne Upload. Port: 8765.

## Terminal, Befehlsliste und VS Code

- **Knopf „Terminal“** (oder Super+T) blendet Claude Code im Terminal ein und wieder aus.
  Zwei Ansichten (Knopf „Ansicht“): **geteilt** – Claude links, rechts Terminal und Befehlsliste –
  oder **eingeblendet unten** über Claude. Ausblenden beendet nichts: die Sitzung (tmux
  „kistengeist“, Ordner `~/Projekte`) läuft weiter.
- **Befehlsliste:** alle wichtigen Claude-Code-Befehle mit kurzer Erklärung, Suche und Kategorien;
  **Doppelklick fügt den Befehl ins Terminal ein** (abgeschickt wird nur mit „Sofort abschicken“).
  „Neu …“ nimmt eigene Befehle auf (vorbelegt mit der Zwischenablage), „Löschen“ entfernt sie (★).
  Eigene Slash-Befehle und Skills aus `~/.claude/commands` und `~/.claude/skills` erscheinen automatisch.
- **Von Claude Desktop ans Terminal:**
  - Text in Claude markieren und **Super+Enter** drücken (oder „Markierung →“ im Panel);
    kopierten Text mit „Zwischenablage →“.
  - Oder Claude im Chat bitten: „Schick das ans Terminal“ – dafür ist der lokale MCP-Server
    `kistengeist-terminal` in Claude Desktop und Claude Code angemeldet (Werkzeuge
    `send_to_terminal`, `list_commands`, `add_command`). Claude fragt vor der Nutzung nach Erlaubnis.
- Wie im Original hat auch der Code-Bereich von Claude Desktop ein eingebautes Terminal (Strg+`).
- **Knopf „VS Code“** (Super+V): Visual Studio Code mit der Erweiterung „Claude Code for VS Code“
  und deutschem Sprachpaket, Ordner `~/Projekte`. Im VS-Code-Terminal verbindet sich `claude`
  automatisch mit dem Editor (`/ide`).

## USB-Stick, Webserver und n8n

- **USB-Stick (dringend empfohlen):** Der Assistent bittet gleich zu Beginn, einen Stick einzustecken,
  zeigt alle USB-Laufwerke (nie die Speicherkarte bzw. das Systemlaufwerk) und formatiert den
  gewählten auf Wunsch mit **exFAT** (MBR, lesbar unter Windows/macOS). Er wird per UUID dauerhaft
  unter `/mnt/usb-stick` eingebunden (Pi startet auch ohne Stick) und erscheint als `~/USB-Stick`
  mit den Ordnern `Austausch` und `Sicherungen`.
- **Webserver (Caddy):** läuft dauerhaft im Hintergrund, Startseite im Heimnetz
  `http://kistengeist.local:8080` (eigene Dateien in `/srv/kistengeist-web`). Erreichbar aus dem Internet:
  - **Eigene DynDNS-Adresse** (kostenlos, Anbieter wählbar: **ipv64.net** (empfohlen), **dynv6**,
    **No-IP**, **DuckDNS** – alle über ihre offizielle Update-API, mit Schritt-für-Schritt-Anleitung im
    Assistenten), z. B. `https://meinpi.ipv64.net` mit automatischem Let's-Encrypt-Zertifikat;
    am Router **TCP 80 und 443** auf den Pi freigeben. Bei DS-Lite: Häkchen „nur IPv6“.
    Der Pi prüft alle 5 Minuten und meldet nur bei geänderter IP (Tageslimits); Stand: `kistengeist-ddns status`.
    No-IP (gratis) verlangt alle 30 Tage eine Bestätigung per E-Mail-Link. deSEC fehlt bewusst:
    dort sind neue dedyn.io-Adressen seit 21.09.2026 gesperrt.
  - **Tailscale Funnel** (kostenlos, ohne Portfreigabe, auch bei DS-Lite).
  - oder nur im Heimnetz.
- **n8n:** offizielles Docker-Image (Kanal `stable`), Besitzerkonto wird mit deinen Angaben aus dem
  Assistenten angelegt, HTTPS über Caddy, MCP-Zugang für Claude (in Claude Code `/mcp` › n8n anmelden),
  Sicherheitsupdates wöchentlich, Sicherung täglich nach `~/USB-Stick/Sicherungen/n8n`. Knopf „n8n“.
- **Zugangsdaten-Datei** `~/Zugangsdaten.txt` (nur für dich lesbar): Adressen, IPv4/IPv6, MAC, alle Ports
  mit „am Router freigeben ja/nein“, FRITZ!Box-Anleitung und – wenn gewählt – Logins; optional Kopie
  auf dem USB-Stick. **Nie freigeben:** RDP 3389, SSH 22, n8n 5678.

## Claude vom Handy (wie in der Original-App)

Knopf **Handy** in der Leiste zeigt alles auf einen Blick:

1. **Claude-App** per QR-Code aufs Handy holen, mit demselben Konto anmelden.
2. **Remote Control**: einmal „Bei Claude Code anmelden“. Danach läuft auf dem Pi dauerhaft
   `claude remote-control` (auch ohne Anmeldung am Bildschirm). Der Pi erscheint in der App unter
   **Code** als Gerät „Kistengeist“: Sitzungen im Ordner `Projekte` starten, verfolgen, steuern,
   Fotos/Dateien schicken, Push-Nachrichten erhalten. Code-Sitzungen in Claude Desktop verbinden
   sich ebenfalls automatisch (`remoteControlAtStartup`). Braucht Pro, Max, Team oder Enterprise.
3. **Dispatch**: in Claude unter **Cowork → Dispatch → Get started** einrichten. Danach Aufgaben in
   der Handy-App an Dispatch schreiben – der Pi erledigt sie. Braucht Pro oder Max und das Modul
   „Cowork und Dispatch“ (virtuelle Maschine; der Pi-4-Kernel unterstützt KVM).

## Fernzugriff: Browser oder RDP

Bei „Nur Fernzugriff“ und „Beides“ wählst du im Assistenten, wie du den Pi aus der Ferne bedienst:

- **Browser (empfohlen):** `https://kistengeist.local:8443` in Chrome, Edge oder Firefox öffnen,
  mit Benutzer `claude` und deinem Passwort anmelden. Ton und Mikrofon laufen über den Browser
  (Selkies). Beim ersten Öffnen warnt der Browser einmal vor dem selbst ausgestellten Zertifikat
  („Erweitert“ → „Weiter“), danach Mikrofon erlauben. Ohne Monitor passt sich die Bildgröße dem
  Browserfenster an; mit Monitor siehst du denselben Bildschirm. Nur im Heimnetz erreichbar.
  Passwort ändern: im Terminal `kistengeist-rdp-password`.
- **RDP:** wie bisher mit „Remotedesktopverbindung“ bzw. der fertigen Datei `Kistengeist.rdp`.

## Schriftgröße, Farben, Ton

- **Schriftgröße** (100–200 %): wird bei der **ersten Anmeldung** abgefragt, später über
  Ausschalten → „Schriftgröße“. Skaliert Schrift (Xft.dpi), Mauszeiger (sofort) und die Leiste;
  Claude Desktop übernimmt Schrift und Zeiger nach einem Neustart (wird angeboten).
- **Farben:** Claude-Fenster weiß, Hintergrund links/rechts und Leiste in zartem Beige.
- **Ton und Mikrofon per RDP** (Zugangsart „Nur RDP“): Sprachausgabe über die Lautsprecher des
  Arbeitsplatzes, dessen Mikrofon geht an den Pi (PipeWire + xrdp-Modul). In Windows:
  *Remotedesktopverbindung → Optionen → Lokale Ressourcen → Remoteaudio → Einstellungen*:
  „Auf diesem Computer wiedergeben“ und „Von diesem Computer aufzeichnen“.
  **Am einfachsten:** die fertige Datei `Kistengeist.rdp` doppelklicken – sie liegt auf der Fertig-Seite
  des Assistenten zum Herunterladen, im Benutzerordner und auf dem USB-Stick. Darin ist alles eingestellt:
  Ton hier, Mikrofon hier, Windows-Tastenkombinationen und **Medientasten bleiben am Arbeitsplatz**
  (xrdp 0.10.1 aus Debian 13 verliert bei Medientasten das E0-Kennzeichen – Stumm/Leiser/Lauter kämen
  sonst als „d“, „c“, „b“ an; xrdp-Issue #1725).
  Bei „Beides“ (Spiegelung über VNC) überträgt RDP keinen Ton. Während einer RDP-Sitzung laufen
  Ton und Mikrofon des Benutzers `claude` über den Arbeitsplatz.

## Zugangsarten

| Zugangsart | Am Bildschirm | Per RDP |
| --- | --- | --- |
| Nur Bildschirm | Kistengeist-Oberfläche, optional automatische Anmeldung | – |
| Nur RDP | – (kein Monitor nötig) | Eigene Sitzung; läuft nach dem Trennen weiter |
| Beides | Kistengeist-Oberfläche | Zeigt **denselben** Bildschirm wie am Pi (Spiegelung) |

RDP-Programme: Windows „Remotedesktopverbindung“, Mac/iPhone/Android „Windows App“.
Adresse: `kistengeist.local` oder die IP des Pi, Benutzer `claude`.

Bei „Beides“ läuft die Spiegelung technisch über VNC (nur intern auf dem Pi); dabei zählen nur
die **ersten 8 Zeichen** des Passworts – wähle sie nicht zu einfach. Der Pi meldet sich in dieser
Zugangsart am Bildschirm automatisch an, sonst gäbe es nichts zu spiegeln. Grund für die
Spiegelung: Claude und Chrome dürfen nicht zweimal gleichzeitig mit demselben Profil laufen.
`passwd` ändert dieses RDP-Passwort nicht; dafür im Terminal `kistengeist-rdp-password` ausführen.

## Module

| Modul | Standard | Zweck |
| --- | --- | --- |
| Grundsystem, Kistengeist-Oberfläche, Claude Desktop, Abschluss | immer | Basis |
| Bildschirm am Pi / Fernzugriff per RDP | je Zugangsart | Zugang |
| Google Chrome | an | Browser mit Erweiterungen (Fallback: Chromium) |
| Claude in Chrome | an | Erweiterung wird automatisch installiert |
| Claude Code (Terminal) | an | CLI; nötig, damit Claude den Browser steuern kann |
| Dateien und USB-Sticks | an | Dateimanager, USB wird automatisch eingebunden |
| Terminal mit Befehlsliste | an | Claude Code einblenden, Befehlsliste mit Doppelklick, Übergabe aus Claude Desktop |
| VS Code mit Claude-Erweiterung | an | Editor von Microsoft mit „Claude Code for VS Code“ (ca. 500 MB) |
| Graphify | an | Skill `/graphify` für Claude Code: Ordner (Code, Texte, PDFs, Bilder) als Wissensgraph (`graph.html`, `GRAPH_REPORT.md`); Code-Analyse lokal |
| USB-Stick als Datenspeicher | an | Stick wählen, optional exFAT formatieren, dauerhaft einbinden |
| Webserver (aus dem Internet erreichbar) | an | Caddy, DynDNS (ipv64/dynv6/No-IP/DuckDNS) + HTTPS oder Tailscale Funnel |
| n8n (Automatisierung) | an | Docker, Konto automatisch, MCP für Claude, Updates und Sicherung |
| Zugangsdaten-Datei | an | `~/Zugangsdaten.txt` mit Ports, Adressen und Logins |
| Upload übers Netzwerk | an | Dateien per QR-Code vom Handy/PC an den Pi senden und in Claude öffnen |
| Speicherverwaltung | an | Belegung, Aufräumen, USB auswerfen, Warnung ab 90 % |
| Speicherkarte schonen | an | weniger Schreibzugriffe (Protokolle begrenzt, zram) |
| Energiesparen | an | Bildschirm nach 10 Minuten aus |
| Automatische Updates | an | System, Claude Desktop, Chrome (ohne Auto-Neustart) |
| Firewall | an | nur RDP/SSH eingehend erlaubt (ab Neustart) |
| SSH-Zugang | aus | Kommandozeile übers Netzwerk |
| Bluetooth abschalten | aus | spart etwas Strom |
| Cowork und Dispatch (Handy) | an | Aufgaben vom Handy per Dispatch; Cowork-VM (QEMU/KVM), viel RAM, auf dem Pi ungetestet |
| Handy-Steuerung (Remote Control) | an | Pi erscheint in der Claude-App unter Code; Sitzungen vom Handy, Push-Nachrichten |

Ein Modul ist ein Ordner unter `…/opt/kistengeist/modules/<name>/` mit `module.conf` und
`install.sh` – neue Module lassen sich so leicht ergänzen.

## Testliste für den ersten Start

Bitte nach dem ersten Start prüfen und Ergebnisse melden:

- [ ] Bildschirm am Pi zeigt die Einrichtungsanzeige mit Adresse und QR-Code
- [ ] `http://kistengeist.local` öffnet den Assistenten (sonst IP-Adresse)
- [ ] Ohne Kabel/WLAN erscheint das WLAN „Kistengeist-Setup“; WLAN-Wechsel im Assistenten klappt
- [ ] Installation läuft durch (bei Fehler: Protokoll im Assistenten kopieren)
- [ ] Nach Neustart startet Claude Desktop im Vollbild, Anmeldung bleibt nach erneutem Neustart erhalten
- [ ] Leiste: Browser, Dateien, Speicher, Ausschalten funktionieren
- [ ] „Code“ öffnet in Claude den Code-Bereich mit Ordner `Projekte` (Sicherheitsabfrage bestätigen)
- [ ] „Handy“: bei Claude Code anmelden; Pi erscheint in der Claude-App unter Code als „Kistengeist“
- [ ] Dispatch einrichten (Cowork → Dispatch) und vom Handy eine Aufgabe schicken
- [ ] „Upload“: QR-Code mit dem Handy scannen, Foto hochladen, „An Claude senden“ öffnet Claude mit der Datei
- [ ] Chrome startet, Erweiterung „Claude in Chrome“ ist installiert
- [ ] USB-Stick wird im Assistenten erkannt, exFAT-Formatierung klappt, `~/USB-Stick` ist nach Neustart da, Stick unter Windows lesbar
- [ ] DynDNS „Prüfen“ meldet OK (je Anbieter: ipv64, dynv6, No-IP, DuckDNS); nach Portfreigabe öffnet `https://<adresse>` n8n mit gültigem Zertifikat
- [ ] n8n-Anmeldung mit den Daten aus dem Assistenten; Knopf „n8n“ öffnet die Seite
- [ ] In Claude Code `/mcp` › n8n anmelden, Claude sieht freigegebene Workflows
- [ ] `~/Zugangsdaten.txt` enthält Ports/Adressen (und Logins, wenn gewählt)
- [ ] „Terminal“: Claude Code erscheint, beide Ansichten ordnen die Fenster richtig an
- [ ] Doppelklick auf einen Befehl fügt ihn ein; eigener Befehl lässt sich anlegen und löschen
- [ ] Text in Claude markieren, Super+Enter → Text steht im Terminal
- [ ] Im Claude-Chat „Schick … ans Terminal“ → Werkzeug `send_to_terminal` erscheint und funktioniert
- [ ] „VS Code“ startet deutsch, Erweiterung Claude Code ist da und lässt sich anmelden
- [ ] USB-Stick wird erkannt, Dateien kopieren, „sicher auswerfen“ klappt
- [ ] RDP-Verbindung (je nach Zugangsart) funktioniert
- [ ] Bildschirm geht nach 10 Minuten aus und mit Maus/Tastatur wieder an

Protokolle auf dem Pi: `/var/log/kistengeist/install.log`, Einstellungen: `/etc/kistengeist/setup.conf`
(enthält keine Passwörter).

## Bekannte Grenzen und Risiken

- **Claude Desktop für Linux ist Beta** und offiziell nur auf Debian/Ubuntu getestet, nicht auf
  dem Pi. Computer Use und Spracheingabe fehlen unter Linux.
- **Leistung**: Auf dem Pi 4 laufen Claude und Chrome spürbar langsamer als auf einem PC.
- **Automatische Anmeldung** legt den Schlüsselbund ohne Passwort an (sonst müsstest du dich bei
  Claude nach jedem Neustart neu anmelden). Wer das nicht möchte, schaltet sie im Assistenten ab.
- **Setup-Assistent** ist bis zum Abschluss ohne Anmeldung im Heimnetz erreichbar (bewusst, damit
  die Einrichtung auch ohne Monitor klappt). Wer im Netz ist, könnte sich zuerst einrichten –
  daher die Einrichtung zügig abschließen. Ebenso hat das Einrichtungs-WLAN ein festes Passwort;
  es existiert nur, solange der Pi weder eingerichtet ist noch Internet hat.
- **Chrome** zeigt „Von deiner Organisation verwaltet“, weil die Claude-Erweiterung per
  Richtlinie installiert wird.
- Pi 5 folgt später.

## Selbst bauen

GitHub Actions baut das Image automatisch:

- **Release**: Tag `vX.Y.Z` pushen → Image, Imager-Datei und Prüfsummen erscheinen unter Releases.
- **Testbuild**: *Actions → „Prüfen und Image bauen“ → Run workflow* → Image als Artefakt.

Lokal (Linux mit Docker): `./build.sh` – das Image liegt danach in `pi-gen/deploy/`.

Tests und Lint: `pytest -q`, `ruff check .`, `shellcheck` (läuft auch in CI).

## Aufbau

```
stage-claude/                     pi-gen-Stufe (läuft nach stage2 = Raspberry Pi OS Lite)
  00-install/00-packages          Pakete im Image (klein halten)
  00-install/01-run.sh            kopiert files/rootfs ins Image
  00-install/02-run-chroot.sh     Rechte, Dienste, Benutzer "claude"
  00-install/files/rootfs/        Dateien, die ins Image kommen
    opt/kistengeist/bin/            Installer, Sitzung, Leiste, Speicher, Hotspot, Konsole
    opt/kistengeist/modules/        wählbare Module (module.conf + install.sh)
    opt/kistengeist/wizard/         Setup-Assistent (Python-Standardbibliothek + HTML/JS)
    etc/systemd/system/           Dienste für die Einrichtung
tools/make_imager_json.py         Repository-Datei für Raspberry Pi Imager
tests/                            Tests inkl. Probelauf des Installers für alle Zugangsarten
```

## Marken

Raspberry Pi is a trademark of Raspberry Pi Ltd. Claude and Claude Code are trademarks of Anthropic, PBC.
Kistengeist ist ein unabhängiges Projekt und weder mit Raspberry Pi Ltd noch mit Anthropic verbunden.
Es läuft auf einem Raspberry Pi und enthält vorinstalliert Claude Desktop und Claude Code; für Claude
braucht jede Nutzerin und jeder Nutzer ein eigenes Claude-Konto.
