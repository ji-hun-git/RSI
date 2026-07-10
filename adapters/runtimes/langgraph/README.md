# langgraph runtime adapter (not yet implemented)

Home of the LangGraph workflow-runtime adapter: it must implement the `foundry.runtime.adapter.RuntimeAdapter` protocol (`start`/`resume`/`cancel`/`status`), emit canonical events to the append-only ledger for every state transition, and keep native LangGraph checkpoints opaque (report 9.3, 19.5 weeks 3-4).
