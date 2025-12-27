#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/nah414/Dual-Clocking-Qubits"
TARGET_DIR="$(cd "$(dirname "$0")/.." && pwd)/tools/dual-clocking-qubits"

mkdir -p "$TARGET_DIR"

restore_on_fail=""
cleanup() {
  if [ -n "$restore_on_fail" ] && [ ! -d "$TARGET_DIR/.git" ]; then
    echo "[dual-clocking] Clone failed; restoring contents from $restore_on_fail" >&2
    rm -rf "$TARGET_DIR"
    mv "$restore_on_fail" "$TARGET_DIR"
  fi
}
trap cleanup ERR

if [ -d "$TARGET_DIR/.git" ]; then
  echo "[dual-clocking] Updating existing checkout in $TARGET_DIR" >&2
  git -C "$TARGET_DIR" pull --ff-only
else
  if [ "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
    backup_dir="${TARGET_DIR}-backup-$(date +%Y%m%d%H%M%S)"
    echo "[dual-clocking] Existing non-git contents detected; moving to $backup_dir" >&2
    mv "$TARGET_DIR" "$backup_dir"
    mkdir -p "$TARGET_DIR"
    restore_on_fail="$backup_dir"
  fi

  echo "[dual-clocking] Cloning toolkit into $TARGET_DIR" >&2
  git clone "$REPO_URL" "$TARGET_DIR"
fi

trap - ERR

if [ -n "$restore_on_fail" ] && [ -d "$restore_on_fail" ]; then
  rm -rf "$restore_on_fail"
fi

cat <<'MSG'
[dual-clocking] Done. If the download failed due to network restrictions, rerun the script when connectivity is available.
MSG
