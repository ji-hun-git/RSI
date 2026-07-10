"""The Stage-1 fixture workflow definition: nodes and node semantics.

Node semantics live here, in exactly one place, so that every runtime
adapter executing ``workflow://fixture/v1`` produces byte-identical
outputs for the same spec, bundle and worker. Cross-runtime conformance
(report 9.3) is only meaningful if the workflow itself cannot drift
between adapters.
"""

from __future__ import annotations

from typing import Any

from foundry.contracts import MissionSpec, SystemBundle, WorkerLike, content_digest, sha256_hex

FIXTURE_WORKFLOW_REF = "workflow://fixture/v1"
FIXTURE_NODES: tuple[str, ...] = ("plan", "execute", "verify")


def derive_node_seed(mission_id: str, node_id: str) -> int:
    """Deterministic worker seed: first 64 bits of sha256(mission_id+node_id)."""
    return int(sha256_hex(f"{mission_id}:{node_id}".encode())[:16], 16)


def run_fixture_node(
    node_id: str,
    spec: MissionSpec,
    bundle: SystemBundle,
    outputs: dict[str, dict[str, Any]],
    worker: WorkerLike,
) -> dict[str, Any]:
    """Compute one fixture node's output from prior outputs. Pure by contract."""
    if node_id == "plan":
        task_input = {
            "task_id": str(spec.inputs.get("task_id", spec.mission_id)),
            "text": spec.inputs["text"],
            "family": str(spec.inputs.get("family", "slugify")),
        }
        return {"task_input": task_input}
    if node_id == "execute":
        seed = derive_node_seed(spec.mission_id, node_id)
        return worker.invoke(outputs["plan"]["task_input"], bundle.config, seed)
    if node_id == "verify":
        return {"output_digest": content_digest(outputs["execute"])}
    raise ValueError(f"unknown fixture node {node_id!r}")
