#!/usr/bin/env python3
"""Generate secrets for hosted SynQc deployments.

Currently generates:
  - OAUTH2_PROXY_COOKIE_SECRET (32 bytes, base64-encoded)

Usage:
  python scripts/generate_hosted_secrets.py
"""

import base64
import secrets

def b64(n_bytes: int) -> str:
    return base64.b64encode(secrets.token_bytes(n_bytes)).decode("ascii")

def main() -> None:
    cookie_secret = b64(32)
    print("# Paste these into deploy/hosted/.env.hosted")
    print(f"OAUTH2_PROXY_COOKIE_SECRET={cookie_secret}")

if __name__ == "__main__":
    main()
