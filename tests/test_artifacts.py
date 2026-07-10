"""Tests for the content-addressed artifact store (report sections 10.3, 15.6).

Covers: ref format and storage layout, dedup of identical content, digest
verification on get (corruption raises), missing refs, sidecar metadata
and the text conveniences.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from foundry.artifacts import ARTIFACT_SCHEME, ArtifactStore
from foundry.contracts import ArtifactStoreLike, sha256_hex

REF_PATTERN = re.compile(r"^artifact://sha256:[0-9a-f]{64}$")


@pytest.fixture()
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts")


class TestPutGet:
    def test_put_get_round_trip(self, store: ArtifactStore) -> None:
        data = b"hello foundry \x00\xff binary"
        ref = store.put(data)
        assert REF_PATTERN.match(ref)
        assert store.get(ref) == data

    def test_ref_is_the_content_digest(self, store: ArtifactStore) -> None:
        data = b"addressed by content"
        ref = store.put(data)
        assert ref == f"{ARTIFACT_SCHEME}sha256:{sha256_hex(data)}"

    def test_storage_layout_and_sidecar_meta(self, store: ArtifactStore) -> None:
        data = b"layout check"
        ref = store.put(data, media_type="application/x-test")
        hex_digest = ref.removeprefix(ARTIFACT_SCHEME + "sha256:")
        blob = store.root_dir / hex_digest[:2] / hex_digest[2:4] / hex_digest
        assert blob.is_file()
        sidecar = blob.with_name(hex_digest + ".meta.json")
        assert sidecar.is_file()
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        assert meta["media_type"] == "application/x-test"
        assert meta["size"] == len(data)
        assert "created_at" in meta
        assert store.meta(ref) == meta

    def test_exists(self, store: ArtifactStore) -> None:
        ref = store.put(b"present")
        assert store.exists(ref) is True
        absent = ARTIFACT_SCHEME + "sha256:" + sha256_hex(b"never stored")
        assert store.exists(absent) is False

    def test_get_missing_raises_key_error(self, store: ArtifactStore) -> None:
        absent = ARTIFACT_SCHEME + "sha256:" + sha256_hex(b"never stored")
        with pytest.raises(KeyError):
            store.get(absent)

    def test_meta_missing_raises_key_error(self, store: ArtifactStore) -> None:
        absent = ARTIFACT_SCHEME + "sha256:" + sha256_hex(b"never stored")
        with pytest.raises(KeyError):
            store.meta(absent)


class TestDedup:
    def test_identical_content_dedupes_to_same_ref(self, store: ArtifactStore) -> None:
        ref1 = store.put(b"same bytes")
        ref2 = store.put(b"same bytes")
        assert ref1 == ref2
        blobs = [p for p in store.root_dir.rglob("*") if p.is_file() and not p.name.endswith(".meta.json")]
        assert len(blobs) == 1

    def test_dedup_keeps_original_metadata(self, store: ArtifactStore) -> None:
        ref = store.put(b"first wins", media_type="text/x-first")
        original_meta = store.meta(ref)
        assert store.put(b"first wins", media_type="text/x-second") == ref
        assert store.meta(ref) == original_meta
        assert store.meta(ref)["media_type"] == "text/x-first"

    def test_different_content_gets_different_refs(self, store: ArtifactStore) -> None:
        assert store.put(b"a") != store.put(b"b")

    def test_put_leaves_no_temp_files_behind(self, store: ArtifactStore) -> None:
        store.put(b"payload one")
        store.put(b"payload one")
        store.put(b"payload two")
        leftovers = [p for p in store.root_dir.rglob("*.tmp")]
        assert leftovers == []


class TestCrashRecovery:
    def test_meta_exists_before_blob_appears(self, store: ArtifactStore, monkeypatch) -> None:
        """The sidecar is written BEFORE os.replace: a crash between the two
        can leave meta-without-blob (harmless) but never blob-without-meta."""
        import foundry.artifacts.store as store_module

        data = b"crash window content"
        hex_digest = sha256_hex(data)

        def exploding_replace(src, dst):
            raise RuntimeError("simulated crash before the blob move")

        monkeypatch.setattr(store_module.os, "replace", exploding_replace)
        with pytest.raises(RuntimeError):
            store.put(data)
        monkeypatch.undo()

        ref = ARTIFACT_SCHEME + "sha256:" + hex_digest
        assert not store.exists(ref)  # blob never appeared ...
        meta_path = store.root_dir / hex_digest[:2] / hex_digest[2:4] / (hex_digest + ".meta.json")
        assert meta_path.exists()  # ... but the sidecar did (safe ordering)
        # A later put completes the pair.
        assert store.put(data) == ref
        assert store.get(ref) == data
        assert store.meta(ref)["size"] == len(data)

    def test_backfills_meta_for_a_blob_missing_its_sidecar(self, store: ArtifactStore) -> None:
        """A pre-fix crash could leave a blob without metadata; put() repairs it."""
        data = b"orphaned blob"
        hex_digest = sha256_hex(data)
        blob = store.root_dir / hex_digest[:2] / hex_digest[2:4] / hex_digest
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(data)
        ref = ARTIFACT_SCHEME + "sha256:" + hex_digest
        with pytest.raises(KeyError):
            store.meta(ref)
        assert store.put(data, media_type="text/x-backfilled") == ref
        assert store.meta(ref)["media_type"] == "text/x-backfilled"


class TestDigestVerification:
    def test_get_raises_on_corrupted_blob(self, store: ArtifactStore) -> None:
        ref = store.put(b"trusted content")
        hex_digest = ref.removeprefix(ARTIFACT_SCHEME + "sha256:")
        blob = store.root_dir / hex_digest[:2] / hex_digest[2:4] / hex_digest
        blob.write_bytes(b"substituted content")  # tamper on disk
        with pytest.raises(ValueError, match="digest verification"):
            store.get(ref)

    def test_get_raises_on_truncated_blob(self, store: ArtifactStore) -> None:
        ref = store.put(b"will be truncated")
        hex_digest = ref.removeprefix(ARTIFACT_SCHEME + "sha256:")
        blob = store.root_dir / hex_digest[:2] / hex_digest[2:4] / hex_digest
        blob.write_bytes(b"will be")
        with pytest.raises(ValueError):
            store.get(ref)


class TestText:
    def test_put_text_get_text_round_trip(self, store: ArtifactStore) -> None:
        text = "unicode round trip: 한국어, ελληνικά, emoji \U0001f9ea"
        ref = store.put_text(text)
        assert store.get_text(ref) == text
        assert store.meta(ref)["media_type"] == "text/plain; charset=utf-8"

    def test_put_text_custom_media_type(self, store: ArtifactStore) -> None:
        ref = store.put_text('{"k": 1}', media_type="application/json")
        assert store.meta(ref)["media_type"] == "application/json"


class TestRefValidation:
    @pytest.mark.parametrize(
        "bad_ref",
        [
            "http://example.com/blob",
            "artifact://sha256:short",
            "artifact://sha256:" + "z" * 64,
            "artifact://md5:" + "0" * 64,
            "sha256:" + "0" * 64,
            "",
        ],
    )
    def test_invalid_refs_raise_value_error(self, store: ArtifactStore, bad_ref: str) -> None:
        with pytest.raises(ValueError):
            store.get(bad_ref)

    def test_conforms_to_artifact_store_like(self, store: ArtifactStore) -> None:
        assert isinstance(store, ArtifactStoreLike)
