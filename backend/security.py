"""
Security Utilities for the Apex Retail POS
==========================================
- Secure credential (PIN / password) hashing with bcrypt, PBKDF2-HMAC-SHA256 fallback.
- Transparent migration of legacy plaintext PINs stored in the users table.
- Signed stateless session tokens (HMAC-SHA256, stdlib only) for API authentication.
- Per-user failed-login lockout to blunt online PIN brute-forcing.

NOTE: No hardcoded universal "manager override" PINs are permitted anywhere in
this module or the application. Only real, provisioned user credentials pass.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Backend selection: bcrypt when available, otherwise PBKDF2-HMAC-SHA256.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - environment dependent
    import bcrypt as _bcrypt

    _HAS_BCRYPT = True
except ImportError:  # pragma: no cover
    _bcrypt = None
    _HAS_BCRYPT = False

_PBKDF2_ITERATIONS = 240_000
_PBKDF2_SALT_BYTES = 16

# Matches a freshly generated hash produced by this module (either backend).
_HASH_RE = re.compile(r"^(?:\$2[abxy]?\$|\$pbkdf2-sha256\$\d+\$)")


def hash_credential(secret: str) -> str:
    """Return a salted, one-way hash for a cashier PIN or account password."""
    secret_bytes = secret.encode("utf-8")
    if _HAS_BCRYPT:
        return _bcrypt.hashpw(secret_bytes, _bcrypt.gensalt(rounds=10)).decode("ascii")
    salt = os.urandom(_PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", secret_bytes, salt, _PBKDF2_ITERATIONS)
    return f"$pbkdf2-sha256${_PBKDF2_ITERATIONS}${_b64u(salt)}${_b64u(dk)}"


def is_hashed(value: str) -> bool:
    """True when the stored value looks like a proper one-way hash."""
    return bool(value) and bool(_HASH_RE.match(value))


def verify_secret(secret: str, stored: str) -> bool:
    """
    Constant-time verification of a candidate secret against a stored hash.
    Supports both bcrypt and PBKDF2-HMAC-SHA256 formats. Returns False for
    malformed/legacy values (use `authenticate` for transparent upgrades).
    """
    if not stored or not secret:
        return False
    try:
        if stored.startswith("$2"):
            if not _HAS_BCRYPT:
                return False
            return _bcrypt.checkpw(secret.encode("utf-8"), stored.encode("ascii"))
        if stored.startswith("$pbkdf2-sha256$"):
            _, _, iters_s, salt_b64, hash_b64 = stored.split("$")
            salt = _b64u_decode(salt_b64)
            expected = _b64u_decode(hash_b64)
            dk = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, int(iters_s))
            return hmac.compare_digest(dk, expected)
    except Exception:
        return False
    return False


def authenticate(candidate_secret: str, stored_value: str) -> Tuple[bool, Optional[str]]:
    """
    Verify a candidate PIN/password against the stored value.

    Returns (ok, new_stored_value). `new_stored_value` is non-None only when a
    legacy plaintext record successfully authenticated and must be upgraded to
    a hashed form by the caller. Hardcoded override PINs are never honoured.
    """
    if not candidate_secret:
        return False, None
    if is_hashed(stored_value):
        return verify_secret(candidate_secret, stored_value), None
    # Legacy plaintext row: constant-time compare, then flag for upgrade.
    if stored_value and hmac.compare_digest(
        candidate_secret.strip().encode("utf-8"), stored_value.strip().encode("utf-8")
    ):
        return True, hash_credential(candidate_secret.strip())
    return False, None


def normalize_for_storage(secret: str) -> str:
    """Hash a raw secret for persistence; pass through values that are already hashed."""
    secret = (secret or "").strip()
    if not secret:
        raise ValueError("Credential cannot be empty.")
    if is_hashed(secret):
        return secret
    return hash_credential(secret)


# ---------------------------------------------------------------------------
# Signed stateless session tokens (stdlib HMAC; JWT-style header.payload.sig)
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"^([A-Za-z0-9_\-]+)\.([A-Za-z0-9_\-]+)\.([A-Za-z0-9_\-]+)$")


def _load_signing_key() -> bytes:
    env_key = os.environ.get("POS_SECRET_KEY")
    if env_key:
        return env_key.encode("utf-8")
    persist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(persist_dir, exist_ok=True)
    key_file = os.path.join(persist_dir, ".pos_secret_key")
    try:
        with open(key_file, "rb") as fh:
            key = fh.read().strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    key = secrets.token_bytes(32)
    try:
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key)
    except OSError:  # pragma: no cover
        pass
    return key


_SIGNING_KEY = _load_signing_key()


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def create_token(payload: dict, ttl_seconds: int = 8 * 3600) -> str:
    body = dict(payload)
    now = int(time.time())
    body.update({"iat": now, "exp": now + ttl_seconds, "jti": secrets.token_hex(8)})
    encoded = _b64u(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = _b64u(hmac.new(_SIGNING_KEY, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"pos.{encoded}.{signature}"


def decode_token(token: str) -> Optional[dict]:
    """Validate signature and expiry; returns payload dict or None."""
    if not token:
        return None
    m = _TOKEN_RE.match(token)
    if not m:
        return None
    prefix, encoded, signature = m.groups()
    expected_sig = _b64u(hmac.new(_SIGNING_KEY, encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected_sig):
        return None
    try:
        payload = json.loads(_b64u_decode(encoded))
    except (ValueError, UnicodeDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# ---------------------------------------------------------------------------
# Failed-attempt lockout (in-memory; per username/PIN identity)
# ---------------------------------------------------------------------------
class LoginLockoutTracker:
    MAX_ATTEMPTS = 5
    WINDOW_SECONDS = 300
    LOCKOUT_SECONDS = 900

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._attempts: dict = {}

    def is_locked(self, identity: str) -> bool:
        with self._lock:
            entry = self._attempts.get(identity)
            if not entry:
                return False
            count, first_ts, locked_until = entry
            if locked_until and time.time() < locked_until:
                return True
            if locked_until and time.time() >= locked_until:
                del self._attempts[identity]
                return False
            if time.time() - first_ts > self.WINDOW_SECONDS:
                del self._attempts[identity]
                return False
            return count >= self.MAX_ATTEMPTS

    def register_failure(self, identity: str) -> None:
        with self._lock:
            now = time.time()
            entry = self._attempts.get(identity)
            if entry and (now - entry[1] <= self.WINDOW_SECONDS):
                count = entry[0] + 1
                locked_until = now + self.LOCKOUT_SECONDS if count >= self.MAX_ATTEMPTS else 0
                self._attempts[identity] = (count, entry[1], locked_until)
            else:
                self._attempts[identity] = (1, now, 0)

    def reset(self, identity: str) -> None:
        with self._lock:
            self._attempts.pop(identity, None)


login_lockouts = LoginLockoutTracker()
