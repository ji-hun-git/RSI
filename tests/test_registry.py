"""Tests for foundry.registry: signing, content addressing, lineage, diff, fork."""

from __future__ import annotations

import json

import pytest

from foundry.contracts import (
    DIGEST_PREFIX,
    FieldChange,
    PromotionStatus,
    SystemBundle,
    is_digest,
)
from foundry.registry import BundleRegistry, HMACSigner, IntegrityError, PolicyViolation

WORKFLOW = "workflow://linear/v1"


def make_bundle(**overrides) -> SystemBundle:
    fields: dict = dict(
        workflow_ref=WORKFLOW,
        config={"strategy": "direct", "retrieval": {"top_k": 4}},
    )
    fields.update(overrides)
    return SystemBundle(**fields)


@pytest.fixture()
def signer(tmp_path):
    return HMACSigner.load_or_create(tmp_path / "keys" / "dev.key")


@pytest.fixture()
def registry(tmp_path, signer):
    return BundleRegistry(tmp_path / "bundles", signer=signer)


# -- signing ------------------------------------------------------------------


class TestHMACSigner:
    def test_load_or_create_generates_32_byte_key(self, tmp_path):
        key_path = tmp_path / "keys" / "dev.key"
        assert not key_path.exists()
        signer = HMACSigner.load_or_create(key_path)
        assert key_path.exists()
        assert len(key_path.read_bytes()) == 32
        assert signer.key_id == "dev"

    def test_load_or_create_reuses_existing_key(self, tmp_path):
        key_path = tmp_path / "dev.key"
        first = HMACSigner.load_or_create(key_path)
        second = HMACSigner.load_or_create(key_path)
        assert first.sign(b"payload") == second.sign(b"payload")

    def test_sign_and_verify(self, signer):
        signature = signer.sign(b"data")
        assert len(signature) == 64  # hex sha256
        assert signer.verify(b"data", signature)
        assert not signer.verify(b"data", "0" * 64)
        assert not signer.verify(b"other", signature)

    def test_different_keys_produce_different_signatures(self, tmp_path):
        a = HMACSigner.load_or_create(tmp_path / "a.key")
        b = HMACSigner.load_or_create(tmp_path / "b.key")
        assert a.sign(b"data") != b.sign(b"data")

    def test_load_never_mints_a_key(self, tmp_path):
        """Verification paths use load(): a missing key is a loud, distinct
        outcome and the audited root is never mutated."""
        missing = tmp_path / "keys" / "absent.key"
        with pytest.raises(FileNotFoundError):
            HMACSigner.load(missing)
        assert not missing.exists()
        created = HMACSigner.load_or_create(tmp_path / "k.key")
        loaded = HMACSigner.load(tmp_path / "k.key")
        assert created.sign(b"payload") == loaded.sign(b"payload")


# -- content addressing and round-trip ---------------------------------------


class TestContentAddress:
    def test_bundle_id_is_a_digest(self):
        assert is_digest(make_bundle().bundle_id)

    def test_identical_identity_fields_share_an_id(self):
        # created_at differs between the two constructions and must not matter.
        assert make_bundle().bundle_id == make_bundle().bundle_id

    def test_different_config_changes_the_id(self):
        base = make_bundle()
        other = make_bundle(config={"strategy": "plan", "retrieval": {"top_k": 4}})
        assert base.bundle_id != other.bundle_id

    def test_signatures_and_status_do_not_affect_the_id(self, registry):
        bundle = make_bundle()
        signed = registry.sign(bundle)
        assert signed.bundle_id == bundle.bundle_id

    def test_round_trip(self, registry):
        bundle = registry.register(make_bundle())
        loaded = registry.get(bundle.bundle_id)
        assert loaded.bundle_id == bundle.bundle_id
        assert loaded.identity_payload() == bundle.identity_payload()
        assert loaded.status == bundle.status
        assert registry.exists(bundle.bundle_id)
        assert registry.list_ids() == [bundle.bundle_id]

    def test_get_unknown_id_raises_key_error(self, registry):
        with pytest.raises(KeyError):
            registry.get(DIGEST_PREFIX + "0" * 64)


# -- tamper detection ---------------------------------------------------------


class TestTamperDetection:
    def _bundle_file(self, registry, bundle_id):
        return registry.dir_path / f"{bundle_id.removeprefix(DIGEST_PREFIX)}.json"

    def test_tampered_content_raises_on_load(self, registry):
        bundle = registry.register(make_bundle())
        path = self._bundle_file(registry, bundle.bundle_id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["config"]["strategy"] = "exfiltrate"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(IntegrityError):
            registry.get(bundle.bundle_id)

    def test_swapped_file_raises_on_load(self, registry):
        # A *valid* bundle placed under another bundle's address must fail.
        bundle = registry.register(make_bundle())
        impostor = make_bundle(config={"strategy": "impostor"})
        from foundry.contracts import canonical_json

        self._bundle_file(registry, bundle.bundle_id).write_bytes(canonical_json(impostor))
        with pytest.raises(IntegrityError):
            registry.get(bundle.bundle_id)

    def test_register_reverifies_content_address(self, registry):
        # model_copy bypasses validation; register must still catch the mismatch.
        stale = make_bundle().model_copy(update={"config": {"strategy": "edited"}})
        with pytest.raises(IntegrityError):
            registry.register(stale)


# -- idempotency and parents ----------------------------------------------------


class TestRegisterSemantics:
    def test_reregistering_identical_bundle_is_a_noop(self, registry):
        bundle = registry.register(make_bundle())
        assert registry.register(bundle) is bundle
        assert registry.list_ids() == [bundle.bundle_id]

    def test_same_address_different_content_raises(self, registry):
        bundle = registry.register(make_bundle())
        signed = registry.sign(bundle)  # same bundle_id, different signature_set
        with pytest.raises(IntegrityError):
            registry.register(signed)

    def test_unknown_parent_rejected(self, registry):
        orphan = make_bundle(parent_bundle_id=DIGEST_PREFIX + "0" * 64)
        with pytest.raises(IntegrityError):
            registry.register(orphan)

    def test_root_bundle_needs_no_parent(self, registry):
        assert registry.register(make_bundle()).parent_bundle_id is None


# -- lineage and diff -------------------------------------------------------------


class TestLineageAndDiff:
    def _three_generations(self, registry):
        root = registry.register(make_bundle())
        c1 = registry.register(
            registry.fork(
                root,
                [FieldChange(field_path="/config/strategy", new_value="plan")],
                allowed_path_prefixes=["/config"],
            )
        )
        c2 = registry.register(
            registry.fork(
                c1,
                [FieldChange(field_path="/config/strategy", new_value="reflect")],
                allowed_path_prefixes=["/config"],
            )
        )
        return root, c1, c2

    def test_lineage_walks_back_to_root(self, registry):
        root, c1, c2 = self._three_generations(registry)
        chain = registry.lineage(c2.bundle_id)
        assert [b.bundle_id for b in chain] == [c2.bundle_id, c1.bundle_id, root.bundle_id]
        assert registry.lineage(root.bundle_id) == [root]

    def test_diff_for_a_config_change_is_exact(self, registry):
        root, c1, _ = self._three_generations(registry)
        diff = registry.diff(root.bundle_id, c1.bundle_id)
        assert diff.parent_bundle_id == root.bundle_id
        assert diff.child_bundle_id == c1.bundle_id
        by_path = {c.field_path: c for c in diff.changes}
        # Exactly the applied change plus the two lineage fields fork sets.
        assert set(by_path) == {"/config/strategy", "/parent_bundle_id", "/semantic_version"}
        assert by_path["/config/strategy"].old_value == "direct"
        assert by_path["/config/strategy"].new_value == "plan"
        assert by_path["/parent_bundle_id"].old_value is None
        assert by_path["/parent_bundle_id"].new_value == root.bundle_id
        assert by_path["/semantic_version"].new_value == "0.1.1"

    def test_diff_reports_added_and_removed_leaves(self, registry):
        root = registry.register(make_bundle())
        child = registry.register(
            registry.fork(
                root,
                [
                    FieldChange(field_path="/config/new_flag", new_value=True),
                    FieldChange(field_path="/config/retrieval", new_value=None),  # removal
                ],
                allowed_path_prefixes=["/config"],
            )
        )
        by_path = {c.field_path: c for c in registry.diff(root.bundle_id, child.bundle_id).changes}
        assert by_path["/config/new_flag"].old_value is None
        assert by_path["/config/new_flag"].new_value is True
        assert by_path["/config/retrieval"].old_value == {"top_k": 4}
        assert by_path["/config/retrieval"].new_value is None


# -- fork -------------------------------------------------------------------------


class TestFork:
    def test_fork_applies_change_and_sets_metadata(self, registry):
        root = registry.register(make_bundle())
        child = registry.fork(
            root,
            [FieldChange(field_path="/config/strategy", old_value="direct", new_value="plan")],
            allowed_path_prefixes=["/config"],
        )
        assert child.config["strategy"] == "plan"
        assert child.config["retrieval"] == {"top_k": 4}  # untouched siblings survive
        assert child.parent_bundle_id == root.bundle_id
        assert child.status == PromotionStatus.EXPERIMENTAL
        assert child.semantic_version == "0.1.1"
        assert child.bundle_id == child.compute_bundle_id()
        # The parent is untouched (deep copy, not aliasing).
        assert root.config["strategy"] == "direct"
        # fork does not register automatically.
        assert not registry.exists(child.bundle_id)

    def test_fork_respects_explicit_semantic_version(self, registry):
        root = registry.register(make_bundle())
        child = registry.fork(
            root,
            [FieldChange(field_path="/config/strategy", new_value="plan")],
            allowed_path_prefixes=["/config"],
            semantic_version="1.0.0",
        )
        assert child.semantic_version == "1.0.0"

    def test_fork_refuses_path_outside_allowed_prefixes(self, registry):
        root = registry.register(make_bundle())
        with pytest.raises(PolicyViolation):
            registry.fork(
                root,
                [FieldChange(field_path="/evaluation_profile_ref", new_value="eval://other")],
                allowed_path_prefixes=["/config"],
            )

    def test_prefix_match_respects_segment_boundaries(self, registry):
        root = registry.register(make_bundle())
        with pytest.raises(PolicyViolation):
            registry.fork(
                root,
                [FieldChange(field_path="/configuration", new_value="x")],
                allowed_path_prefixes=["/config"],
            )

    def test_fork_refuses_parent_bundle_id_even_when_listed(self, registry):
        root = registry.register(make_bundle())
        with pytest.raises(PolicyViolation):
            registry.fork(
                root,
                [FieldChange(field_path="/parent_bundle_id", new_value=DIGEST_PREFIX + "0" * 64)],
                allowed_path_prefixes=["/parent_bundle_id"],
            )

    def test_fork_refuses_workflow_ref_unless_explicitly_allowed(self, registry):
        root = registry.register(make_bundle())
        with pytest.raises(PolicyViolation):
            registry.fork(
                root,
                [FieldChange(field_path="/workflow_ref", new_value="workflow://dag/v2")],
                allowed_path_prefixes=["/"],  # broad prefix is not an explicit allowance
            )
        child = registry.fork(
            root,
            [FieldChange(field_path="/workflow_ref", new_value="workflow://dag/v2")],
            allowed_path_prefixes=["/workflow_ref"],
        )
        assert child.workflow_ref == "workflow://dag/v2"

    def test_forked_lineage_registers_cleanly(self, registry):
        root = registry.register(make_bundle())
        child = registry.fork(
            root,
            [FieldChange(field_path="/config/strategy", new_value="plan")],
            allowed_path_prefixes=["/config"],
        )
        registered = registry.register(child)
        assert registry.get(registered.bundle_id).parent_bundle_id == root.bundle_id


# -- bundle signing ------------------------------------------------------------------


class TestBundleSigning:
    def test_sign_appends_record_and_verifies(self, registry, signer):
        bundle = make_bundle()
        signed = registry.sign(bundle)
        assert len(signed.signature_set) == 1
        assert signed.signature_set[0].signer == signer.key_id
        assert signed.signature_set[0].algorithm == "hmac-sha256"
        assert registry.verify_signatures(signed)

    def test_unsigned_bundle_does_not_verify(self, registry):
        assert not registry.verify_signatures(make_bundle())

    def test_signature_copied_to_altered_bundle_fails(self, registry):
        signed = registry.sign(make_bundle())
        altered = make_bundle(config={"strategy": "evil"}).model_copy(
            update={"signature_set": signed.signature_set}
        )
        assert not registry.verify_signatures(altered)

    def test_model_copy_tampered_bundle_fails_verification(self, registry):
        """A model_copy edit keeps the signed bundle_id but changes content;
        the signature must not transfer (content-integrity proof, not an
        id-string signature)."""
        signed = registry.sign(make_bundle())
        assert registry.verify_signatures(signed)
        tampered = signed.model_copy(update={"config": {"strategy": "EVIL_BACKDOOR"}})
        assert tampered.bundle_id == signed.bundle_id  # stale, self-asserted address
        assert tampered.bundle_id != tampered.compute_bundle_id()
        assert not registry.verify_signatures(tampered)

    def test_signature_does_not_verify_for_id_only_match(self, registry):
        """Same content address cannot be claimed by different content: the
        signature is computed over the identity payload itself."""
        bundle = make_bundle()
        signed = registry.sign(bundle)
        # Replay the signature records onto a content-tampered copy whose
        # bundle_id was ALSO updated to look internally consistent.
        impostor = make_bundle(config={"strategy": "impostor"}).model_copy(
            update={"signature_set": signed.signature_set}
        )
        assert impostor.bundle_id == impostor.compute_bundle_id()  # consistent address
        assert not registry.verify_signatures(impostor)  # but wrong signed content

    def test_wrong_key_fails_verification(self, tmp_path, registry):
        signed = registry.sign(make_bundle())
        other = BundleRegistry(
            tmp_path / "other-bundles",
            signer=HMACSigner.load_or_create(tmp_path / "other.key", key_id="other"),
        )
        assert not other.verify_signatures(signed)

    def test_sign_without_signer_is_an_error(self, tmp_path):
        unsigned_registry = BundleRegistry(tmp_path / "plain")
        with pytest.raises(ValueError):
            unsigned_registry.sign(make_bundle())
