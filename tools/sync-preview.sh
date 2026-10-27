#!/usr/bin/env bash
# Mirrors the site into a preview sandbox (~/Desktop is not readable there).
#   tools/sync-preview.sh /path/to/scratch/layers-preview
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:?usage: tools/sync-preview.sh <destination-dir>}"
mkdir -p "$DEST/tools"
rsync -a --delete "$SRC/public/" "$DEST/public/"
rsync -a "$SRC/tools/devserver.py" "$DEST/tools/"
rsync -a "$SRC/data/" "$DEST/data/"
echo "synced -> $DEST"
