#!/usr/bin/env bash
set -euo pipefail

# Build a Qiskit wheel cache and package it into a tarball for offline installs.
# Intended for CI environments that can upload the tarball as an artifact so
# air-gapped machines can consume it without rebuilding wheels locally.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REQ_FILE=${QISKIT_REQUIREMENTS_FILE:-"${BACKEND_ROOT}/requirements.lock"}
CACHE_DIR=${QISKIT_WHEEL_DIR:-"${BACKEND_ROOT}/synqc_backend/vendor/qiskit_wheels"}
TARBALL=${QISKIT_WHEEL_TARBALL:-"${CACHE_DIR}.tar.gz"}

mkdir -p "${CACHE_DIR}"

echo "[qiskit-cache] Building wheels from ${REQ_FILE} into ${CACHE_DIR}" >&2
python -m pip install --upgrade pip wheel >/dev/null
python -m pip wheel -r "${REQ_FILE}" --wheel-dir "${CACHE_DIR}"

echo "[qiskit-cache] Packaging cache to ${TARBALL}" >&2
tar -czf "${TARBALL}" -C "${CACHE_DIR}" .

cat <<MSG
[qiskit-cache] Done.
[qiskit-cache] Wheel cache directory: ${CACHE_DIR}
[qiskit-cache] Tarball for artifact upload: ${TARBALL}
MSG
