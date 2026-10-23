#!/usr/bin/env bash
set -euo pipefail

CI_DIR="${SOFTWIKI_CI_DIR:-$HOME/softwiki-ci}"
BRANCH="${SOFTWIKI_CI_BRANCH:-master}"
REMOTE="${SOFTWIKI_GIT_REMOTE:-ssh://git@10.3.9.19:2222/faye/softwiki.git}"
ENV_FILE="${SOFTWIKI_ENV_FILE:-/opt/aitools/apps/softwiki/.env}"
WORKSPACE="${SOFTWIKI_WORKSPACE:-/opt/aitools/apps/softwiki/workspace}"
ACTIVE_WORKSPACE="${SOFTWIKI_ACTIVE_WORKSPACE:-lsl-kb}"
API_HOST_PORT="${API_HOST_PORT:-6300}"
MCP_HOST_PORT="${MCP_HOST_PORT:-6301}"
WEB_HOST_PORT="${WEB_HOST_PORT:-6308}"
STATE_DIR="$CI_DIR/.deploy"
LOCK_FILE="/tmp/softwiki-ci.lock"

mkdir -p "$STATE_DIR" "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "[ci] another run in progress"; exit 0; }

if [ -d "$CI_DIR" ] && [ ! -d "$CI_DIR/.git" ]; then
  echo "[ci] $CI_DIR exists but is not a git clone" >&2
  exit 1
fi
if [ ! -d "$CI_DIR/.git" ]; then
  git clone -q "$REMOTE" "$CI_DIR"
fi

git -C "$CI_DIR" fetch -q --prune origin "$BRANCH"
SHA="$(git -C "$CI_DIR" rev-parse --short=12 "origin/$BRANCH")"
LAST="$(cat "$STATE_DIR/last-deployed-sha" 2>/dev/null || true)"
if [ "$SHA" = "$LAST" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "[ci] up to date ($SHA)"
  exit 0
fi

PREV="$(cat "$STATE_DIR/last-good-sha" 2>/dev/null || true)"
git -C "$CI_DIR" reset --hard -q "origin/$BRANCH"

export TAG="$SHA"
export SOFTWIKI_ENV_FILE="$ENV_FILE"
export SOFTWIKI_WORKSPACE="$WORKSPACE"
export SOFTWIKI_ACTIVE_WORKSPACE="$ACTIVE_WORKSPACE"
export API_HOST_PORT MCP_HOST_PORT WEB_HOST_PORT

COMPOSE=(docker compose -f "$CI_DIR/docker-compose.yml" --project-name softwiki)

echo "[ci] deploying $SHA"
"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --no-build --remove-orphans

health() {
  for _ in $(seq 1 90); do
    if curl -fsS -m 3 "http://127.0.0.1:${API_HOST_PORT}/api/status" >/dev/null 2>&1 \
      && curl -fsS -m 3 -o /dev/null "http://127.0.0.1:${WEB_HOST_PORT}/" \
      && (echo > "/dev/tcp/127.0.0.1/${MCP_HOST_PORT}") >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

if ! health; then
  echo "[ci] health check failed" >&2
  "${COMPOSE[@]}" logs --tail=100 || true
  if [ -n "$PREV" ]; then
    echo "[ci] rolling back to $PREV" >&2
    export TAG="$PREV"
    "${COMPOSE[@]}" up -d --no-build --remove-orphans || true
  fi
  exit 1
fi

echo "$SHA" > "$STATE_DIR/last-deployed-sha"
echo "$SHA" > "$STATE_DIR/last-good-sha"
echo "[ci] deployed $SHA"
