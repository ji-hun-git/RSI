# mini_swe_agent baseline adapter (not yet implemented)

Home of the mini-SWE-agent baseline worker adapter: it must implement the same `foundry.contracts.WorkerLike` protocol (`invoke(task_input, config, seed) -> dict`) as the primary coding worker, so paired control/candidate comparisons can use it as the minimal-agent baseline arm (report 18.2, 19.1).
