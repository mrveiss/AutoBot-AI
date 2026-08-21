# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A dependabot hard-exclude must hold in every block that can reach the pin.

#14727: an `ignore` entry is scoped to ONE update block. Dependabot, however,
follows ``-r`` includes, so a manifest owned by one block routinely reaches a
requirements file owned by another. Excluding a package in one block therefore
leaves every other block that reaches the same file free to propose it.

That is not hypothetical. #14431 hard-excluded ``openai >=3.0.0`` in the
``/autobot-backend`` block. #14722 bumped ``openai`` to 3.2.0 anyway — from the
root ``/`` block, which reaches the very same file:

    requirements-dev.txt:6  -r autobot-backend/requirements.txt
    requirements-ci.txt:14  -r requirements-ci/ai-ml.txt

``smoke-test`` then died on ``ResolutionImpossible`` against ``llama-index``,
which is precisely what the exclusion existed to prevent. The exclusion was
present, correct and documented, and it protected nothing.

So the invariant is not "the entry exists" but "no block can reach a pin that
another block has judged unsafe". This test computes the reachability and
asserts it, because the layout that makes one exclusion sufficient and another
insufficient is not visible from reading the config.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _REPO_ROOT / ".github" / "dependabot.yml"

# `openai>=2.53.0`, `openai==2.53.0  # note`, `pkg[extra]>=1 ; marker`
_PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*[=<>!~]")
_INCLUDE = re.compile(r"^\s*-r\s+(\S+)")


def _normalise(name: str) -> str:
    """PyPI treats ``-``/``_``/``.`` and case as equivalent."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _version(text: str) -> tuple[int, ...] | None:
    """The ``>=`` version in *text* as a comparable tuple, or ``None``.

    Compared as a full tuple, never by major alone: ``tokenizers >=0.24.0``
    against a ``>=0.22.0`` floor is major 0 on both sides, and a major-only
    comparison calls that frozen when it is simply a cap. Every 0.x package
    would be a false positive.
    """
    match = re.search(r">=\s*(\d+(?:\.\d+)*)", text)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _resolve_includes(path: Path, seen: set[Path]) -> set[Path]:
    """Every requirements file reachable from *path* through ``-r``."""
    path = path.resolve()
    if path in seen or not path.is_file():
        return seen
    seen.add(path)
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _INCLUDE.match(line)
        if match:
            _resolve_includes(path.parent / match.group(1), seen)
    return seen


def _manifests_of(directory: str) -> list[Path]:
    """The requirements manifests a pip block owns directly."""
    base = _REPO_ROOT / directory.lstrip("/")
    if not base.is_dir():
        return []
    return sorted(base.glob("requirements*.txt"))


def _files_reachable_from(directory: str) -> set[Path]:
    """Every requirements file a block can edit, following ``-r``."""
    files: set[Path] = set()
    for manifest in _manifests_of(directory):
        _resolve_includes(manifest, files)
    return files


def _packages_pinned_in(file: Path) -> set[str]:
    """Normalised package names pinned in one file."""
    packages: set[str] = set()
    for line in file.read_text(encoding="utf-8").splitlines():
        match = _PIN.match(line)
        if match:
            packages.add(_normalise(match.group(1)))
    return packages


def _packages_reachable_from(directory: str) -> set[str]:
    """Normalised package names a block can propose, following ``-r``."""
    packages: set[str] = set()
    for file in _files_reachable_from(directory):
        packages |= _packages_pinned_in(file)
    return packages


def _pip_blocks() -> list[dict]:
    config = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    return [u for u in config["updates"] if u.get("package-ecosystem") == "pip"]


def _hard_excludes(block: dict) -> set[str]:
    """Packages this block hard-excludes by version range.

    A ``update-types`` ignore is deliberately not counted: #14431 recorded that
    a semver-major ignore does NOT stop a grouped ``all-dependencies`` bump from
    re-proposing the package. Only a ``versions:`` range actually holds.
    """
    return {
        _normalise(entry["dependency-name"])
        for entry in block.get("ignore", [])
        if entry.get("versions")
    }


def test_the_config_is_where_this_guard_expects() -> None:
    """A missing config would make every assertion below vacuous."""
    assert _CONFIG.is_file(), f"{_CONFIG} is missing"
    assert _pip_blocks(), "no pip blocks parsed — the guard would cover nothing"


def test_include_resolution_finds_the_known_chains() -> None:
    """Guard the guard: the reachability walk must actually walk.

    If ``-r`` resolution silently stopped working, every block's reachable set
    would shrink to its own directory and the assertion below would pass by
    covering nothing. These two chains are the ones that caused #14722.
    """
    reachable = _packages_reachable_from("/")
    assert "openai" in reachable, (
        "the root block should reach openai via requirements-dev.txt -> "
        "autobot-backend/requirements.txt and requirements-ci.txt -> "
        "requirements-ci/ai-ml.txt; if it no longer does, either the layout "
        "changed or this guard has stopped following -r includes"
    )


def test_a_hard_exclude_holds_in_every_block_that_can_reach_it() -> None:
    """The #14727 invariant, stated over FILES rather than package names.

    The leak is two blocks able to edit **the same physical pin**, which is
    what ``-r`` creates. Two blocks pinning a same-named package in their own
    separate manifests is not a leak — those are independent requirements that
    may legitimately sit at different ranges, and demanding they carry an
    identical exclusion is actively harmful: an exclusion below a manifest's
    own floor freezes that block out of every future update.

    This distinction is not academic. Stated over package names, this test
    demanded `websockets >=16.0.0` for `/autobot-slm-backend` (whose manifest
    pins `>=17.0.1,<18`) and `protobuf >=7.0.0` for the ai-stack block (whose
    manifest pins `>=7.35.1,<8.0.0`). Neither block has a single `-r` line, so
    neither can touch the file the exclusion protects — and both additions
    would have frozen those blocks permanently. The guard would have reported
    green while doing the opposite of its purpose.
    """
    blocks = _pip_blocks()
    files = {b["directory"]: _files_reachable_from(b["directory"]) for b in blocks}
    excluded = {b["directory"]: _hard_excludes(b) for b in blocks}

    gaps: list[str] = []
    for owner, packages in sorted(excluded.items()):
        for package in sorted(packages):
            # The specific files this owner protects for this package.
            protected = {f for f in files[owner] if package in _packages_pinned_in(f)}
            if not protected:
                continue
            for other in sorted(files):
                if other == owner or package in excluded[other]:
                    continue
                shared = protected & files[other]
                if shared:
                    names = ", ".join(sorted(str(f.relative_to(_REPO_ROOT)) for f in shared))
                    gaps.append(
                        f"{package!r} is hard-excluded in {owner!r}, but {other!r} "
                        f"can also edit {names} and does not exclude it"
                    )

    assert not gaps, (
        "a dependabot hard-exclude does not hold on a file another block can "
        "also edit (#14727). `-r` includes let one block edit a pin another "
        "block protects. Add the same `versions:` entry to the block named "
        "below — and use the value that protects THAT file, not a copied "
        "number:\n  " + "\n  ".join(gaps)
    )


def test_an_exclusion_never_sits_below_its_own_manifest_floor() -> None:
    """An exclusion under a block's own floor freezes it forever.

    This is the failure the previous version of the test above introduced. A
    block that pins ``websockets>=17.0.1`` and excludes ``>=16.0.0`` can never
    be offered any version at all — dependabot is told everything at or above
    16 is off limits while the manifest demands at least 17.
    """
    frozen: list[str] = []
    for block in _pip_blocks():
        directory = block["directory"]
        for entry in block.get("ignore", []):
            ranges = entry.get("versions") or []
            package = _normalise(entry.get("dependency-name", ""))
            for spec in ranges:
                excluded = _version(spec)
                if excluded is None:
                    continue
                for file in _files_reachable_from(directory):
                    for line in file.read_text(encoding="utf-8").splitlines():
                        pin = _PIN.match(line)
                        if not pin or _normalise(pin.group(1)) != package:
                            continue
                        floor = _version(line.split("#")[0])
                        if floor is not None and floor >= excluded:
                            frozen.append(
                                f"{directory!r} excludes {package} {spec} but "
                                f"{file.relative_to(_REPO_ROOT)} pins it at "
                                f"'{line.split('#')[0].strip()}' — the floor is at "
                                f"or above the exclusion, so no version can ever "
                                f"be offered"
                            )

    assert not frozen, (
        "an exclusion sits at or below its own manifest's floor, which freezes "
        "the block out of every future update rather than capping it:\n  "
        + "\n  ".join(sorted(set(frozen)))
    )


@pytest.mark.parametrize("package", ["openai"])
def test_the_known_offenders_stay_excluded_everywhere(package: str) -> None:
    """Pin the specific regression, so a future edit cannot quietly undo it."""
    blocks = _pip_blocks()
    reaching = [
        b["directory"]
        for b in blocks
        if _normalise(package) in _packages_reachable_from(b["directory"])
    ]
    assert reaching, f"no pip block reaches {package} — has it been removed?"

    missing = [d for d in reaching if _normalise(package) not in _hard_excludes(
        next(b for b in blocks if b["directory"] == d)
    )]
    assert not missing, (
        f"{package} is reachable from {missing} without a hard exclude there. "
        f"#14722 is what that costs: a grouped bump to an unsatisfiable major "
        f"that kills smoke-test at the Docker pip layer."
    )
