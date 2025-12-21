from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import uuid


def now_ts() -> float:
    return time.time()


# ---------------------------
# Password hashing (stdlib)
# ---------------------------
# Format: pbkdf2_sha256$<iters>$<salt_b64url>$<dk_b64url>
def hash_password(password: str, iterations: int) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Password must be a string of length >= 8")

    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return "pbkdf2_sha256${}${}${}".format(
        int(iterations),
        b64url_encode(salt),
        b64url_encode(dk),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters_s, salt_b64, dk_b64 = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iters_s)
        salt = b64url_decode(salt_b64)
        expected = b64url_decode(dk_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


# ---------------------------
# Token helpers
# ---------------------------
def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_id() -> str:
    return uuid.uuid4().hex  # 32 chars


def make_secret(nbytes: int = 32) -> str:
    # urlsafe, long enough for tokens
    return secrets.token_urlsafe(nbytes)


def make_prefixed_token(prefix: str) -> tuple[str, str]:
    """
    Returns (token_string, token_id)

    token_string format: f"{prefix}{id}.{secret}"
    Example prefix: "synqc_at_" or "synqc_sess_"
    """
    token_id = make_id()
    token = f"{prefix}{token_id}.{make_secret(32)}"
    return token, token_id


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def b64url_decode(data: str) -> bytes:
    pad = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("utf-8"))
