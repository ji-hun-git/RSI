"""Tool-provider conformance (report 17.2/17.3 at the tool boundary).

A tool is admitted through ``register_conformant`` only after it passes the
tool-provider suite: a valid declared side-effect class, the contract dict
output on valid input, and determinism -- required only of a tool that
declares itself side-effect-free. Seeded incompatibilities are refused.
"""

from __future__ import annotations

from typing import Any

import pytest

from foundry.ledger import EventLedger
from foundry.tools import (
    AppendLogTool,
    EchoTool,
    FetchTool,
    ToolConformanceError,
    ToolConformanceHarness,
    ToolGateway,
    tool_manifest,
)


@pytest.fixture()
def gateway() -> ToolGateway:
    return ToolGateway(EventLedger(":memory:"))


# -- well-behaved tools are admitted ------------------------------------------


def test_pure_tool_is_admitted(gateway: ToolGateway) -> None:
    evidence = gateway.register_conformant(
        tool_manifest("echo"), EchoTool(), example_args=[{"a": 1}, {}]
    )
    assert evidence.passed
    assert {c.name for c in evidence.checks} == {"side_effect_class", "output_shape", "determinism"}
    assert "echo" in gateway.list_tools()
    assert gateway.tool_evidence("echo").passed


def test_side_effecting_tool_is_admitted_without_determinism(gateway: ToolGateway) -> None:
    # AppendLogTool changes state on every call; it is exempt from determinism
    evidence = gateway.register_conformant(
        tool_manifest("log.append"), AppendLogTool(), example_args=[{"line": "x"}]
    )
    assert evidence.passed
    det = next(c for c in evidence.checks if c.name == "determinism")
    assert det.passed and "exempt" in det.detail


def test_external_tool_is_admitted(gateway: ToolGateway) -> None:
    evidence = gateway.register_conformant(
        tool_manifest("net.fetch"), FetchTool(), example_args=[{"url": "https://example.com/x"}]
    )
    assert evidence.passed


# -- seeded incompatibilities are refused -------------------------------------


def test_pure_declared_but_nondeterministic_tool_is_refused(gateway: ToolGateway) -> None:
    class LyingTool:
        tool_id = "lying"
        side_effect_class = "none"  # claims purity...

        def __init__(self) -> None:
            self._n = 0

        def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
            self._n += 1  # ...but is stateful
            return {"n": self._n}

    with pytest.raises(ToolConformanceError, match="determinism"):
        gateway.register_conformant(tool_manifest("lying"), LyingTool(), example_args=[{}])
    assert "lying" not in gateway.list_tools()


def test_invalid_side_effect_class_is_refused(gateway: ToolGateway) -> None:
    class BadClassTool:
        tool_id = "badclass"
        side_effect_class = "teleport"  # not a known class

        def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
            return {"ok": True}

    with pytest.raises(ToolConformanceError, match="side_effect_class"):
        gateway.register_conformant(tool_manifest("badclass"), BadClassTool(), example_args=[{}])


def test_wrong_shape_tool_is_refused(gateway: ToolGateway) -> None:
    class BadShapeTool:
        tool_id = "badshape"
        side_effect_class = "none"

        def invoke(self, args: dict[str, Any]) -> Any:
            return "not a dict"

    with pytest.raises(ToolConformanceError, match="output_shape"):
        gateway.register_conformant(tool_manifest("badshape"), BadShapeTool(), example_args=[{}])


def test_crashing_tool_is_refused(gateway: ToolGateway) -> None:
    class CrashTool:
        tool_id = "crash"
        side_effect_class = "none"

        def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

    with pytest.raises(ToolConformanceError, match="output_shape"):
        gateway.register_conformant(tool_manifest("crash"), CrashTool(), example_args=[{}])


# -- a refused tool is not callable -------------------------------------------


def test_refused_tool_cannot_be_called(gateway: ToolGateway) -> None:
    class CrashTool:
        tool_id = "crash"
        side_effect_class = "none"

        def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("boom")

    with pytest.raises(ToolConformanceError):
        gateway.register_conformant(tool_manifest("crash"), CrashTool(), example_args=[{}])
    assert gateway.tool_evidence("crash") is None
    assert "crash" not in gateway.list_tools()


# -- harness used directly ----------------------------------------------------


def test_harness_reports_each_check() -> None:
    evidence = ToolConformanceHarness().evidence(EchoTool(), [{"a": 1}])
    assert evidence.tool_id == "echo" and evidence.suite == "tool-provider/1"
    assert evidence.passed
