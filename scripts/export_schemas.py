"""Export JSON Schemas for every pydantic model in ``foundry.contracts``.

Writes one ``<ModelName>.json`` per exported contract model (report 17.4:
the schemas are the stable interchange layer) so non-Python tooling can
validate events, bundles, experiment records and governance records.
Output is deterministic: sorted keys, two-space indent, trailing newline.

Usage: ``python scripts/export_schemas.py [--out DIR]``
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

import foundry.contracts as contracts

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "schemas"


def contract_models() -> dict[str, type[BaseModel]]:
    """Every pydantic model re-exported by ``foundry.contracts``, by name."""
    models: dict[str, type[BaseModel]] = {}
    for name in contracts.__all__:
        obj = getattr(contracts, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            models[name] = obj
    return models


def export_schemas(out_dir: Path) -> list[Path]:
    """Write one JSON Schema file per contract model; returns the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in sorted(contract_models().items()):
        schema = model.model_json_schema()
        path = out_dir / f"{name}.json"
        # newline="\n" pins LF on every platform: without it, Windows would
        # emit CRLF and the "stable interchange layer" bytes (and their
        # digests) would differ per platform.
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args(argv)
    written = export_schemas(args.out)
    print(f"wrote {len(written)} schemas to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
