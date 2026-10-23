import base64
import hashlib
import hmac
import json
import os
import time

PBKDF2_ITERATIONS = 260000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _secret() -> bytes:
    return os.getenv("SOFTWIKI_SECRET_KEY", "dev-insecure-secret-change-me").encode()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(username: str, ttl_seconds: int = 604800) -> str:
    payload = {"u": username, "exp": int(time.time()) + ttl_seconds}
    raw = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64encode(hmac.new(_secret(), raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{signature}"


def verify_token(token: str) -> str | None:
    try:
        raw, signature = token.split(".", 1)
        expected = hmac.new(_secret(), raw.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            return None
        payload = json.loads(_b64decode(raw))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload.get("u")
    except Exception:
        return None


def auth_enabled() -> bool:
    return os.getenv("SOFTWIKI_AUTH_ENABLED", "").lower() in ("1", "true", "yes")
