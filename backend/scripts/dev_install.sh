#!/usr/bin/env bash
set -euo pipefail

# Use system-installed build tools to avoid network fetches in constrained environments.
export PIP_NO_BUILD_ISOLATION=1

if ! python - <<'PY'
try:
    import wheel  # noqa: F401
except ImportError:
    raise SystemExit(1)
PY
then
  echo "wheel is not installed. Install a local wheel package (e.g., python -m pip install --no-index --find-links <dir> wheel) before continuing." >&2
  exit 1
fi

python -m pip install -e ".[dev]"
