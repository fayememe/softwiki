#!/usr/bin/env bash
# Prepare and start the lightweight auth demo.
#
# Generates secrets and password hashes locally (nothing secret is committed),
# renders the Authelia config, then brings the stack up.
set -euo pipefail

cd "$(dirname "$0")"

IMAGE_AUTHELIA="authelia/authelia:4.38"

# Public host/ports. Defaults are local; override for a remote install, e.g.
#   DEMO_PUBLIC_HOST=203.0.113.10 DEMO_BIND_ADDR=0.0.0.0 ./setup.sh
DEMO_PUBLIC_HOST="${DEMO_PUBLIC_HOST:-127.0.0.1}"
DEMO_APP_PORT="${DEMO_APP_PORT:-6190}"
DEMO_PORTAL_PORT="${DEMO_PORTAL_PORT:-6191}"
DEMO_BIND_ADDR="${DEMO_BIND_ADDR:-0.0.0.0}"
# Where compose comes from. On hosts without the docker group use e.g.
#   COMPOSE_CMD="sudo -n /usr/local/bin/docker-compose"
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"
# Docker CLI used for one-off helpers (password hashing). Same story as compose.
DOCKER_CMD="${DOCKER_CMD:-docker}"
DEMO_UID="${DEMO_UID:-$(id -u)}"
DEMO_GID="${DEMO_GID:-$(id -g)}"
export DEMO_PUBLIC_HOST DEMO_APP_PORT DEMO_PORTAL_PORT DEMO_BIND_ADDR
export DEMO_UID DEMO_GID

say() { printf '%s\n' "$*"; }

need() {
  command -v "$1" >/dev/null 2>&1 || { say "missing dependency: $1"; exit 1; }
}
need openssl
need python3

# --- secrets -----------------------------------------------------------------
if [ ! -f authelia/configuration.yml ]; then
  say "generating secrets..."
  PUBLIC_HOST="$DEMO_PUBLIC_HOST" APP_PORT="$DEMO_APP_PORT" PORTAL_PORT="$DEMO_PORTAL_PORT" \
  python3 - <<'PY'
import os, secrets, pathlib, string
alphabet = string.ascii_letters + string.digits
def rnd(n): return "".join(secrets.choice(alphabet) for _ in range(n))
tmpl = pathlib.Path("authelia/configuration.yml.tmpl").read_text()
out = (tmpl
       .replace("__JWT_SECRET__", rnd(64))
       .replace("__SESSION_SECRET__", rnd(64))
       .replace("__STORAGE_KEY__", rnd(64))
       .replace("__PUBLIC_HOST__", os.environ["PUBLIC_HOST"])
       .replace("__APP_PORT__", os.environ["APP_PORT"])
       .replace("__PORTAL_PORT__", os.environ["PORTAL_PORT"]))
pathlib.Path("authelia/configuration.yml").write_text(out)
PY
  # A new storage encryption key must go with a fresh database, otherwise
  # Authelia refuses to start ("encryption key does not appear to be valid").
  rm -f authelia/db.sqlite3
  chmod 600 authelia/configuration.yml
else
  say "reusing existing authelia/configuration.yml"
fi

# --- users -------------------------------------------------------------------
# Two demo users so the group -> role mapping is visible:
#   alice  staff   -> wiki-work   (can ingest, adjudicate)
#   bob    student -> wiki-study  (read-only)
if [ ! -f authelia/users.yml ]; then
  say "creating demo users (password: demo123)..."
  hash() {
    ${DOCKER_CMD} run --rm "$IMAGE_AUTHELIA" \
      authelia crypto hash generate argon2 --password "$1" \
      | sed -n 's/^Digest: //p'
  }
  ALICE_HASH="$(hash demo123)"
  BOB_HASH="$(hash demo123)"
  cat > authelia/users.yml <<EOF
users:
  alice:
    displayname: 'Alice Staff'
    password: '${ALICE_HASH}'
    email: 'alice@example.edu'
    groups:
      - staff
  bob:
    displayname: 'Bob Student'
    password: '${BOB_HASH}'
    email: 'bob@example.edu'
    groups:
      - student
EOF
  chmod 600 authelia/users.yml
else
  say "reusing existing authelia/users.yml"
fi

# --- TLS ---------------------------------------------------------------------
# Authelia 4.38 refuses http:// for authelia_url, so the demo runs TLS with a
# self-signed certificate. Production uses a real certificate at the customer.
mkdir -p certs
if [ ! -f certs/demo.crt ]; then
  say "generating self-signed certificate (browsers will warn)..."
  SAN="IP:127.0.0.1,DNS:localhost"
  # Add the public host to the SAN list so browsers can pin it if desired.
  if echo "$DEMO_PUBLIC_HOST" | grep -Eq '^[0-9.]+$'; then
    SAN="$SAN,IP:$DEMO_PUBLIC_HOST"
  else
    SAN="$SAN,DNS:$DEMO_PUBLIC_HOST"
  fi
  openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout certs/demo.key -out certs/demo.crt \
    -subj "/CN=$DEMO_PUBLIC_HOST" \
    -addext "subjectAltName=$SAN" >/dev/null 2>&1
  chmod 600 certs/demo.key
fi

# --- demo workspace (softwiki needs an initialised kb) -----------------------
mkdir -p workspaces/demo/.softwiki workspaces/demo/config
if [ ! -f workspaces/demo/config/meta.yaml ]; then
  cat > workspaces/demo/config/meta.yaml <<'EOF'
name: demo
description: "Auth demo knowledge base — contains no real data"
EOF
fi

# --- softwiki group -> role mapping ------------------------------------------
# Authelia sends group names; softwiki maps them to roles in config/identity.yaml
# (the user table is a separate file and is written by the app itself).
# Without a mapping a user still gets in, but only at the lowest role.
mkdir -p workspaces/config
if [ ! -f workspaces/config/identity.yaml ]; then
  cat > workspaces/config/identity.yaml <<'EOF'
groups:
  staff:
    - wiki-work
  student:
    - wiki-study
EOF
fi

# Compose reads .env from the project directory. Needed because compose may be
# invoked through sudo, which strips the caller's environment.
cat > .env <<EOF
DEMO_APP_PORT=${DEMO_APP_PORT}
DEMO_PORTAL_PORT=${DEMO_PORTAL_PORT}
DEMO_BIND_ADDR=${DEMO_BIND_ADDR}
DEMO_UID=${DEMO_UID}
DEMO_GID=${DEMO_GID}
DEMO_NGINX_IMAGE=${DEMO_NGINX_IMAGE:-nginx:1.27-alpine}
SOFTWIKI_IMAGE=${SOFTWIKI_IMAGE:-softwiki-api:auth-demo}
EOF

say "starting stack..."
# shellcheck disable=SC2086
${COMPOSE_CMD} up -d

say ""
say "ready:  https://${DEMO_PUBLIC_HOST}:${DEMO_APP_PORT}   app   (self-signed: accept the warning)"
say "portal: https://${DEMO_PUBLIC_HOST}:${DEMO_PORTAL_PORT}   login page"
say "login:  alice / demo123   (staff   -> wiki-work)"
say "        bob   / demo123   (student -> wiki-study)"
say ""
say "verify: python3 ../../scripts/verify_proxy_headers.py https://${DEMO_PUBLIC_HOST}:${DEMO_APP_PORT} --insecure --user alice"
say "bind:   ${DEMO_BIND_ADDR}:${DEMO_APP_PORT}/${DEMO_PORTAL_PORT} (only nginx is published)"
