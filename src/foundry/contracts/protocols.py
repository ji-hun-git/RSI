"""Structural protocols shared across foundry packages.

These exist so packages can be built and tested against interfaces
rather than each other's concrete classes (the LEGO-connector rule,
report section 17). Concrete implementations must conform exactly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .events import Event


@runtime_checkable
class LedgerLike(Protocol):
    """Minimal append-only event ledger interface.

    ``append`` must be idempotent on ``event_id`` (returning the already
    recorded event) and must fill the ``integrity`` block. There is no
    update or delete: corrections are new events.
    """

    def append(self, event: Event) -> Event: ...

    def query(
        self,
        *,
        mission_id: str | None = None,
        run_id: str | None = None,
        experiment_id: str | None = None,
        event_type: str | None = None,
    ) -> list[Event]: ...


@runtime_checkable
class ArtifactStoreLike(Protocol):
    """Content-addressed immutable blob store: ``artifact://sha256:<hex>``."""

    def put(self, data: bytes, media_type: str = "application/octet-stream") -> str: ...

    def get(self, ref: str) -> bytes: ...

    def exists(self, ref: str) -> bool: ...


@runtime_checkable
class WorkerLike(Protocol):
    """A semantic or deterministic worker invoked by the runtime.

    ``config`` is the frozen SystemBundle ``config`` mapping; workers must
    be pure functions of (task_input, config, seed) -- no hidden state.
    """

    def invoke(self, task_input: dict[str, Any], config: dict[str, Any], seed: int) -> dict[str, Any]: ...
