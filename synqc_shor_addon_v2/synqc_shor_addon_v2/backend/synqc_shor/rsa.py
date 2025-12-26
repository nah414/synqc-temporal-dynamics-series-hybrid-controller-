"""Toy RSA helpers used by the Shor demo.

Important: this is intentionally *not* production RSA.
- No OAEP / PKCS#1 padding
- Small integers only
- Designed for educational demos + UI interactivity

The purpose of this module is to provide a clean, readable reference implementation
that works without external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Tuple, Optional


# ----------------------------
# Math primitives
# ----------------------------

def egcd(a: int, b: int) -> Tuple[int, int, int]:
    """Extended Euclidean algorithm: returns (g, x, y) s.t. ax + by = g = gcd(a,b)."""
    if b == 0:
        return (abs(a), 1 if a >= 0 else -1, 0)
    g, x1, y1 = egcd(b, a % b)
    return (g, y1, x1 - (a // b) * y1)


def modinv(a: int, m: int) -> int:
    """Modular inverse of a modulo m."""
    g, x, _ = egcd(a, m)
    if g != 1:
        raise ValueError(f"No modular inverse for a={a} mod m={m} (gcd={g}).")
    return x % m


def _try_small_primes(n: int) -> bool:
    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False
    return True


def is_probable_prime(n: int, k: int = 10) -> bool:
    """Miller-Rabin probabilistic primality test."""
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0:
        return False
    if not _try_small_primes(n):
        return False

    # Write n-1 = d * 2^s with d odd.
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1

    # Witness loop
    for _ in range(k):
        a = secrets.randbelow(n - 3) + 2  # [2, n-2]
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _r in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def generate_prime(bits: int) -> int:
    """Generate a probable prime of exactly `bits` bits."""
    if bits < 2:
        raise ValueError("bits must be >= 2")
    while True:
        # Ensure top and bottom bits set so we get the requested bit length and an odd number.
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(candidate):
            return candidate


# ----------------------------
# RSA key & operations
# ----------------------------

@dataclass(frozen=True)
class RSAKeyPair:
    p: int
    q: int
    N: int
    phi: int
    e: int
    d: int


def generate_rsa_keypair(prime_bits: int = 12, e: int = 65537) -> RSAKeyPair:
    """Generate a toy RSA keypair.

    `prime_bits` controls the bit-length of each prime (p and q).
    The modulus N will be roughly 2*prime_bits.

    This function will regenerate primes until gcd(e, phi(N)) == 1.
    """
    if prime_bits < 4:
        raise ValueError("prime_bits must be >= 4 for a meaningful demo")
    if e <= 1:
        raise ValueError("e must be > 1")

    while True:
        p = generate_prime(prime_bits)
        q = generate_prime(prime_bits)
        if p == q:
            continue
        N = p * q
        phi = (p - 1) * (q - 1)

        # If e is too large, we still allow it, but it must be coprime to phi.
        if egcd(e, phi)[0] != 1:
            continue

        d = modinv(e, phi)
        return RSAKeyPair(p=p, q=q, N=N, phi=phi, e=e, d=d)


def rsa_encrypt_int(m: int, N: int, e: int) -> int:
    if m < 0:
        raise ValueError("plaintext must be non-negative")
    if m >= N:
        raise ValueError("plaintext must be < N for raw RSA (no padding)")
    return pow(m, e, N)


def rsa_decrypt_int(c: int, N: int, d: int) -> int:
    if c < 0:
        raise ValueError("ciphertext must be non-negative")
    if c >= N:
        raise ValueError("ciphertext must be < N")
    return pow(c, d, N)


# ----------------------------
# Optional text encoding helpers
# ----------------------------

def text_to_int(s: str) -> int:
    """Encode a UTF-8 string into a non-negative integer."""
    b = s.encode("utf-8")
    if len(b) == 0:
        return 0
    return int.from_bytes(b, byteorder="big", signed=False)


def int_to_text(n: int) -> Optional[str]:
    """Attempt to decode an integer as UTF-8.

    Returns None if decoding fails.
    """
    if n < 0:
        return None
    if n == 0:
        return ""
    # Compute minimal byte length
    length = (n.bit_length() + 7) // 8
    b = n.to_bytes(length, byteorder="big", signed=False)
    try:
        return b.decode("utf-8")
    except Exception:
        return None
