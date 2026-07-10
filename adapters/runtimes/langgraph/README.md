# langgraph runtime adapter (implemented)

Implementation: `src/foundry/adapters/langgraph_runtime.py` (`foundry.adapters.langgraph_runtime.LangGraphRuntime`), installed with the optional dependency group:

```bash
pip install -e ".[langgraph]"
```

The adapter implements the `foundry.runtime.adapter.RuntimeAdapter` protocol (`start`/`resume`/`cancel`/`status`) by inheriting the shared `foundry.runtime.LedgerBackedRuntime` control plane and using LangGraph's `StateGraph` purely as the node scheduler. Consequences, per report 9.3:

- Canonical events remain the record: every node execution goes through the shared ledger envelope, so the event stream is byte-identical to `DeterministicRuntime`'s for the same spec, bundle and worker.
- Native checkpoints stay opaque: no LangGraph checkpointer is registered; crash recovery reconstructs completed-node outputs exclusively from the ledger before the graph is re-invoked.

Conformance is pinned by `tests/test_runtime_conformance.py`, which runs the full crash/resume/cancel/duplicate-suppression suite against every installed runtime and asserts equivalence with the deterministic reference.
