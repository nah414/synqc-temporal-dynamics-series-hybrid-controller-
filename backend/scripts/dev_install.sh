#!/usr/bin/env bash
set -euo pipefail

# Use system-installed build tools to avoid network fetches in constrained environments.
export PIP_NO_BUILD_ISOLATION=1

# Optional: point at a cached wheel directory so qiskit extras can be installed
# behind a proxy without hitting package indexes.
QISKIT_WHEEL_DIR=${QISKIT_WHEEL_DIR:-}
if [[ -n "${QISKIT_WHEEL_DIR}" && ! -d "${QISKIT_WHEEL_DIR}" ]]; then
  echo "QISKIT_WHEEL_DIR is set but \"${QISKIT_WHEEL_DIR}\" does not exist." >&2
  echo "Create the directory and drop predownloaded qiskit wheels (e.g., with 'pip wheel -r backend/requirements.lock')." >&2
  exit 1
fi

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

if [[ -n "${QISKIT_WHEEL_DIR}" ]]; then
  echo "Installing dev + qiskit extras from cached wheels in ${QISKIT_WHEEL_DIR}" >&2
  python -m pip install --no-index --find-links "${QISKIT_WHEEL_DIR}" -e ".[dev,qiskit]"
else
  python -m pip install -e ".[dev,qiskit]"
fi
