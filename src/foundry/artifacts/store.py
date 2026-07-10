"""Content-addressed artifact store (report sections 10.3, 15.6).

Artifacts are immutable blobs addressed as ``artifact://sha256:<hex>``
(report 10.3, Artifact/Source Store: "content-addressed blobs with
provenance; immutable objects"). Identical content dedupes to the same
reference. ``get`` re-verifies the digest on every read so silent blob
substitution or on-disk corruption is detected rather than propagated.
A sidecar ``<hex>.meta.json`` records media type, size and creation time.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from foundry.contracts import DIGEST_PREFIX, sha256_hex, utcnow

ARTIFACT_SCHEME = "artifact://"
_HEX_CHARS = frozenset("0123456789abcdef")


class ArtifactStore:
    """Filesystem-backed content-addressed blob store (``ArtifactStoreLike``).

    Blobs live at ``root_dir/ab/cd/<hex>`` where ``ab``/``cd`` are the first
    two byte-pairs of the sha256 hex digest, keeping directories small.
    """

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, media_type: str = "application/octet-stream") -> str:
        """Store *data*, returning its ref. Identical content dedupes.

        The blob is written to a uniquely named temp file (so concurrent
        writers of the same content never collide on one temp path) and
        the meta sidecar is written *before* the blob is moved into place:
        a crash mid-put can never leave a blob without metadata. A blob
        found without its sidecar (a pre-fix crash window) is backfilled.
        """
        hex_digest = sha256_hex(data)
        blob = self._blob_path(hex_digest)
        if not blob.exists():
            blob.parent.mkdir(parents=True, exist_ok=True)
            self._write_meta(hex_digest, media_type, len(data))
            fd, tmp_name = tempfile.mkstemp(
                dir=blob.parent, prefix=hex_digest, suffix=".tmp"
            )
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp_name, blob)
        elif not self._meta_path(hex_digest).exists():
            self._write_meta(hex_digest, media_type, len(data))
        return ARTIFACT_SCHEME + DIGEST_PREFIX + hex_digest

    def _write_meta(self, hex_digest: str, media_type: str, size: int) -> None:
        meta = {
            "media_type": media_type,
            "size": size,
            "created_at": utcnow().isoformat(),
        }
        self._meta_path(hex_digest).write_text(
            json.dumps(meta, sort_keys=True), encoding="utf-8"
        )

    def get(self, ref: str) -> bytes:
        """Return the blob for *ref*, verifying its digest on read.

        Raises ``KeyError`` for an unknown ref and ``ValueError`` when the
        stored bytes no longer match the content address (tamper evidence).
        """
        hex_digest = self._parse_ref(ref)
        blob = self._blob_path(hex_digest)
        if not blob.exists():
            raise KeyError(ref)
        data = blob.read_bytes()
        if sha256_hex(data) != hex_digest:
            raise ValueError(f"artifact {ref} failed digest verification on read")
        return data

    def exists(self, ref: str) -> bool:
        return self._blob_path(self._parse_ref(ref)).exists()

    def meta(self, ref: str) -> dict[str, Any]:
        """Sidecar metadata (media_type, size, created_at) for *ref*."""
        meta_path = self._meta_path(self._parse_ref(ref))
        if not meta_path.exists():
            raise KeyError(ref)
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def put_text(self, text: str, media_type: str = "text/plain; charset=utf-8") -> str:
        return self.put(text.encode("utf-8"), media_type=media_type)

    def get_text(self, ref: str) -> str:
        return self.get(ref).decode("utf-8")

    def _parse_ref(self, ref: str) -> str:
        prefix = ARTIFACT_SCHEME + DIGEST_PREFIX
        hex_digest = ref[len(prefix):] if ref.startswith(prefix) else ""
        if len(hex_digest) != 64 or not set(hex_digest) <= _HEX_CHARS:
            raise ValueError(f"not a valid artifact reference: {ref!r}")
        return hex_digest

    def _blob_path(self, hex_digest: str) -> Path:
        return self.root_dir / hex_digest[:2] / hex_digest[2:4] / hex_digest

    def _meta_path(self, hex_digest: str) -> Path:
        return self._blob_path(hex_digest).with_name(hex_digest + ".meta.json")
