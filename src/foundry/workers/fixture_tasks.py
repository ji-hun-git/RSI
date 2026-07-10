"""Deterministic fixture task corpus (report 18.3, 19.5 weeks 9-10).

The Stage-1 benchmark families are foundry-generated briefs over one tiny,
fully checkable transformation: slugify. The robust transformation defined
here is the single source of truth -- ``robust_slugify`` computes every
``expected_output`` and is the same function the robust FixtureWorker
strategy executes, so the oracle and the ground-truth worker can never
drift apart.

Corpus roles mirror :class:`~foundry.contracts.TaskSetRole` (report 17.4):
development (tuning), protected (holdout, disjoint from development),
retention (tasks the naive baseline already solves; used for
non-inferiority checks) and adversarial (nasty inputs). Generation is a
pure function of the seed: same seed, identical corpora on any platform.
All randomness is drawn through ``random.Random.random()`` -- the only
generator method with a documented cross-version stability guarantee --
so a future CPython cannot silently change the generated corpus.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

# Unicode dash-like characters normalized to ASCII hyphen by the robust
# transformation: hyphen, non-breaking hyphen, figure dash, en dash,
# em dash, horizontal bar, minus sign.
_DASH_CHARS = "‐‑‒–—―−"
_DASH_TRANSLATION = {ord(ch): "-" for ch in _DASH_CHARS}

_WHITESPACE_RUN = re.compile(r"\s+")
_HYPHEN_RUN = re.compile(r"-{2,}")

_WORDS = (
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
    "hotel", "india", "juliet", "kilo", "lima", "mike", "november",
    "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform",
    "victor", "whiskey", "xray", "yankee", "zulu", "amber", "birch",
    "cedar", "dune", "ember", "flint", "grove", "harbor", "ivory",
    "jasper", "krypton", "lumen", "meadow", "nimbus",
)

_UNICODE_DASH_SEPARATORS = ("—", "–")
_TRAILING_PUNCTUATION = ("!", ".", "?")


def _pick(rng: random.Random, options: tuple[str, ...]) -> str:
    """Stable replacement for ``rng.choice``: derived from ``rng.random()`` only."""
    return options[int(rng.random() * len(options))]


def _randint(rng: random.Random, low: int, high: int) -> int:
    """Stable replacement for ``rng.randint`` (inclusive bounds)."""
    return low + int(rng.random() * (high - low + 1))


def robust_slugify(text: str) -> str:
    """Ground-truth slugify transformation.

    Lowercase; normalize unicode dashes to ``-``; drop punctuation and
    control characters (everything not alphanumeric, whitespace or a
    hyphen); collapse whitespace runs to single hyphens; collapse hyphen
    runs; strip leading/trailing hyphens.
    """
    lowered = text.lower().translate(_DASH_TRANSLATION)
    kept = "".join(
        ch for ch in lowered if ch.isalnum() or ch == "-" or ch.isspace()
    )
    hyphenated = _WHITESPACE_RUN.sub("-", kept)
    return _HYPHEN_RUN.sub("-", hyphenated).strip("-")


def naive_slugify(text: str) -> str:
    """The naive baseline transformation: lowercase, single spaces to hyphens."""
    return text.lower().replace(" ", "-")


@dataclass(frozen=True)
class FixtureTask:
    """One deterministic benchmark item; ``expected_output`` is the robust slug."""

    task_id: str
    family: str
    input_text: str
    expected_output: str
    difficulty: str  # "easy" | "hard" | "adversarial"


def _make_task(task_id: str, input_text: str, difficulty: str) -> FixtureTask:
    return FixtureTask(
        task_id=task_id,
        family="slugify",
        input_text=input_text,
        expected_output=robust_slugify(input_text),
        difficulty=difficulty,
    )


def _easy_input(rng: random.Random) -> str:
    """Single-space-separated lowercase words: naive == robust by construction."""
    return " ".join(_pick(rng, _WORDS) for _ in range(_randint(rng, 2, 4)))


def _hard_input(rng: random.Random) -> str:
    """Input on which the naive and robust transformations provably differ.

    Every hard input applies exactly one difference-guaranteeing hardener
    (double space, inline punctuation or a unicode dash separator), plus
    optional mixed case and trailing punctuation.
    """
    words = [_pick(rng, _WORDS) for _ in range(_randint(rng, 2, 4))]
    words = [w.capitalize() if rng.random() < 0.5 else w for w in words]
    hardener = _pick(rng, ("double_space", "punctuation", "unicode_dash"))
    if hardener == "double_space":
        separator = "  "
    elif hardener == "punctuation":
        separator = ", "
    else:
        separator = _pick(rng, _UNICODE_DASH_SEPARATORS)
    text = separator.join(words)
    if rng.random() < 0.5:
        text += _pick(rng, _TRAILING_PUNCTUATION)
    return text


def _fresh(rng: random.Random, make_input, seen: set[str]) -> str:
    """Draw inputs until one is globally unseen (deterministic given rng)."""
    text = make_input(rng)
    while text in seen:
        text = make_input(rng)
    seen.add(text)
    return text


def _adversarial_tasks(rng: random.Random) -> list[FixtureTask]:
    w = [_pick(rng, _WORDS) for _ in range(8)]
    long_text = " ".join(_pick(rng, _WORDS) for _ in range(400))
    inputs = [
        long_text,
        f"{w[0]}\x00{w[1]}\t{w[2]}\x1f{w[3]}",
        "!!!,,,;;;***???",
        f"{w[4]}—{w[5]}—{w[6]}",
        f"   {w[0]} {w[7]}   ",
        f"  {w[1].upper()}—{w[2]},,  {w[3]}!\x07  ",
    ]
    return [
        _make_task(f"adv-{i:03d}", text, "adversarial")
        for i, text in enumerate(inputs, start=1)
    ]


def generate_task_sets(seed: int) -> dict[str, list[FixtureTask]]:
    """Generate the four Stage-1 corpora; a pure function of *seed*.

    Returns ``{"development": 10 easy + 10 hard, "protected": 12 hard
    (inputs disjoint from development), "retention": 10 easy the naive
    strategy already solves, "adversarial": 6 nasty inputs}``.
    """
    rng = random.Random(seed)
    seen: set[str] = set()

    development = [
        _make_task(f"dev-easy-{i:03d}", _fresh(rng, _easy_input, seen), "easy")
        for i in range(1, 11)
    ] + [
        _make_task(f"dev-hard-{i:03d}", _fresh(rng, _hard_input, seen), "hard")
        for i in range(1, 11)
    ]
    protected = [
        _make_task(f"prot-hard-{i:03d}", _fresh(rng, _hard_input, seen), "hard")
        for i in range(1, 13)
    ]
    retention = [
        _make_task(f"ret-easy-{i:03d}", _fresh(rng, _easy_input, seen), "easy")
        for i in range(1, 11)
    ]
    return {
        "development": development,
        "protected": protected,
        "retention": retention,
        "adversarial": _adversarial_tasks(rng),
    }
