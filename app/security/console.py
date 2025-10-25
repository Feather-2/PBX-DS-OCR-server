from __future__ import annotations

import base64
import hmac
import hashlib
import time
from typing import Optional


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(data: str) -> bytes:
    pad = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + pad).encode("ascii"))


def sign_session(secret: str, subject: str, exp_ts: int) -> str:
    payload = f"{subject}:{exp_ts}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64u(payload)}.{_b64u(sig)}"


def verify_session(secret: str, token: str) -> bool:
    try:
        p_b64, s_b64 = token.split(".", 1)
        payload = _b64u_decode(p_b64)
        exp = int(payload.decode("utf-8").split(":", 1)[1])
        if exp < int(time.time()):
            return False
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
        actual = _b64u_decode(s_b64)
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False

