"""Tests for the exported JSON Schema interchange layer (report 17.4).

The committed ``schemas/*.json`` files are byte-stable interchange
artifacts: regeneration must be byte-identical on every platform, which
in particular means LF newlines everywhere (a Windows regeneration must
not flip the bytes -- and therefore the digests -- to CRLF).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from export_schemas import DEFAULT_OUT, contract_models, export_schemas  # noqa: E402


def test_exported_schemas_use_lf_only(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    assert written
    for path in written:
        data = path.read_bytes()
        assert b"\r" not in data, f"{path.name} contains CR bytes (platform-dependent output)"
        assert data.endswith(b"\n")


def test_regeneration_matches_the_committed_schemas(tmp_path: Path) -> None:
    """The committed interchange files round-trip byte-for-byte."""
    written = export_schemas(tmp_path)
    committed = sorted(DEFAULT_OUT.glob("*.json"))
    assert [p.name for p in sorted(written)] == [p.name for p in committed]
    for regenerated in written:
        assert regenerated.read_bytes() == (DEFAULT_OUT / regenerated.name).read_bytes(), (
            f"{regenerated.name} differs from the committed schema; "
            "run scripts/export_schemas.py"
        )


def test_one_schema_per_contract_model() -> None:
    models = contract_models()
    assert {f"{name}.json" for name in models} == {p.name for p in DEFAULT_OUT.glob("*.json")}
