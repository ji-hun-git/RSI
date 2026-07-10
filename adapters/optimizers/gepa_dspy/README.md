# gepa_dspy proposer adapter (not yet implemented)

Home of the GEPA/DSPy proposal adapter: it must consume ledger evidence and emit typed `foundry.contracts.ImprovementProposal` objects (declared `FieldChange` diffs inside the PDP's allowed mutation surface, with pre-registered thresholds and rollback condition); it receives no promotion authority and no holdout-vault access (report 12.4, 19.3).
