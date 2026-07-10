# Pre-registration: Stage-1 Campaign v1

Registered before any campaign result was computed. This document fixes the
design; the runner (`foundry.experiment.campaign`) reads its parameters from
`default_campaign_v1()`, which must match this text. The archived analysis
(`research/analyses/stage1_campaign_v1.json`) records this file's content
digest so post-hoc edits are detectable.

## Purpose

Satisfy the report 19.1 exit criterion "20+ paired candidate/control
experiments reproducible" as a recorded, archived research campaign
(STAGE1_PROTOCOL.md section 3 procedure). Phase A scope: this campaign makes
NO improvement claim beyond the fixture domains' known ground truth and NO
RSI claim of any kind; its purpose is to demonstrate that the platform runs,
records and reproduces paired comparisons at protocol standard.

## Design

- 20 experiments, fixed-size, single-pass, no adaptive peeking, no holdout
  reuse: 12 on the slugify string-transformation domain (seeds 101-112) and
  8 on the executable-test coding domain (seeds 201-208).
- Per experiment: control = frozen bundle with `strategy=naive`; one
  candidate = child bundle with `strategy=robust` (typed single-field diff
  `/config/strategy`, inside the level-2 mutation surface).
- Proposal: human-designed (report 12.4 row 1), pre-registered per protocol
  section 3.1 with `minimum_practical_effect = 0.05`, `retention_floor = 0.0`,
  executable rollback condition, retention set reference per seed.
- Holdout sealed in the vault before the run; leakage check over proposal
  text and evidence before results open; protected tasks execute only
  through blind handles.
- Matched execution: identical tasks, order and per-task seeds across arms;
  equalized budgets; randomization unit = task, paired.
- Analysis: paired per-task deltas, mean delta, seeded paired percentile
  bootstrap CI, win/loss/tie counts, per role (development, protected
  holdout, retention, adversarial).
- Gate: G0-G9 run WITHOUT human approval. This campaign measures; it does
  not deploy.

## Pre-declared endpoints and predictions

Primary endpoint: paired task-success delta on the protected holdout
(lower confidence bound, one-sided, per gate G3).

Predictions (known ground truth of the fixture domains):

1. Every experiment: development mean delta > 0 and protected-holdout
   ci_low >= 0.05 (the candidate genuinely dominates on hard tasks).
2. Every experiment: zero per-task retention losses (non-inferiority).
3. Every experiment: zero critical adversarial violations for the candidate.
4. Every experiment: gate decision = QUARANTINE (all evidence gates pass;
   G8 fails because no human approval is supplied) -- authority is never
   implicit, even in a measurement campaign.
5. Zero leakage hits.
6. Bit-identical reproduction: re-running the campaign from this
   pre-registration's seeds yields an identical deterministic results
   payload (excluding run metadata), and rerun agreement within each
   experiment is 1.0.

## Deviations

Any deviation from this design must be reported in the campaign report with
its reason; silent deviation invalidates the campaign.
