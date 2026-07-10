"""Optional-dependency adapters (report sections 4, 16: adopt and wrap).

Each adapter wraps an external framework behind a foundry protocol and is
importable only when its optional dependency group is installed, e.g.::

    pip install -e ".[langgraph]"
    from foundry.adapters.langgraph_runtime import LangGraphRuntime

Adapters never define their own evidence or governance semantics: the
canonical event ledger remains the record, and native framework state
(checkpoints, sessions, graphs) stays opaque (report 9.3). The top-level
``adapters/`` directory in the repo holds the per-adapter documentation.
"""
