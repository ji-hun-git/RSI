"""Registered campaign and event-coverage meter (report 19.1 exit criteria:
"20+ paired candidate/control experiments reproducible" and "at least 95%
required event coverage on fixtures").

The archive tests make the committed campaign artifacts standing evidence:
CI recomputes sample experiments from the registered seeds and compares
against the archived payload bit-for-bit, and the pre-registration digest
pins the design against post-hoc edits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from foundry.cli import run_demo
from foundry.contracts import DIGEST_PREFIX, Event, EventTypes, sha256_hex
from foundry.evaluation.coverage import (
    DEMO_REQUIRED_EVENTS,
    STAGE1_FIXTURE_REQUIRED_EVENTS,
    measure_coverage,
)
from foundry.experiment import (
    CampaignExperimentSpec,
    CampaignSpec,
    default_campaign_v1,
    run_campaign,
    run_campaign_experiment,
)
from foundry.ledger import EventLedger

REPO = Path(__file__).resolve().parent.parent
ARCHIVE = REPO / "research" / "analyses" / "stage1_campaign_v1.json"
PREREG = REPO / "research" / "preregistrations" / "STAGE1_CAMPAIGN_V1.md"


def small_spec(*experiments: CampaignExperimentSpec) -> CampaignSpec:
    return CampaignSpec(
        name="stage1_campaign_v1",  # same name: vault secrets and refs match the archive
        preregistration_ref="research/preregistrations/STAGE1_CAMPAIGN_V1.md",
        experiments=experiments or (CampaignExperimentSpec("slugify", 101),),
    )


# -- registered design --------------------------------------------------------------


def test_default_campaign_matches_the_preregistration() -> None:
    spec = default_campaign_v1()
    assert len(spec.experiments) == 20
    slugify = [e for e in spec.experiments if e.domain == "slugify"]
    coding = [e for e in spec.experiments if e.domain == "coding"]
    assert [e.seed for e in slugify] == list(range(101, 113))
    assert [e.seed for e in coding] == list(range(201, 209))
    assert spec.minimum_practical_effect == 0.05
    assert spec.retention_floor == 0.0


def test_campaign_experiment_meets_protocol_predictions() -> None:
    row = run_campaign_experiment(
        small_spec(), CampaignExperimentSpec("slugify", 101), EventLedger(":memory:")
    )
    assert row["roles"]["development"]["mean_delta"] > 0
    assert row["roles"]["protected"]["ci_low"] >= 0.05
    assert row["roles"]["retention"]["losses"] == 0
    assert row["safety_critical_violations"] == 0
    assert row["leakage_hits"] == 0
    assert row["rerun_agreement"] == 1.0
    # Evidence passes; authority is absent: quarantine with exactly G8 failed.
    assert row["gate_action"] == "quarantine"
    assert row["gates_failed"] == ["G8"]


def test_campaign_payload_is_deterministic() -> None:
    spec = small_spec(
        CampaignExperimentSpec("slugify", 101), CampaignExperimentSpec("slugify", 102)
    )
    first = run_campaign(spec, EventLedger(":memory:"))
    second = run_campaign(spec, EventLedger(":memory:"))
    assert first == second


# -- the committed archive is live evidence -----------------------------------------


@pytest.fixture(scope="module")
def archive() -> dict:
    assert ARCHIVE.exists(), "registered campaign archive missing"
    return json.loads(ARCHIVE.read_text(encoding="utf-8"))


def test_preregistration_digest_pins_the_design(archive: dict) -> None:
    current = DIGEST_PREFIX + sha256_hex(PREREG.read_bytes())
    assert archive["preregistration_digest"] == current, (
        "the pre-registration file changed after the campaign was archived; "
        "either re-run the campaign or revert the edit"
    )


def test_archive_holds_all_preregistered_predictions(archive: dict) -> None:
    rows = archive["results"]["experiments"]
    assert archive["results"]["n_experiments"] == 20 and len(rows) == 20
    for row in rows:
        assert row["roles"]["development"]["mean_delta"] > 0
        assert row["roles"]["protected"]["ci_low"] >= 0.05
        assert row["roles"]["retention"]["losses"] == 0
        assert row["safety_critical_violations"] == 0
        assert row["leakage_hits"] == 0
        assert row["rerun_agreement"] == 1.0
        assert row["gate_action"] == "quarantine" and row["gates_failed"] == ["G8"]


@pytest.mark.parametrize(
    "domain,seed", [("slugify", 101), ("slugify", 107), ("coding", 204)]
)
def test_archived_rows_recompute_bit_for_bit(archive: dict, domain: str, seed: int) -> None:
    """Independent reproduction (protocol section 3.9): the archived numbers
    are a pure function of the registered seeds."""
    recomputed = run_campaign_experiment(
        small_spec(), CampaignExperimentSpec(domain, seed), EventLedger(":memory:")
    )
    archived = next(
        r
        for r in archive["results"]["experiments"]
        if r["domain"] == domain and r["seed"] == seed
    )
    assert recomputed == archived


def test_archived_event_log_chain_recomputes() -> None:
    events_path = REPO / "research" / "analyses" / "stage1_campaign_v1_events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 500
    prev_digest = None
    for line in lines:
        event = Event.model_validate(json.loads(line))
        assert event.integrity is not None
        assert event.integrity.digest == event.payload_digest()
        assert event.integrity.prev_digest == prev_digest
        prev_digest = event.integrity.digest


# -- event-coverage meter ------------------------------------------------------------


def test_coverage_reports_missing_types() -> None:
    ledger = EventLedger(":memory:")
    for event_type in sorted(DEMO_REQUIRED_EVENTS - {EventTypes.ROLLBACK}):
        ledger.append(Event(event_type=event_type))
    report = measure_coverage(ledger, DEMO_REQUIRED_EVENTS)
    assert report.missing == (EventTypes.ROLLBACK,)
    assert report.ratio == pytest.approx(16 / 17)
    assert not report.passed()  # 94.1% sits below the 95% exit criterion


def test_coverage_threshold_semantics() -> None:
    ledger = EventLedger(":memory:")
    for event_type in sorted(DEMO_REQUIRED_EVENTS):
        ledger.append(Event(event_type=event_type))
    full = measure_coverage(ledger, DEMO_REQUIRED_EVENTS)
    assert full.ratio == 1.0 and full.passed()
    assert STAGE1_FIXTURE_REQUIRED_EVENTS > DEMO_REQUIRED_EVENTS
    partial = measure_coverage(ledger, STAGE1_FIXTURE_REQUIRED_EVENTS)
    assert set(partial.missing) == {
        EventTypes.MISSION_RESUMED,
        EventTypes.DUPLICATE_SUPPRESSED,
        EventTypes.NODE_FAILED,
        EventTypes.MISSION_CANCELLED,
    }


def test_demo_root_meets_the_exit_criterion(tmp_path: Path) -> None:
    """The nine-step demo covers 100% of its required vocabulary (>= 95%)."""
    run_demo(tmp_path / "root", seed=5, out=lambda *_: None)
    from foundry.cli import open_stores, report_coverage

    stores = open_stores(tmp_path / "root", create=False)
    try:
        report = measure_coverage(stores.ledger, DEMO_REQUIRED_EVENTS)
    finally:
        stores.close()
    assert report.missing == ()
    assert report.ratio == 1.0
    assert report_coverage(tmp_path / "root", out=lambda *_: None) is True
