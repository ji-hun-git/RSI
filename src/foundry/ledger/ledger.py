"""Canonical append-only event ledger (report sections 10.3, 15.1, 15.6).

The ledger is the foundry's authoritative evidence store (report 10.3,
Event Collector / Event Store rows): every event is recorded exactly once
(idempotent on ``event_id``), receives a filled ``Integrity`` block --
producer, payload digest, hash chain over prior events, monotonically
increasing sequence, optional producer signature -- and is never updated
or deleted. Corrections are new events. ``verify_chain`` recomputes every
digest and chain link so in-place tampering is evident (report 10.1,
Audit Ledger), and cross-checks a signed tip checkpoint so silently
truncating the newest events is evident too. ``export_jsonl`` /
``import_jsonl`` support independent replay of the evidence stream.

Concurrency: ``append`` performs its tip read and insert inside one
``BEGIN IMMEDIATE`` transaction, so two writers on the same database file
serialize instead of racing into a UNIQUE-constraint crash.

Verification is model-independent: ``verify_chain`` recomputes digests
from the *stored* canonical-JSON bytes (parse, drop the integrity block,
re-canonicalize), never by round-tripping through pydantic serialization,
so a future pydantic serialization change cannot make honest historical
events look tampered.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from foundry.contracts import Event, Integrity, canonical_json, content_digest, utcnow

#: Fields excluded from the payload digest (mirrors ``Event.payload_digest``).
_DIGEST_EXCLUDED_FIELDS = ("integrity", "recorded_at")


@runtime_checkable
class SignerLike(Protocol):
    """Duck type for the optional producer signer."""

    @property
    def key_id(self) -> str: ...

    def sign(self, data: bytes) -> str: ...

    def verify(self, data: bytes, signature: str) -> bool: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    sequence      INTEGER PRIMARY KEY,
    event_id      TEXT NOT NULL UNIQUE,
    event_type    TEXT NOT NULL,
    mission_id    TEXT,
    run_id        TEXT,
    experiment_id TEXT,
    digest        TEXT NOT NULL,
    prev_digest   TEXT,
    body          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_mission ON events (mission_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON events (run_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
"""


def _raw_payload_digest(doc: dict[str, Any]) -> str:
    """Payload digest recomputed from a stored body, without pydantic round-trip."""
    payload = {k: v for k, v in doc.items() if k not in _DIGEST_EXCLUDED_FIELDS}
    return content_digest(payload)


class EventLedger:
    """SQLite-backed append-only event ledger conforming to ``LedgerLike``.

    The public surface is deliberately append-only: there is no update or
    delete method. ``signature`` is recorded as ``"<key_id>:<sig>"`` where
    ``sig = signer.sign(digest.encode("utf-8"))`` (the producer signs the
    payload digest, per the ``Integrity`` contract).

    Tail tamper-evidence: after every append the ledger writes a tip
    checkpoint file next to the database (``<db>.checkpoint``, overridable
    via ``checkpoint_path``) recording ``(tip_sequence, tip_digest,
    count)``, signed by the producer signer when one is configured.
    ``verify_chain`` treats the checkpoint as a floor: the checkpointed
    sequence must still exist with the checkpointed digest, so deleting
    the most recent event(s) is detected. In-memory ledgers keep no
    checkpoint.
    """

    def __init__(
        self,
        db_path: Path | str,
        producer: str = "ledger-1",
        signer: SignerLike | None = None,
        checkpoint_path: Path | str | None = None,
    ) -> None:
        self.db_path = db_path if isinstance(db_path, str) else str(db_path)
        self.producer = producer
        self.signer = signer
        if checkpoint_path is not None:
            self.checkpoint_path: Path | None = Path(checkpoint_path)
        elif self.db_path == ":memory:":
            self.checkpoint_path = None
        else:
            self.checkpoint_path = Path(self.db_path + ".checkpoint")
        # Autocommit mode with an explicit write transaction in append();
        # the timeout keeps concurrent cross-process writers polite.
        self._conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        """Release the underlying SQLite connection (file handles on Windows)."""
        self._conn.close()

    def append(self, event: Event) -> Event:
        """Record *event*, filling its integrity block; idempotent on event_id.

        The duplicate check, tip read and insert run inside a single
        ``BEGIN IMMEDIATE`` transaction, so a second writer on the same
        database file blocks until this append commits instead of reading
        a stale tip and crashing on the sequence PRIMARY KEY.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT body FROM events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if row is not None:
                self._conn.execute("ROLLBACK")
                return Event.model_validate_json(row[0])
            tip = self._conn.execute(
                "SELECT sequence, digest FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            prev_sequence, prev_digest = tip if tip is not None else (0, None)
            digest = event.payload_digest()
            signature: str | None = None
            if self.signer is not None:
                signature = f"{self.signer.key_id}:{self.signer.sign(digest.encode('utf-8'))}"
            integrity = Integrity(
                producer=self.producer,
                digest=digest,
                prev_digest=prev_digest,
                sequence=prev_sequence + 1,
                signature=signature,
            )
            stored = event.with_integrity(integrity, recorded_at=utcnow())
            self._conn.execute(
                "INSERT INTO events (sequence, event_id, event_type, mission_id, run_id,"
                " experiment_id, digest, prev_digest, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    integrity.sequence,
                    stored.event_id,
                    stored.event_type,
                    stored.mission_id,
                    stored.run_id,
                    stored.experiment_id,
                    digest,
                    prev_digest,
                    canonical_json(stored).decode("utf-8"),
                ),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._write_checkpoint(integrity.sequence, digest)
        return stored

    def get(self, event_id: str) -> Event | None:
        row = self._conn.execute(
            "SELECT body FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        return Event.model_validate_json(row[0]) if row is not None else None

    def query(
        self,
        *,
        mission_id: str | None = None,
        run_id: str | None = None,
        experiment_id: str | None = None,
        event_type: str | None = None,
    ) -> list[Event]:
        """Events matching every given filter, in ledger sequence order."""
        clauses: list[str] = []
        params: list[str] = []
        for column, value in (
            ("mission_id", mission_id),
            ("run_id", run_id),
            ("experiment_id", experiment_id),
            ("event_type", event_type),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT body FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sequence"
        return [Event.model_validate_json(row[0]) for row in self._conn.execute(sql, params)]

    def all_events(self) -> list[Event]:
        return self.query()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    # -- tip checkpoint -----------------------------------------------------

    def _checkpoint_signature(self, payload: dict[str, Any]) -> str | None:
        if self.signer is None:
            return None
        return self.signer.sign(canonical_json(payload))

    def _write_checkpoint(self, sequence: int, digest: str) -> None:
        """Persist the signed tip checkpoint, monotonically (floor semantics)."""
        if self.checkpoint_path is None:
            return
        existing = self._read_checkpoint()
        if existing is not None and int(existing.get("tip_sequence", 0)) >= sequence:
            return
        payload = {"tip_sequence": sequence, "tip_digest": digest, "count": sequence}
        record = dict(payload)
        record["signature"] = self._checkpoint_signature(payload)
        tmp = self.checkpoint_path.with_name(f"{self.checkpoint_path.name}.{sequence}.tmp")
        tmp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8", newline="\n")
        try:
            os.replace(tmp, self.checkpoint_path)
        except OSError:
            # A concurrent writer replaced the checkpoint at this instant.
            # Safe to skip: the checkpoint is a monotonic floor, and the
            # competing writer anchored an equal-or-newer tip.
            tmp.unlink(missing_ok=True)

    def _read_checkpoint(self) -> dict[str, Any] | None:
        if self.checkpoint_path is None or not self.checkpoint_path.exists():
            return None
        return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))

    def _verify_checkpoint(self, digests_by_sequence: dict[int, str]) -> list[str]:
        """Cross-check the stored events against the anchored tip checkpoint."""
        if self.checkpoint_path is None:
            return []
        checkpoint = self._read_checkpoint()
        if checkpoint is None:
            if digests_by_sequence:
                return [
                    "checkpoint: missing tip checkpoint for a non-empty ledger "
                    "(possible tail truncation)"
                ]
            return []
        errors: list[str] = []
        payload = {
            "tip_sequence": checkpoint.get("tip_sequence"),
            "tip_digest": checkpoint.get("tip_digest"),
            "count": checkpoint.get("count"),
        }
        if self.signer is not None:
            signature = checkpoint.get("signature")
            if not signature or not self.signer.verify(canonical_json(payload), signature):
                errors.append("checkpoint: tip checkpoint signature missing or invalid")
        tip_sequence = int(checkpoint["tip_sequence"])
        tip_digest = checkpoint["tip_digest"]
        if digests_by_sequence.get(tip_sequence) != tip_digest:
            errors.append(
                f"checkpoint: anchored tip (sequence {tip_sequence}, digest {tip_digest}) "
                "is absent or altered (tail truncation)"
            )
        if len(digests_by_sequence) < int(checkpoint["count"]):
            errors.append(
                f"checkpoint: ledger holds {len(digests_by_sequence)} events, "
                f"fewer than the anchored count {checkpoint['count']}"
            )
        return errors

    # -- verification ---------------------------------------------------------

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Recompute every payload digest and chain link; list all mismatches.

        Returns ``(ok, errors)`` where ``ok`` is True iff *errors* is empty.
        Detects payload tampering (digest recomputed from the stored bytes
        disagrees with the integrity block), index-column tampering, broken
        ``prev_digest`` links, non-contiguous sequences and -- via the
        signed tip checkpoint -- deletion of the newest events (report
        10.1, Audit Ledger). Digests are recomputed from the stored
        canonical JSON, never through model re-serialization, so
        verification does not depend on the installed pydantic version.
        """
        errors: list[str] = []
        prev_digest: str | None = None
        prev_sequence = 0
        digests_by_sequence: dict[int, str] = {}
        for row_digest, body in self._conn.execute(
            "SELECT digest, body FROM events ORDER BY sequence"
        ):
            doc = json.loads(body)
            event_id = doc.get("event_id", "<unknown>")
            integrity = doc.get("integrity")
            if integrity is None:
                errors.append(f"{event_id}: stored event has no integrity block")
                continue
            recomputed = _raw_payload_digest(doc)
            if recomputed != integrity["digest"]:
                errors.append(
                    f"{event_id}: payload digest mismatch"
                    f" (stored {integrity['digest']}, recomputed {recomputed})"
                )
            if row_digest != integrity["digest"]:
                errors.append(
                    f"{event_id}: indexed digest column disagrees with integrity block"
                )
            if integrity["prev_digest"] != prev_digest:
                errors.append(
                    f"{event_id}: chain break"
                    f" (prev_digest {integrity['prev_digest']}, expected {prev_digest})"
                )
            if integrity["sequence"] != prev_sequence + 1:
                errors.append(
                    f"{event_id}: sequence {integrity['sequence']}"
                    f" not contiguous after {prev_sequence}"
                )
            prev_digest = integrity["digest"]
            prev_sequence = integrity["sequence"]
            digests_by_sequence[integrity["sequence"]] = integrity["digest"]
        errors.extend(self._verify_checkpoint(digests_by_sequence))
        return (not errors, errors)

    def export_jsonl(self, path: Path | str) -> int:
        """Write every stored event as one canonical-JSON line, in sequence order."""
        written = 0
        with Path(path).open("w", encoding="utf-8", newline="\n") as fh:
            for (body,) in self._conn.execute("SELECT body FROM events ORDER BY sequence"):
                fh.write(body + "\n")
                written += 1
        return written


def import_jsonl(path: Path | str) -> list[Event]:
    """Load an ``export_jsonl`` stream back into Event objects, in file order.

    Integrity blocks are preserved verbatim so an independent process can
    re-verify digests and the hash chain without the originating database.
    """
    events: list[Event] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(Event.model_validate_json(line))
    return events
