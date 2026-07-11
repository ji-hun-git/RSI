"""Deterministic reference tool providers (report 16: native and MCP tools
behind the same internal interface).

These are model-free, side-effect-honest tools used to exercise the gateway.
A real MCP or native tool implements the same ``ToolProvider`` shape and is
admitted the same way; the gateway does not care which it is.
"""

from __future__ import annotations

from typing import Any

from foundry.contracts import ModuleManifest, ModuleType


class EchoTool:
    """A pure, side-effect-free tool: returns its arguments."""

    tool_id = "echo"
    side_effect_class = "none"

    def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"echo": dict(args)}


class FetchTool:
    """An external-side-effect tool stub: it names a resource the gateway must
    egress-check, and returns a deterministic canned body (no real network)."""

    tool_id = "net.fetch"
    side_effect_class = "external"

    def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url", ""))
        return {"fetched": url, "status": 200, "body": f"canned:{url}"}


class AppendLogTool:
    """A write-side-effect tool with observable state: appends to a log.

    Used to show idempotent replay -- a repeated call carrying the same
    idempotency key must not append twice.
    """

    tool_id = "log.append"
    side_effect_class = "write"

    def __init__(self) -> None:
        self.log: list[str] = []

    def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
        self.log.append(str(args.get("line", "")))
        return {"appended": len(self.log)}


class OversizeTool:
    """Returns an output larger than any reasonable cap (excessive-output test)."""

    tool_id = "oversize"
    side_effect_class = "none"

    def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"blob": "x" * 200_000}


def tool_manifest(tool_id: str, version: str = "1.0.0", **extra: Any) -> ModuleManifest:
    """A minimal manifest for a tool provider (module_type=tool)."""
    return ModuleManifest(
        module_id=tool_id, module_type=ModuleType.TOOL, version=version, **extra
    )


class SlugifyConfirmWorker:
    """A demo ContextualWorker: slugify, then confirm via a governed tool call.

    If the echo tool is authorized, the confirmed slug comes back through the
    gateway (a receipted call); if the call is denied, the worker degrades to
    the local slug -- respecting governance rather than reaching around it.
    """

    def invoke(
        self, task_input: dict[str, Any], config: dict[str, Any], seed: int, tools: Any
    ) -> dict[str, Any]:
        from foundry.workers import robust_slugify

        from .gateway import ToolDenied

        slug = robust_slugify(task_input["text"])
        try:
            result = tools.call("echo", {"slug": slug}, action="tool.echo")
            confirmed = result.output["echo"]["slug"]
            confirmed_via = "tool"
        except ToolDenied:
            confirmed = slug
            confirmed_via = "local"
        return {"output": confirmed, "confirmed_via": confirmed_via}
