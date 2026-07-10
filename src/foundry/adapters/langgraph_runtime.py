"""LangGraph runtime adapter (report 9.3, 16.1, 19.5 weeks 3-4).

Wraps LangGraph's ``StateGraph`` as a :class:`~foundry.runtime.RuntimeAdapter`
for the Stage-1 fixture workflow. The adapter rules hold exactly as for the
deterministic runtime, because both inherit the same control plane
(:class:`~foundry.runtime.LedgerBackedRuntime`):

* Canonical events are the record. Every node execution goes through the
  shared per-node envelope (NODE_STARTED / NODE_COMPLETED / NODE_FAILED /
  DUPLICATE_SUPPRESSED), so the ledger stream is byte-compatible with the
  deterministic runtime's and conformance is testable across both.
* Native checkpoints stay opaque. LangGraph is used purely as the node
  scheduler; no LangGraph checkpointer is registered, and crash recovery
  reconstructs completed-node outputs exclusively from the ledger before
  the graph is (re-)invoked. A framework checkpoint is not a scientific
  record (report 5.1).

Requires the optional dependency group: ``pip install agent-foundry[langgraph]``.
"""

from __future__ import annotations

from typing import Any, ClassVar, TypedDict

from foundry.contracts import MissionSpec, SystemBundle
from foundry.runtime import FIXTURE_NODES, LedgerBackedRuntime

try:
    from langgraph.graph import END, StateGraph

    _LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    _LANGGRAPH_AVAILABLE = False


class _FixtureState(TypedDict):
    """Graph state: the accumulated node outputs, keyed by node id."""

    outputs: dict[str, dict[str, Any]]


class LangGraphRuntime(LedgerBackedRuntime):
    """RuntimeAdapter that schedules the fixture workflow through LangGraph."""

    actor: ClassVar[str] = "langgraph-runtime"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if not _LANGGRAPH_AVAILABLE:
            raise ImportError(
                "LangGraphRuntime requires the 'langgraph' optional dependency; "
                'install it with: pip install "agent-foundry[langgraph]"'
            )
        super().__init__(*args, **kwargs)

    def _advance(self, run_id: str, spec: MissionSpec, bundle: SystemBundle) -> None:
        graph = self._build_graph(run_id, spec, bundle)
        initial: _FixtureState = {"outputs": self._completed_outputs(run_id)}
        final_state: _FixtureState = graph.invoke(initial)
        self._finalize(run_id, spec, bundle, final_state["outputs"])

    def _build_graph(self, run_id: str, spec: MissionSpec, bundle: SystemBundle):
        """Compile the linear plan -> execute -> verify StateGraph.

        Each graph node delegates to the shared ledger-enveloped executor,
        which makes it idempotent per run: already-completed nodes are
        suppressed as evidence and their recorded output is reused.
        """
        builder = StateGraph(_FixtureState)

        def make_node(node_id: str):
            def node_fn(state: _FixtureState) -> _FixtureState:
                outputs = dict(state["outputs"])
                self._execute_node(run_id, spec, bundle, node_id, outputs)
                return {"outputs": outputs}

            return node_fn

        for node_id in FIXTURE_NODES:
            builder.add_node(node_id, make_node(node_id))
        builder.set_entry_point(FIXTURE_NODES[0])
        for previous, following in zip(FIXTURE_NODES, FIXTURE_NODES[1:], strict=False):
            builder.add_edge(previous, following)
        builder.add_edge(FIXTURE_NODES[-1], END)
        # Deliberately no checkpointer: the ledger is the only durable state.
        return builder.compile()
