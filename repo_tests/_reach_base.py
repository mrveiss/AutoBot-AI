# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A reach floor computed from the base commit, not committed as a literal (#19676).

A committed ``floor=`` pins a guard against a population (all tracked Python, say) that
moves whenever any file is added, so unrelated PRs went stale on it and trains carried
re-pin commits across many test files (#19673). The floor has to come from somewhere the
PR under test cannot move. Running the PR's own ``discover`` over the base tree is not that:
a narrowed glob or filter shrinks the base count by the same amount, and the floor follows it
down. So the base population is measured by the BASE's declaration -- the guard module as it
was at the base commit, imported from the base tree in a separate ``python -I`` process:

    floor = population the base's declaration finds at the base - skips - growth

which is the bottom of the window a pinned floor had to sit in, so the meaning is kept: the
PR may shrink the population by up to ``growth``, and ``completed()`` must still reach the
floor. The base is the one :func:`repo_tests._ratchet_base.base_commit` resolves. A base that
cannot be read or measured raises :class:`BaseUnavailable`, never a pass. A declaration the
base does not have (a guard new in this PR) is refused the same way: pin ``floor=`` until it
lands.

The base tree is one detached ``git worktree`` per process, in its own directory under the
system temp dir, checked out with ``read-tree`` so the repository's checkout hooks never run on
it, and removed (then pruned) when the process exits. A guard whose ``discover`` reads untracked
or generated files cannot be measured at the base and keeps an explicit ``floor=``; it is listed
in :data:`PINNED_BY_DESIGN`, which ``reach_base_floor_19676_test`` holds to pinned declarations.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repo_tests._ratchet_base import BaseUnavailable, base_commit

from autobot_shared.paths import scrubbed_git_env

if TYPE_CHECKING:
    from repo_tests._reach import Reach

REPO_ROOT = Path(__file__).resolve().parents[1]
TREE_PREFIX = "autobot-reach-base-"
#: A base tree left by a killed process is removed on the next first use once it is this old.
_STALE_AFTER_S = 6 * 3600

#: Declarations that keep an explicit ``floor=`` because their population cannot be measured at
#: the base, each with the reason. Empty: measured on all declarations, the base and live
#: populations agree (see #20731).
PINNED_BY_DESIGN: dict[str, str] = {}

_TREE: dict[str, Path] = {}
_BASE_COUNT: dict[str, int] = {}
_BASE_FAILED: dict[str, str] = {}

#: Runs in the base tree: imports each declaring module from there and prints what the base's
#: declarations find. One marker line, so a module that logs to stdout cannot corrupt the answer.
_MEASURE = r"""
import configparser, importlib.util, json, sys
from pathlib import Path
base, wanted = Path(sys.argv[1]), json.loads(sys.argv[2])
ini = configparser.ConfigParser(interpolation=None)
ini.read(base / "pytest.ini", encoding="utf-8")
sys.path[:0] = [str(base / p) for p in ini["pytest"]["pythonpath"].split()]
errors = {}
for name, rel in wanted:
    try:
        spec = importlib.util.spec_from_file_location(name, base / rel)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception as exc:
        errors[rel] = f"{type(exc).__name__}: {exc}"[:300]
from repo_tests._reach import REGISTRY
counts = {}
for key, reach in REGISTRY.items():
    try:
        counts[key] = len(reach.population(base))
    except Exception as exc:
        errors[key] = f"{type(exc).__name__}: {exc}"[:300]
sys.stdout.write("\nREACH-BASE " + json.dumps({"counts": counts, "errors": errors}) + "\n")
"""


def _git(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=600, env=scrubbed_git_env()
    )


def _sweep_stale_trees() -> None:
    """Remove base trees a killed process left behind; a live one (younger) is never touched."""
    for old in Path(tempfile.gettempdir()).glob(f"{TREE_PREFIX}*"):
        if old.is_dir() and time.time() - old.stat().st_mtime > _STALE_AFTER_S:
            shutil.rmtree(old, ignore_errors=True)
    _git("worktree", "prune")


def base_tree() -> Path:
    """The base commit checked out once for this process, in its own temp directory."""
    if "tree" in _TREE:
        return _TREE["tree"]
    _sweep_stale_trees()
    sha = base_commit(REPO_ROOT)
    tree = Path(tempfile.mkdtemp(prefix=TREE_PREFIX))
    added = _git("worktree", "add", "--detach", "--no-checkout", str(tree), sha)
    if added.returncode != 0:
        shutil.rmtree(tree, ignore_errors=True)
        raise BaseUnavailable(f"git worktree add failed ({added.stderr.strip()}); no floor without the base.")
    atexit.register(remove_base_tree, tree)
    out = _git("read-tree", "-u", "--reset", "HEAD", cwd=tree)
    if out.returncode != 0:
        remove_base_tree(tree)
        raise BaseUnavailable(f"checking out the base failed ({out.stderr.strip()}).")
    _TREE["tree"] = tree
    return tree


def remove_base_tree(tree: Path) -> None:
    """Remove the base worktree and its record; fall back to deleting the directory, and say so."""
    try:
        out = _git("worktree", "remove", str(tree))
        if out.returncode != 0 and tree.exists():
            warnings.warn(f"git worktree remove {tree} failed ({out.stderr.strip()}); deleting it", stacklevel=2)
            shutil.rmtree(tree, ignore_errors=True)
    finally:
        _git("worktree", "prune")
        _TREE.pop("tree", None)


def _declaring_file(reach: "Reach[Any]") -> str:
    module = sys.modules.get(reach.module)
    path = Path(getattr(module, "__file__", "") or "")
    if not reach.module or not path.is_file():
        raise BaseUnavailable(f"[{reach.name}] its declaring module is unknown, so the base cannot be measured.")
    return str(path.resolve().relative_to(REPO_ROOT))


def _measure_at_base(reaches: list["Reach[Any]"]) -> None:
    """Measure every declaration in *reaches* with the base's own code, in one base process."""
    wanted = sorted({(r.module, _declaring_file(r)) for r in reaches})
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run(
        [sys.executable, "-I", "-c", _MEASURE, str(base_tree()), json.dumps(wanted)],
        cwd=base_tree(), capture_output=True, text=True, timeout=1800, env=env,
    )  # fmt: skip
    line = next((ln for ln in reversed(out.stdout.splitlines()) if ln.startswith("REACH-BASE ")), None)
    if line is None:
        raise BaseUnavailable(f"measuring the base failed (exit {out.returncode}): {out.stderr.strip()[-800:]}")
    result = json.loads(line[len("REACH-BASE ") :])
    _BASE_COUNT.update(result["counts"])
    for reach in reaches:
        if reach.name not in _BASE_COUNT:
            _BASE_FAILED[reach.name] = result["errors"].get(reach.name) or _declaring_file(reach)


def base_population(reach: "Reach[Any]") -> int:
    """What the BASE's declaration of *reach* finds at the base; measured once per process."""
    if reach.name not in _BASE_COUNT and reach.name not in _BASE_FAILED:
        from repo_tests._reach import REGISTRY  # noqa: PLC0415 - _reach imports this module

        pending = [r for r in REGISTRY.values() if r.computed and r.name not in _BASE_COUNT]
        _measure_at_base(pending if reach in pending else [*pending, reach])
    if reach.name not in _BASE_COUNT:
        raise BaseUnavailable(
            f"[{reach.name}] the base has no declaration by this name ({_BASE_FAILED.get(reach.name)}): "
            f"a guard new in this PR pins floor= until it lands, then the pin can go (#19676)."
        )
    return _BASE_COUNT[reach.name]


def computed_floor(reach: "Reach[Any]") -> int:
    """``base population - skips - growth``, the bottom of the pinned-floor window; refuses a non-positive one."""
    floor = base_population(reach) - reach.skips - reach.growth
    if floor <= 0:
        raise BaseUnavailable(
            f"[{reach.name}] the base population leaves a floor of {floor} after skips+growth: that asserts "
            f"nothing. Pin floor= or lower growth."
        )
    return floor


class BaseFloor:
    """Gives :class:`~repo_tests._reach.Reach` its ``floor``: the pinned one, or the base's."""

    pinned_floor: int
    min_fraction: float | None

    @property
    def floor(self) -> int:
        """The declared ``floor=`` when one was pinned, else the floor computed from the base.

        A ``min_fraction`` declaration has no count floor at all (its bound is a fraction), so 0.
        """
        if self.pinned_floor or self.min_fraction is not None:
            return self.pinned_floor
        return computed_floor(self)  # type: ignore[arg-type]

    @property
    def computed(self) -> bool:
        """True for a count floor that nothing pinned: there is no constant to go stale."""
        return not self.pinned_floor and self.min_fraction is None
