"""Worker package: deterministic fixture worker and benchmark corpus (report 18.3, 19.5)."""

from .fixture_tasks import FixtureTask, generate_task_sets, naive_slugify, robust_slugify
from .fixture_worker import FixtureWorker

__all__ = [
    "FixtureTask",
    "FixtureWorker",
    "generate_task_sets",
    "naive_slugify",
    "robust_slugify",
]
