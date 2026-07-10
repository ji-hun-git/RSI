# Stage1 Campaign V1: Results

Registered campaign per `research/preregistrations/STAGE1_CAMPAIGN_V1.md` (content digest `sha256:b61d28ba90901460645b2e472309aa6b819758aa3c391bdb61efc1e04f9dc7d6` at run time) and STAGE1_PROTOCOL.md section 3. Scope: Phase A infrastructure validation on deterministic fixtures; no improvement claim beyond the fixtures' known ground truth and no RSI claim (report 21.1: everything here is governed system optimization infrastructure).

Generated 2026-07-10T14:35:12.154910+00:00 on Python 3.11.9/Windows; 540 hash-chain-verified canonical events archived in `research/analyses/stage1_campaign_v1_events.jsonl`; deterministic results payload in `research/analyses/stage1_campaign_v1.json` (bit-reproducible from the registered seeds).

## Aggregates

| Domain | n | mean dev delta | min holdout ci_low | retention losses | leakage hits | gate actions |
|---|---|---|---|---|---|---|
| coding | 8 | +0.500 | +1.000 | 0 | 0 | quarantine |
| slugify | 12 | +0.500 | +1.000 | 0 | 0 | quarantine |

## Per-experiment results

| # | Domain | Seed | Dev delta | Holdout ci_low | Ret. losses | Adv. viol. | Rerun | Gate | Failed gates |
|---|---|---|---|---|---|---|---|---|---|
| 1 | slugify | 101 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 2 | slugify | 102 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 3 | slugify | 103 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 4 | slugify | 104 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 5 | slugify | 105 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 6 | slugify | 106 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 7 | slugify | 107 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 8 | slugify | 108 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 9 | slugify | 109 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 10 | slugify | 110 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 11 | slugify | 111 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 12 | slugify | 112 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 13 | coding | 201 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 14 | coding | 202 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 15 | coding | 203 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 16 | coding | 204 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 17 | coding | 205 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 18 | coding | 206 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 19 | coding | 207 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |
| 20 | coding | 208 | +0.500 | +1.000 | 0 | 0 | 1.0 | quarantine | G8 |

## Pre-registered predictions, checked

1. Development mean delta > 0 and holdout ci_low >= 0.05 in every experiment: **held**
2. Zero per-task retention losses: **held**
3. Zero critical adversarial violations (candidate): **held**
4. Gate decision QUARANTINE everywhere (evidence passes, authority absent): **held**
5. Zero leakage hits: **held**
6. Rerun agreement 1.0 in every experiment: **held**

## Deviations from the pre-registration

None.
