#!/usr/bin/env bash
# Blue Archive GL: Traditional Chinese -> Simplified Chinese, on-device (Linux / macOS / WSL).
#
# OPTIONAL helper (pull / convert / push via adb). The converter itself is `batr patch`,
# which fixes the CRC32 of the output database in place (appends 4 bytes), so the
# TableCatalog.bytes rewrite step is gone entirely.
#
# Usage:
#   ./localize_phone.sh                 # auto-pick the first non-emulator device
#   ./localize_phone.sh <serial>        # target a specific device
#   DRY_RUN=1 ./localize_phone.sh       # pull + convert, do not push
#   BA_KEY=<hex> ./localize_phone.sh    # override the SQLCipher key
#
# Requirements: uv (https://docs.astral.sh/uv/) and adb in PATH.
set -euo pipefail

PKG=com.nexon.bluearchive
BASE="/sdcard/Android/data/$PKG/files/PUB/Resource"
# Repo root = grandparent of the scripts/legacy/ directory this file lives in.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$ROOT/work"
OUT="$ROOT/output"
ADB="${ADB:-adb}"
UV="${UV:-uv}"
DRY_RUN="${DRY_RUN:-0}"

command -v "$ADB" >/dev/null || { echo "!! adb not found in PATH"; exit 1; }
command -v "$UV"  >/dev/null || { echo "!! uv not found (https://docs.astral.sh/uv/)"; exit 1; }

echo "=== locating device ==="
"$ADB" start-server >/dev/null 2>&1 || true
mapfile -t DEVICES < <("$ADB" devices | awk '$2=="device"{print $1}')
if [ "${1:-}" != "" ]; then
    DEV="$1"
    printf '%s\n' "${DEVICES[@]:-}" | grep -qx "$DEV" || { echo "!! device '$DEV' not found"; exit 1; }
else
    DEV=""
    for d in "${DEVICES[@]:-}"; do
        case "$d" in emulator-*) continue;; esac
        DEV="$d"; break
    done
    [ -n "$DEV" ] || DEV="${DEVICES[0]:-}"
fi
[ -n "$DEV" ] || { echo "!! no device connected (enable USB debugging)"; exit 1; }
echo "  [ok] device = $DEV"

mkdir -p "$WORK" "$OUT"
ORIG_DB="$WORK/ExcelDB.orig.db"
CN_DB="$OUT/ExcelDB.cn.db"

echo "=== stopping the game and pulling the current database (backup kept) ==="
"$ADB" -s "$DEV" shell "am force-stop $PKG" >/dev/null 2>&1 || true
"$ADB" -s "$DEV" pull "$BASE/Preload/TableBundles/ExcelDB.db" "$ORIG_DB"

echo "=== converting Traditional -> Simplified (batr: conversion + CRC fix) ==="
KEY_ARGS=()
[ -n "${BA_KEY:-}" ] && KEY_ARGS=(--key "$BA_KEY")
(cd "$ROOT" && "$UV" run batr "$ORIG_DB" --out "$CN_DB" --verify "${KEY_ARGS[@]}")

if [ "$DRY_RUN" != "0" ]; then
    echo "=== dry run: nothing pushed ==="
    exit 0
fi

echo "=== pushing the patched database back (catalog untouched: CRC already matches) ==="
"$ADB" -s "$DEV" push "$CN_DB" "$BASE/Preload/TableBundles/ExcelDB.db"

cat <<EOF

=== done ===
Launch the game; the UI and story text should now be Simplified Chinese.

Notes:
  * Re-run after every game update (the database changes).
  * Do not use the in-game repair / redownload button; it restores the original files.
  * Original file is backed up at: $ORIG_DB
EOF
