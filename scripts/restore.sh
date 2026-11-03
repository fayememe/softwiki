#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:?usage: restore.sh <archive> [workspace_dir]}"
WORKSPACE="${2:-/opt/aitools/apps/softwiki/workspace/kb-alpha}"
PARENT="$(dirname "$WORKSPACE")"
mkdir -p "$PARENT"
tar -xzf "$ARCHIVE" -C "$PARENT"
echo "restored to $WORKSPACE"
