#!/usr/bin/env bash
# Install a pinned opencode binary for SoftWiki Agent.
# Usage: scripts/install-opencode.sh [version] [arch]
set -euo pipefail

VERSION="${1:-1.19.5}"
ARCH="${2:-x64}"
BASE="/opt/aitools/apps/softwiki/engine/opencode/${VERSION}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

case "$ARCH" in
  x64) ASSET="opencode-linux-x64.tar.gz" ;;
  arm64) ASSET="opencode-linux-arm64.tar.gz" ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

mkdir -p "$BASE"
curl -fL --retry 3 -o "$TMP/$ASSET" \
  "https://github.com/anomalyco/opencode/releases/download/v${VERSION}/${ASSET}"
echo "sha256: $(sha256sum "$TMP/$ASSET" | awk '{print $1}')"
tar -xzf "$TMP/$ASSET" -C "$TMP"
install -m 0755 "$TMP/opencode" "$BASE/opencode"
"$BASE/opencode" --version
echo "$VERSION" > "$BASE/VERSION"
