"""Dashboard projection and renderer (report sections 15.3, 15.4, 15.5).

The load-bearing cases encode report 15.4's line between useful and actively
harmful observability: uncertainty is always shown, failed and rejected
branches are never omitted, and no decision is rendered without its exact
diff and every gate result. Plus the rendering-safety invariants: all
dynamic content is HTML-escaped, secrets are redacted (15.5), the page is
fully self-contained, and a broken chain is stated, not hidden.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

from foundry.cli import run_demo, write_dashboard
from foundry.contracts import Event, EventTypes, SystemBundle
from foundry.dashboard import build_dashboard_model, render_html
from foundry.dashboard.render import esc
from foundry.ledger import EventLedger
from foundry.registry import BundleRegistry
from foundry.runtime import FIXTURE_WORKFLOW_REF

FIXED_TS = "2026-07-11T00:00:00+00:00"


# -- a real demo root (integration + projection) ------------------------------


@pytest.fixture(scope="module")
def demo_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dash-demo") / "root"
    run_demo(root, seed=13, out=lambda *_: None)
    return root


@pytest.fixture(scope="module")
def demo_html(demo_root: Path) -> str:
    from foundry.cli import ARTIFACTS_DIR, _artifact_blobs, open_stores

    stores = open_stores(demo_root, create=False)
    try:
        artifact_count = len(_artifact_blobs(stores.root / ARTIFACTS_DIR))
        model = build_dashboard_model(
            stores.ledger, stores.registry, root_name="demo", artifact_count=artifact_count
        )
    finally:
        stores.close()
    return render_html(model, generated_at=FIXED_TS)


def test_projection_covers_the_full_demo_story(demo_root: Path) -> None:
    from foundry.cli import open_stores

    stores = open_stores(demo_root, create=False)
    try:
        model = build_dashboard_model(stores.ledger, stores.registry, root_name="demo")
    finally:
        stores.close()
    assert len(model.missions) == 3
    assert all(m.status == "completed" for m in model.missions)
    assert len(model.proposals) == 1
    assert len(model.experiments) == 1
    # both the quarantine and the canary decision are present -- the loop's
    # rejection is not dropped in favour of the eventual success.
    actions = {d.action for d in model.decisions}
    assert "quarantine" in actions and "canary" in actions
    assert model.evidence.chain_ok
    # the two-bundle lineage with S1 active after re-activation.
    assert model.active_bundle_id is not None
    flat = _flatten(model.bundle_roots)
    assert len(flat) == 2


def _flatten(nodes):
    out = []
    for n in nodes:
        out.append(n)
        out.extend(_flatten(n.children))
    return out


# -- report 15.4: uncertainty is always shown ---------------------------------


def test_every_experiment_delta_carries_its_interval(demo_html: str) -> None:
    # the interval column is present and the confidence level is described in
    # the caption (not asserted as a hardcoded column label the payload cannot prove)
    assert "bootstrap CI" in demo_html
    assert "95% percentile bootstrap" in demo_html
    assert "[+" in demo_html or "[-" in demo_html  # interval brackets rendered


# -- report 15.4: failed / rejected branches are never omitted ----------------


def test_quarantined_candidate_is_shown_not_hidden(demo_html: str) -> None:
    assert "quarantine" in demo_html
    # the quarantined candidate appears as an incident and/or lifecycle label
    assert "Incident and audit" in demo_html


def test_rollback_appears_in_the_record(demo_html: str) -> None:
    # the demo rolls back to S0 then re-activates S1; the rollback must be visible
    assert "rolled back" in demo_html or "rollback" in demo_html


# -- report 15.4: exact diff + every gate, no trust-without-evidence ----------


def test_each_decision_shows_diff_and_all_ten_gates(demo_html: str) -> None:
    assert "Exact diff under review" in demo_html
    assert "Protected-gate results" in demo_html
    for gate in ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"]:
        assert gate in demo_html, f"gate {gate} not rendered"
    # the typed diff old->new for the strategy change is shown
    assert "/config/strategy" in demo_html
    assert "naive" in demo_html and "robust" in demo_html


# -- report 15.4: exact evidence identity in the header -----------------------


def test_header_states_the_evidence_snapshot(demo_html: str) -> None:
    assert "canonical events" in demo_html
    assert "chain verified" in demo_html
    assert "sha256:" in demo_html  # tip digest shown


# -- rendering safety: escaping (XSS) -----------------------------------------


def _model_from_events(events: list[Event], registry: BundleRegistry | None = None):
    ledger = EventLedger(":memory:")
    for event in events:
        ledger.append(event)
    reg = registry if registry is not None else BundleRegistry(_MEM_REGISTRY_DIR())
    return build_dashboard_model(ledger, reg, root_name="test")


def _MEM_REGISTRY_DIR() -> Path:
    import tempfile

    return Path(tempfile.mkdtemp(prefix="dash-reg-"))


def test_untrusted_content_is_html_escaped() -> None:
    payload_spec = {
        "inputs": {"text": "<script>alert('xss')</script>", "task_id": "x"},
    }
    events = [
        Event(
            event_type=EventTypes.MISSION_STARTED,
            mission_id="mis_evil",
            run_id="run_evil",
            system_bundle_id="sha256:" + "a" * 64,
            payload={"spec": payload_spec, "bundle": {}},
        ),
        Event(
            event_type=EventTypes.MISSION_COMPLETED,
            mission_id="mis_evil",
            run_id="run_evil",
            payload={"final_output": {"output": "<img src=x onerror=alert(1)>"}, "output_digest": "sha256:bb"},
        ),
    ]
    html = render_html(_model_from_events(events), generated_at=FIXED_TS)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x onerror" not in html
    assert "&lt;img" in html


def test_esc_helper_escapes_quotes_and_angles() -> None:
    assert esc('<a href="x">&') == "&lt;a href=&quot;x&quot;&gt;&amp;"


# -- review-driven fixes: robustness and honesty on adverse evidence ----------


def _proposal_event(proposal_id: str, changes: list[dict]) -> Event:
    return Event(
        event_type=EventTypes.PROPOSAL_SUBMITTED,
        system_bundle_id="sha256:" + "e" * 64,
        payload={
            "proposal": {
                "proposal_id": proposal_id,
                "hypothesis": "h",
                "current_behavior": "",
                "changes": changes,
                "proposer": {"id": "optimizer.x"},
            }
        },
    )


def _analyzed_event(experiment_id: str, arms_payload: dict) -> Event:
    return Event(
        event_type=EventTypes.EXPERIMENT_ANALYZED,
        experiment_id=experiment_id,
        payload={"seed": 1, "minimum_practical_effect": 0.05, "arms": arms_payload},
    )


def _designed_event(experiment_id: str, arms: list[dict]) -> Event:
    return Event(
        event_type=EventTypes.EXPERIMENT_DESIGNED,
        experiment_id=experiment_id,
        payload={"arms": arms},
    )


def test_all_candidate_arms_are_projected_not_just_the_first() -> None:
    arms = [
        {"arm_id": "control", "bundle_id": "sha256:" + "0" * 64, "is_control": True},
        {"arm_id": "candidate_a", "bundle_id": "sha256:" + "1" * 64, "is_control": False},
        {"arm_id": "candidate_b", "bundle_id": "sha256:" + "2" * 64, "is_control": False},
    ]
    row = {"n_pairs": 4, "mean_delta": 0.5, "ci": [0.3, 0.7], "wins": 2, "losses": 0, "ties": 2}
    arms_payload = {
        "candidate_a": {"development": row},
        "candidate_b": {"development": {**row, "mean_delta": -0.25, "losses": 2, "wins": 0}},
    }
    model = _model_from_events([_designed_event("exp1", arms), _analyzed_event("exp1", arms_payload)])
    exp = model.experiments[0]
    arm_ids = {a.arm_id for a in exp.analyses}
    assert arm_ids == {"candidate_a", "candidate_b"}  # the losing arm is not dropped
    html = render_html(model, generated_at=FIXED_TS)
    assert "candidate_a" in html and "candidate_b" in html


def test_malformed_ci_does_not_crash_and_reads_as_unavailable() -> None:
    arms = [
        {"arm_id": "control", "bundle_id": "sha256:" + "0" * 64, "is_control": True},
        {"arm_id": "candidate_a", "bundle_id": "sha256:" + "1" * 64, "is_control": False},
    ]
    # a tampered/partial ci: one element, then a missing ci entirely
    arms_payload = {
        "candidate_a": {
            "development": {"n_pairs": 4, "mean_delta": 0.5, "ci": [0.3], "wins": 2, "losses": 0, "ties": 2},
            "retention": {"n_pairs": 4, "mean_delta": 0.05, "wins": 0, "losses": 0, "ties": 4},
        }
    }
    model = _model_from_events([_designed_event("exp1", arms), _analyzed_event("exp1", arms_payload)])
    rows = model.experiments[0].analyses
    assert all(not r.ci_available for r in rows)  # never fabricated as [0,0]
    html = render_html(model, generated_at=FIXED_TS)
    assert "unavailable" in html
    # a nonzero mean with a missing CI must NOT render a zero-width interval
    assert "[+0.000, +0.000]" not in html


def test_expanded_redactor_covers_passwords_keys_cookies() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc123\n-----END RSA PRIVATE KEY-----"
    events = [
        Event(
            event_type=EventTypes.MISSION_STARTED,
            mission_id="m",
            run_id="r",
            system_bundle_id="sha256:" + "a" * 64,
            payload={
                "spec": {
                    "inputs": {
                        "text": f"password: hunter2secret and {pem} and Set-Cookie: sess=abc123def",
                        "task_id": "t",
                    }
                },
                "bundle": {},
            },
        ),
        Event(
            event_type=EventTypes.MISSION_COMPLETED,
            mission_id="m",
            run_id="r",
            payload={"final_output": {"output": "ok"}, "output_digest": "sha256:bb"},
        ),
    ]
    html = render_html(_model_from_events(events), generated_at=FIXED_TS)
    assert "hunter2secret" not in html
    assert "PRIVATE KEY" not in html
    assert "sess=abc123def" not in html
    assert "[REDACTED]" in html


def test_reject_and_quarantine_are_distinct_outcomes() -> None:
    def decision_event(action: str, bundle_hex: str, failed_gate: str | None) -> Event:
        gates = [{"gate": g, "passed": g != failed_gate, "reason": ""} for g in
                 ["G0","G1","G2","G3","G4","G5","G6","G7","G8","G9"]]
        return Event(
            event_type=EventTypes.GOVERNANCE_DECISION,
            system_bundle_id="sha256:" + bundle_hex * 64,
            payload={"decision": {
                "decision_id": f"dec_{action}", "action": action,
                "candidate_bundle_id": "sha256:" + bundle_hex * 64,
                "parent_bundle_id": "sha256:" + "0" * 64,
                "gate_results": gates, "reason": f"{action} reason", "signature": "x",
            }},
        )
    model = _model_from_events([
        decision_event("quarantine", "1", "G8"),
        decision_event("reject", "2", "G3"),
    ])
    kinds = {i.kind for i in model.incidents}
    assert "quarantine" in kinds and "rejected" in kinds  # not folded together
    html = render_html(model, generated_at=FIXED_TS)
    assert "failed G3" in html  # the reject names the hard gate failure


def test_mission_failed_event_marks_the_mission_failed() -> None:
    events = [
        Event(event_type=EventTypes.MISSION_STARTED, mission_id="m", run_id="r",
              system_bundle_id="sha256:" + "a" * 64, payload={"spec": {"inputs": {"text": "x"}}, "bundle": {}}),
        Event(event_type=EventTypes.MISSION_FAILED, mission_id="m", run_id="r",
              payload={"error": "boom"}),
    ]
    model = _model_from_events(events)
    assert model.missions[0].status == "failed"


def test_decision_diff_comes_from_the_registry_even_without_a_proposal(tmp_path: Path) -> None:
    # register a real parent/candidate pair; a decision with NO linked proposal
    # must still render the exact diff (report 15.4).
    from foundry.registry import BundleRegistry as Reg

    registry = Reg(tmp_path / "bundles")
    parent = SystemBundle(workflow_ref=FIXTURE_WORKFLOW_REF, config={"strategy": "naive"})
    registry.register(parent)
    child = registry.fork(parent, [_fc("/config/strategy", "naive", "robust")],
                          allowed_path_prefixes=["/config"])
    registry.register(child)
    ledger = EventLedger(":memory:")
    ledger.append(Event(
        event_type=EventTypes.GOVERNANCE_DECISION,
        system_bundle_id=child.bundle_id,
        payload={"decision": {
            "decision_id": "dec_x", "action": "canary", "proposal_id": None,
            "candidate_bundle_id": child.bundle_id, "parent_bundle_id": parent.bundle_id,
            "gate_results": [{"gate": g, "passed": True, "reason": ""} for g in
                             ["G0","G1","G2","G3","G4","G5","G6","G7","G8","G9"]],
            "reason": "ok", "signature": "x",
        }},
    ))
    model = build_dashboard_model(ledger, registry, root_name="t")
    d = model.decisions[0]
    assert d.diff_source == "registry"
    assert any(c.field_path == "/config/strategy" for c in d.changes)
    html = render_html(model, generated_at=FIXED_TS)
    assert "computed from the registry" in html


def _fc(path, old, new):
    from foundry.contracts import FieldChange
    return FieldChange(field_path=path, old_value=old, new_value=new)


# -- rendering safety: secret redaction (report 15.5) -------------------------


def test_secret_tokens_are_redacted_but_digests_are_not() -> None:
    # A secret pasted into a mission input is always rendered (workflow traces),
    # so it is the realistic redaction path.
    secret = "sk-proj-" + "A1b2C3d4E5f6G7h8J9k0" * 2
    digest = "sha256:" + "c" * 64
    events = [
        Event(
            event_type=EventTypes.MISSION_STARTED,
            mission_id="mis_leak",
            run_id="run_leak",
            system_bundle_id=digest,
            payload={
                "spec": {
                    "inputs": {
                        "text": f"leak {secret} and Bearer abcdef0123456789 near {digest}",
                        "task_id": "t",
                    }
                },
                "bundle": {},
            },
        ),
        Event(
            event_type=EventTypes.MISSION_COMPLETED,
            mission_id="mis_leak",
            run_id="run_leak",
            payload={"final_output": {"output": "ok"}, "output_digest": digest},
        ),
    ]
    html = render_html(_model_from_events(events), generated_at=FIXED_TS)
    assert secret not in html
    assert "[REDACTED]" in html
    assert "Bearer abcdef0123456789" not in html
    # a legitimate evidence digest must survive intact
    assert "c" * 16 in html  # short form of the sha256 digest is preserved


def test_pending_proposal_is_rendered_when_no_decision_exists() -> None:
    events = [
        Event(
            event_type=EventTypes.PROPOSAL_SUBMITTED,
            system_bundle_id="sha256:" + "d" * 64,
            payload={
                "proposal": {
                    "proposal_id": "prop_pending",
                    "hypothesis": "an in-flight hypothesis",
                    "current_behavior": "",
                    "changes": [
                        {"field_path": "/config/strategy", "old_value": "naive", "new_value": "robust"}
                    ],
                    "proposer": {"id": "optimizer.x"},
                }
            },
        ),
    ]
    html = render_html(_model_from_events(events), generated_at=FIXED_TS)
    assert "Pending proposals" in html
    assert "prop_pending" in html
    assert "an in-flight hypothesis" in html


# -- rendering safety: self-contained -----------------------------------------


def test_page_is_fully_self_contained(demo_html: str) -> None:
    assert "http://" not in demo_html and "https://" not in demo_html
    assert "<script" not in demo_html.lower()
    assert demo_html.startswith("<!doctype html>")
    assert demo_html.rstrip().endswith("</html>")


def test_rendered_html_is_well_formed(demo_html: str) -> None:
    _WellFormed().validate(demo_html)


# -- determinism --------------------------------------------------------------


def test_render_is_deterministic_for_a_fixed_model(demo_root: Path) -> None:
    from foundry.cli import open_stores

    def model():
        stores = open_stores(demo_root, create=False)
        try:
            return build_dashboard_model(stores.ledger, stores.registry, root_name="demo")
        finally:
            stores.close()

    a = render_html(model(), generated_at=FIXED_TS)
    b = render_html(model(), generated_at=FIXED_TS)
    assert a == b


# -- honesty about a broken chain ---------------------------------------------


def test_broken_chain_is_flagged_in_the_header(tmp_path: Path) -> None:
    import sqlite3

    from foundry.cli import LEDGER_FILE

    run_demo(tmp_path / "root", seed=3, out=lambda *_: None)
    # tamper one stored event row directly, breaking the hash chain
    db = tmp_path / "root" / LEDGER_FILE
    con = sqlite3.connect(db)
    con.execute(
        "UPDATE events SET body = replace(body, 'deterministic-runtime', 'tampered-runtime') "
        "WHERE sequence = 5"
    )
    con.commit()
    con.close()

    out_path = tmp_path / "dash.html"
    write_dashboard(tmp_path / "root", out_path, printer=lambda *_: None)
    html = out_path.read_text(encoding="utf-8")
    assert "CHAIN BROKEN" in html
    assert "chain verified" not in html


# -- empty root ---------------------------------------------------------------


def test_empty_root_renders_without_crashing(tmp_path: Path) -> None:
    ledger = EventLedger(":memory:")
    registry = BundleRegistry(tmp_path / "bundles")
    model = build_dashboard_model(ledger, registry, root_name="empty")
    html = render_html(model, generated_at=FIXED_TS)
    _WellFormed().validate(html)
    assert "no bundles registered" in html
    assert "no missions recorded" in html


# -- CLI ----------------------------------------------------------------------


def test_cli_writes_dashboard_file(demo_root: Path, tmp_path: Path) -> None:
    out_path = tmp_path / "board.html"
    returned = write_dashboard(demo_root, out_path, printer=lambda *_: None)
    assert returned == out_path
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8").startswith("<!doctype html>")


# -- helpers ------------------------------------------------------------------


class _WellFormed(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f"auto-closed <{self.stack[-1]}>")
                self.stack.pop()
            if self.stack:
                self.stack.pop()
        else:
            self.errors.append(f"stray </{tag}>")

    def validate(self, html: str) -> None:
        self.feed(html)
        assert not self.stack, f"unclosed tags: {self.stack}"
        assert not self.errors, f"malformed: {self.errors}"
