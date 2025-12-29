import pytest

pytest.importorskip("synqc_shor")

from synqc_shor.rsa import generate_rsa_keypair, rsa_encrypt_int, rsa_decrypt_int
from synqc_shor.factor import factor_N


def test_rsa_roundtrip_int():
    kp = generate_rsa_keypair(prime_bits=10, e=65537)
    m = 42
    c = rsa_encrypt_int(m, kp.N, kp.e)
    m2 = rsa_decrypt_int(c, kp.N, kp.d)
    assert m2 == m


def test_factor_matches_key():
    kp = generate_rsa_keypair(prime_bits=10, e=65537)
    fres = factor_N(kp.N, method="classical")
    assert fres.p * fres.q == kp.N
    assert set([fres.p, fres.q]) == set([kp.p, kp.q])
