# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A ``tokenizers`` floor above what ``transformers`` accepts is unresolvable.

``transformers`` caps ``tokenizers<=0.23.0``. A requirement of ``>=0.23.1``
therefore has an empty intersection with it, and pip cannot resolve the
environment at all — the install dies with "conflicting dependencies" and every
package in the file is left uninstalled.

This has now happened twice with the same two versions:

* #9424 set ``tokenizers>=0.23.1``.
* #10331 / #10332 diagnosed it and fixed the floor to ``>=0.22.0``, leaving a
  comment on the line that says in as many words that ``>=0.23.1`` is
  unsatisfiable.
* #10416 — a grouped dependency bump — raised the floor back to ``>=0.23.1``
  **two days later, keeping the comment**. The file has said "this value is
  unsatisfiable" directly above that value ever since, and the ai-stack and
  npu-worker installs have failed to resolve.

A comment is not a guard. The second regression was invisible because the
explanation of the bug survived the reintroduction of the bug, so the file read
as though it had been considered.

The rule below is deliberately about the *intersection*, not about a literal
string: a bump that legitimately raises the cap updates ``_TRANSFORMERS_CAP``
and the floor together, and anything that moves only one fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The highest `tokenizers` that the pinned `transformers` accepts. Verified
# against transformers 5.14.1 and 5.15.0, both of which declare
# `tokenizers<=0.23.0,>=0.22.0`. Raise this only alongside a transformers bump
# that actually widens the cap.
_TRANSFORMERS_CAP = (0, 23, 0)
_TRANSFORMERS_FLOOR = (0, 22, 0)

_REQUIREMENT_FILES = (
    "autobot-infrastructure/shared/docker/ai-stack/requirements-ai.txt",
    "autobot-infrastructure/autobot-npu-worker/docker/requirements-npu.txt",
    # #14562: this one was excluded below as "an old, independent stack nothing
    # deploys", which was true of the deploy roles and irrelevant to the risk.
    # It pins `transformers>=4.36.0` with no cap, so pip resolves transformers
    # to 5.x and inherits the same tokenizers<=0.23.0 cap the two above face —
    # and the directory is now inside dependabot's reach, so a grouped bump can
    # move the pin. Guarded rather than exempted.
    "autobot-npu-worker/resources/windows-npu-worker/requirements.txt",
)

_SKIP_PARTS = {"venv", ".venv", "node_modules", ".worktrees", ".claude", "__pycache__"}


def _outside_excluded_dirs(path: Path, root: Path = _REPO_ROOT) -> bool:
    """True when no part of `path` RELATIVE to `root` is an excluded directory.

    Relative, never a substring of the absolute path (#15121): this repo runs
    from `.worktrees/<branch>/` checkouts, where an absolute match hits the repo
    root itself, skips every requirements file, and leaves the assertion below
    comparing an empty set against the expected one.
    """
    return not any(part in _SKIP_PARTS for part in path.relative_to(root).parts)


_TOKENIZERS_LINE = re.compile(r"^tokenizers\s*(?P<spec>[^#\n]*)", re.M)
_SPEC = re.compile(r"(?P<op>>=|<=|==|<|>)\s*(?P<version>\d+(?:\.\d+)*)")


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _specifiers(path: Path) -> list[tuple[str, tuple[int, ...]]]:
    match = _TOKENIZERS_LINE.search(path.read_text(encoding="utf-8"))
    assert match, f"{path} declares no tokenizers requirement — this test names the wrong file"
    return [(m.group("op"), _version(m.group("version"))) for m in _SPEC.finditer(match.group("spec"))]


def _pad(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Zero-pad two version tuples to equal length before comparing.

    Review finding: raw tuple comparison is not PEP 440. ``(0, 23, 0) <= (0, 23)``
    is False in Python while the two versions are *equal* to pip, so a future
    edit to ``tokenizers<=0.23`` — the same bound written with one component
    fewer — would fail this guard against a range that is actually fine.

    The failure direction is loud rather than silent, which is why it is a
    latent bug and not an escape. Fixed anyway: a guard that cries wolf on a
    correct change is one people learn to edit around.
    """
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)), right + (0,) * (width - len(right))


def _admits(specs: list[tuple[str, tuple[int, ...]]], version: tuple[int, ...]) -> bool:
    for op, raw_bound in specs:
        version, bound = _pad(version, raw_bound)
        if op == ">=" and not version >= bound:
            return False
        if op == ">" and not version > bound:
            return False
        if op == "<=" and not version <= bound:
            return False
        if op == "<" and not version < bound:
            return False
        if op == "==" and version != bound:
            return False
    return True


@pytest.mark.parametrize("relative", _REQUIREMENT_FILES)
def test_the_tokenizers_range_intersects_what_transformers_allows(relative):
    """The intersection must be non-empty, or pip cannot resolve anything.

    Checked by asking whether the declared range admits a version transformers
    also admits — not by matching the specifier text, which is what let the
    same two values come back a second time under a different diff.
    """
    path = _REPO_ROOT / relative
    specs = _specifiers(path)
    assert specs, f"{relative}: tokenizers is declared with no version specifier at all"

    usable = [v for v in (_TRANSFORMERS_FLOOR, _TRANSFORMERS_CAP) if _admits(specs, v)]
    rendered = ",".join(f"{op}{'.'.join(map(str, b))}" for op, b in specs)
    cap = ".".join(map(str, _TRANSFORMERS_CAP))
    assert usable, (
        f"{relative}: tokenizers{rendered} excludes every version transformers accepts "
        f"(transformers caps tokenizers<={cap}). pip will fail to resolve the whole file. See #10331."
    )


@pytest.mark.parametrize("relative", _REQUIREMENT_FILES)
def test_the_floor_does_not_exceed_the_cap(relative):
    """The specific shape both regressions took.

    Stated separately from the intersection rule because it is the one a
    dependency bump produces, and naming it makes the failure message point at
    the cause rather than at arithmetic.
    """
    path = _REPO_ROOT / relative
    floors = [bound for op, bound in _specifiers(path) if op in (">=", ">")]
    for floor in floors:
        assert floor <= _TRANSFORMERS_CAP, (
            f"{relative}: tokenizers floor {'.'.join(map(str, floor))} is above the "
            f"transformers cap {'.'.join(map(str, _TRANSFORMERS_CAP))} — unsatisfiable (#10331, #10416)"
        )


def test_every_file_declaring_tokenizers_is_covered():
    """The parametrised rules are worth exactly what this list covers.

    A third requirements file picking up the same pin would otherwise be
    unguarded, which is how the npu-worker copy went unnoticed while only the
    ai-stack one was being discussed.
    """
    declaring = {
        str(p.relative_to(_REPO_ROOT))
        for p in _REPO_ROOT.rglob("requirements*.txt")
        if _outside_excluded_dirs(p) and _TOKENIZERS_LINE.search(p.read_text(encoding="utf-8", errors="replace"))
    }
    # No subtraction any more (#14562). The windows npu-worker resource file was
    # excluded here for being "an old, independent stack nothing deploys" — a
    # statement about deploy roles, not about whether the pin can go
    # unsatisfiable. It is in _REQUIREMENT_FILES now, so this set comparison is
    # a plain equality with nothing carved out of it.
    assert declaring, "the rglob matched no requirements file at all — FIX THE SWEEP, every rule above is vacuous"
    assert declaring == set(
        _REQUIREMENT_FILES
    ), f"unguarded tokenizers pins: {sorted(declaring - set(_REQUIREMENT_FILES))}"


@pytest.mark.parametrize(
    "spec,version,expected",
    [
        # Exactly two shapes are False without _pad and True with it, and both
        # are here: `<=` where the BOUND is shorter, and `>=` where the
        # VERSION is shorter. Review found the original set contained only the
        # first — the other two "must now be admitted" cases were already True
        # by accident of which side happened to be longer, so they documented
        # an equivalence rather than pinning the fix.
        ("<=0.23", (0, 23, 0), True),  # discriminates
        (">=0.23.0", (0, 23), True),  # discriminates
        # equivalences that hold with or without padding, kept as documentation
        (">=0.22", (0, 22, 0), True),
        ("<=0.23.0", (0, 23), True),
        # and the ones that must still be rejected
        ("<=0.23", (0, 23, 1), False),
        (">=0.23.1", (0, 23, 0), False),
        ("<0.24", (0, 24, 0), False),
    ],
)
def test_version_comparison_is_length_normalised(spec, version, expected):
    """``0.23`` and ``0.23.0`` are the same version to pip, not to a tuple.

    Without padding, ``(0, 23, 0) <= (0, 23)`` is False and this guard would
    reject ``tokenizers<=0.23`` — a range that is perfectly correct, written
    one component shorter. Loud rather than silent, but a guard that fails on
    a correct change is one people learn to route around.
    """
    specs = [(m.group("op"), _version(m.group("version"))) for m in _SPEC.finditer(spec)]

    assert _admits(specs, version) is expected


def test_a_checkout_under_worktrees_is_still_scanned(tmp_path):
    """#15121: the sweep must see a tree rooted inside `.worktrees/`."""
    root = tmp_path / ".worktrees" / "issue-9999"
    (root / "venv").mkdir(parents=True)

    assert _outside_excluded_dirs(root / "requirements.txt", root)
    assert not _outside_excluded_dirs(root / "venv" / "requirements.txt", root)
