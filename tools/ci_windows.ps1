# Windows-Werkzeug echt testen (GitHub-Runner windows-latest, Administrator):
#  1. Testbetrieb: Ersteinrichtungsdateien (UTF-8 ohne BOM, LF, Sonderzeichen im WLAN)
#  2. Ernstfall auf einem virtuellen Laufwerk (VHDX): echter Raspberry Pi Imager, echtes
#     Raspberry Pi OS Lite, danach Boot-Partition einhängen und Dateien prüfen.
$ErrorActionPreference = 'Stop'
$fail = 0
function Err($t) { Write-Host "::error::$t"; $script:fail = 1 }
$cmd = Join-Path $PWD 'windows\Kistengeist-Installer.cmd'
$out = Join-Path $env:RUNNER_TEMP 'kg-test'

Write-Host '== 1. Testbetrieb'
$env:KG_NONINTERACTIVE = '1'
$env:KG_TEST_OUT = $out
$env:KG_TEST_SSID = 'Mein "WLAN" \ äö'
$env:KG_TEST_PASS = 'p@ss"wo\rd#1 x'
cmd /c "`"$cmd`""
if ($LASTEXITCODE -ne 0) { Err "Testbetrieb endet mit $LASTEXITCODE" }
foreach ($f in 'user-data', 'network-config') {
    $b = [IO.File]::ReadAllBytes((Join-Path $out $f))
    if ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB) { Err "$f mit BOM" }
    if ($b -contains 13) { Err "$f enthält CR" }
}
$code = (Get-Content (Join-Path $out 'code.txt') -Raw).Trim()
if ($code -notmatch '^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{10}$') { Err "Code ungültig: $code" }
if ((Get-Content (Join-Path $out 'user-data') -Raw) -notmatch [regex]::Escape($code)) { Err 'Code fehlt in user-data' }
Remove-Item Env:KG_TEST_OUT, Env:KG_TEST_SSID, Env:KG_TEST_PASS

Write-Host '== 2. Ernstfall auf virtuellem Laufwerk'
$vhd = Join-Path $env:RUNNER_TEMP 'kg.vhdx'
"create vdisk file=`"$vhd`" maximum=12288 type=expandable`nattach vdisk" | Out-File -Encoding ascii "$env:RUNNER_TEMP\dp.txt"
diskpart /s "$env:RUNNER_TEMP\dp.txt" | Out-Host
Start-Sleep 3
$disk = Get-Disk | Where-Object { $_.Location -like "*kg.vhdx*" }
if (-not $disk) { Err 'VHDX nicht gefunden'; exit 1 }
Write-Host "Virtuelles Laufwerk: Nummer $($disk.Number), Typ $($disk.BusType)"
$env:KG_DISK = "$($disk.Number)"
$env:KG_CONFIRM = 'JA'
$env:KG_ALLOW_ANY_DISK = '1'
$env:KG_WIFI_SSID = 'TestWLAN'
$env:KG_WIFI_PASS = 'geheimgeheim'
cmd /c "`"$cmd`""
$rc = $LASTEXITCODE
$log = Join-Path $env:LOCALAPPDATA 'Kistengeist\imager.log'
if (Test-Path $log) { Write-Host '--- imager.log'; Get-Content $log -Tail 40 }
if ($rc -ne 0) { Err "Ernstfall endet mit $rc"; exit 1 }

Update-HostStorageCache
Start-Sleep 3
$part = Get-Partition -DiskNumber $disk.Number | Sort-Object PartitionNumber | Select-Object -First 1
if (-not $part.DriveLetter -or $part.DriveLetter -eq "`0") {
    $part | Add-PartitionAccessPath -AssignDriveLetter
    Start-Sleep 2
    $part = Get-Partition -DiskNumber $disk.Number -PartitionNumber $part.PartitionNumber
}
$boot = "$($part.DriveLetter):\"
Write-Host "Boot-Partition: $boot"; Get-ChildItem $boot | Select-Object -First 40 | Out-Host
foreach ($f in 'user-data', 'meta-data', 'network-config', 'cmdline.txt', 'kernel8.img') {
    if (-not (Test-Path (Join-Path $boot $f))) { Err "$f fehlt auf der Boot-Partition" }
}
$ud = Get-Content (Join-Path $boot 'user-data') -Raw
if ($ud -notmatch '^#cloud-config') { Err 'user-data beginnt nicht mit #cloud-config' }
foreach ($needle in 'hostname: kistengeist', 'kistengeist-firstboot', 'install.sh', '/etc/kistengeist/setup-code') {
    if ($ud -notmatch [regex]::Escape($needle)) { Err "user-data ohne $needle" }
}
$cl = Get-Content (Join-Path $boot 'cmdline.txt') -Raw
if ($cl -notmatch 'ds=nocloud') { Err 'cmdline.txt ohne ds=nocloud' }
if (($cl.Trim() -split "`n").Count -ne 1) { Err 'cmdline.txt hat mehrere Zeilen' }
if ((Get-Content (Join-Path $boot 'network-config') -Raw) -notmatch 'TestWLAN') { Err 'network-config ohne WLAN' }
Copy-Item (Join-Path $boot 'user-data'), (Join-Path $boot 'network-config'), (Join-Path $boot 'meta-data') $out -Force
$desk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Kistengeist-Code.txt'
if (-not (Test-Path $desk)) { Err 'Kistengeist-Code.txt fehlt auf dem Desktop' }
if (Test-Path (Join-Path $env:LOCALAPPDATA 'Kistengeist\network-config')) { Err 'WLAN-Daten bleiben auf dem PC liegen' }
"select vdisk file=`"$vhd`"`ndetach vdisk" | Out-File -Encoding ascii "$env:RUNNER_TEMP\dp2.txt"
diskpart /s "$env:RUNNER_TEMP\dp2.txt" | Out-Null
if ($fail) { exit 1 }
Write-Host 'Windows-Werkzeug: alle Prüfungen bestanden.'
