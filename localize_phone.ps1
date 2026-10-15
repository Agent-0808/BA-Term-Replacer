# localize_phone.ps1 -- Blue Archive GL: Traditional Chinese -> Simplified Chinese, on-device.
#
# Ported from a working setup; contains no machine-specific paths.
# Requirements: adb in PATH, python 3.9+ with `pip install -r requirements.txt`.
#
# ASCII-only source on purpose: Windows PowerShell decodes BOM-less .ps1 files as ANSI,
# and non-ASCII bytes can break the parser.
param(
    [string]$Serial = "",
    [string]$Key = "",
    [switch]$DryRun
)
$ErrorActionPreference = 'Continue'

$Root   = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Pkg    = 'com.nexon.bluearchive'
$Base   = "/sdcard/Android/data/$Pkg/files/PUB/Resource"
$Work   = Join-Path $Root 'work'

function Step($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Bad($m)  { Write-Host "  [!!] $m" -ForegroundColor Red }

# ---------------------------------------------------------------- tools
$Adb = $env:ADB
if (-not $Adb) {
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { $Adb = $cmd.Source }
}
if (-not $Adb) { Bad 'adb not found. Install Android platform-tools and add it to PATH, or set $env:ADB.'; exit 1 }
Ok "adb = $Adb"

$Py = $env:PYTHON
if (-not $Py) {
    foreach ($cand in @('python', 'python3', 'py')) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if ($cmd) { $Py = $cmd.Source; break }
    }
}
if (-not $Py) { Bad 'python not found in PATH (or set $env:PYTHON).'; exit 1 }
Ok "python = $Py"

$PackDb  = Join-Path $Root 'tools\patch_db.py'
$PackCat = Join-Path $Root 'tools\patch_catalog.py'
if (-not (Test-Path $PackDb)) { Bad "missing $PackDb"; exit 1 }

# ---------------------------------------------------------------- device
Step 'locating device'
& $Adb start-server 2>&1 | Out-Null
$cands = @()
foreach ($l in (& $Adb devices 2>&1)) {
    if ($l -match '^(\S+)\s+device') { $cands += $Matches[1] }
}
if ($Serial) {
    if ($cands -notcontains $Serial) { Bad "device '$Serial' not found. available: $($cands -join ', ')"; exit 1 }
    $Dev = $Serial
} else {
    $Dev = ($cands | Where-Object { $_ -notlike 'emulator-*' } | Select-Object -First 1)
    if (-not $Dev) { $Dev = $cands | Select-Object -First 1 }
}
if (-not $Dev) { Bad 'no device. Connect the phone over USB with USB debugging enabled.'; exit 1 }
Ok "device = $Dev"

New-Item -ItemType Directory -Force $Work | Out-Null
$OrigDb  = Join-Path $Work 'ExcelDB.orig.db'
$OrigCat = Join-Path $Work 'TableCatalog.orig.bytes'
$CnDb    = Join-Path $Work 'ExcelDB.cn.db'
$CnCat   = Join-Path $Work 'TableCatalog.cn.bytes'

# ---------------------------------------------------------------- pull
Step 'stopping the game and pulling the current database + catalog (kept as backup)'
& $Adb -s $Dev shell "am force-stop $Pkg" 2>&1 | Out-Null
& $Adb -s $Dev pull "$Base/Preload/TableBundles/ExcelDB.db" $OrigDb 2>&1 | Select-String 'pulled|error'
& $Adb -s $Dev pull "$Base/Catalog/TableBundles/TableCatalog.bytes" $OrigCat 2>&1 | Select-String 'pulled|error'
if (-not (Test-Path $OrigDb)) { Bad 'pull failed'; exit 1 }
Ok ('backup: {0:N1} MB' -f ((Get-Item $OrigDb).Length / 1MB))

# ---------------------------------------------------------------- convert
Step 'converting Traditional -> Simplified'
$argsDb = @($PackDb, '--in', $OrigDb, '--out', $CnDb)
if ($Key) { $argsDb += @('--key', $Key) }
& $Py -u @argsDb 2>&1 | Select-Object -Last 5
if (-not (Test-Path $CnDb)) { Bad 'conversion failed'; exit 1 }

Step 'patching the catalog CRC32'
$argsCat = @($PackCat, '--catalog', $OrigCat, '--db', $CnDb, '--out', $CnCat, '--expect-crc-db', $OrigDb)
& $Py -u @argsCat 2>&1 | Select-String 'crc|CRC|written'
if (-not (Test-Path $CnCat)) { Bad 'catalog patch failed'; exit 1 }

if ($DryRun) { Ok 'dry run: nothing was pushed'; exit 0 }

# ---------------------------------------------------------------- push
Step 'pushing the patched files back'
& $Adb -s $Dev push $CnDb "$Base/Preload/TableBundles/ExcelDB.db" 2>&1 | Select-String 'pushed|error'
& $Adb -s $Dev push $CnCat "$Base/Catalog/TableBundles/TableCatalog.bytes" 2>&1 | Select-String 'pushed|error'

Step 'done'
Ok 'Launch the game - the UI and story text should be Simplified Chinese.'
Write-Host ''
Write-Host 'Notes:' -ForegroundColor Yellow
Write-Host '  * Re-run this script after every game update (the database changes).'
Write-Host '  * Do not use the in-game repair / redownload button; it restores the original files.'
Write-Host "  * Backups of the original files: $Work"
