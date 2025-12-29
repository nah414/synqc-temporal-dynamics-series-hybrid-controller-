#!/usr/bin/env python3
"""
Generate secrets used by hosted mode (oauth2-proxy).

Usage:
  python3 scripts/generate_hosted_secrets.py
"""
import base64
import secrets


def main() -> None:
    # oauth2-proxy cookie secret: 32 bytes, base64-encoded
    cookie_secret = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    print("OAUTH2_PROXY_COOKIE_SECRET=" + cookie_secret)


if __name__ == "__main__":
    main()
