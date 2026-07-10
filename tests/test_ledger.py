"""Tests for the canonical event ledger (report sections 10.3, 15.1, 15.6).

Covers: integrity filling and sequence ordering, hash-chain links,
idempotent duplicate append, query filters, honest verify_chain, tamper
detection via raw SQL edits, JSONL export/import round-trip and
persistence across reopen of a file-backed ledger.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from foundry.contracts import Event, EventTypes, LedgerLike
from foundry.ledger import EventLedger, import_jsonl


def make_event(i: int = 0, **overrides: object) -> Event:
    fields: dict[str, object] = {
        "event_id": f"evt_{i:04d}",
        "event_type": EventTypes.NODE_COMPLETED,
        "mission_id": "mis_1",
        "run_id": "run_1",
        "payload": {"i": i},
    }
    fields.update(overrides)
    return Event(**fields)  # type: ignore[arg-type]


class HmacSigner:
    """Minimal duck-typed signer: .sign/.verify over bytes and .key_id."""

    def __init__(self, key: bytes = b"test-key", key_id: str = "k1") -> None:
        self._key = key
        self.key_id = key_id

    def sign(self, data: bytes) -> str:
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(data), signature)


@pytest.fixture()
def ledger() -> EventLedger:
    return EventLedger(":memory:")


class TestAppend:
    def test_append_fills_integrity_and_recorded_at(self, ledger: EventLedger) -> None:
        stored = ledger.append(make_event(1))
        assert stored.integrity is not None
        assert stored.integrity.producer == "ledger-1"
        assert stored.integrity.digest == stored.payload_digest()
        assert stored.integrity.prev_digest is None
        assert stored.integrity.sequence == 1
        assert stored.integrity.signature is None
        assert stored.recorded_at is not None

    def test_sequence_is_monotonic(self, ledger: EventLedger) -> None:
        stored = [ledger.append(make_event(i)) for i in range(1, 5)]
        assert [e.integrity.sequence for e in stored] == [1, 2, 3, 4]

    def test_hash_chain_links(self, ledger: EventLedger) -> None:
        stored = [ledger.append(make_event(i)) for i in range(1, 4)]
        assert stored[0].integrity.prev_digest is None
        assert stored[1].integrity.prev_digest == stored[0].integrity.digest
        assert stored[2].integrity.prev_digest == stored[1].integrity.digest

    def test_digest_excludes_integrity_and_recorded_at(self, ledger: EventLedger) -> None:
        event = make_event(1)
        stored = ledger.append(event)
        # The digest computed pre-append equals the one on the stored event.
        assert event.payload_digest() == stored.payload_digest()

    def test_idempotent_duplicate_append(self, ledger: EventLedger) -> None:
        first = ledger.append(make_event(1))
        # Same event_id with DIFFERENT content: stored row must win, unchanged.
        duplicate = make_event(1, payload={"i": 999})
        second = ledger.append(duplicate)
        assert second == first
        assert second.payload == {"i": 1}
        assert ledger.count() == 1
        # Re-appending the exact stored event is also a no-op.
        assert ledger.append(first) == first
        assert ledger.count() == 1

    def test_signer_fills_signature(self) -> None:
        signer = HmacSigner()
        ledger = EventLedger(":memory:", producer="ledger-signed", signer=signer)
        stored = ledger.append(make_event(1))
        digest = stored.integrity.digest
        assert stored.integrity.signature == f"k1:{signer.sign(digest.encode('utf-8'))}"
        assert stored.integrity.producer == "ledger-signed"


class TestQuery:
    @pytest.fixture()
    def populated(self, ledger: EventLedger) -> EventLedger:
        ledger.append(make_event(1, mission_id="mis_a", run_id="run_1"))
        ledger.append(make_event(2, mission_id="mis_a", run_id="run_2",
                                 event_type=EventTypes.NODE_FAILED))
        ledger.append(make_event(3, mission_id="mis_b", run_id="run_3",
                                 experiment_id="exp_1"))
        ledger.append(make_event(4, mission_id="mis_b", run_id="run_3",
                                 experiment_id="exp_1",
                                 event_type=EventTypes.ARM_COMPLETED))
        return ledger

    def test_query_by_mission(self, populated: EventLedger) -> None:
        events = populated.query(mission_id="mis_a")
        assert [e.event_id for e in events] == ["evt_0001", "evt_0002"]

    def test_query_by_run(self, populated: EventLedger) -> None:
        assert [e.event_id for e in populated.query(run_id="run_3")] == ["evt_0003", "evt_0004"]

    def test_query_by_experiment(self, populated: EventLedger) -> None:
        assert len(populated.query(experiment_id="exp_1")) == 2

    def test_query_by_event_type(self, populated: EventLedger) -> None:
        events = populated.query(event_type=EventTypes.NODE_FAILED)
        assert [e.event_id for e in events] == ["evt_0002"]

    def test_query_combined_filters(self, populated: EventLedger) -> None:
        events = populated.query(mission_id="mis_b", event_type=EventTypes.ARM_COMPLETED)
        assert [e.event_id for e in events] == ["evt_0004"]

    def test_query_no_filters_returns_all_in_sequence_order(self, populated: EventLedger) -> None:
        events = populated.query()
        assert [e.integrity.sequence for e in events] == [1, 2, 3, 4]
        assert events == populated.all_events()

    def test_query_no_match(self, populated: EventLedger) -> None:
        assert populated.query(mission_id="mis_zzz") == []

    def test_get(self, populated: EventLedger) -> None:
        event = populated.get("evt_0003")
        assert event is not None and event.experiment_id == "exp_1"
        assert populated.get("evt_missing") is None

    def test_count(self, populated: EventLedger) -> None:
        assert populated.count() == 4


class TestAppendOnlySurface:
    def test_conforms_to_ledger_like(self, ledger: EventLedger) -> None:
        assert isinstance(ledger, LedgerLike)

    def test_no_update_or_delete_api(self, ledger: EventLedger) -> None:
        for name in ("update", "delete", "remove", "pop", "clear", "set", "replace"):
            assert not hasattr(ledger, name)


class TestVerifyChain:
    def test_honest_ledger_verifies(self, ledger: EventLedger) -> None:
        for i in range(1, 6):
            ledger.append(make_event(i))
        ok, errors = ledger.verify_chain()
        assert ok is True
        assert errors == []

    def test_empty_ledger_verifies(self, ledger: EventLedger) -> None:
        assert ledger.verify_chain() == (True, [])

    def test_detects_payload_tamper_via_raw_sql(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        ledger = EventLedger(db)
        for i in range(1, 4):
            ledger.append(make_event(i))

        raw = sqlite3.connect(str(db))
        (body,) = raw.execute("SELECT body FROM events WHERE sequence = 2").fetchone()
        doc = json.loads(body)
        doc["payload"]["i"] = 999_999  # in-place tamper: rewrite history
        raw.execute("UPDATE events SET body = ? WHERE sequence = 2", (json.dumps(doc),))
        raw.commit()
        raw.close()

        ok, errors = ledger.verify_chain()
        assert ok is False
        assert any("evt_0002" in e and "payload digest mismatch" in e for e in errors)
        ledger.close()

    def test_detects_digest_column_tamper(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        ledger = EventLedger(db)
        for i in range(1, 3):
            ledger.append(make_event(i))

        raw = sqlite3.connect(str(db))
        raw.execute(
            "UPDATE events SET digest = ? WHERE sequence = 1",
            ("sha256:" + "0" * 64,),
        )
        raw.commit()
        raw.close()

        ok, errors = ledger.verify_chain()
        assert ok is False
        assert any("evt_0001" in e and "digest column" in e for e in errors)
        ledger.close()

    def test_detects_deleted_row_as_chain_break(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        ledger = EventLedger(db)
        for i in range(1, 4):
            ledger.append(make_event(i))

        raw = sqlite3.connect(str(db))
        raw.execute("DELETE FROM events WHERE sequence = 2")
        raw.commit()
        raw.close()

        ok, errors = ledger.verify_chain()
        assert ok is False
        assert any("chain break" in e for e in errors)
        assert any("not contiguous" in e for e in errors)
        ledger.close()

    def test_detects_tail_truncation_via_checkpoint(self, tmp_path: Path) -> None:
        """Deleting the newest event leaves the chain intact but not the anchor."""
        db = tmp_path / "ledger.db"
        ledger = EventLedger(db)
        for i in range(1, 6):
            ledger.append(make_event(i))
        assert ledger.verify_chain() == (True, [])

        raw = sqlite3.connect(str(db))
        raw.execute("DELETE FROM events WHERE sequence = (SELECT MAX(sequence) FROM events)")
        raw.commit()
        raw.close()

        ok, errors = ledger.verify_chain()
        assert ok is False
        assert any("tail truncation" in e for e in errors)
        ledger.close()

    def test_forged_checkpoint_requires_the_signing_key(self, tmp_path: Path) -> None:
        """With a signer, an adversary cannot rewrite the checkpoint to hide truncation."""
        db = tmp_path / "ledger.db"
        ledger = EventLedger(db, signer=HmacSigner())
        for i in range(1, 6):
            ledger.append(make_event(i))
        assert ledger.verify_chain() == (True, [])

        raw = sqlite3.connect(str(db))
        raw.execute("DELETE FROM events WHERE sequence = (SELECT MAX(sequence) FROM events)")
        (new_tip_digest,) = raw.execute(
            "SELECT digest FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        raw.commit()
        raw.close()

        checkpoint_path = Path(str(db) + ".checkpoint")
        forged = {
            "tip_sequence": 4,
            "tip_digest": new_tip_digest,
            "count": 4,
            "signature": "0" * 64,  # attacker holds no key
        }
        checkpoint_path.write_text(json.dumps(forged), encoding="utf-8")

        ok, errors = ledger.verify_chain()
        assert ok is False
        assert any("signature missing or invalid" in e for e in errors)
        ledger.close()

    def test_missing_checkpoint_for_nonempty_ledger_is_flagged(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        ledger = EventLedger(db)
        ledger.append(make_event(1))
        Path(str(db) + ".checkpoint").unlink()
        ok, errors = ledger.verify_chain()
        assert ok is False
        assert any("missing tip checkpoint" in e for e in errors)
        ledger.close()

    def test_verification_is_independent_of_stored_byte_formatting(self, tmp_path: Path) -> None:
        """Digests are recomputed from the parsed data, not the exact bytes a
        particular serializer emitted -- so re-encoding the same data (as a
        future pydantic might) never reads as tampering."""
        db = tmp_path / "ledger.db"
        ledger = EventLedger(db)
        for i in range(1, 4):
            ledger.append(make_event(i))

        raw = sqlite3.connect(str(db))
        (body,) = raw.execute("SELECT body FROM events WHERE sequence = 2").fetchone()
        reformatted = json.dumps(json.loads(body), indent=4, sort_keys=False)
        assert reformatted != body  # different bytes, identical data
        raw.execute("UPDATE events SET body = ? WHERE sequence = 2", (reformatted,))
        raw.commit()
        raw.close()

        assert ledger.verify_chain() == (True, [])
        ledger.close()


class TestExportImport:
    def test_jsonl_round_trip_preserves_digests_and_chain(
        self, ledger: EventLedger, tmp_path: Path
    ) -> None:
        stored = [ledger.append(make_event(i)) for i in range(1, 5)]
        out = tmp_path / "events.jsonl"
        assert ledger.export_jsonl(out) == 4

        loaded = import_jsonl(out)
        assert loaded == stored
        assert [e.integrity.digest for e in loaded] == [e.integrity.digest for e in stored]
        # Independent chain re-verification without the database.
        for prev, curr in zip(loaded, loaded[1:], strict=False):
            assert curr.integrity.prev_digest == prev.integrity.digest
        for event in loaded:
            assert event.payload_digest() == event.integrity.digest

    def test_export_empty_ledger(self, ledger: EventLedger, tmp_path: Path) -> None:
        out = tmp_path / "empty.jsonl"
        assert ledger.export_jsonl(out) == 0
        assert import_jsonl(out) == []


class TestConcurrentWriters:
    def test_two_ledger_handles_append_without_crashing(self, tmp_path: Path) -> None:
        """Two writers on one database serialize via BEGIN IMMEDIATE instead of
        racing into an uncaught sqlite3.IntegrityError on the sequence key."""
        db = tmp_path / "ledger.db"
        n_per_writer = 20
        errors: list[BaseException] = []

        def writer(offset: int) -> None:
            handle = EventLedger(db, producer=f"writer-{offset}")
            try:
                for i in range(n_per_writer):
                    handle.append(make_event(offset * 1000 + i))
            except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
                errors.append(exc)
            finally:
                handle.close()

        threads = [threading.Thread(target=writer, args=(k,)) for k in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        verifier = EventLedger(db, producer="verifier")
        try:
            assert verifier.count() == 2 * n_per_writer
            ok, chain_errors = verifier.verify_chain()
            assert ok is True, chain_errors
        finally:
            verifier.close()

    def test_interleaved_appends_from_two_handles_keep_the_chain(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        a = EventLedger(db, producer="a")
        b = EventLedger(db, producer="b")
        try:
            for i in range(1, 11):
                (a if i % 2 else b).append(make_event(i))
            assert a.count() == b.count() == 10
            assert a.verify_chain() == (True, [])
        finally:
            a.close()
            b.close()


class TestPersistence:
    def test_reopen_preserves_events_and_continues_chain(self, tmp_path: Path) -> None:
        db = tmp_path / "ledger.db"
        first = EventLedger(db)
        stored = [first.append(make_event(i)) for i in range(1, 3)]
        first.close()

        reopened = EventLedger(db)
        assert reopened.count() == 2
        assert reopened.all_events() == stored
        assert reopened.verify_chain() == (True, [])

        third = reopened.append(make_event(3))
        assert third.integrity.sequence == 3
        assert third.integrity.prev_digest == stored[1].integrity.digest
        assert reopened.verify_chain() == (True, [])
        reopened.close()

    def test_accepts_str_path(self, tmp_path: Path) -> None:
        ledger = EventLedger(str(tmp_path / "str_path.db"))
        ledger.append(make_event(1))
        assert ledger.count() == 1
        ledger.close()
