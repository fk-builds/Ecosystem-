"""Auth: session tokens (demo mode) + optional Supabase JWT (HS256, stdlib-only).

Demo mode (no external auth configured):
  - POST /api/auth/signup|login issues an opaque session token (pbkdf2 password
    hashing, stdlib). Tokens live in the store and work across restarts.

Supabase mode (SUPABASE_JWT_SECRET set):
  - Any Bearer token signed with the Supabase project JWT secret is accepted;
    the `sub` claim becomes the user id and the user row is auto-provisioned.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

PBKDF2_ITERATIONS = 240_000


class AuthError(Exception):
    pass


# ── password hashing (stdlib pbkdf2) ────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


# ── tokens ──────────────────────────────────────────────────────────

def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def supabase_verify_jwt(token: str, secret: str) -> dict[str, Any] | None:
    """Verify an HS256 JWT (Supabase access tokens) and return claims or None."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            return None
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            return None
        claims = json.loads(_b64url_decode(payload_b64))
        if claims.get("exp") and float(claims["exp"]) < time.time():
            return None
        return claims
    except Exception:  # noqa: BLE001
        return None


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
