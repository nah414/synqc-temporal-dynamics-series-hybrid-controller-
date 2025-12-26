# Qiskit wheel cache (optional)

Drop predownloaded `qiskit` family wheels here when working behind a proxy or in
an offline environment so editable installs can run without hitting the package
index. The dev install script will automatically prefer this directory when
`QISKIT_WHEEL_DIR` points at it:

```bash
# From repo root
pip wheel -r backend/requirements.lock -w backend/synqc_backend/vendor/qiskit_wheels
QISKIT_WHEEL_DIR=backend/synqc_backend/vendor/qiskit_wheels ./backend/scripts/dev_install.sh
```

Use `--no-index`/`--find-links` with other tools the same way if you relocate the
cache; the directory just needs to be readable by `pip`. CI can also prebuild the
cache and wrap it in a tarball for artifact upload (see
`.github/workflows/qiskit-cache.yml` for a scheduled example):

```bash
cd backend
./scripts/build_qiskit_cache.sh
# artifact emitted to: synqc_backend/vendor/qiskit_wheels.tar.gz
```

The scheduled workflow publishes the tarball to a release tagged
`qiskit-cache-latest`, uploads a `latest` alias to GitHub Packages, mirrors the
versioned tarball to the same registry so it survives release cleanup, and
prunes older package versions automatically to keep the mirror small. Retention
defaults to 5 versions and can be changed via the workflow_dispatch input
`keep_versions` or repo variable/secret `QISKIT_CACHE_KEEP_VERSIONS`. Offline
users can download it directly instead of digging through workflow runs:

```bash
gh release download qiskit-cache-latest -p 'qiskit_wheels.tar.gz' -D backend/synqc_backend/vendor
tar -xzf backend/synqc_backend/vendor/qiskit_wheels.tar.gz -C backend/synqc_backend/vendor

# Or from the package registry mirror (requires a GH token with packages:read)
GH_TOKEN=...
OWNER=${OWNER:-$(gh repo view --json owner --jq .owner.login)}
REPO=${REPO:-$(basename $(git rev-parse --show-toplevel))}
LATEST_ID=$(gh api -H "Accept: application/vnd.github+json" "/repos/${OWNER}/${REPO}/packages/generic/qiskit-wheel-cache/versions?per_page=1" --jq '.[0].id')
DOWNLOAD_URL=$(gh api -H "Accept: application/vnd.github+json" "/repos/${OWNER}/${REPO}/packages/generic/qiskit-wheel-cache/versions/${LATEST_ID}" --jq '.package_files[0].download_url')
curl -L -H "Authorization: Bearer ${GH_TOKEN}" -o backend/synqc_backend/vendor/qiskit_wheels.tar.gz "${DOWNLOAD_URL}"
tar -xzf backend/synqc_backend/vendor/qiskit_wheels.tar.gz -C backend/synqc_backend/vendor
```
