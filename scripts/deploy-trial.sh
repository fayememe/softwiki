#!/usr/bin/env bash
# Deploy the current working tree to trial-host, in one shot.
#
# trial-host has no CI and cannot reach Forgejo / Docker Hub / npmjs, so this
# script is the supported deploy path: sync source over ssh, rebuild the API
# image from the already-verified dependency layer, recreate both stacks and
# verify health. Web assets are NOT rebuilt (trial keeps its own web build).
#
# Usage:
#   scripts/deploy-trial.sh                 # sync + build + recreate + verify
#   scripts/deploy-trial.sh --skip-build    # source-only (reuse current image)
#   scripts/deploy-trial.sh --skip-backup   # skip pg_dump
#   scripts/deploy-trial.sh --migrate-vectors
#   scripts/deploy-trial.sh --check         # preflight only
#
# Env:
#   TRIAL_HOST (default faye@118.193.105.3)
#   TRIAL_DIR  (default /opt/aitools/apps/softwiki)
set -euo pipefail

TRIAL_HOST="${TRIAL_HOST:-faye@118.193.105.3}"
TRIAL_DIR="${TRIAL_DIR:-/opt/aitools/apps/softwiki}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"

SKIP_BUILD=0
SKIP_BACKUP=0
MIGRATE_VECTORS=0
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --skip-backup) SKIP_BACKUP=1 ;;
    --migrate-vectors) MIGRATE_VECTORS=1 ;;
    --check) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '\n[deploy-trial] %s\n' "$*"; }
remote() { ssh -o BatchMode=yes "$TRIAL_HOST" "$@"; }
remote_sh() { ssh -o BatchMode=yes "$TRIAL_HOST" "bash -lc '$1'"; }

log "preflight: $TRIAL_HOST:$TRIAL_DIR"
remote "test -d '$TRIAL_DIR' && test -f '$TRIAL_DIR/docker-compose.yml' && sudo -n true" \
  || { echo "preflight failed: dir/compose/sudo" >&2; exit 1; }
remote "command -v docker >/dev/null && command -v /usr/local/bin/docker-compose >/dev/null || command -v docker-compose >/dev/null"
remote "sudo docker ps --format '{{.Names}}' | grep -q softwiki-api-1" \
  || { echo "preflight failed: coffee stack not running" >&2; exit 1; }
remote "df -h '$TRIAL_DIR' | tail -1"

if [ "$CHECK_ONLY" = "1" ]; then
  log "check-only: ok"
  exit 0
fi

if [ "$SKIP_BACKUP" = "0" ]; then
  log "backup: pg_dump coffee + ai-history"
  remote "cd '$TRIAL_DIR' && \
    sudo docker exec softwiki-postgres-1 pg_dump -U softwiki -d softwiki_coffee | gzip > backup-coffee-deploy-$STAMP.sql.gz && \
    sudo docker exec softwiki-ai-postgres-1 pg_dump -U softwiki -d softwiki_ai_history | gzip > backup-ai-deploy-$STAMP.sql.gz && \
    ls -lh backup-*-deploy-$STAMP.sql.gz"
fi

log "sync: softwiki/ scripts/ kb-templates/"
tar -czf - -C "$REPO_DIR" --exclude='__pycache__' --exclude='*.pyc' \
  softwiki scripts kb-templates \
  | remote "cd '$TRIAL_DIR' && cp -a softwiki softwiki.bak-$STAMP && tar -xzf - && echo synced"

if [ "$SKIP_BUILD" = "0" ]; then
  log "build: softwiki-api:latest (Dockerfile.api-fast)"
  remote "cd '$TRIAL_DIR' && sudo docker build -f Dockerfile.api-fast -t softwiki-api:latest . 2>&1 | tail -3"
fi

log "recreate: coffee (project softwiki)"
remote "cd '$TRIAL_DIR' && sudo /usr/local/bin/docker-compose -f docker-compose.yml -p softwiki up -d --no-build --remove-orphans 2>&1 | tail -5"

log "recreate: ai-history (project softwiki-ai)"
remote "cd '$TRIAL_DIR' && sudo /usr/local/bin/docker-compose --env-file .env.ai -f docker-compose.yml -p softwiki-ai up -d --no-build --remove-orphans 2>&1 | tail -5"

if remote "systemctl list-unit-files | grep -q '^swagent-coffee.service'"; then
  log "restart: swagent-coffee swagent-ai"
  remote "sudo systemctl restart swagent-coffee swagent-ai && systemctl is-active swagent-coffee swagent-ai"
fi

if [ "$MIGRATE_VECTORS" = "1" ]; then
  log "migrate vectors: only when chunk_embeddings is empty"
  for spec in "softwiki-api-1|softwiki-postgres-1|softwiki_coffee" \
              "softwiki-ai-api-1|softwiki-ai-postgres-1|softwiki_ai_history"; do
    api="${spec%%|*}"; rest="${spec#*|}"; pg="${rest%%|*}"; db="${rest##*|}"
    count=$(remote "sudo docker exec $pg psql -U softwiki -d $db -tAc 'select count(*) from chunk_embeddings'" 2>/dev/null || echo 0)
    count="${count//[^0-9]/}"
    if [ "${count:-0}" = "0" ]; then
      log "  $db: empty -> migrating npz"
      remote "sudo docker exec $api python /app/scripts/migrate_vectors_to_pg.py --batch 200 --index hnsw --samples 10 2>&1 | tail -2"
    else
      log "  $db: $count vectors already present, skip"
    fi
  done
fi

log "health"
remote "set -e
  for p in 6200 6202; do printf '%s ' \$p; curl -fsS -m 8 http://127.0.0.1:\$p/api/health; echo; done
  curl -fsS -m 10 'http://127.0.0.1:6200/api/kb?verify=true' | head -c 200; echo
  curl -fsS -m 10 'http://127.0.0.1:6202/api/kb?verify=true' | head -c 200; echo
  for p in 6108 6109; do printf '%s web ' \$p; curl -s -o /dev/null -w '%{http_code}\n' -m 8 http://127.0.0.1:\$p/; done
  sudo docker ps --format '{{.Names}} {{.Status}}' | grep -E 'softwiki(-ai)?-(api|mcp|web|postgres)-1'"

log "done (backup stamp $STAMP)"
