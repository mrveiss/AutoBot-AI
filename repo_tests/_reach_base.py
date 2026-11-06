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

The base tree is one directory per base commit in a private per-user cache under the system temp
dir, shared by every xdist worker and concurrent run: built once under a file lock from
``git archive`` into a temp dir and renamed into place, so it is never half-built and never a
registered ``git worktree`` (#20875). SIGTERM removes this process's partial builds; trees for other
commits are pruned after a TTL. A guard whose ``discover`` reads untracked
or generated files cannot be measured at the base and keeps an explicit ``floor=``; it is listed
in :data:`PINNED_BY_DESIGN`, which ``reach_base_floor_19676_test`` holds to pinned declarations.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import BaseUnavailable, base_commit

from autobot_shared.paths import scrubbed_git_env

if TYPE_CHECKING:
    from repo_tests._reach import Reach

REPO_ROOT = repo_root()
TREE_PREFIX = "autobot-reach-base-"
#: Env var naming the cache directory that holds the base trees; default is under the system temp dir.
CACHE_DIR_ENV = "AUTOBOT_REACH_BASE_CACHE_DIR"
#: A tree for another commit (or a partial build) untouched for this long is pruned on the next use.
_STALE_AFTER_S = int(os.environ.get("AUTOBOT_REACH_BASE_TTL_S", str(6 * 3600)))

#: Declarations that keep an explicit ``floor=`` because their population cannot be measured at
#: the base, each with the reason. Empty: measured on all declarations, the base and live
#: populations agree (see #20731).
PINNED_BY_DESIGN: dict[str, str] = {}

_TREE: dict[str, Path] = {}
#: Temp build dirs this process created and has not yet renamed into place; SIGTERM removes only these.
_PARTIAL: set[Path] = set()
_PREVIOUS_HANDLER: dict[int, Any] = {}
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


def _cache_root() -> Path:
    """The per-user directory holding every base tree; private to this user, never in the repo."""
    root = Path(os.environ.get(CACHE_DIR_ENV) or Path(tempfile.gettempdir()) / f"{TREE_PREFIX}cache-{os.getuid()}")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_uid != os.getuid():
        raise BaseUnavailable(f"{root} is owned by another user; refusing to read a base tree from it.")
    return root


@contextlib.contextmanager
def _locked(root: Path) -> Iterator[None]:
    """Hold the cache's exclusive lock: all xdist workers and concurrent runs queue here."""
    fd = os.open(root / ".lock", os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the flock


def _prune(root: Path, keep: Path) -> None:
    """Remove trees for other commits, and partial builds, that nobody has touched for the TTL."""
    for old in root.iterdir():
        if old == keep or not old.is_dir() or time.time() - old.stat().st_mtime <= _STALE_AFTER_S:
            continue
        shutil.rmtree(old)


def _extract(sha: str, into: Path) -> None:
    """Materialise *sha* in *into* from ``git archive``; nothing is registered with git."""
    with subprocess.Popen(
        ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", sha],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=scrubbed_git_env(),
    ) as proc:  # fmt: skip
        assert proc.stdout is not None
        with tarfile.open(fileobj=proc.stdout, mode="r|") as archive:
            archive.extractall(into, filter="data")
        stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.returncode != 0:
        raise BaseUnavailable(f"git archive {sha} failed ({stderr.strip()}); no floor without the base.")


def _index(sha: str, tree: Path) -> None:
    """Give the extracted *tree* its own standalone repository holding *sha*'s index.

    ``git ls-files`` (what every ``discover`` runs) needs one. It borrows the source repository's
    objects through ``alternates`` and records nothing in the source's ``.git/worktrees``.
    """
    objects = _git("rev-parse", "--path-format=absolute", "--git-path", "objects")
    if objects.returncode != 0:
        raise BaseUnavailable(f"cannot locate the object store ({objects.stderr.strip()}).")
    steps = (("init", "--quiet"), ("read-tree", sha), ("update-ref", "--no-deref", "HEAD", sha))
    for i, step in enumerate(steps):
        if i == 1:
            (tree / ".git" / "objects" / "info" / "alternates").write_text(objects.stdout, encoding="utf-8")
        out = _git(*step, cwd=tree)
        if out.returncode != 0:
            raise BaseUnavailable(f"git {step[0]} in the base tree failed ({out.stderr.strip()}).")


def _remove_partials(*_signal_args: object) -> None:
    for partial in list(_PARTIAL):
        shutil.rmtree(partial, ignore_errors=True)
    _PARTIAL.clear()


def _on_sigterm(signum: int, frame: FrameType | None) -> None:
    """Drop this process's partial builds, then let the previous disposition act (default: die)."""
    _remove_partials()
    previous = _PREVIOUS_HANDLER.get(signum, signal.SIG_DFL)
    if callable(previous):
        previous(signum, frame)
        return
    if previous == signal.SIG_IGN:
        return
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _build(root: Path, sha: str, final: Path) -> None:
    """Extract into a private temp dir, then rename it into place: *final* is never half-built."""
    partial = Path(tempfile.mkdtemp(prefix=".partial-", dir=root))
    _PARTIAL.add(partial)
    try:
        _extract(sha, partial)
        _index(sha, partial)
        partial.rename(final)
    except BaseException:
        _remove_partials()
        raise
    _PARTIAL.discard(partial)


def base_tree() -> Path:
    """The base commit's tree: one per commit, shared by every worker and run, built once."""
    if "tree" in _TREE:
        return _TREE["tree"]
    sha = base_commit(REPO_ROOT)
    root = _cache_root()
    final = root / f"{TREE_PREFIX}{sha}"
    can_trap = threading.current_thread() is threading.main_thread()
    with _locked(root):
        if can_trap:
            _PREVIOUS_HANDLER[signal.SIGTERM] = signal.signal(signal.SIGTERM, _on_sigterm)
        try:
            if not final.is_dir():
                _build(root, sha, final)
            os.utime(final)
            _prune(root, keep=final)
        finally:
            if can_trap:
                signal.signal(signal.SIGTERM, _PREVIOUS_HANDLER.pop(signal.SIGTERM))
    _TREE["tree"] = final
    return final


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
