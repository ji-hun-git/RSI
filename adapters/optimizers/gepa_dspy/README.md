# gepa_dspy proposer adapter (not yet implemented; seam ready)

Home of the GEPA/DSPy proposal adapter. The seam it must implement now exists and has a deterministic reference implementation:

- Implement `foundry.improvement.ProposerLike`: `propose(diagnoses, parent, constraints) -> list[ImprovementProposal]`, where `diagnoses` come from the read-only `EvidenceDiagnoser` (or richer trace readers) and `constraints` carry the PDP's allowed mutation surface, the proposal budget, pre-registered thresholds and previously rejected diffs.
- Every emitted proposal must be fully formed per report 12.3: declared `FieldChange` diffs inside `constraints.allowed_path_prefixes`, one primary falsifiable hypothesis, `evidence_refs` pointing at real ledger event ids, pre-registered `minimum_practical_effect`/`retention_floor`, and an executable rollback condition. `TemplateMutationProposer` in `foundry.improvement` shows the exact shape and is the baseline to beat (report 12.4).
- Honor the report 12.5 stopping rule the same way the reference does: a diff matching `constraints.rejected_diffs` may only be re-emitted with new evidence ids (`foundry.improvement.diff_digest` computes the diff identity).
- Authority boundary (report 12, 14.1): the adapter receives no registry write handle, no vault access (`holdout.read` is PDP-denied to optimizer principals) and no approval power. Its output is data; forking, experiments, gates and approvals all happen downstream. GEPA/DSPy may read development-set traces for reflective mutation but never protected holdout contents.

Blockers, stated honestly: GEPA/DSPy proposal generation needs an LLM provider key. The wiring (diagnosis evidence in, typed proposals out, full loop to canary) is already exercised model-free end-to-end in `tests/test_improvement_loop.py`.
