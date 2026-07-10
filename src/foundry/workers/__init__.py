"""Worker package: deterministic fixture workers and benchmark corpora.

Two domains, both no-model and replay-exact (report 18.3, 19.5): the
slugify string-transformation corpus (`FixtureWorker`) and the
executable-test coding corpus (`DeterministicCodingWorker`), whose oracle
runs each task's checks via `foundry.evaluation.DeterministicTestService`.
"""

from .coding_tasks import CodingTask, generate_coding_task_sets
from .coding_worker import DeterministicCodingWorker, make_coding_run_arm
from .fixture_tasks import FixtureTask, generate_task_sets, naive_slugify, robust_slugify
from .fixture_worker import FixtureWorker

__all__ = [
    "CodingTask",
    "DeterministicCodingWorker",
    "FixtureTask",
    "FixtureWorker",
    "generate_coding_task_sets",
    "generate_task_sets",
    "make_coding_run_arm",
    "naive_slugify",
    "robust_slugify",
]
