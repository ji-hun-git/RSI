# Resume guide: how to work in this repo effectively

This complements the two canonical files. Read them first, in order:

1. `HANDOFF.md` — current state, how to run everything, and the next-work queue.
2. `CLAUDE.md` — the hard rules (frozen contracts, governance invariants, claims language).
3. `docs/TECHNICAL_REPORT.md` — the authoritative spec; every source docstring cites the sections it implements.
4. `docs/DECISIONS.md` — ADR-001..NN, the "why" behind every design choice and substitution.
5. `docs/ROADMAP.md` — Stage 1-4 checklist with honest `[x]` / `[~]` / `[ ]` status.

This file is the missing third thing: not state, not rules, but **how the work has been done well** so far.

## The working loop (one coherent piece per commit)

1. **Pick the next item** from `HANDOFF.md` "What to build next". Prefer the highest-value item that is self-contained and model-free (buildable without external keys/sandboxes). When unsure which, say so and pick the one that makes an existing standalone piece load-bearing.
2. **Read the exact APIs first.** Contracts and neighbouring packages get touched by linters between sessions; grep/read the real signatures before building against them. Never assume a signature from memory.
3. **Build it.** Default to building inline for tightly-coupled work where cohesion matters. Reach for a `Workflow` only when the task genuinely decomposes into independent parallel work or benefits from adversarial multi-lens review, and only when the user has opted in (see the Workflow gotcha below).
4. **Prove it green:** `python -m pytest -q` (full suite) AND `python -m ruff check src tests examples scripts`. A change is not done while either fails. Run the actual demo/CLI when the change is observable there.
5. **Self-review before committing** (this has repeatedly caught real bugs — see below).
6. **Commit one coherent piece** with a full message (see commit hygiene).
7. **Update the docs in the same commit:** `HANDOFF.md` (state + count + next list), `docs/ROADMAP.md` (flip status), a new `docs/DECISIONS.md` ADR for any design decision, `README.md` (package map + test count), and the project memory file.

## Patterns that have paid off

- **Self-review at the point of use catches what tests-you-wrote-first miss.** Concrete finds this session: the tool gateway checked idempotency *before* authorization (a cached side-effect result could reach an expired/revoked capability); the dashboard projected only the first candidate arm (a losing branch would vanish) and fabricated a `[0,0]` CI when data was missing. After building, re-read each new code path adversarially: what happens on empty/partial/malformed input, on a denied capability, on a second caller. Then add the test that pins the fix.
- **Additive composition beats rippling the core.** `ModuleResolvingRuntime` and `ToolAugmentedRuntime` both wrap `DeterministicRuntime` via a `WorkerLike` closure instead of changing the base runtime — new adapters, ~500 other tests untouched. When an integration tempts you to edit a frozen-ish core, look for a composition seam first.
- **Honest scoping is a feature.** Mark partial work `[~]` in the roadmap, name the blocker in the ADR, and never overclaim. Examples: the module registry is in-process (implementations are Python objects, not serialized); tool-using missions are auditable but not replay-exact (external tools); the egress check vets the literal/resolved host but a production proxy must still pin the connection. State the limit in the code and the ADR.
- **Deterministic + cross-platform by default.** No wall-clock or unseeded randomness in anything that affects a digest, corpus, or analysis. Seeds are explicit. Paths via `pathlib`; no `:` in filenames (the `sha256:` prefix bites on Windows); explicit `encoding=`/`newline=`. Tests must not flake on another machine or timezone.
- **Claims language, always.** "Governed system optimization", never "autonomous/open-ended RSI" — in code, docstrings, commit messages, demos. "Bounded RSI" needs multi-generation evidence that does not exist yet.

## Gotchas (learned the hard way)

- **Workflow reviews can die mid-run on a session limit.** A multi-agent review's VERIFY phase once failed entirely on a limit and reported `confirmed: []` — which was *not* trustworthy because verification never ran. If a workflow's post-processing looks empty or too clean, read `.../workflows/.../journal.jsonl` for the raw per-agent findings and triage them yourself before trusting the summary.
- **Commit with `git -c core.safecrlf=false commit ...`** to suppress the wall of LF/CRLF warnings on this Windows checkout. End messages with the `Co-Authored-By` trailer.
- **`OPENAI_API_KEY` is environment-only.** It lives in the machine env (and `Desktop\openapi key.txt`). Never write it into code, events, artifacts, logs, or a commit. The live OpenAI test skips without it; model events carry digests only.
- **This repo is NOT `Desktop\RSI-project`.** Same acronym, unrelated project (a typed-instruction-corpus study). Do not cross the streams.
- **Two blocked frontiers, by design:** real coding agents (OpenHands/mini-SWE-agent) need LLM keys *and* a real sandbox — the local subprocess test service is a determinism convenience, not a security boundary, so model-generated code must not run under it (ADR-008). GEPA/DSPy library wrappers and the real MCP/PydanticAI adapters need their libraries; the seams (`ProposerLike`, `WorkerLike`, `ContextualWorker`, `ToolProvider`) are ready.

## Environment

- Repo: `C:\Users\Jason\RSI`, GitHub `ji-hun-git/RSI`, branch `main`. Windows 11, PowerShell + Git Bash, Python 3.11, pydantic v2.
- Install for dev: `pip install -e ".[dev,langgraph]"` (drop the extra for the dependency-light core; add `openai` for the live proposer test).
- Run: `foundry demo|verify|lineage|replay|coverage|dashboard --root <DIR>`. State roots (`.foundry*/`, `*.db`) are gitignored — never commit one.
