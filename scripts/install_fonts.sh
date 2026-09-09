#!/usr/bin/env bash
# install_fonts.sh — Install Vazirmatn Persian fonts for LibreOffice, Chrome, and system viewers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$SCRIPT_DIR/assets/fonts"
DEST="$HOME/.fonts"

count=$(find "$SRC" -maxdepth 2 \( -iname '*.ttf' -o -iname '*.otf' \) 2>/dev/null | wc -l)
if [ "$count" -eq 0 ]; then
  echo "ERROR: no font files found in $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"
find "$SRC" -maxdepth 2 \( -iname '*.ttf' -o -iname '*.otf' \) -exec cp -f {} "$DEST/" \;
fc-cache -f "$DEST" >/dev/null 2>&1 || fc-cache -f >/dev/null 2>&1

echo "Successfully installed $count font file(s) to $DEST:"
fc-list :lang=fa family 2>/dev/null | sort -u | sed 's/^/  /'
