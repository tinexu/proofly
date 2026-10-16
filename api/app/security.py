"""Random tokens and how we store them.

Only a SHA-256 hash of each token is saved, so someone who reads the
database can't use it to sign in.
"""

import hashlib
import secrets


def new_token() -> str:
    """A 256-bit random, URL-safe token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()