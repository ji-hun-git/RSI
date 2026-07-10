"""Stage-1 signing primitive for bundles and governance records (report 9.1, 14.5).

``HMACSigner`` is the Stage-1 stand-in for a real signing infrastructure
(Sigstore/Cosign or an organizational PKI): a keyed HMAC-SHA256 over raw
bytes, with the key held in a local file. It provides integrity and a
minimal notion of signer identity (``key_id``) so that the registry and
policy layers can exercise the full sign/verify workflow; it does not
provide non-repudiation. Swapping in asymmetric signatures later changes
only this module (the LEGO-connector rule, report section 17).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from pathlib import Path


class HMACSigner:
    """HMAC-SHA256 signer bound to a ``key_id`` and a secret key."""

    KEY_BYTES = 32

    def __init__(self, key_id: str, secret: bytes) -> None:
        self.key_id = key_id
        self._secret = secret

    def sign(self, data: bytes) -> str:
        """Hex-encoded HMAC-SHA256 signature over *data*."""
        return hmac.new(self._secret, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, signature: str) -> bool:
        """Constant-time check that *signature* was produced by this key."""
        return hmac.compare_digest(self.sign(data), signature)

    @classmethod
    def load(cls, key_path: Path, key_id: str = "dev") -> HMACSigner:
        """Load an existing key; raises ``FileNotFoundError`` when absent.

        Verification and replay paths must use this instead of
        :meth:`load_or_create`: a verifier must never mint a new key into
        the evidence root it is auditing, and "key missing" is a distinct
        audit outcome from "signature forged".
        """
        if not key_path.exists():
            raise FileNotFoundError(f"signing key not present at {key_path}")
        return cls(key_id, key_path.read_bytes())

    @classmethod
    def load_or_create(cls, key_path: Path, key_id: str = "dev") -> HMACSigner:
        """Load the key at *key_path*, generating a random 32-byte key on first use."""
        if not key_path.exists():
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(secrets.token_bytes(cls.KEY_BYTES))
        return cls.load(key_path, key_id=key_id)
