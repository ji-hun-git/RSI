"""DeterministicTestService: executable-check oracle with command receipts.

The report 10.2 Deterministic Test Service in Stage-1 form: it materializes
a candidate's patched repository into an ephemeral workspace, force-writes
the TRUSTED checks file over whatever the candidate returned, executes the
checks in a subprocess with a hard timeout, and emits a signed-content
receipt (command, exit code, output digests -- report 14.4 "execution
receipts"). Tests are read-only truth: a worker that edits ``checks.py``
to always pass is scored against the original checks anyway (report 14.2,
"tamper with tests" / known failure mode "edits tests to fit incorrect
implementation").

Scoring untrusted candidate output is fail-closed: malformed JSON, wrong
shapes, path traversal in file names or a timeout all score 0.0 rather
than raising into the experiment loop.

SECURITY BOUNDARY, stated plainly (report 5.3, 14.4): a local subprocess
is an isolation *convenience* for deterministic fixtures, not a security
sandbox. The Stage-1 corpus executes code produced by the in-repo
deterministic worker only. Output from real model-backed coding agents
must not be executed here until a real sandbox (rootless container or
microVM, report 14.4) sits behind this same interface.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from foundry.contracts import DIGEST_PREFIX, ModuleRef, sha256_hex
from foundry.workers.coding_tasks import CHECKS_FILE, CodingTask

_TAIL_CHARS = 400


@dataclass(frozen=True)
class CommandReceipt:
    """Execution receipt (report 14.4): what ran, how it exited, what it said."""

    command: tuple[str, ...]
    exit_code: int | None  # None when the process was killed on timeout
    duration_ms: int
    stdout_digest: str
    stderr_digest: str
    stdout_tail: str
    stderr_tail: str
    timed_out: bool = False


@dataclass(frozen=True)
class TestReport:
    passed: bool
    receipt: CommandReceipt


def _receipt_fields(data: bytes | None) -> tuple[str, str]:
    raw = data or b""
    digest = DIGEST_PREFIX + sha256_hex(raw)
    tail = raw.decode("utf-8", errors="replace")[-_TAIL_CHARS:]
    return digest, tail


def _safe_relative(name: str) -> str:
    """Reject absolute paths, drive letters and traversal in file names.

    Candidate output is untrusted data; a file name must stay a plain
    relative path inside the workspace (no zip-slip style escapes).
    """
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or ":" in name or ".." in pure.parts or not pure.parts:
        raise ValueError(f"unsafe file path in candidate output: {name!r}")
    return str(pure)


class DeterministicTestService:
    """Runs a repository's checks file in an ephemeral workspace."""

    evaluator = ModuleRef(id="eval.executable_checks", version="1.0.0")

    def __init__(self, timeout_seconds: float = 30.0, checks_file: str = CHECKS_FILE) -> None:
        self._timeout = timeout_seconds
        self._checks_file = checks_file

    def run_checks(
        self,
        candidate_files: Mapping[str, str],
        *,
        trusted_files: Mapping[str, str],
    ) -> TestReport:
        """Materialize *candidate_files*, restore the trusted checks, execute.

        The checks file always comes from *trusted_files* -- candidate
        content for it is discarded, never merged (read-only tests,
        report 14.2). File contents are written byte-preserving
        (``newline=""``) so CRLF fixtures survive the round trip.
        """
        if self._checks_file not in trusted_files:
            raise ValueError(f"trusted files are missing {self._checks_file!r}")
        with tempfile.TemporaryDirectory(prefix="foundry-checks-") as workspace:
            root = Path(workspace)
            for name, content in candidate_files.items():
                target = root / _safe_relative(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="")
            # Trusted tests overwrite whatever the candidate returned.
            (root / self._checks_file).write_text(
                trusted_files[self._checks_file], encoding="utf-8", newline=""
            )
            command = (sys.executable, "-X", "utf8", self._checks_file)
            started = time.monotonic()
            try:
                completed = subprocess.run(
                    command,
                    cwd=root,
                    capture_output=True,
                    timeout=self._timeout,
                )
            except subprocess.TimeoutExpired as expired:
                duration_ms = int((time.monotonic() - started) * 1000)
                stdout_digest, stdout_tail = _receipt_fields(expired.stdout)
                stderr_digest, stderr_tail = _receipt_fields(expired.stderr)
                return TestReport(
                    passed=False,
                    receipt=CommandReceipt(
                        command=command,
                        exit_code=None,
                        duration_ms=duration_ms,
                        stdout_digest=stdout_digest,
                        stderr_digest=stderr_digest,
                        stdout_tail=stdout_tail,
                        stderr_tail=stderr_tail,
                        timed_out=True,
                    ),
                )
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_digest, stdout_tail = _receipt_fields(completed.stdout)
        stderr_digest, stderr_tail = _receipt_fields(completed.stderr)
        return TestReport(
            passed=completed.returncode == 0,
            receipt=CommandReceipt(
                command=command,
                exit_code=completed.returncode,
                duration_ms=duration_ms,
                stdout_digest=stdout_digest,
                stderr_digest=stderr_digest,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
            ),
        )

    def score(self, task: CodingTask, output: str) -> float:
        """Experiment ``Score``/vault ``Scorer``: 1.0 iff the checks pass.

        Fail-closed over untrusted output: anything that is not a JSON
        object with a ``files`` mapping of relative-path strings scores
        0.0. The trusted checks come from the TASK, so a candidate that
        returns a doctored checks file is scored against the original.
        """
        files = self._parse_output(output)
        if files is None:
            return 0.0
        try:
            report = self.run_checks(files, trusted_files=dict(task.files))
        except ValueError:  # unsafe path in candidate output
            return 0.0
        return 1.0 if report.passed else 0.0

    @staticmethod
    def _parse_output(output: str) -> dict[str, str] | None:
        try:
            data: Any = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return None
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, dict) or not files:
            return None
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
            return None
        return files
