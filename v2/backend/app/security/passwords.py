from __future__ import annotations

import re

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError


_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4,
                         hash_len=32, salt_len=16, type=Type.ID)
_COMMON = {"password", "password123", "admin123", "qwerty123", "letmein123"}


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str) -> None:
    if len(password) < 12 or len(password) > 128:
        raise PasswordPolicyError("password must contain 12 to 128 characters")
    if password.casefold() in _COMMON:
        raise PasswordPolicyError("password is too common")
    classes = (
        bool(re.search(r"[a-z]", password)), bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"\d", password)), bool(re.search(r"[^A-Za-z0-9]", password)),
    )
    if sum(classes) < 3:
        raise PasswordPolicyError("password must use at least three character classes")


def hash_password(password: str) -> str:
    validate_password(password)
    return _HASHER.hash(password)


def verify_password(encoded: str, password: str) -> tuple[bool, bool]:
    try:
        valid = _HASHER.verify(encoded, password)
        return bool(valid), bool(valid and _HASHER.check_needs_rehash(encoded))
    except (VerifyMismatchError, InvalidHashError):
        return False, False


def dummy_verify(password: str) -> None:
    # Keeps the unknown-user path computationally similar without storing a secret.
    _HASHER.verify(_HASHER.hash("Synthetic-Dummy-Password!9"), password)
