#!/usr/bin/env python3
"""Generate secrets for hosted mode.

- OAUTH2_PROXY_COOKIE_SECRET: 32 random bytes, base64-encoded (oauth2-proxy expects base64)
- SYNQC_MASTER_KEY: urlsafe base64 32 bytes (Fernet-compatible)

Usage:
  python scripts/generate_hosted_secrets.py
"""
import base64
import secrets

def main() -> None:
    cookie_secret = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    fernet_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    print("OAUTH2_PROXY_COOKIE_SECRET=" + cookie_secret)
    print("SYNQC_MASTER_KEY=" + fernet_key)

if __name__ == "__main__":
    main()
