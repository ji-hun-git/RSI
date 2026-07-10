"""Signed, content-addressed SystemBundle registry (report 9.1, 17.3).

The registry is the single source of truth for bundle identity and
lineage: every bundle is persisted as canonical JSON under its content
digest, parents must exist before children, and every load re-verifies
the content address so a tampered file can never masquerade as a
registered bundle. Forking is the only mutation primitive and it is
policy-checked at the edge: a change outside the caller's allowed path
prefixes raises ``PolicyViolation`` before any child bundle exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from foundry.contracts import (
    DIGEST_PREFIX,
    BundleDiff,
    FieldChange,
    PromotionStatus,
    SignatureRecord,
    SystemBundle,
    canonical_json,
)

from .signing import HMACSigner


class IntegrityError(Exception):
    """A stored or presented bundle fails content-address or lineage checks."""


class PolicyViolation(Exception):
    """A requested mutation falls outside the allowed mutation surface."""


def _path_within(path: str, prefix: str) -> bool:
    """JSON-pointer prefix match: exact segment boundaries, not string prefixes."""
    if path == prefix:
        return True
    return path.startswith(prefix if prefix.endswith("/") else prefix + "/")


def _diff_dicts(old: dict[str, Any], new: dict[str, Any], prefix: str) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for key in sorted(set(old) | set(new)):
        path = f"{prefix}/{key}"
        if key not in old:
            changes.append(FieldChange(field_path=path, old_value=None, new_value=new[key]))
        elif key not in new:
            changes.append(FieldChange(field_path=path, old_value=old[key], new_value=None))
        elif isinstance(old[key], dict) and isinstance(new[key], dict):
            changes.extend(_diff_dicts(old[key], new[key], path))
        elif old[key] != new[key]:
            changes.append(FieldChange(field_path=path, old_value=old[key], new_value=new[key]))
    return changes


def _apply_change(payload: dict[str, Any], change: FieldChange) -> None:
    """Set (or, when ``new_value`` is None, remove) the leaf named by ``field_path``."""
    segments = change.field_path.lstrip("/").split("/")
    node = payload
    for segment in segments[:-1]:
        node = node.setdefault(segment, {})
    leaf = segments[-1]
    if change.new_value is None:
        node.pop(leaf, None)
    else:
        node[leaf] = change.new_value


def _bump_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


class BundleRegistry:
    """Content-addressed bundle store with lineage, diff, fork and signing.

    All state lives under ``dir_path`` (one canonical-JSON file per bundle,
    named by the digest hex); nothing is global, so registries are cheap to
    create in tests and can be pointed at any location on Windows or POSIX.
    """

    #: ``fork`` refuses these identity fields regardless of allowed prefixes,
    #: except ``/workflow_ref`` when it is listed *explicitly* (report 14.1:
    #: lineage and topology roots are outside the default mutation surface).
    PROTECTED_FIELD_PATHS: tuple[str, ...] = ("/parent_bundle_id", "/workflow_ref")

    def __init__(self, dir_path: Path, signer: HMACSigner | None = None) -> None:
        self.dir_path = dir_path
        self.signer = signer
        self.dir_path.mkdir(parents=True, exist_ok=True)

    # -- storage -----------------------------------------------------------

    def _path_for(self, bundle_id: str) -> Path:
        # ":" is not a legal filename character on Windows; store the hex only.
        return self.dir_path / f"{bundle_id.removeprefix(DIGEST_PREFIX)}.json"

    def register(self, bundle: SystemBundle) -> SystemBundle:
        """Persist *bundle* under its content address.

        Re-verifies the content address (guarding against ``model_copy``
        edits that bypass validation), requires the parent to be registered
        first, and is idempotent for byte-identical re-registration.
        """
        computed = bundle.compute_bundle_id()
        if bundle.bundle_id != computed:
            raise IntegrityError(
                f"bundle_id {bundle.bundle_id!r} does not match content digest {computed!r}"
            )
        if bundle.parent_bundle_id is not None and not self.exists(bundle.parent_bundle_id):
            raise IntegrityError(
                f"parent bundle {bundle.parent_bundle_id!r} is not registered; "
                "register lineage root-first"
            )
        payload = canonical_json(bundle)
        path = self._path_for(bundle.bundle_id)
        if path.exists():
            if path.read_bytes() == payload:
                return bundle
            raise IntegrityError(
                f"registry already holds different content for {bundle.bundle_id!r}"
            )
        path.write_bytes(payload)
        return bundle

    def get(self, bundle_id: str) -> SystemBundle:
        """Load a bundle, re-validating its content address (tamper check)."""
        path = self._path_for(bundle_id)
        if not path.exists():
            raise KeyError(bundle_id)
        raw = json.loads(path.read_bytes().decode("utf-8"))
        try:
            bundle = SystemBundle.model_validate(raw)
        except ValueError as exc:
            raise IntegrityError(f"stored bundle {bundle_id!r} failed validation: {exc}") from exc
        if bundle.bundle_id != bundle_id:
            raise IntegrityError(
                f"file for {bundle_id!r} contains bundle {bundle.bundle_id!r}"
            )
        return bundle

    def exists(self, bundle_id: str) -> bool:
        return self._path_for(bundle_id).exists()

    def list_ids(self) -> list[str]:
        return sorted(DIGEST_PREFIX + path.stem for path in self.dir_path.glob("*.json"))

    # -- lineage and diff ----------------------------------------------------

    def lineage(self, bundle_id: str) -> list[SystemBundle]:
        """The chain from *bundle_id* back to its root, child first."""
        chain = [self.get(bundle_id)]
        while chain[-1].parent_bundle_id is not None:
            chain.append(self.get(chain[-1].parent_bundle_id))
        return chain

    def diff(self, parent_id: str, child_id: str) -> BundleDiff:
        """Machine-readable diff over the two bundles' identity payloads."""
        parent = self.get(parent_id)
        child = self.get(child_id)
        return BundleDiff(
            parent_bundle_id=parent_id,
            child_bundle_id=child_id,
            changes=_diff_dicts(parent.identity_payload(), child.identity_payload(), ""),
        )

    # -- fork ----------------------------------------------------------------

    def fork(
        self,
        parent: SystemBundle,
        changes: list[FieldChange],
        *,
        allowed_path_prefixes: list[str],
        semantic_version: str | None = None,
    ) -> SystemBundle:
        """Create (but do not register) a child bundle by applying *changes*.

        Every change must fall under one of *allowed_path_prefixes*;
        protected fields are refused outright (``/workflow_ref`` only when
        listed explicitly). A change whose ``new_value`` is None removes the
        leaf. The child gets ``parent_bundle_id``, EXPERIMENTAL status and a
        patch-bumped semantic version unless one is supplied.
        """
        for change in changes:
            if _path_within(change.field_path, "/parent_bundle_id"):
                raise PolicyViolation(
                    "/parent_bundle_id is set by fork() and may never be edited directly"
                )
            if (
                _path_within(change.field_path, "/workflow_ref")
                and "/workflow_ref" not in allowed_path_prefixes
            ):
                raise PolicyViolation(
                    "/workflow_ref is protected; allow it explicitly to change topology"
                )
            if not any(_path_within(change.field_path, p) for p in allowed_path_prefixes):
                raise PolicyViolation(
                    f"change to {change.field_path!r} is outside the allowed mutation "
                    f"surface {allowed_path_prefixes!r}"
                )

        payload = parent.identity_payload()  # model_dump builds fresh nested dicts
        for change in changes:
            _apply_change(payload, change)
        payload["parent_bundle_id"] = parent.bundle_id
        payload["semantic_version"] = semantic_version or _bump_patch(parent.semantic_version)
        return SystemBundle(status=PromotionStatus.EXPERIMENTAL, **payload)

    # -- signing ---------------------------------------------------------------

    def _require_signer(self) -> HMACSigner:
        if self.signer is None:
            raise ValueError("registry was constructed without a signer")
        return self.signer

    def sign(self, bundle: SystemBundle) -> SystemBundle:
        """Return *bundle* with a SignatureRecord over its identity payload appended.

        The signature covers the canonical JSON of every identity field --
        a content-integrity proof -- never just the self-asserted
        ``bundle_id`` string, so a ``model_copy``-tampered bundle cannot
        reuse a signature minted for different content.
        """
        signer = self._require_signer()
        record = SignatureRecord(
            signer=signer.key_id,
            signature=signer.sign(canonical_json(bundle.identity_payload())),
        )
        return bundle.model_copy(update={"signature_set": [*bundle.signature_set, record]})

    def verify_signatures(self, bundle: SystemBundle) -> bool:
        """True iff the content address is intact and every signature verifies.

        Recomputes the content address first (guarding against
        ``model_copy`` edits that bypass model validation), then verifies
        each signature over the canonical identity payload.
        """
        signer = self._require_signer()
        if bundle.bundle_id != bundle.compute_bundle_id():
            return False
        if not bundle.signature_set:
            return False
        data = canonical_json(bundle.identity_payload())
        return all(signer.verify(data, record.signature) for record in bundle.signature_set)
