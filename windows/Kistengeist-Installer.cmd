<# : Kistengeist-Installer (Windows) – Batch-Teil, danach folgt PowerShell
@echo off
setlocal
title Kistengeist-Installer
set "KG_SELF=%~f0"
rem Adminrechte (zum Schreiben der Speicherkarte nötig) – sonst neu mit UAC-Abfrage starten.
fltmc >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "try { Start-Process -FilePath $env:KG_SELF -Verb RunAs -ErrorAction Stop } catch { exit 1 }"
    if errorlevel 1 (
        echo Ohne Administratorrechte kann die Speicherkarte nicht beschrieben werden.
        pause
    )
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:KG_SELF); Invoke-Expression $s"
set "rc=%errorlevel%"
echo.
if not defined KG_NONINTERACTIVE pause
exit /b %rc%
#>
# ---------------------------------------------------------------------------------------------
# Kistengeist-Installer für Windows 10/11
#
# 1. lädt das offizielle Raspberry Pi OS Lite (64-bit) und prüft die SHA256-Prüfsumme,
# 2. installiert bei Bedarf den offiziellen Raspberry Pi Imager (signiert von Raspberry Pi Ltd),
# 3. schreibt das System auf die gewählte Speicherkarte bzw. den USB-Stick und legt dabei eine
#    Ersteinrichtung an (cloud-init): Gerätename „kistengeist“, optional WLAN, und beim ersten
#    Start lädt der Pi den Kistengeist-Installer aus dem Internet und baut sich selbst um,
# 4. zeigt den Einrichtungscode für den Setup-Assistenten (http://kistengeist.local).
#
# Raspberry Pi is a trademark of Raspberry Pi Ltd. Claude is a trademark of Anthropic, PBC.
# Kistengeist ist ein unabhängiges Projekt und nicht mit diesen Unternehmen verbunden.
#
# Ohne Rückfragen (Fortgeschrittene/Tests), Umgebungsvariablen:
#   KG_NONINTERACTIVE=1  KG_DISK=<Datenträgernummer>  KG_CONFIRM=JA  [KG_WIFI_SSID=… KG_WIFI_PASS=…]
#   KG_ALLOW_ANY_DISK=1  auch andere Datenträgertypen (z. B. virtuelle Laufwerke im Test)
# Testbetrieb (nur Entwicklung): KG_TEST_OUT=<ordner> schreibt nur die Ersteinrichtungsdateien.
# ---------------------------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Wird im Release auf die Installer-Datei genau dieser Version festgelegt.
$KgInstallUrl = 'https://raw.githubusercontent.com/TimoKapp/kistengeist/main/install.sh'
$KgInstallSha = ''   # im Release: SHA256 von install.sh
$OsLatestUrl = 'https://downloads.raspberrypi.com/raspios_lite_arm64_latest'
$ImagerUrl = 'https://downloads.raspberrypi.org/imager/imager_latest.exe'
$ImagerMin = [version]'2.0.11'
$Work = Join-Path $env:LOCALAPPDATA 'Kistengeist'
$TestOut = $env:KG_TEST_OUT

function Say($t) { Write-Host "==> $t" -ForegroundColor Green }
function Warn($t) { Write-Host "    $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "Fehler: $t" -ForegroundColor Red; exit 1 }

# Text als UTF-8 ohne BOM und mit LF schreiben (sonst ignoriert cloud-init die Datei stillschweigend).
function Write-Unix($path, $text) {
    [IO.File]::WriteAllText($path, ($text -replace "`r`n", "`n"), (New-Object Text.UTF8Encoding($false)))
}

# YAML-Zeichenkette in doppelten Anführungszeichen.
function Q($s) { '"' + ($s -replace '\\', '\\' -replace '"', '\"') + '"' }

function New-SetupCode {
    $alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 64
    $rng.GetBytes($bytes)
    $code = ''
    foreach ($b in $bytes) {
        if ($b -lt 248) { $code += $alphabet[$b % 31] }   # 248 = 8*31: ohne Verzerrung
        if ($code.Length -eq 10) { break }
    }
    if ($code.Length -ne 10) { return New-SetupCode }
    return $code
}

function New-UserData($code) {
    # Ohne Kopfzeile: der Imager setzt „#cloud-config“ selbst davor.
    $boot = @'
#!/bin/bash
# Kistengeist: beim ersten Start den Installer laden und ausführen. Wiederholt endlos (mit
# wachsender Pause), bis Internet da ist; Fortschritt und Fehler stehen am Bildschirm (tty1).
log=/var/log/kistengeist-firstboot.log
(umask 077; touch "$log")
exec >>"$log" 2>&1
show() { printf '\033[2J\033[H\n  Kistengeist wird eingerichtet\n\n  %s\n\n' "$*" >/dev/tty1 2>/dev/null || true; }
url="@URL@"
sha="@SHA@"
f=/root/kistengeist-install.sh
pause=10
while :; do
  show "Lade den Installer ... (Netzwerkkabel bzw. WLAN nötig)"
  if curl -fsSL --max-time 120 "$url" -o "$f.tmp"; then
    if [ -z "$sha" ] || echo "$sha  $f.tmp" | sha256sum -c - >/dev/null; then
      mv -f "$f.tmp" "$f"
      break
    fi
    show "Prüfsumme des Installers stimmt nicht - neuer Versuch in $pause Sekunden."
  else
    show "Kein Internet. Bitte Netzwerkkabel bzw. WLAN prüfen. Neuer Versuch in $pause Sekunden."
  fi
  sleep "$pause"
  [ "$pause" -lt 300 ] && pause=$((pause * 2))
done
show "Installiere Kistengeist ... (einige Minuten)"
if KG_START_CONSOLE=1 bash "$f"; then
  systemctl disable kistengeist-firstboot.service
else
  show "Fehler bei der Einrichtung (neuer Versuch in 1 Minute):" "$(tail -n 3 "$log")"
  exit 1
fi
'@
    $boot = $boot.Replace('@URL@', $KgInstallUrl).Replace('@SHA@', $KgInstallSha)
    $bootIndented = ($boot -split "`r?`n" | ForEach-Object { "      $_" }) -join "`n"
    return @"
hostname: kistengeist
manage_etc_hosts: true
timezone: Europe/Berlin
keyboard:
  model: pc105
  layout: de
user:
  name: claude
  shell: /bin/bash
  lock_passwd: true
  sudo: null
  groups: [sudo, video, render, audio, input, plugdev, netdev]
ssh_pwauth: false
write_files:
  - path: /etc/kistengeist/setup-code
    permissions: '0600'
    content: |
      $code
  - path: /usr/local/sbin/kistengeist-firstboot
    permissions: '0755'
    content: |
$bootIndented
  - path: /etc/systemd/system/kistengeist-firstboot.service
    content: |
      [Unit]
      Description=Kistengeist: Erstinstallation aus dem Internet
      Wants=network-online.target
      After=network-online.target cloud-final.service
      [Service]
      Type=oneshot
      ExecStart=/usr/local/sbin/kistengeist-firstboot
      TimeoutStartSec=0
      Restart=on-failure
      RestartSec=60
      [Install]
      WantedBy=multi-user.target
runcmd:
  - [systemctl, daemon-reload]
  - [systemctl, enable, kistengeist-firstboot.service]
  - [systemctl, start, --no-block, kistengeist-firstboot.service]
"@
}

function New-NetworkConfig($ssid, $pass, $country) {
    $auth = if ($pass) { "            password: $(Q $pass)" } else { "            auth:`n              key-management: none" }
    return @"
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      dhcp6: true
      optional: true
  wifis:
    wlan0:
      dhcp4: true
      dhcp6: true
      regulatory-domain: $(Q $country)
      optional: true
      access-points:
        $(Q $ssid):
$auth
"@
}

function Find-Imager {
    $keys = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    $found = @()
    foreach ($e in (Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like 'Raspberry Pi Imager*' })) {
        $dir = $e.InstallLocation
        if (-not $dir -and $e.DisplayIcon) { $dir = Split-Path ($e.DisplayIcon -replace '"', '' -replace ',\d+$', '') }
        $exe = if ($dir) { Join-Path $dir 'rpi-imager.exe' } else { $null }
        if ($exe -and (Test-Path $exe)) {
            try { $v = [version]((Get-Item $exe).VersionInfo.ProductVersion -replace '[^0-9.].*$', '') } catch { $v = [version]'0.0' }
            $found += [pscustomobject]@{ Exe = $exe; Version = $v }
        }
    }
    return ($found | Sort-Object Version -Descending | Select-Object -First 1)
}

function Install-Imager {
    Say 'Raspberry Pi Imager wird installiert (offizielles, signiertes Programm von Raspberry Pi Ltd)'
    $setup = Join-Path $Work 'imager-setup.exe'
    & curl.exe --ssl-revoke-best-effort -fL --retry 3 -o $setup $ImagerUrl
    if ($LASTEXITCODE -ne 0) { Fail 'Raspberry Pi Imager konnte nicht geladen werden.' }
    $sig = Get-AuthenticodeSignature $setup
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notlike 'CN=Raspberry Pi Ltd*') {
        Remove-Item $setup -Force
        Fail "Die Signatur des Imagers ist ungültig ($($sig.Status)). Abbruch."
    }
    Warn 'Fragt Windows gleich, ob Gerätesoftware von Raspberry Pi Ltd installiert werden soll: INSTALLIEREN klicken.'
    $p = Start-Process -FilePath $setup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
    if ($p.ExitCode -ne 0) { Fail "Installation des Imagers fehlgeschlagen (Code $($p.ExitCode))." }
}

# ---------------------------------------------------------------------------------------------
Clear-Host
Write-Host ''
Write-Host '  Kistengeist-Installer' -ForegroundColor Cyan
Write-Host '  Macht aus einer Speicherkarte (oder einem USB-Stick) einen Kistengeist für den Raspberry Pi 4/5.'
Write-Host '  Dauer: ca. 10 Minuten am PC, danach ca. 5-15 Minuten am Pi bis zum Setup-Assistenten (Internet nötig).'
Write-Host ''
New-Item -ItemType Directory -Force -Path $Work | Out-Null

$code = New-SetupCode

if ($TestOut) {
    New-Item -ItemType Directory -Force -Path $TestOut | Out-Null
    Write-Unix (Join-Path $TestOut 'user-data') (New-UserData $code)
    Write-Unix (Join-Path $TestOut 'network-config') (New-NetworkConfig $env:KG_TEST_SSID $env:KG_TEST_PASS 'DE')
    Write-Unix (Join-Path $TestOut 'code.txt') $code
    Say "Testbetrieb: Dateien in $TestOut"
    exit 0
}

# --- 1. Raspberry Pi Imager --------------------------------------------------------------------
$imager = Find-Imager
if (-not $imager -or $imager.Version -lt $ImagerMin) {
    Install-Imager
    $imager = Find-Imager
    if (-not $imager -or $imager.Version -lt $ImagerMin) { Fail "Raspberry Pi Imager $ImagerMin oder neuer wurde nicht gefunden." }
}
Say "Raspberry Pi Imager $($imager.Version)"

# --- 2. Raspberry Pi OS Lite laden und prüfen ----------------------------------------------------
Say 'Neueste Version von Raspberry Pi OS Lite (64-bit) ermitteln'
$url = (& curl.exe --ssl-revoke-best-effort -sSLI -o NUL -w '%{url_effective}' $OsLatestUrl)
if ($LASTEXITCODE -ne 0 -or $url -notmatch '^https://downloads\.raspberrypi\.com/.+\.img\.xz$') {
    Fail 'Download-Adresse von Raspberry Pi OS nicht gefunden (Internet?).'
}
$name = Split-Path $url -Leaf
$img = Join-Path $Work $name
$expected = ((& curl.exe --ssl-revoke-best-effort -fsSL "$url.sha256") -split '\s+')[0].ToLower()
if ($expected -notmatch '^[0-9a-f]{64}$') { Fail 'Prüfsumme von Raspberry Pi OS nicht erhältlich.' }
$have = if (Test-Path $img) { (Get-FileHash -Algorithm SHA256 $img).Hash.ToLower() } else { '' }
if ($have -ne $expected) {
    Say "Lade $name (ca. 500 MB)"
    & curl.exe --ssl-revoke-best-effort -fL --retry 5 -C - -o $img $url
    if ($LASTEXITCODE -ne 0) { Fail 'Download fehlgeschlagen.' }
    $have = (Get-FileHash -Algorithm SHA256 $img).Hash.ToLower()
    if ($have -ne $expected) { Remove-Item $img -Force; Fail 'Prüfsumme stimmt nicht – Datei verworfen.' }
}
Say 'Prüfsumme in Ordnung'
# Das Image muss die Ersteinrichtung per cloud-init lesen (seit Trixie 11/2025). Stellt Raspberry Pi
# künftig um, würde die Einrichtung sonst still ignoriert.
try {
    $list = (& curl.exe --ssl-revoke-best-effort -fsSL 'https://downloads.raspberrypi.com/os_list_imagingutility_v4.json') -join "`n" | ConvertFrom-Json
    $stack = New-Object System.Collections.Stack
    $stack.Push($list.os_list)
    $entry = $null
    while ($stack.Count -gt 0 -and -not $entry) {
        foreach ($o in @($stack.Pop())) {
            if ($o.url -and ($o.url -like '*raspios_lite_arm64*' -or $o.url -like "*$name")) { $entry = $o; break }
            if ($o.subitems) { $stack.Push($o.subitems) }
        }
    }
    if ($entry -and $entry.init_format -and $entry.init_format -notlike 'cloudinit*') {
        Fail "Raspberry Pi OS nutzt eine neue Art der Ersteinrichtung ($($entry.init_format)). Bitte eine neue Version des Kistengeist-Installers laden."
    }
} catch {
    Warn 'Art der Ersteinrichtung konnte nicht geprüft werden (weiter mit cloud-init).'
}
# Alte Versionen aufräumen
Get-ChildItem $Work -Filter '*raspios*.img.xz' | Where-Object { $_.Name -ne $name } | Remove-Item -Force

# --- 3. Speicherkarte wählen ------------------------------------------------------------------
Write-Host ''
$auto = $env:KG_NONINTERACTIVE -eq '1'
if (-not $auto) {
    Write-Host '  Bitte jetzt die Speicherkarte (bzw. den USB-Stick) für den Pi einstecken.' -ForegroundColor Cyan
    Read-Host '  Danach Enter drücken' | Out-Null
}
$types = if ($env:KG_ALLOW_ANY_DISK -eq '1') { @('USB', 'SD', 'MMC', 'File Backed Virtual') } else { @('USB', 'SD', 'MMC') }
$disks = @(Get-Disk | Where-Object { "$($_.BusType)" -in $types -and -not $_.IsBoot -and -not $_.IsSystem -and $_.Size -gt 0 })
if ($disks.Count -eq 0) { Fail 'Keine Speicherkarte bzw. kein USB-Stick gefunden.' }
Write-Host ''
foreach ($d in $disks) {
    $gb = [math]::Round($d.Size / 1GB, 1)
    $vols = @(Get-Partition -DiskNumber $d.Number -ErrorAction SilentlyContinue | Get-Volume -ErrorAction SilentlyContinue |
        Where-Object { $_.DriveLetter } | ForEach-Object { "$($_.DriveLetter): $($_.FileSystemLabel)".Trim() })
    $where = if ($vols) { '  [' + ($vols -join ', ') + ']' } else { '' }
    $warn = if ($d.Size -gt 128GB) { '  (groß - ist das wirklich die Speicherkarte?)' } else { '' }
    Write-Host ("   [{0}]  {1}  {2} GB{3}{4}" -f $d.Number, $d.FriendlyName, $gb, $where, $warn)
}
Write-Host ''
$num = if ($auto) { "$env:KG_DISK" } else { Read-Host '  Nummer des Ziels eingeben' }
$disk = $disks | Where-Object { "$($_.Number)" -eq $num.Trim() }
if (-not $disk) { Fail 'Ungültige Auswahl.' }
if ($disk.Size -lt 14GB) { Fail 'Die Karte ist zu klein (mindestens 16 GB, empfohlen 32 GB).' }
Write-Host ''
Write-Host ("  ALLE DATEN auf '{0}' ({1} GB) werden gelöscht!" -f $disk.FriendlyName, [math]::Round($disk.Size / 1GB, 1)) -ForegroundColor Red
$confirm = if ($auto) { "$env:KG_CONFIRM" } else { Read-Host '  Zum Fortfahren JA eingeben' }
if ($confirm.Trim() -ne 'JA') { Fail 'Abgebrochen - nichts wurde verändert.' }
if ($disk.Size -gt 128GB -and -not $auto) {
    if ((Read-Host '  Das Ziel ist größer als 128 GB (Festplatte?). Wirklich löschen? Nochmal JA eingeben').Trim() -ne 'JA') {
        Fail 'Abgebrochen - nichts wurde verändert.'
    }
}

# --- 4. WLAN (optional) ------------------------------------------------------------------------
Write-Host ''
Write-Host '  Netzwerk: Am einfachsten ist ein Netzwerkkabel am Pi. Ohne Kabel hier das WLAN eintragen.'
$ssid = if ($auto) { "$env:KG_WIFI_SSID" } else { Read-Host '  WLAN-Name (leer lassen bei Netzwerkkabel)' }
$nc = $null
if ($ssid) {
    if ($auto) {
        $pass = "$env:KG_WIFI_PASS"
    } else {
        $sec = Read-Host '  WLAN-Passwort' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        $pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($pass -and ($pass.Length -lt 8 -or $pass.Length -gt 63)) { Fail 'Ein WLAN-Passwort hat 8 bis 63 Zeichen.' }
    if ([Text.Encoding]::UTF8.GetByteCount($ssid) -gt 32) { Fail 'Der WLAN-Name ist zu lang (höchstens 32 Zeichen).' }
    $nc = Join-Path $Work 'network-config'
    Write-Unix $nc (New-NetworkConfig $ssid $pass 'DE')
}
$ud = Join-Path $Work 'user-data'
Write-Unix $ud (New-UserData $code)

# --- 5. Schreiben --------------------------------------------------------------------------------
Write-Host ''
Say 'Schreibe die Speicherkarte (ca. 5-10 Minuten, danach wird geprüft)'
Warn 'Fragt Windows zwischendurch, ob ein Datenträger formatiert werden soll: immer ABBRECHEN!'
$log = Join-Path $Work 'imager.log'
$imgArgs = @('--cli', '--debug', '--cloudinit-userdata', $ud)
if ($nc) { $imgArgs += @('--cloudinit-networkconfig', $nc) }
if ($env:KG_ALLOW_ANY_DISK -eq '1') { $imgArgs += @('--enable-writing-system-drives', '--disable-eject') }
$imgArgs += @('--log-file', $log, $img, "\\.\PhysicalDrive$($disk.Number)")
$p = Start-Process -FilePath $imager.Exe -ArgumentList ($imgArgs | ForEach-Object { '"' + $_ + '"' }) -Wait -PassThru -NoNewWindow
# WLAN-Daten nicht auf dem PC liegen lassen
if ($nc) { Remove-Item $nc -Force -ErrorAction SilentlyContinue }
Remove-Item $ud -Force -ErrorAction SilentlyContinue
if ($p.ExitCode -ne 0) {
    $tail = if (Test-Path $log) { (Get-Content $log -Tail 30) -join "`n" } else { '' }
    if ($tail -match 'removable') {
        Fail 'Der Imager lehnt dieses Laufwerk ab (kein Wechseldatenträger). Bitte eine Speicherkarte bzw. einen USB-Stick verwenden.'
    }
    if ($tail) { Write-Host $tail }
    Fail "Schreiben fehlgeschlagen (Code $($p.ExitCode)). Protokoll: $log"
}

# --- 6. Fertig ---------------------------------------------------------------------------------
$codeText = @(
    'Kistengeist - Einrichtungscode',
    '',
    "Code:     $code",
    'Adresse:  http://kistengeist.local',
    '          Klappt das nicht: http://kistengeist.fritz.box, die IP-Adresse vom Bildschirm des Pi',
    '          oder aus der Geräteliste des Routers (PC nicht im Gast-WLAN/VPN).',
    '',
    'Der Code schützt die Einrichtung vor anderen Geräten im Netz. Nach der Einrichtung',
    'wird er nicht mehr gebraucht - diese Datei dann bitte löschen.')
# Auf den Desktop und neben dieses Programm (bei UAC mit fremdem Admin-Konto liegt der Desktop woanders).
$codeFiles = @()
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), (Split-Path $env:KG_SELF))) {
    try {
        if ($dir) {
            $f = Join-Path $dir 'Kistengeist-Code.txt'
            Set-Content -Path $f -Encoding UTF8 -Value $codeText
            $codeFiles += $f
        }
    } catch { }
}
$codeFile = ($codeFiles | Select-Object -Unique) -join ' und '
if (-not $codeFile) { $codeFile = '(konnte nicht gespeichert werden - bitte notieren!)' }
Write-Host ''
Write-Host '  Fertig! So geht es weiter:' -ForegroundColor Green
Write-Host '   1. Karte in den Raspberry Pi stecken, Netzwerkkabel (falls kein WLAN) und Strom anschließen.'
Write-Host '   2. 5-15 Minuten warten: Der Pi lädt Kistengeist aus dem Internet und bereitet sich vor.'
Write-Host '   3. Im Browser öffnen:  http://kistengeist.local'
Write-Host '      (sonst http://kistengeist.fritz.box oder die IP-Adresse vom Bildschirm des Pi)'
Write-Host "   4. Einrichtungscode:   $code" -ForegroundColor Cyan
Write-Host "      (auch gespeichert in $codeFile)"
Write-Host ''
exit 0
