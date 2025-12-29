from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOSTED_PACK_ROOT = REPO_ROOT / "archives" / "hosted" / "synqc_hosted_pack_v2"
COMPOSE_FILE = HOSTED_PACK_ROOT / "docker-compose.hosted.yml"
NGINX_FILE = HOSTED_PACK_ROOT / "deploy" / "hosted" / "edge" / "nginx.conf"


def _extract_block(text: str, key: str) -> str:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.startswith(f"  {key}:"):
            start = idx + 1
            break
    assert start is not None, f"Block for '{key}' was not found"

    body_lines: list[str] = []
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("    "):
            break
        if line.startswith("    ") or line.strip() == "":
            body_lines.append(line)
    return "\n".join(body_lines) + "\n"


def _extract_location(text: str, location: str) -> str:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.startswith(f"  location {location} ") or line.startswith(
            f"  location = {location} "
        ):
            start = idx + 1
            break
    assert start is not None, f"Location block for '{location}' was not found"

    body_lines: list[str] = []
    for line in lines[start:]:
        if line.startswith("  }"):
            break
        if line.startswith("    ") or line.strip() == "":
            body_lines.append(line)
    return "\n".join(body_lines) + "\n"


def test_hosted_bundle_paths_exist() -> None:
    assert COMPOSE_FILE.is_file(), "Hosted compose file is missing from archives layout"
    assert NGINX_FILE.is_file(), "Hosted nginx edge config is missing from archives layout"


def test_hosted_compose_services_gated() -> None:
    compose_text = COMPOSE_FILE.read_text(encoding="utf-8")

    api_block = _extract_block(compose_text, "api")
    worker_block = _extract_block(compose_text, "worker")
    oauth_block = _extract_block(compose_text, "oauth2-proxy")
    edge_block = _extract_block(compose_text, "edge")

    # Core services stay internal-only (expose but do not publish ports)
    assert "expose:" in api_block
    assert "ports:" not in api_block
    assert "redis://redis:6379/0" in api_block

    # Worker runs alongside Redis and does not open ports
    assert "SYNQC_REDIS_URL" in worker_block
    assert "ports:" not in worker_block

    # OAuth2 proxy remains present with OIDC settings
    assert "oauth2-proxy" in oauth_block
    assert "OAUTH2_PROXY_OIDC_ISSUER_URL" in oauth_block
    assert "OAUTH2_PROXY_REDIRECT_URL" in oauth_block

    # Edge depends on both api + oauth2-proxy so auth is enforced before UI/API are served
    assert "depends_on:" in edge_block
    assert "oauth2-proxy:" in edge_block
    assert "api:" in edge_block


def test_edge_nginx_auth_requests() -> None:
    nginx_text = NGINX_FILE.read_text(encoding="utf-8")

    root_block = _extract_location(nginx_text, "/")
    api_block = _extract_location(nginx_text, "/api/")
    stream_block = _extract_location(nginx_text, "/api/shor/runs/stream")

    for block in (root_block, api_block, stream_block):
        assert "auth_request /oauth2/auth;" in block
        assert "error_page 401 = /oauth2/start?rd=$request_uri;" in block

    # SSE/stream path keeps buffering disabled while still requiring auth
    assert "proxy_buffering off;" in stream_block
    assert "proxy_read_timeout 3600s;" in stream_block
