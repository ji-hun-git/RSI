"""Canonical serialization, content addressing and identifier helpers.

Every digest in the foundry is computed over *canonical JSON*: UTF-8,
sorted keys, no insignificant whitespace. This makes content addresses
stable across platforms and Python versions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

DIGEST_PREFIX = "sha256:"


def utcnow() -> datetime:
    """Timezone-aware UTC now (the only clock the foundry uses)."""
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    """Opaque unique identifier with a readable type prefix, e.g. ``mis_1a2b...``."""
    return f"{prefix}_{uuid.uuid4().hex}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # A naive datetime would be interpreted in the host timezone,
            # making the digest machine-dependent. Refuse instead.
            raise ValueError(
                "naive datetime in a digest payload; canonical digests require "
                "timezone-aware datetimes (use foundry.contracts.utcnow())"
            )
        return value.astimezone(timezone.utc).isoformat()
    return value


def canonical_json(value: Any) -> bytes:
    """Deterministic JSON encoding used for all content digests."""
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_jsonable,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_digest(value: Any) -> str:
    """``sha256:<hex>`` digest of the canonical JSON encoding of *value*."""
    return DIGEST_PREFIX + sha256_hex(canonical_json(value))


def is_digest(ref: str) -> bool:
    return ref.startswith(DIGEST_PREFIX) and len(ref) == len(DIGEST_PREFIX) + 64
