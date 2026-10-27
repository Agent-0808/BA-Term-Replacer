# localize_phone.ps1 -- Blue Archive GL: Traditional Chinese -> Simplified Chinese, on-device.
#
# OPTIONAL helper (pull / convert / push via adb). The converter itself is `batr patch`,
# which now fixes the CRC32 of the output database in place (appends 4 bytes), so the
# TableCatalog.bytes rewrite step is gone entirely.
#
# Requirements: uv (https://docs.astral.sh/uv/) and adb in PATH.
# ASCII-only source on purpose: Windows PowerShell decodes BOM-less .ps1 files as ANSI,
# and non-ASCII bytes can break the parser.
param(
    [string]$Serial = "",
    [string]$Key = "",
    [switch]$DryRun
)
$ErrorActionPreference = 'Continue'

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# Repo root = parent of the scripts/ directory this file lives in.
$Root   = Split-Path -Parent $PSScriptRoot
$Pkg    = 'com.nexon.bluearchive'
$Base   = "/sdcard/Android/data/$Pkg/files/PUB/Resource"
$Work   = Join-Path $Root 'work'

function Step($m) { Write-Host ''; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Bad($m)  { Write-Host "  [!!] $m" -ForegroundColor Red }

# ---------------------------------------------------------------- uv (python env manager)
$Uv = $env:UV
if (-not $Uv) {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { $Uv = $cmd.Source }
}
if (-not $Uv) {
    Bad 'uv not found.'
    Write-Host '     Install it first:   powershell -c "irm https://get.scoop.sh | iex" ; scoop install uv'
    Write-Host '     or per the docs:    https://docs.astral.sh/uv/getting-started/installation/'
    exit 1
}
Ok "uv = $Uv"

# ---------------------------------------------------------------- adb
$Adb = $env:ADB
if (-not $Adb) {
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { $Adb = $cmd.Source }
}
if (-not $Adb) {
    $guesses = @(
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "C:\platform-tools\adb.exe",
        "C:\Android\platform-tools\adb.exe",
        "${env:ProgramFiles(x86)}\Netease\MuMu\nx_main\adb.exe",
        "$env:ProgramFiles\Netease\MuMu\nx_main\adb.exe",
        "$env:ProgramFiles\Netease\MuMuPlayer-12.0\shell\adb.exe",
        "C:\Program Files\Netease\MuMu\nx_main\adb.exe",
        "D:\Program Files\Netease\MuMu\nx_main\adb.exe",
        "E:\Program Files\Netease\MuMu\nx_main\adb.exe",
        "${env:ProgramFiles(x86)}\Nox\bin\adb.exe",
        "$env:ProgramFiles\BlueStacks_nxt\HD-Adb.exe",
        "$env:ProgramFiles\LDPlayer\LDPlayer9\adb.exe",
        "D:\LDPlayer\LDPlayer9\adb.exe"
    )
    foreach ($g in $guesses) { if (Test-Path $g) { $Adb = $g; break } }
}
if (-not $Adb) {
    Bad 'adb not found.'
    Write-Host '     Install Android platform-tools and add it to PATH,'
    Write-Host '     or set the path explicitly:   $env:ADB = "C:\path\to\adb.exe"'
    exit 1
}
Ok "adb = $Adb"

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
$OrigDb = Join-Path $Work 'ExcelDB.orig.db'
$CnDb   = Join-Path $Work 'ExcelDB.cn.db'

# ---------------------------------------------------------------- pull
Step 'stopping the game and pulling the current database (kept as backup)'
& $Adb -s $Dev shell "am force-stop $Pkg" 2>&1 | Out-Null
& $Adb -s $Dev pull "$Base/Preload/TableBundles/ExcelDB.db" $OrigDb 2>&1 | Select-String 'pulled|error'
if (-not (Test-Path $OrigDb)) { Bad 'pull failed'; exit 1 }
Ok ('backup: {0:N1} MB' -f ((Get-Item $OrigDb).Length / 1MB))

# ---------------------------------------------------------------- convert
Step 'converting Traditional -> Simplified (batr patch: conversion + CRC fix, no catalog step)'
$argsBatr = @('run', 'batr', 'patch', '--db', $OrigDb, '--out', $CnDb, '--verify')
if ($Key) { $argsBatr += @('--key', $Key) }
& $Uv @argsBatr 2>&1 | Select-Object -Last 6
if (-not (Test-Path $CnDb)) { Bad 'conversion failed'; exit 1 }

if ($DryRun) { Ok 'dry run: nothing was pushed'; exit 0 }

# ---------------------------------------------------------------- push
Step 'pushing the patched database back (catalog untouched: CRC already matches)'
& $Adb -s $Dev push $CnDb "$Base/Preload/TableBundles/ExcelDB.db" 2>&1 | Select-String 'pushed|error'

Step 'done'

# ---------------------------------------------------------------- font fix
# The Android client bundles no Chinese font on the UI render path, so replaced
# characters may trigger per-glyph font fallback (mixed sizes/weights).  Setting the
# app language to Simplified makes the system pick a full Simplified font.
Step 'fixing font fallback (app language -> Simplified Chinese)'
$sdkRaw = ((& $Adb -s $Dev shell "getprop ro.build.version.sdk" 2>&1) -join ' ').Trim()
$sdk = 0
if ($sdkRaw -match '(\d+)') { $sdk = [int]$Matches[1] }
if ($sdk -ge 33) {
    & $Adb -s $Dev shell "cmd locale set-app-locales $Pkg --locales zh-Hans-CN" 2>&1 | ForEach-Object { Write-Host "  $_" }
    $now = ((& $Adb -s $Dev shell "cmd locale get-app-locales $Pkg" 2>&1) -join ' ').Trim()
    Ok "app locale = $now"
    Write-Host '  (restart the game once so it re-loads the font)'
} else {
    Write-Host "  Android $sdk < 13 - per-app language is not supported."
    Write-Host '  If Chinese text has mixed glyph sizes, set the SYSTEM language to' -ForegroundColor Yellow
    Write-Host '  Simplified Chinese (Settings -> System -> Languages). Same fallback fix.' -ForegroundColor Yellow
}

Ok 'Launch the game - the UI and story text should be Simplified Chinese.'
Write-Host ''
Write-Host 'Notes:' -ForegroundColor Yellow
Write-Host '  * Re-run this script after every game update (the database changes).'
Write-Host '  * Do not use the in-game repair / redownload button; it restores the original files.'
Write-Host "  * Backups of the original file: $OrigDb"
