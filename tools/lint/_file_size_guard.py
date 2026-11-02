# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One file-size guard core for the Python, shell and frontend gates (#18954).

``scripts/check_{python,shell,frontend}_file_size.py`` were one guard written
three times: ``count_lines``, ``normalise``, ``unmeasured``, the three-way
ceiling ``verdict``, the tree walk, ``audit_ceilings``, ``run_audit`` and the
staged-path check, each pasted with a different extension. This module holds
the single implementation; each script keeps only its *configuration* (the
``MAX_LINES`` / ``KNOWN_LARGE`` / ``EXCLUDED_PREFIXES`` / floor constants, the
git globs, the wording of the clean-run summary) and its CLI.

The ratchet semantics (grandfathered files may not grow, a file under its
ceiling must lower it, a file now compliant must drop its entry, a file that
cannot be read is a violation and never a skip) are unchanged; they are
documented once in each script's module docstring.

``FileSizeGuard`` reads its configuration from the *live namespace of the
script that owns it* on every call, not from a snapshot taken at import. That
is what lets the ratchet tests keep monkeypatching ``KNOWN_LARGE``,
``repo_root``, ``audit_ceilings`` or ``tracked_*_files`` on the script module
and have the shared logic see the substitution.

Plain stdlib logging, deliberately (#1082): this runs inside bare pre-commit
hooks, where ``autobot_shared.logging_manager`` would drag config loading onto
every commit.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from collections.abc import MutableMapping
from typing import Any

from autobot_shared.paths import scrubbed_git_env


def normalise(path: str) -> str:
    """Forward-slash repo-relative form used as the KNOWN_LARGE key."""
    return str(path).replace("\\", "/")


def count_lines(path: pathlib.Path) -> int | None:
    """Line count for *path*, or None when it cannot be read.

    ``UnicodeDecodeError`` is not an ``OSError`` and is raised lazily while the
    generator below is consumed, still inside this ``try`` -- one undecodable
    file must not crash the whole audit.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except (OSError, UnicodeDecodeError):
        return None


def unmeasured(rel: str) -> str:
    """Violation message for a path that could not be read at all.

    ``count_lines`` returns None for "missing", "unreadable", "not a file" and
    "not UTF-8" alike. That is a finding on every path: exit 0 is only entitled
    to mean *within the limit*, and a file never opened has not earned that
    (#14975).
    """
    return (
        f"{rel}: could not be read, so its size was never measured. This is not "
        "a size violation — check the path, its permissions, whether it is a "
        "broken symlink, and whether it decodes as UTF-8. An unmeasured file "
        "is not a passing one."
    )


def load_known_large(script_file: str, data_module: str) -> dict[str, int]:
    """Load ``KNOWN_LARGE`` from the data module beside *script_file*, by path.

    By path rather than ``import`` so it still resolves when the script is
    loaded through ``importlib.util`` (as the ratchet tests do) and not only
    when run directly.
    """
    path = pathlib.Path(script_file).resolve().parent / data_module
    spec = importlib.util.spec_from_file_location(f"_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.KNOWN_LARGE


def git_tracked(root: pathlib.Path, globs: tuple[str, ...], excluded: tuple[str, ...]) -> list[str]:
    """In-scope, git-tracked paths matching *globs* under *root*, relative to it.

    Git-tracked so the walk can only see what pre-commit could have staged; a
    stray local file cannot masquerade as a repo file. *excluded* mirrors the
    script's own ``exclude:`` in ``.pre-commit-config.yaml``.
    """
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell, no caller input
        ["git", "ls-files", *globs],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        # An inherited GIT_DIR outranks `cwd=` and would enumerate another
        # checkout's index while *root* names this one (#14896).
        env=scrubbed_git_env(),
    )
    return [line for line in out.stdout.splitlines() if line.strip() and not line.startswith(excluded)]


class FileSizeGuard:
    """The shared ratchet logic, configured by the owning script's namespace.

    *namespace* is the script's ``globals()``. It must hold the configuration
    (``MAX_LINES``, ``KNOWN_LARGE``, ``SELF_REL``,
    ``EXCLUDED_PREFIXES``, ``logger``, ``repo_root``) and the script-level
    bindings of the methods below under their historical names
    (``verdict``, ``audit_ceilings``, ``_scan_tracked_files``, ...), so a
    substitution made on the script is honoured by every caller.
    *floor_name* and *tracked_name* name the per-language reach-floor constant
    and tracked-file enumerator; *summary* is the clean-run log format.
    """

    def __init__(self, namespace: MutableMapping[str, Any], *, floor_name: str, tracked_name: str, summary: str):
        self._ns = namespace
        self._floor_name = floor_name
        self._tracked_name = tracked_name
        self._summary = summary

    def _get(self, name: str) -> Any:
        return self._ns[name]

    def grandfathered_verdict(self, rel: str, line_count: int, ceiling: int) -> str | None:
        """Violation message for a KNOWN_LARGE file, or None when it is at ceiling."""
        max_lines, self_rel = self._get("MAX_LINES"), self._get("SELF_REL")
        if line_count <= max_lines:
            return (
                f"{rel}: {line_count} lines — now within the {max_lines}-line limit. "
                f"Delete its KNOWN_LARGE entry in {self_rel}: an entry naming a compliant "
                "file exempts nothing while looking authoritative."
            )
        if line_count > ceiling:
            return (
                f"{rel}: {line_count} lines, over its recorded ceiling of {ceiling}. "
                "A grandfathered file may not grow — the exemption freezes the size "
                "it was granted for, it does not license more."
            )
        if line_count < ceiling:
            return (
                f"{rel}: {line_count} lines, under its recorded ceiling of {ceiling}. "
                f"Lower the ceiling to {line_count} in {self_rel} — the ratchet only "
                "turns down, and an unlowered ceiling re-licenses the lines just cut."
            )
        return None

    def verdict(self, rel: str, line_count: int) -> str | None:
        """Violation message for *rel* at *line_count* lines, or None if acceptable."""
        ceiling = self._get("KNOWN_LARGE").get(normalise(rel))
        if ceiling is not None:
            return self._get("_grandfathered_verdict")(rel, line_count, ceiling)
        max_lines = self._get("MAX_LINES")
        if line_count > max_lines:
            return (
                f"{rel}: {line_count} lines (max {max_lines}). Split it — do not add "
                f"a KNOWN_LARGE entry in {self._get('SELF_REL')}, which grandfathers what already "
                "existed and is not a way in for new files."
            )
        return None

    def vanished_entry_problem(self, rel: str, root: pathlib.Path) -> str:
        """Message for a KNOWN_LARGE entry the tree walk never reached."""
        return (
            f"{rel}: not found by the tracked-file walk under {root} — this entry "
            f"(ceiling {self._get('KNOWN_LARGE')[rel]}) names a file that moved or was deleted. "
            f"Remove it from {self._get('SELF_REL')}."
        )

    def report_unmeasured(self, rel: str, seen: set[str], problems: list[str]) -> None:
        """Report a file that could not be read: SEEN but not REACHED (#14975).

        ``seen`` answers "did the walk find this path" (it did, so the
        ``KNOWN_LARGE - seen`` pass must not also call it moved-or-deleted);
        ``reached`` stays exclusive so an unmeasured file cannot prop up the
        floor check in ``run_audit`` without having been ruled on.
        """
        problems.append(self._get("unmeasured")(rel))
        seen.add(normalise(rel))

    def scan_tracked_files(self, root: pathlib.Path, tracked: list[str]) -> tuple[int, set[str], list[str]]:
        """Rule on every readable file in *tracked*. Returns (reached, seen, problems).

        ``reached`` counts files actually read off disk, not ``len(tracked)``:
        a file that cannot be opened must not inflate the floor check.
        """
        seen: set[str] = set()
        problems: list[str] = []
        reached = 0
        for rel in sorted(tracked):
            line_count = self._get("count_lines")(root / rel)
            if line_count is None:
                self._get("_report_unmeasured")(rel, seen, problems)
                continue
            reached += 1
            seen.add(normalise(rel))
            message = self._get("verdict")(rel, line_count)
            if message is not None:
                problems.append(message)
        return reached, seen, problems

    def audit_ceilings(self) -> tuple[int, list[str]]:
        """Rule on every in-scope tracked file, not just KNOWN_LARGE's keys (#14547).

        A dict-only scan can only re-check a file someone already added, so a
        file that grows past MAX_LINES without being added stays invisible to
        every run. Entries the walk never reaches are still reported.
        """
        root = self._get("repo_root")()
        tracked = self._get(self._tracked_name)(root)
        reached, seen, problems = self._get("_scan_tracked_files")(root, tracked)
        for rel in sorted(set(self._get("KNOWN_LARGE")) - seen):
            problems.append(self._get("_vanished_entry_problem")(rel, root))
        return reached, problems

    def reach_breach_problem(self, reached: int) -> str:
        """The reach-breach finding, worded identically in all three gates (#17377)."""
        return (
            f"reach check: the tree walk reached {reached} tracked file(s), under the "
            f"{self._get(self._floor_name)}-file floor — it stopped covering the tree, so this "
            f"run's verdict covers almost nothing. Check EXCLUDED_PREFIXES in {self._get('SELF_REL')} "
            "and that `git ls-files` works from the repo root."
        )

    def run_audit(self) -> int:
        """``--audit-ceilings``: walk the tree, and assert the walk actually reached it.

        The reach breach is *collected* alongside the violations, not returned
        on: it explains the violations, so suppressing them hid the evidence of
        what the short walk missed.
        """
        reached, problems = self._get("audit_ceilings")()
        if reached < self._get(self._floor_name):
            problems.append(self._get("_reach_breach_problem")(reached))
        logger = self._get("logger")
        if problems:
            logger.error("%s", "\n".join(problems))
            return 1
        logger.info(self._summary, reached, len(self._get("KNOWN_LARGE")))
        return 0

    def rule_on(self, rel: str, path: pathlib.Path) -> str | None:
        """Finding for one staged path (unmeasured or over-limit), or None if it passes."""
        line_count = self._get("count_lines")(path)
        if line_count is None:
            return self._get("unmeasured")(rel)
        return self._get("verdict")(rel, line_count)

    def check_paths(self, paths: list[str]) -> int:
        """The commit path: rule on the staged files pre-commit passed in."""
        root = self._get("repo_root")()
        excluded = self._get("EXCLUDED_PREFIXES")
        findings: list[str] = []
        for raw in paths:
            rel = normalise(raw)
            if rel.startswith(excluded):
                continue
            message = self.rule_on(rel, root / rel)
            if message is not None:
                findings.append(message)
        return self.emit(findings)

    def emit(self, findings: list[str]) -> int:
        """Log *findings* at ERROR (this blocks a push) and return the exit code.

        ERROR, not INFO: logged below ``lastResort``'s WARNING threshold the
        finding would vanish on any path that never configured logging,
        leaving a hook that refuses the push and says nothing about why.
        """
        if findings:
            self._get("logger").error("%s", "\n".join(findings))
            return 1
        return 0
