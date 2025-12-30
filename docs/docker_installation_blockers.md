# Docker installation blockers in this environment

The current container cannot install the Docker CLI or compose plugin because outbound package
mirrors return HTTP 403 errors through the proxy. Attempts to refresh package metadata fail with
messages like:

```
E: Failed to fetch http://archive.ubuntu.com/ubuntu/dists/noble/InRelease  403  Forbidden [IP: 172.30.0.195 8080]
E: Failed to fetch http://security.ubuntu.com/ubuntu/dists/noble-security/InRelease  403  Forbidden [IP: 172.30.0.195 8080]
```

Because of these proxy blocks, `docker` and `docker compose` are unavailable. To unblock the
verification flow in `scripts/verify_web_proxy.sh`, an administrator will need to either:

1. Provide a working Docker installation on the host (e.g., Docker Desktop or a preinstalled
   `docker` + compose plugin package), **or**
2. Supply a whitelisted mirror that allows downloading Docker binaries and Ubuntu package metadata
   without 403 responses, then rerun `apt-get update` followed by the Docker install steps from
   https://docs.docker.com/engine/install/.

Other escape hatches when package mirrors are blocked:

- Use the official Docker static binaries (untar to `/usr/local/bin` or your PATH) so you do not
  depend on apt repositories.
- Copy a known-good `docker` + compose plugin bundle from another Linux host.
- Point the CLI at a remote daemon by exporting `DOCKER_HOST=tcp://<host>:<port>` after a CLI
  binary is available locally.

Once Docker is available, rerun `./scripts/verify_web_proxy.sh` to rebuild the web image and confirm
nginx serves `web/index.html` and proxies `/api/health` end-to-end.

## Latest attempt

As of this run, `apt-get update` still fails due to proxy-blocked mirrors:

```
E: Failed to fetch http://archive.ubuntu.com/ubuntu/dists/noble/InRelease  403  Forbidden [IP: 172.31.0.131 8080]
E: Failed to fetch http://security.ubuntu.com/ubuntu/dists/noble-security/InRelease  403  Forbidden [IP: 172.31.0.131 8080]
```

With Docker still unavailable, `./scripts/verify_web_proxy.sh` exits immediately, reminding users to
install Docker or point to a remote daemon before retrying the nginx proxy verification.
