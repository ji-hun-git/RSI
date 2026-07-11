"""Run a mission under the module its bundle declares (report 17.2/17.3).

Shows the module layer end to end: a worker is admitted to the registry
only after passing conformance, a bundle pins that module by
``module_id@version``, and the mission runs the resolved, admitted module.
A bundle naming an unregistered module cannot run at all.

Run it with:  python examples/governed_modules.py
"""

from foundry.compiler import MissionCompiler
from foundry.contracts import MissionRequest, ModuleManifest, ModuleType, SystemBundle
from foundry.ledger import EventLedger
from foundry.modules import ModuleRegistry, ModuleResolvingRuntime, check_replacement
from foundry.runtime import FIXTURE_WORKFLOW_REF
from foundry.workers import FixtureWorker, naive_slugify, robust_slugify


class RobustWorker:
    tool_id = "n/a"

    def invoke(self, task_input, config, seed):
        return {"output": robust_slugify(task_input["text"]), "strategy": "robust"}


class NaiveWorker:
    def invoke(self, task_input, config, seed):
        return {"output": naive_slugify(task_input["text"]), "strategy": "naive"}


# 1. Admit a worker to the registry -- only if it passes conformance.
registry = ModuleRegistry()
evidence = registry.register(
    ModuleManifest(module_id="worker.fixture", module_type=ModuleType.AGENT, version="1.0.0"),
    FixtureWorker(),
)
print(f"[1] admitted worker.fixture@1.0.0; conformance checks: "
      f"{[c.name for c in evidence.checks]} all passed = {evidence.passed}")

# 2. A bundle declares which module fills its worker slot.
ledger = EventLedger(":memory:")
bundle = SystemBundle(
    workflow_ref=FIXTURE_WORKFLOW_REF,
    config={"strategy": "robust"},
    module_refs={"worker": "worker.fixture@1.0.0"},
)
print(f"[2] bundle {bundle.bundle_id[:19]}... declares module_refs={bundle.module_refs}")

# 3. The mission runs the resolved, admitted module.
spec = MissionCompiler(ledger).compile(
    MissionRequest(inputs={"task_id": "t1", "text": "Hello  World--Modules!", "family": "slugify"}),
    bundle,
)
run_id = ModuleResolvingRuntime(ledger, registry).start(spec, bundle)
final = ledger.query(run_id=run_id, event_type="mission.completed")[0].payload["final_output"]
print(f"[3] mission ran the declared module -> {final['output']!r}")

# 4. A bundle naming an unregistered module cannot run.
rogue = SystemBundle(
    workflow_ref=FIXTURE_WORKFLOW_REF,
    config={"strategy": "robust"},
    module_refs={"worker": "worker.unknown@9.9.9"},
)
rogue_spec = MissionCompiler(ledger).compile(
    MissionRequest(inputs={"task_id": "t2", "text": "x", "family": "slugify"}), rogue
)
try:
    ModuleResolvingRuntime(ledger, registry).start(rogue_spec, rogue)
except KeyError as exc:
    print(f"[4] a bundle naming an unadmitted module is refused: {exc}")

# 5. Hot-swap check: is replacing robust with naive a drop-in, or a change?
report = check_replacement(RobustWorker(), NaiveWorker())
print(f"[5] robust -> naive replacement compatible? {report.compatible}; "
      f"diverging cases: {[d.case for d in report.divergences]}")
