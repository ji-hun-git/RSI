# CLAUDE.md

Instructions for agents working in this repository.

## Start here

1. Read `HANDOFF.md` first: it holds the current state, how to run everything, and what to build next.
2. `docs/TECHNICAL_REPORT.md` is the authoritative spec; source docstrings cite the sections they implement.

## Hard rules

- **Contracts are frozen.** `src/foundry/contracts/` is the interchange layer for code, exported schemas and persisted evidence. Any schema change requires a migration note (a new ADR) in `docs/DECISIONS.md`, and changes that alter the digest of existing events or bundles are effectively forbidden (they make honest historical evidence look tampered).
- **Verify before claiming done.** Run `python -m pytest -q` (the full suite must pass; 356 tests at the time of writing) and `python -m ruff check src tests` (expect clean). A change is not done while either fails.
- **Never commit `.foundry` state.** Local roots (`.foundry*/`, `*.db`) contain signing keys and machine-local evidence; they are gitignored and must stay out of version control.
- **The governance invariants are load-bearing and tests pin them.** No self-approval (G8 plus the deployment controller's independent check), append-only evidence (no ledger update/delete; corrections are new events), and blind holdouts (protected tasks only via `HoldoutVault.run_blind`; ground truth never leaves the vault) are the point of the system, not implementation details. If a test guarding one of these turns red, the change is wrong; do not weaken the test.
- **Fail-closed is the default.** Gates that throw have failed; missing evidence is refusal, never a vacuous pass; unknown policy subjects/actions are denied. Preserve this posture in anything you add.
- **Claims language (report 21.1).** Never describe this repo as autonomous, open-ended or self-aware RSI, in code, docs, comments or demos. Correct terms: "governed system optimization", "experiment control plane", "bounded agent-system self-modification" (as the design goal). "Bounded RSI" is reserved for multi-generation evidence that does not exist yet (report 12.6, 18.8).

## Conventions

- Python 3.11+ (see ADR-006), pydantic v2, pytest, ruff (line length 110, rules E/F/I/UP/B).
- Windows and POSIX both matter: no `:` in filenames, paths via `pathlib`, explicit encodings and newlines.
- New integrations go in `adapters/` behind the existing protocols (`RuntimeAdapter`, `WorkerLike`, `LedgerLike`, `ArtifactStoreLike`), never inside the control-plane packages.
- Determinism is a feature: corpus and bootstrap randomness only via `random.Random.random()`; seeds derived through `derive_seed`, never wall-clock.
