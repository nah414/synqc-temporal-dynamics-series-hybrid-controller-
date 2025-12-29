#!/usr/bin/env bash
set -euo pipefail

PACK_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$PACK_DIR"

ENV_FILE="deploy/hosted/.env.ci"
LOG_DIR=${LOG_DIR:-"${PWD}/ci-logs"}
BUILD_IMAGES=${BUILD_IMAGES:-1}

mkdir -p "$LOG_DIR"

cat > "$ENV_FILE" <<'ENVEOF'
SYNQC_HTTP_PORT=8080
OIDC_ISSUER_URL=https://issuer.invalid
OIDC_CLIENT_ID=synqc-ci-client
OIDC_CLIENT_SECRET=synqc-ci-secret
OAUTH2_PROXY_COOKIE_SECRET=MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI=
OAUTH2_PROXY_REDIRECT_URL=http://localhost:8080/oauth2/callback
ENVEOF

COMPOSE_FILES=(
  -f docker-compose.hosted.yml
  -f docker-compose.hosted.ci.yml
  --env-file "$ENV_FILE"
)

cleanup() {
  status=$1
  trap - EXIT

  if [[ $status -ne 0 ]]; then
    echo "Collecting docker compose diagnostics in $LOG_DIR" >&2
    docker compose "${COMPOSE_FILES[@]}" ps -a >"$LOG_DIR/compose_ps.txt" || true
    docker compose "${COMPOSE_FILES[@]}" logs --no-color >"$LOG_DIR/compose_logs.txt" || true
  fi

  docker compose "${COMPOSE_FILES[@]}" down -v || true
  exit "$status"
}
trap 'cleanup $?' EXIT

printf 'Starting hosted compose with CI overrides...\n'
if [[ "$BUILD_IMAGES" == "1" ]]; then
  docker compose "${COMPOSE_FILES[@]}" up -d --build
else
  docker compose "${COMPOSE_FILES[@]}" up -d
fi

printf 'Waiting for API health...\n'
for _ in $(seq 1 30); do
  if docker compose "${COMPOSE_FILES[@]}" exec -T api curl -sf http://127.0.0.1:8001/health >/dev/null; then
    break
  fi
  sleep 2
done

docker compose "${COMPOSE_FILES[@]}" exec -T api curl -sf http://127.0.0.1:8001/health

printf 'Checking edge gating redirects...\n'
root_headers=$(curl -i -s http://localhost:8080/)
api_headers=$(curl -i -s http://localhost:8080/api/health)
stream_headers=$(curl -i -s http://localhost:8080/api/shor/runs/stream)

grep -qi "location: /oauth2/start?rd=/" <<<"$root_headers"
grep -qi "location: /oauth2/start?rd=/api/health" <<<"$api_headers"
grep -qi "location: /oauth2/start?rd=/api/shor/runs/stream" <<<"$stream_headers"

echo "$api_headers" | grep -qi "HTTP/1.1 302" || echo "$api_headers" | grep -qi "HTTP/1.0 302"

echo "Validating oauth2-proxy auth endpoint..."
auth_response=$(curl -i -s http://localhost:8080/oauth2/auth)
grep -qi "401 Unauthorized" <<<"$auth_response"

echo "Hosted compose smoke checks passed."
