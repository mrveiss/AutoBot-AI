# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One ratchet engine, configured per language (#17377 AC1).

`scripts/check_python_file_size.py` and `scripts/check_shell_file_size.py` implemented the
same ratchet twice. #17377 enumerated what genuinely differs -- the glob, ``MAX_LINES``, the
ceilings mapping, the excluded prefixes, the reach floor and two repo-relative path strings
-- and that list is this module's :class:`GateConfig`. Anything a gate needs beyond it is a
finding, not a configuration.

**``root`` and ``logger`` are parameters, not module state, and that is the point.** The
Python gate's ratchet test reached inside the hook with twelve
``monkeypatch.setattr(hook, …)`` calls against ``repo_root``, ``KNOWN_LARGE``,
``tracked_python_files`` and ``audit_ceilings``, because there was no other way to point it
at a synthetic tree. An engine resolving those names through itself would ignore every one
of them, so #17377 named the rewrite as a precondition of the extraction. Passing the root
and the config in removes the need for the patches rather than relocating it: a test builds
a ``GateConfig`` and a ``tmp_path`` and calls the function.

The logger is passed rather than owned so each gate keeps its own ``__name__`` in the
records -- the ratchet tests capture by logger name, and a shared engine logger would make
both gates' findings arrive under one name.

ONE DIFFERENCE WAS OUTSIDE THE ENUMERATED SURFACE, and it is resolved here deliberately:
the shell gate's commit path filtered ``EXCLUDED_PREFIXES`` and the Python gate's did not.
Both hooks carry a matching ``exclude:`` in ``.pre-commit-config.yaml``, so pre-commit never
hands either an excluded file and neither was wrong -- but a gate invoked directly, by a
developer or a script, has no pre-commit in front of it. :func:`check_paths` keeps the
filter, which is the safer of the two and strictly adds to the Python path.
"""

from __future__ import annotations

import logging
import pathlib
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from autobot_shared.paths import scrubbed_git_env


@dataclass(frozen=True)
class GateConfig:
    """Everything that differs between one size gate and another.

    Frozen because a gate's identity is not something a caller should edit at runtime; a
    test that needs different values builds a different config, which is the seam.
    """

    #: Name in the clean-run summary, e.g. ``"python-file-size"``.
    label: str
    #: Hard limit for a file with no recorded ceiling.
    max_lines: int
    #: Repo-relative path of the gate itself, quoted in messages asking for an edit.
    self_rel: str
    #: Repo-relative path of the DATA module holding the second copy of the ceilings.
    ratchet_rel: str
    #: Path prefixes out of scope, mirroring the hook's ``exclude:`` in pre-commit.
    excluded_prefixes: tuple[str, ...]
    #: Floor for the tree walk: below this the walk covered almost nothing (#14547).
    min_tracked_files: int
    #: Grandfathered files and their recorded ceilings. Shrinks only.
    known_large: Mapping[str, int]
    #: ``git ls-files`` patterns selecting this gate's language. A tuple because a language
    #: can have more than one extension -- the frontend gate covers ``*.ts`` and ``*.vue`` --
    #: and ``git ls-files`` takes several pathspecs in one call, so one subprocess still does.
    globs: tuple[str, ...]


def normalise(path: str) -> str:
    """Forward-slash repo-relative form used as the ceilings key."""
    return str(path).replace("\\", "/")


def count_lines(path: pathlib.Path) -> int | None:
    """Line count for *path*, or None when it cannot be read.

    ``UnicodeDecodeError`` is not an ``OSError``, and is raised lazily while the generator
    is consumed, still inside this ``try`` -- one non-UTF-8 file must not crash the audit.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except (OSError, UnicodeDecodeError):
        return None


def tracked_files(cfg: GateConfig, root: pathlib.Path) -> list[str]:
    """In-scope, git-tracked paths matching ``cfg.glob`` under *root*, relative to it.

    Git-tracked so the walk can only see what pre-commit could have staged -- a stray local
    file cannot masquerade as a repo file. ``cfg.excluded_prefixes`` mirrors the hook's own
    ``exclude:``, so the audit's scope and the staged-file scope are the same set (#14547).
    """
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell, no caller input
        ["git", "ls-files", *cfg.globs],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        # An inherited GIT_DIR outranks `cwd=` and would enumerate another checkout's
        # index while *root* names this one (#14896).
        env=scrubbed_git_env(),
    )
    return [line for line in out.stdout.splitlines() if line.strip() and not line.startswith(cfg.excluded_prefixes)]


def _grandfathered_verdict(cfg: GateConfig, rel: str, line_count: int, ceiling: int) -> str | None:
    """Violation message for a recorded file, or None when it is exactly at its ceiling."""
    if line_count <= cfg.max_lines:
        return (
            f"{rel}: {line_count} lines — now within the {cfg.max_lines}-line limit. "
            f"Delete its KNOWN_LARGE entry in {cfg.self_rel} and its RATCHET_BASELINE "
            f"entry in {cfg.ratchet_rel}: an entry naming a compliant file exempts "
            "nothing while looking authoritative."
        )
    if line_count > ceiling:
        return (
            f"{rel}: {line_count} lines, over its recorded ceiling of {ceiling}. "
            "A grandfathered file may not grow — the exemption freezes "
            "the size it was granted for, it does not license more."
        )
    if line_count < ceiling:
        return (
            f"{rel}: {line_count} lines, under its recorded ceiling of {ceiling}. "
            f"Lower the ceiling to {line_count} in {cfg.self_rel} and the matching "
            f"RATCHET_BASELINE entry in {cfg.ratchet_rel} — the ratchet only turns "
            "down, and an unlowered ceiling re-licenses the lines just cut."
        )
    return None


def verdict(cfg: GateConfig, rel: str, line_count: int) -> str | None:
    """Violation message for *rel* at *line_count* lines, or None if acceptable."""
    ceiling = cfg.known_large.get(normalise(rel))
    if ceiling is not None:
        return _grandfathered_verdict(cfg, rel, line_count, ceiling)
    if line_count > cfg.max_lines:
        return (
            f"{rel}: {line_count} lines (max {cfg.max_lines}). Split it — do not add "
            f"a KNOWN_LARGE entry in {cfg.self_rel}, which grandfathers what already "
            "existed and is not a way in for new files."
        )
    return None


def vanished_entry_problem(cfg: GateConfig, rel: str, root: pathlib.Path) -> str:
    """Message for a recorded entry the tree walk never reached."""
    return (
        f"{rel}: not found by the tracked-file walk under {root} — this entry "
        f"(ceiling {cfg.known_large[rel]}) names a file that moved or was deleted. "
        f"Remove it from {cfg.self_rel} and its RATCHET_BASELINE entry in {cfg.ratchet_rel}."
    )


def unmeasured(rel: str) -> str:
    """Violation message for a path that could not be read at all.

    ``count_lines`` returns None for "missing", "unreadable", "not a file" and "not UTF-8"
    alike, and the walk treats that None as a finding rather than skipping it. Exit 0 is only
    entitled to mean *within the limit*, and a file that was never opened has not earned that
    (#14975). Takes no config: the wording carries no per-gate value, and both gates emitted
    it identically before the extraction -- which `gate_reporting_parity_17377_test.py`
    asserts, so a paraphrase here would be a silent divergence.
    """
    return (
        f"{rel}: could not be read, so its size was never measured. This is not "
        "a size violation — check the path, its permissions, whether it is a "
        "broken symlink, and whether it decodes as UTF-8. An unmeasured file "
        "is not a passing one."
    )


def report_unmeasured(rel: str, seen: set[str], problems: list[str]) -> None:
    """Report an unreadable file, and record it as SEEN but not as REACHED.

    NOT a skip (#14975). ``seen`` answers "did the walk find this path", which it did, so the
    ``known_large - seen`` pass must not ALSO call it moved-or-deleted -- that message is
    wrong for a file that exists and cannot be read, and reporting both tells the developer
    two stories about one file. ``reached`` stays exclusive, so an unmeasured file cannot
    prop up the floor check without having been ruled on.
    """
    problems.append(unmeasured(rel))
    seen.add(normalise(rel))


def reach_breach_problem(cfg: GateConfig, reached: int) -> str:
    """The reach-breach finding, worded identically in both gates (#17377).

    The actionable half -- which knob to check -- was in the shell gate only; a Python
    developer got "covers almost nothing" and no next step.
    """
    return (
        f"reach check: the tree walk reached {reached} tracked file(s), under the "
        f"{cfg.min_tracked_files}-file floor — it stopped covering the tree, so this "
        f"run's verdict covers almost nothing. Check EXCLUDED_PREFIXES in {cfg.self_rel} "
        "and that `git ls-files` works from the repo root."
    )


def scan_tracked_files(cfg: GateConfig, root: pathlib.Path, tracked: list[str]) -> tuple[int, set[str], list[str]]:
    """Rule on every readable file in *tracked*. Returns ``(reached, seen, problems)``.

    ``reached`` counts files actually read off disk, not ``len(tracked)``: one that cannot be
    opened must not inflate the floor check in :func:`run_audit` without having been ruled on.
    """
    seen: set[str] = set()
    problems: list[str] = []
    reached = 0
    for rel in sorted(tracked):
        line_count = count_lines(root / rel)
        if line_count is None:
            report_unmeasured(rel, seen, problems)
            continue
        reached += 1
        seen.add(normalise(rel))
        message = verdict(cfg, rel, line_count)
        if message is not None:
            problems.append(message)
    return reached, seen, problems


def audit_ceilings(
    cfg: GateConfig,
    root: pathlib.Path,
    *,
    enumerate_files: Callable[[pathlib.Path], list[str]] | None = None,
    scan: Callable[[pathlib.Path, list[str]], tuple[int, set[str], list[str]]] | None = None,
) -> tuple[int, list[str]]:
    """Rule on every in-scope tracked file, not just the ceilings mapping's keys.

    Walking the tree (#14547) instead of ``known_large.items()`` is the actual fix: a
    dict-only scan can only re-check a file someone already added, so a file that grows past
    the limit without ever being added stays invisible forever -- which is how
    ``reconciler.py`` reached 2000+ lines unnoticed. Entries the walk never reaches are still
    reported.

    *root* is a parameter rather than a call to a module-level ``repo_root()``, which is what
    lets a test point this at a synthetic tree without patching the gate (#17377 AC2).
    """
    # The collaborators are injectable because the gates' tests patch THEIR module's copies
    # to point at a synthetic tree. An engine that called its own would ignore those patches
    # silently, which is #17377 AC2's warning arriving inside the extraction itself -- found
    # by running the existing parity test against a first version that did exactly that.
    files = enumerate_files(root) if enumerate_files else tracked_files(cfg, root)
    scanner = scan or (lambda r, t: scan_tracked_files(cfg, r, t))
    reached, seen, problems = scanner(root, files)
    for rel in sorted(set(cfg.known_large) - seen):
        problems.append(vanished_entry_problem(cfg, rel, root))
    return reached, problems


def configure_logging(logger: logging.Logger) -> None:
    """Attach a stderr handler so findings actually reach the developer.

    Run as a bare script the gate's logger has no handler, and logging's ``lastResort``
    fallback emits WARNING and above only -- the informational "all live" line would vanish
    silently. Findings are logged at ERROR precisely so they survive even when this was never
    called. The logger is passed so each gate keeps its own ``__name__`` in the records.
    """
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


def run_audit(
    cfg: GateConfig,
    root: pathlib.Path,
    logger: logging.Logger,
    *,
    audit: Callable[[], tuple[int, list[str]]] | None = None,
) -> int:
    """The audit path: rule on the whole tree, and refuse a walk that covered too little.

    *audit* is injectable for the same reason the collaborators above are: the parity test
    patches the gate's ``audit_ceilings`` to drive the reach-breach branch, and that patch has
    to be the thing this calls.
    """
    reached, problems = audit() if audit else audit_ceilings(cfg, root)
    if reached < cfg.min_tracked_files:
        problems.append(reach_breach_problem(cfg, reached))
    if problems:
        logger.error("%s", "\n".join(problems))
        return 1
    logger.info(
        "%s ceilings: %d files scanned, %d grandfathered, all live and at size.",
        cfg.label,
        reached,
        len(cfg.known_large),
    )
    return 0


def check_paths(cfg: GateConfig, root: pathlib.Path, paths: list[str], logger: logging.Logger) -> int:
    """The commit path: rule on the staged files pre-commit passed in.

    The excluded-prefix filter is kept from the shell gate, where the Python gate had none.
    Both hooks carry a matching ``exclude:`` in pre-commit so neither was wrong, but a gate
    invoked directly has no pre-commit in front of it (#17377).
    """
    problems: list[str] = []
    for raw in paths:
        rel = normalise(raw)
        if rel.startswith(cfg.excluded_prefixes):
            continue
        line_count = count_lines(root / rel)
        if line_count is None:
            problems.append(unmeasured(rel))
            continue
        message = verdict(cfg, rel, line_count)
        if message is not None:
            problems.append(message)
    if problems:
        # ERROR, not INFO: this is the COMMIT path, so a finding here blocks a push. Below
        # `lastResort`'s WARNING threshold it would vanish on any path that never called
        # `configure_logging`, leaving a hook that refuses the push and says nothing.
        logger.error("%s", "\n".join(problems))
        return 1
    return 0
