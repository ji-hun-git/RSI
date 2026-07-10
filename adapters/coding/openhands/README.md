# openhands coding-worker adapter (not yet implemented)

Home of the OpenHands coding-worker adapter: it must implement the `foundry.contracts.WorkerLike` protocol (`invoke(task_input, config, seed) -> dict`), run in an isolated workspace with no hidden state, and report artifacts/usage through canonical events (report 9.3, 19.5 weeks 5-6).
