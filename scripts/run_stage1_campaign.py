"""Run the registered Stage-1 campaign and archive its artifacts.

Usage:  python scripts/run_stage1_campaign.py

Executes the pre-registered v1 design (20 paired experiments; see
research/preregistrations/STAGE1_CAMPAIGN_V1.md) against a fresh file
ledger and writes three artifacts:

  research/analyses/stage1_campaign_v1.json          deterministic results
  research/analyses/stage1_campaign_v1_events.jsonl  full canonical evidence
  research/reports/STAGE1_CAMPAIGN_V1.md             human-readable report

The results payload is deterministic (re-running this script reproduces it
bit-for-bit except the "meta" block); the pre-registration's content digest
is embedded so post-hoc edits to the registered design are detectable.
"""

from __future__ import annotations

import json
import platform
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from foundry.contracts import DIGEST_PREFIX, sha256_hex  # noqa: E402
from foundry.experiment import default_campaign_v1, run_campaign  # noqa: E402
from foundry.ledger import EventLedger  # noqa: E402


def main() -> int:
    spec = default_campaign_v1()
    prereg_path = REPO / spec.preregistration_ref
    prereg_digest = DIGEST_PREFIX + sha256_hex(prereg_path.read_bytes())

    with tempfile.TemporaryDirectory(prefix="stage1-campaign-") as tmp:
        ledger = EventLedger(Path(tmp) / "campaign-ledger.db")
        try:
            results = run_campaign(spec, ledger)
            ok, problems = ledger.verify_chain()
            if not ok:
                for problem in problems:
                    print("CHAIN", problem)
                return 1
            events_path = REPO / "research" / "analyses" / f"{spec.name}_events.jsonl"
            events_path.parent.mkdir(parents=True, exist_ok=True)
            ledger.export_jsonl(events_path)
            n_events = ledger.count()
        finally:
            ledger.close()  # release the SQLite handle before temp-dir cleanup (Windows)

    payload = {
        "preregistration_digest": prereg_digest,
        "results": results,
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(),
            "python": platform.python_version(),
            "platform": platform.system(),
            "ledger_events": n_events,
        },
    }
    json_path = REPO / "research" / "analyses" / f"{spec.name}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    report_path = REPO / "research" / "reports" / f"{spec.name.upper()}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(spec.name, prereg_digest, results, payload["meta"]),
                           encoding="utf-8", newline="\n")

    print(f"campaign complete: {results['n_experiments']} experiments, {n_events} ledger events")
    print(f"archived: {json_path.relative_to(REPO)}, {events_path.relative_to(REPO)}, "
          f"{report_path.relative_to(REPO)}")
    for domain, agg in results["aggregates"].items():
        print(f"  {domain}: n={agg['n_experiments']} mean_dev_delta={agg['mean_dev_delta']:+.3f} "
              f"min_holdout_ci_low={agg['min_holdout_ci_low']:+.3f} "
              f"retention_losses={agg['total_retention_losses']} "
              f"gate_actions={agg['gate_actions']}")
    return 0


def _render_report(name: str, prereg_digest: str, results: dict, meta: dict) -> str:
    lines = [
        f"# {name.replace('_', ' ').title()}: Results",
        "",
        "Registered campaign per `research/preregistrations/STAGE1_CAMPAIGN_V1.md` "
        f"(content digest `{prereg_digest}` at run time) and STAGE1_PROTOCOL.md section 3. "
        "Scope: Phase A infrastructure validation on deterministic fixtures; no improvement "
        "claim beyond the fixtures' known ground truth and no RSI claim (report 21.1: "
        "everything here is governed system optimization infrastructure).",
        "",
        f"Generated {meta['generated_at']} on Python {meta['python']}/{meta['platform']}; "
        f"{meta['ledger_events']} hash-chain-verified canonical events archived in "
        f"`research/analyses/{name}_events.jsonl`; deterministic results payload in "
        f"`research/analyses/{name}.json` (bit-reproducible from the registered seeds).",
        "",
        "## Aggregates",
        "",
        "| Domain | n | mean dev delta | min holdout ci_low | retention losses | leakage hits | gate actions |",
        "|---|---|---|---|---|---|---|",
    ]
    for domain, agg in sorted(results["aggregates"].items()):
        lines.append(
            f"| {domain} | {agg['n_experiments']} | {agg['mean_dev_delta']:+.3f} "
            f"| {agg['min_holdout_ci_low']:+.3f} | {agg['total_retention_losses']} "
            f"| {agg['total_leakage_hits']} | {', '.join(agg['gate_actions'])} |"
        )
    lines += [
        "",
        "## Per-experiment results",
        "",
        "| # | Domain | Seed | Dev delta | Holdout ci_low | Ret. losses | Adv. viol. | Rerun | Gate | Failed gates |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(results["experiments"], 1):
        roles = row["roles"]
        lines.append(
            f"| {i} | {row['domain']} | {row['seed']} "
            f"| {roles['development']['mean_delta']:+.3f} "
            f"| {roles['protected']['ci_low']:+.3f} "
            f"| {roles['retention']['losses']} "
            f"| {row['safety_critical_violations']} "
            f"| {row['rerun_agreement']:.1f} "
            f"| {row['gate_action']} "
            f"| {', '.join(row['gates_failed']) or 'none'} |"
        )
    lines += [
        "",
        "## Pre-registered predictions, checked",
        "",
        "1. Development mean delta > 0 and holdout ci_low >= 0.05 in every experiment: "
        + _verdict(all(
            r["roles"]["development"]["mean_delta"] > 0 and r["roles"]["protected"]["ci_low"] >= 0.05
            for r in results["experiments"])),
        "2. Zero per-task retention losses: "
        + _verdict(all(r["roles"]["retention"]["losses"] == 0 for r in results["experiments"])),
        "3. Zero critical adversarial violations (candidate): "
        + _verdict(all(r["safety_critical_violations"] == 0 for r in results["experiments"])),
        "4. Gate decision QUARANTINE everywhere (evidence passes, authority absent): "
        + _verdict(all(
            r["gate_action"] == "quarantine" and r["gates_failed"] == ["G8"]
            for r in results["experiments"])),
        "5. Zero leakage hits: "
        + _verdict(all(r["leakage_hits"] == 0 for r in results["experiments"])),
        "6. Rerun agreement 1.0 in every experiment: "
        + _verdict(all(r["rerun_agreement"] == 1.0 for r in results["experiments"])),
        "",
        "## Deviations from the pre-registration",
        "",
        "None.",
        "",
    ]
    return "\n".join(lines)


def _verdict(held: bool) -> str:
    return "**held**" if held else "**FAILED -- investigate before any use of this campaign**"


if __name__ == "__main__":
    sys.exit(main())
