#!/usr/bin/env bash
set -euo pipefail

# Simple helper to (re)build the web image and verify the SPA can reach the backend
# health endpoint through the nginx proxy at http://127.0.0.1:8080/api/health.

compose_cmd=""

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    compose_cmd="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    compose_cmd="docker-compose"
  fi
fi

if [[ -z "${compose_cmd}" ]]; then
  cat >&2 <<'EOF'
docker compose is required but not available on this host.
- Install Docker Desktop or the Docker CLI + compose plugin (portable binaries work even when apt mirrors are blocked).
- If you must use a remote daemon, install the Docker CLI locally and set DOCKER_HOST to point at it.
- See docs/docker_installation_blockers.md for the proxy errors observed here and remediation options.
EOF
  exit 127
fi

# Ensure images are current before starting containers.
${compose_cmd} build web

# Start the web stack (web depends_on api, which depends_on redis + worker).
${compose_cmd} up -d web

health_url="http://127.0.0.1:8080/api/health"
max_attempts=30
sleep_seconds=2

for attempt in $(seq 1 ${max_attempts}); do
  if curl -fsSL "${health_url}"; then
    echo "\nAPI health reachable through nginx at ${health_url}"
    exit 0
  fi
  echo "Attempt ${attempt}/${max_attempts}: waiting for web/api to become healthy..."
  sleep "${sleep_seconds}"
  echo
  # Show current container state occasionally to aid troubleshooting.
  if (( attempt % 5 == 0 )); then
    ${compose_cmd} ps
  fi
  if (( attempt % 10 == 0 )); then
    ${compose_cmd} logs --tail 20 web api || true
  fi
done

echo "Web/API health check did not succeed after $(( max_attempts * sleep_seconds )) seconds." >&2
exit 1
