#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE_DIR:-/opt/aitools/apps/softwiki/workspace/armkb}"
DEST="${1:-/opt/aitools/apps/softwiki/backups}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$DEST/softwiki-$(basename "$WORKSPACE")-$STAMP.tar.gz"
tar -czf "$ARCHIVE" -C "$(dirname "$WORKSPACE")" "$(basename "$WORKSPACE")"
echo "$ARCHIVE"
