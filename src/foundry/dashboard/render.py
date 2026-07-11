"""Render a :class:`DashboardModel` to a single self-contained HTML page.

This module is pure presentation: it introduces no fact the model does not
carry, and it is bound by report 15.4's distinction between useful and
actively harmful observability. Concretely, the renderer:

* shows uncertainty everywhere -- every experiment delta is printed with its
  confidence interval, never as a bare point estimate;
* never omits a failed branch -- quarantined candidates, rolled-back
  deployments, failed gates and policy denials each get an explicit, visually
  distinct place (report 15.4 "actively harmful: omit failed branches");
* never asks for trust without the evidence -- each governance decision
  renders the exact typed diff and every G0-G9 gate result with its reason
  (report 15.4 "encourage approval without showing the exact diff and
  protected-gate results");
* states the evidence snapshot -- the header carries the event count, ledger
  tip digest and chain-verification status, so the page is honest about
  exactly which evidence it reflects;
* escapes every dynamic string (ledger content is untrusted for rendering
  purposes) and passes free text through a conservative secret redactor as
  defense-in-depth (report 15.5: redact tokens, keys, passwords), while
  leaving ``sha256:`` evidence digests intact.

The output is a fully offline document: inline CSS only, no scripts, no
external fetches, collapsibles via native ``<details>``. It renders in the
viewer's light or dark theme.
"""

from __future__ import annotations

import html
import re
from typing import Any

from .model import (
    BundleNode,
    DashboardModel,
    DecisionView,
    ExperimentView,
    MissionView,
    ProposalView,
)

# Conservative, high-confidence secret patterns (report 15.5: redact access
# tokens, API keys, passwords, private keys, session cookies). sha256: digests
# are deliberately NOT matched -- they are evidence identity, not secrets.
_SECRET_PATTERNS = (
    # API-token prefixes
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z._\-]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    # PEM / OpenSSH private-key blocks
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    # password / secret / api_key / token assignments (value only redacted)
    re.compile(
        r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)"
        r"(\s*[:=]\s*)([^\s,;\"']{6,})"
    ),
    # session cookies
    re.compile(r"(?i)(set-cookie|session[_-]?id|sessionid)(\s*[:=]\s*)([^\s;,]{6,})"),
)
_REDACTION = "[REDACTED]"

_LIFECYCLE_LABEL = {
    "active": "active",
    "rolled_back": "rolled back",
    "rejected": "rejected",
    "quarantined": "quarantined",
    "registered": "registered",
}


def _redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTION, text)
    return text


def esc(value: Any) -> str:
    """HTML-escape (both text and attribute contexts) after secret redaction."""
    return html.escape(_redact(str(value)), quote=True)


def _short(digest: str | None, keep: int = 16) -> str:
    if not digest:
        return "-"
    body = digest.removeprefix("sha256:")
    if len(body) <= keep:
        return esc(digest)
    prefix = "sha256:" if digest.startswith("sha256:") else ""
    return f'<span title="{esc(digest)}">{esc(prefix + body[:keep])}&hellip;</span>'


def _delta(value: float) -> str:
    return f"{value:+.3f}"


def _ci(analysis) -> str:
    """Render an interval, or an explicit "unavailable" -- never a fabricated
    zero-width interval that would read as certainty (report 15.4)."""
    if not analysis.ci_available:
        return '<span class="muted">unavailable</span>'
    return f"[{_delta(analysis.ci_low)}, {_delta(analysis.ci_high)}]"


def render_html(model: DashboardModel, *, generated_at: str | None = None) -> str:
    """Render *model* to a complete, self-contained HTML document string."""
    sections = [
        _header(model, generated_at),
        _command_center(model),
        _evolution_tree(model),
        _governance_chamber(model),
        _experiment_lab(model),
        _mission_traces(model),
        _resource_economy(model),
        _incident_audit(model),
        _footer(model),
    ]
    body = "\n".join(sections)
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Foundry dashboard: {esc(model.root_name)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        f'<main class="wrap">\n{body}\n</main>\n</body>\n</html>\n'
    )


# -- header / command center --------------------------------------------------


def _header(model: DashboardModel, generated_at: str | None) -> str:
    ev = model.evidence
    chain = (
        '<span class="ok">chain verified</span>'
        if ev.chain_ok
        else '<span class="bad">CHAIN BROKEN</span>'
    )
    gen = f'<div class="muted">rendered {esc(generated_at)}</div>' if generated_at else ""
    return (
        '<header class="head">\n'
        "  <div>\n"
        f"    <h1>Modular RSI Agent Foundry</h1>\n"
        f'    <div class="muted">governed system optimization &middot; dashboard for '
        f"<code>{esc(model.root_name)}</code></div>\n"
        "  </div>\n"
        '  <div class="evidence">\n'
        f"    <div>{ev.event_count} canonical events &middot; {chain}</div>\n"
        f'    <div class="muted">tip {_short(ev.tip_digest)}</div>\n'
        f"    {gen}\n"
        "  </div>\n"
        "</header>\n"
        '<p class="claim">This view is a read-only projection of the append-only event '
        "ledger. It is infrastructure for governed system optimization, not evidence of "
        "autonomous self-improvement (report section 21.1).</p>"
    )


def _command_center(model: DashboardModel) -> str:
    r = model.resources
    active = _short(model.active_bundle_id) if model.active_bundle_id else "<em>none</em>"
    tiles = [
        ("active bundle", active),
        ("missions", str(r.missions)),
        ("experiments", str(r.experiments)),
        ("governance decisions", str(r.decisions)),
        ("bundles", str(r.bundles)),
        ("incidents", str(len(model.incidents))),
    ]
    cells = "\n".join(
        f'<div class="tile"><div class="tile-v">{value}</div>'
        f'<div class="tile-k">{esc(label)}</div></div>'
        for label, value in tiles
    )
    return _card("Command center", "what is running and what needs attention", f'<div class="tiles">{cells}</div>')


# -- evolution tree -----------------------------------------------------------


def _evolution_tree(model: DashboardModel) -> str:
    if not model.bundle_roots:
        inner = '<p class="muted">no bundles registered</p>'
    else:
        inner = "\n".join(_bundle_node_html(node) for node in model.bundle_roots)
    legend = (
        '<p class="muted">Every registered configuration is shown, including '
        "quarantined candidates and rolled-back deployments (report 15.4: failed "
        "branches are never omitted).</p>"
    )
    return _card(
        "Evolution tree",
        "how the system configuration has changed across generations",
        legend + f'<ul class="tree">{inner}</ul>',
    )


def _bundle_node_html(node: BundleNode) -> str:
    label = _LIFECYCLE_LABEL.get(node.lifecycle, node.lifecycle)
    config = ", ".join(f"{esc(k)}={esc(v)}" for k, v in sorted(node.config.items()))
    active_mark = ' <span class="pill active">active</span>' if node.is_active else ""
    children = ""
    if node.children:
        children = "<ul>" + "".join(_bundle_node_html(c) for c in node.children) + "</ul>"
    return (
        "<li>"
        f'<span class="pill lc-{esc(node.lifecycle)}">{esc(label)}</span> '
        f"{_short(node.bundle_id)} "
        f'<span class="muted">v{esc(node.semantic_version)} '
        f"[{esc(node.registry_status)}]</span>{active_mark}"
        f'<div class="cfg muted">{config}</div>'
        f"{children}"
        "</li>"
    )


# -- governance chamber -------------------------------------------------------


def _governance_chamber(model: DashboardModel) -> str:
    proposals_by_id = {p.proposal_id: p for p in model.proposals}
    decided_proposals = {d.proposal_id for d in model.decisions}
    parts: list[str] = []

    # Proposals submitted but not yet decided are shown, not dropped: an
    # in-flight change is exactly what "needs attention" (report 15.3).
    pending = [p for p in model.proposals if p.proposal_id not in decided_proposals]
    if pending:
        parts.append("<h4>Pending proposals (submitted, not yet decided)</h4>")
        parts.extend(_pending_proposal_html(p) for p in pending)

    if model.decisions:
        parts.append("<h4>Decisions</h4>")
        parts.extend(
            _decision_html(d, proposals_by_id.get(d.proposal_id)) for d in model.decisions
        )
    elif not pending:
        parts.append('<p class="muted">no proposals or governance decisions recorded</p>')

    return _card(
        "Governance chamber",
        "why a change may (or may not) affect production",
        "\n".join(parts),
    )


def _pending_proposal_html(proposal: ProposalView) -> str:
    return (
        '<details class="decision">\n'
        f'<summary><span class="pill warn">pending</span> proposal '
        f"{esc(proposal.proposal_id)} by {esc(proposal.proposer)}</summary>\n"
        f'<div class="detail-body">\n'
        f'<p><span class="k">hypothesis</span> {esc(proposal.hypothesis)}</p>\n'
        f"<h4>Proposed diff</h4>{_diff_html(proposal.changes)}\n"
        f"{_provenance_html(proposal, None)}\n"
        f'<p class="muted">rollback: {esc(proposal.rollback_condition)}</p>\n'
        "</div>\n</details>"
    )


def _decision_html(decision: DecisionView, proposal: ProposalView | None) -> str:
    action_class = {
        "promote": "ok",
        "canary": "ok",
        "quarantine": "warn",
        "reject": "bad",
        "retest": "warn",
    }.get(decision.action, "muted")
    signed = (
        '<span class="ok">gate-signed</span>'
        if decision.signed
        else '<span class="bad">UNSIGNED</span>'
    )
    source_note = {
        "registry": "computed from the registry (parent vs candidate)",
        "proposal": "from the linked proposal",
        "unavailable": "unavailable: neither bundle resolves in the registry",
    }.get(decision.diff_source, decision.diff_source)
    diff_html = _diff_html(decision.changes) + (
        f'<p class="muted">diff source: {esc(source_note)}</p>'
    )
    gates_html = _gates_html(decision)
    approvals = (
        ", ".join(esc(a) for a in decision.approvals) if decision.approvals else "<em>none</em>"
    )
    hypothesis = (
        f'<p><span class="k">hypothesis</span> {esc(proposal.hypothesis)}</p>'
        if proposal
        else ""
    )
    thresholds = (
        f'<p class="muted">minimum practical effect '
        f"{proposal.minimum_practical_effect:+.3f} &middot; retention floor "
        f"{proposal.retention_floor:+.3f} &middot; rollback: {esc(proposal.rollback_condition)}</p>"
        if proposal
        else ""
    )
    provenance = _provenance_html(proposal, decision.experiment_id)
    return (
        '<details class="decision" open>\n'
        f'<summary><span class="pill {action_class}">{esc(decision.action)}</span> '
        f"decision {esc(decision.decision_id)} &middot; tier {esc(decision.required_tier)} "
        f"&middot; {signed}</summary>\n"
        f'<div class="detail-body">\n'
        f'<p class="muted">candidate {_short(decision.candidate_bundle_id)} '
        f"from parent {_short(decision.parent_bundle_id)} &middot; "
        f"rollback target {_short(decision.rollback_target)}</p>\n"
        f"{hypothesis}\n{thresholds}\n"
        f"<h4>Exact diff under review</h4>{diff_html}\n"
        f"<h4>Protected-gate results (G0-G9)</h4>{gates_html}\n"
        f'<p><span class="k">approvals accepted by G8</span> {approvals}</p>\n'
        f"{provenance}\n"
        f'<p class="muted">reason: {esc(decision.reason)}</p>\n'
        "</div>\n</details>"
    )


def _diff_html(changes) -> str:
    if not changes:
        return '<p class="muted">diff unavailable</p>'
    rows = "\n".join(
        f"<tr><td><code>{esc(c.field_path)}</code></td>"
        f'<td class="old">{esc(c.old_value)}</td>'
        f'<td class="new">{esc(c.new_value)}</td></tr>'
        for c in changes
    )
    return (
        '<table class="diff"><thead><tr><th>path</th><th>from</th><th>to</th></tr>'
        f"</thead><tbody>{rows}</tbody></table>"
    )


def _provenance_html(proposal: ProposalView | None, experiment_id: str | None) -> str:
    """Evidence provenance links (report 15.4 "useful: evidence provenance;
    trace-to-artifact links")."""
    rows: list[str] = []
    if experiment_id:
        rows.append(f'<span class="k">experiment</span> <code>{esc(experiment_id)}</code>')
    if proposal is not None:
        if proposal.experiment_plan_ref:
            rows.append(
                f'<span class="k">plan</span> {_short(proposal.experiment_plan_ref)}'
            )
        if proposal.retention_set_ref:
            rows.append(
                f'<span class="k">retention set</span> <code>{esc(proposal.retention_set_ref)}</code>'
            )
        if proposal.evidence_refs:
            refs = " ".join(_short(r) for r in proposal.evidence_refs)
            rows.append(f'<span class="k">evidence</span> {refs}')
    if not rows:
        return ""
    return "<h4>Evidence provenance</h4>" + "".join(f"<p>{r}</p>" for r in rows)


def _gates_html(decision: DecisionView) -> str:
    if not decision.gate_results:
        return '<p class="bad">no gate results recorded (a decision must carry all of G0-G9)</p>'
    rows = "\n".join(
        f'<tr class="{"gpass" if g.passed else "gfail"}">'
        f"<td>{esc(g.gate)}</td>"
        f'<td>{"pass" if g.passed else "FAIL"}</td>'
        f"<td>{esc(g.reason)}</td></tr>"
        for g in decision.gate_results
    )
    return (
        '<table class="gates"><thead><tr><th>gate</th><th>result</th><th>reason</th></tr>'
        f"</thead><tbody>{rows}</tbody></table>"
    )


# -- experiment lab -----------------------------------------------------------


def _experiment_lab(model: DashboardModel) -> str:
    if not model.experiments:
        body = '<p class="muted">no experiments recorded</p>'
    else:
        body = "\n".join(_experiment_html(e) for e in model.experiments)
    caption = (
        '<p class="muted">Each delta is a paired comparison of candidate minus control '
        "under identical tasks, seeds and budgets (a matched controlled contrast), reported "
        "with its bootstrap interval (Stage-1 uses a 95% percentile bootstrap). The interval "
        "is the evidence of uncertainty; the gate, not this table, decides promotion. Every "
        "candidate arm is shown.</p>"
    )
    return _card("Experiment lab", "does the candidate beat the control, and how certain is that", caption + body)


def _experiment_html(experiment: ExperimentView) -> str:
    arms = ", ".join(
        f'{esc(a.arm_id)}{" (control)" if a.is_control else ""} &rarr; {_short(a.bundle_id)}'
        for a in experiment.arms
    )
    seed = esc(experiment.seed) if experiment.seed is not None else "-"
    mpe = (
        f"{experiment.minimum_practical_effect:+.3f}"
        if experiment.minimum_practical_effect is not None
        else "-"
    )
    leak_class = "ok" if experiment.leakage_hits == 0 else "bad"
    if experiment.analyses:
        rows = "\n".join(
            f"<tr><td>{esc(a.arm_id)}</td><td>{esc(a.role)}</td><td>{a.n_pairs}</td>"
            f"<td>{_delta(a.mean_delta)}</td>"
            f"<td>{_ci(a)}</td>"
            f"<td>{a.wins}/{a.losses}/{a.ties}</td></tr>"
            for a in experiment.analyses
        )
        table = (
            '<table class="analyses"><thead><tr><th>arm</th><th>role</th><th>n</th>'
            "<th>mean delta</th><th>bootstrap CI</th><th>w/l/t</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        table = '<p class="muted">no analysis recorded for this experiment</p>'
    return (
        '<details class="experiment" open>\n'
        f"<summary>experiment {esc(experiment.experiment_id)} &middot; "
        f"seed {seed} &middot; min effect {mpe} &middot; "
        f'<span class="{leak_class}">{experiment.leakage_hits} leakage hit(s)</span>'
        "</summary>\n"
        f'<div class="detail-body">\n'
        f'<p class="muted">arms: {arms}</p>\n{table}\n</div>\n</details>'
    )


# -- mission traces -----------------------------------------------------------


def _mission_traces(model: DashboardModel) -> str:
    if not model.missions:
        body = '<p class="muted">no missions recorded</p>'
    else:
        body = "\n".join(_mission_html(m) for m in model.missions)
    return _card("Workflow traces", "where each mission went and what it produced", body)


def _mission_html(mission: MissionView) -> str:
    status_class = {"completed": "ok", "failed": "bad", "cancelled": "warn"}.get(
        mission.status, "muted"
    )
    steps = "".join(
        f'<li class="step step-{esc(s.status)}">{esc(s.node_id)} '
        f'<span class="muted">{esc(s.status)}</span>'
        f"{(' &middot; ' + _short(s.output_digest)) if s.output_digest else ''}"
        f"{(' &middot; ' + esc(s.detail)) if s.detail else ''}</li>"
        for s in mission.timeline
    )
    artifacts = (
        " &middot; ".join(_short(a) for a in mission.artifact_refs)
        if mission.artifact_refs
        else "<em>none</em>"
    )
    return (
        '<details class="mission">\n'
        f'<summary><span class="pill {status_class}">{esc(mission.status)}</span> '
        f"{esc(mission.mission_id)} &middot; bundle {_short(mission.bundle_id)}</summary>\n"
        f'<div class="detail-body">\n'
        f'<p><span class="k">input</span> {esc(mission.input_text)}</p>\n'
        f'<p><span class="k">output</span> {esc(mission.final_output)} '
        f"&middot; digest {_short(mission.output_digest)}</p>\n"
        f'<ol class="steps">{steps}</ol>\n'
        f'<p class="muted">artifacts: {artifacts}</p>\n'
        "</div>\n</details>"
    )


# -- resource economy ---------------------------------------------------------


def _resource_economy(model: DashboardModel) -> str:
    r = model.resources
    rows = [
        ("canonical events", str(r.events)),
        ("artifacts", str(r.artifacts)),
        ("model calls", str(r.model_calls)),
        ("input tokens", str(r.input_tokens)),
        ("output tokens", str(r.output_tokens)),
        ("cost (USD)", f"{r.cost_usd:.6f}"),
        ("wall time (ms)", str(r.wall_ms)),
    ]
    cells = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in rows
    )
    return _card(
        "Resource economy",
        "the recorded cost of running and improving the system",
        f'<table class="kv"><tbody>{cells}</tbody></table>',
    )


# -- incident and audit -------------------------------------------------------


def _incident_audit(model: DashboardModel) -> str:
    if not model.incidents:
        body = '<p class="ok">no incidents recorded</p>'
    else:
        severe = {"chain_error", "corrupt_bundle", "rejected", "leakage"}
        rows = "\n".join(
            f'<li class="incident inc-{esc(i.kind)}">'
            f'<span class="pill {"bad" if i.kind in severe else "warn"}">{esc(i.kind)}</span> '
            f"{esc(i.summary)}"
            f'{(" &middot; seq " + str(i.sequence)) if i.sequence is not None else ""}</li>'
            for i in model.incidents
        )
        body = f'<ul class="incidents">{rows}</ul>'
    note = (
        '<p class="muted">Quarantines and rollbacks are recorded here as first-class '
        "outcomes: a candidate whose evidence passed every gate but lacked authorization is "
        "quarantined, not hidden.</p>"
    )
    return _card("Incident and audit", "can an operator contain and explain a failure", note + body)


# -- shell --------------------------------------------------------------------


def _card(title: str, subtitle: str, inner: str) -> str:
    return (
        '<section class="card">\n'
        f"<h2>{esc(title)}</h2>\n"
        f'<p class="sub muted">{esc(subtitle)}</p>\n'
        f"{inner}\n</section>"
    )


def _footer(model: DashboardModel) -> str:
    return (
        '<footer class="foot muted">\n'
        f"Projected from {model.evidence.event_count} append-only events "
        f"(tip {_short(model.evidence.tip_digest)}). "
        "Reproduce the underlying evidence with <code>foundry verify</code> and "
        "<code>foundry replay</code>.\n"
        "</footer>"
    )


_CSS = """
:root{--bg:#fbfcfd;--fg:#1a1f24;--muted:#5b6672;--card:#fff;--line:#e3e8ee;
--ok:#177245;--bad:#b3261e;--warn:#8a6d00;--accent:#1f5fbf;--code:#f2f4f7;}
@media (prefers-color-scheme:dark){:root{--bg:#0f1319;--fg:#e6eaef;--muted:#93a1b0;
--card:#161b22;--line:#26303b;--ok:#4cc38a;--bad:#f26d63;--warn:#e0b341;--accent:#5b9bf3;--code:#1c232c;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.wrap{max-width:960px;margin:0 auto;padding:24px 18px 60px;}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:16px;}
h1{font-size:22px;margin:0 0 2px;}
h2{font-size:17px;margin:0;}
h4{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:16px 0 6px;}
.muted{color:var(--muted);}
.claim{background:var(--code);border:1px solid var(--line);border-radius:8px;
padding:10px 14px;font-size:13px;margin:16px 0;}
.evidence{text-align:right;font-size:13px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px 20px;margin:16px 0;}
.sub{margin:2px 0 12px;font-size:13px;}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;}
.tile{background:var(--code);border-radius:8px;padding:12px;text-align:center;}
.tile-v{font-size:20px;font-weight:600;overflow-wrap:anywhere;}
.tile-k{font-size:12px;color:var(--muted);margin-top:2px;}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;
font-weight:600;border:1px solid var(--line);}
.pill.ok,.ok{color:var(--ok);}.pill.bad,.bad{color:var(--bad);}.pill.warn,.warn{color:var(--warn);}
.pill.active,.lc-active{color:var(--accent);border-color:var(--accent);}
.lc-quarantined{color:var(--warn);border-color:var(--warn);}
.lc-rolled_back,.lc-rejected{color:var(--bad);border-color:var(--bad);}
.tree,.tree ul{list-style:none;padding-left:16px;margin:6px 0;}
.tree>li{border-left:2px solid var(--line);padding-left:12px;margin:8px 0;}
.cfg{font-size:12px;margin:2px 0;}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.9em;
overflow-wrap:anywhere;}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0;overflow-wrap:anywhere;}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top;}
th{background:var(--code);font-weight:600;}
.diff .old{color:var(--bad);}.diff .new{color:var(--ok);}
.gates .gfail td{color:var(--bad);font-weight:600;}
.gates .gpass td:nth-child(2){color:var(--ok);}
details{border:1px solid var(--line);border-radius:8px;margin:8px 0;padding:2px 12px;}
summary{cursor:pointer;padding:8px 0;font-weight:500;}
.detail-body{padding:0 0 10px;}
.k{display:inline-block;min-width:70px;color:var(--muted);font-size:12px;
text-transform:uppercase;letter-spacing:.03em;}
.steps,.incidents{padding-left:18px;margin:6px 0;}
.step-failed{color:var(--bad);}.step-suppressed{color:var(--muted);}
.incident{margin:4px 0;}
.foot{border-top:1px solid var(--line);margin-top:24px;padding-top:14px;font-size:12px;}
"""
