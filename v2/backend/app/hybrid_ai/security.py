from __future__ import annotations

import hashlib
import hmac
import json
import time


def canonical_body(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")


def sign_request(secret: str, timestamp: int, body: bytes) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    return hmac.new(secret.encode(), f"{timestamp}.{body_hash}".encode(), hashlib.sha256).hexdigest()


def verify_signature(secret: str, timestamp: int, body: bytes, signature: str,
                     now: int | None = None, validity_seconds: int = 300) -> bool:
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > validity_seconds: return False
    expected = sign_request(secret, timestamp, body)
    return hmac.compare_digest(expected, signature.lower())
