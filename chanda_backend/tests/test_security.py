"""
Pure unit tests for app/core/security.py -- no database, no running server
required. Run with: pytest tests/ -v

These deliberately do NOT hit the DB (unlike full_system_test.py, which is
a live end-to-end smoke test against a running server + real Postgres).
Keeping a DB-free layer means CI can run these on every commit without
provisioning Postgres first.
"""
import time
import pytest
from jose import JWTError

from app.core.security import (
    hash_password, verify_password, create_token, decode_token, generate_reset_token,
)


def test_password_hash_is_not_plaintext():
    hashed = hash_password("MySecret123!")
    assert hashed != "MySecret123!"
    assert hashed.startswith("$2b$")  # bcrypt prefix


def test_password_verify_correct_and_incorrect():
    hashed = hash_password("MySecret123!")
    assert verify_password("MySecret123!", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_two_hashes_of_same_password_differ():
    # bcrypt uses a random salt per call -- this guards against someone
    # "optimizing" hash_password into something deterministic later.
    h1 = hash_password("MySecret123!")
    h2 = hash_password("MySecret123!")
    assert h1 != h2
    assert verify_password("MySecret123!", h1)
    assert verify_password("MySecret123!", h2)


def test_access_token_roundtrip():
    token = create_token(subject=42, role="store_manager", token_type="access")
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "store_manager"
    assert payload["type"] == "access"


def test_refresh_token_type_differs_from_access():
    access = create_token(subject=1, role="admin", token_type="access")
    refresh = create_token(subject=1, role="admin", token_type="refresh")
    assert decode_token(access)["type"] == "access"
    assert decode_token(refresh)["type"] == "refresh"


def test_expired_token_is_rejected():
    # expires_minutes accepts a float in practice via timedelta; use a
    # negative value to produce an already-expired token deterministically
    # instead of sleeping in the test.
    token = create_token(subject=1, role="admin", token_type="access", expires_minutes=-1)
    with pytest.raises(JWTError):
        decode_token(token)


def test_reset_token_is_random_and_url_safe():
    t1 = generate_reset_token()
    t2 = generate_reset_token()
    assert t1 != t2
    assert len(t1) > 20
    # url-safe: no characters that would need escaping in a query string
    assert all(c.isalnum() or c in "-_" for c in t1)
