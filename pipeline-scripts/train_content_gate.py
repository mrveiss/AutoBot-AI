#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A merge train's members must keep their content, read from the content (#20406).

Train PR #20271 merged #20179 with an empty diff: its commits were reachable, the PR read MERGED,
and five of its files were not on main. The cause is unknown, so this keys on the result and not
on how a train is built.

``--range BASE..TIP`` runs before landing. Each ``Merge #N @ sha`` is judged at its own merge
commit, because at the tip a deliberate in-train fix reads as a loss, and a member merged twice is
judged by its last merge. A member fails when a file it added or deleted did not take effect there,
or when under half of a file's added lines are present. ``--title`` names the members the train
declares, so one with no merge at all fails too, as does a merge the gate cannot account for.

``--landed MERGE`` runs after landing. A file the train changed and main did not must arrive
byte-identical.

Blind spots: a file above half can still have lost lines, moved or split code reads as lost, and a
modified binary has no lines to compare. A file gone by the tip but present at its member's merge is
only a note, because a deliberate in-train fix looks the same. Files that trains recompute are
skipped (``RECOMPUTED``), so a loss in one of those goes unseen.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autobot_shared.git_probe import run_git  # noqa: E402

MEMBER_MERGE = re.compile(r"^Merge #(\d+) @ [0-9a-f]{7,40}\b")
#: Bringing main into the train adds no member: "Merge main into ...", "Merge branch 'main' into ...".
BASE_MERGE = re.compile(r"^Merge (?:branch |remote-tracking branch )?['\"]?(?:origin/)?main\b")
DECLARED_MEMBER = re.compile(r"#(\d+)")
#: Files a train recomputes on purpose, so the member's own value is not expected to survive.
RECOMPUTED = re.compile(r"(_known_large\.py|_baseline\.py|_ratchet_test\.py|_ratchet_\d+_test\.py)$")
#: A line this short matches by chance; a floor pin is recomputed by the train.
MIN_LINE = 12
FLOOR_LINE = "floor="
MIN_SURVIVAL = 0.5


@dataclass
class ContentReport:
    members: int = 0
    files: int = 0
    lines: int = 0
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _git(*args: str) -> str:
    return run_git(list(args), capture_output=True, check=True, errors="replace").stdout


def last_merges(rng: str, report: ContentReport) -> dict[str, str]:
    """``{pr: merge commit}``, keeping each member's last merge; an unknown merge is a finding."""
    found: dict[str, str] = {}
    for line in _git("log", "--first-parent", "--merges", "--format=%H %s", rng).splitlines():  # newest first
        sha, _, subject = line.partition(" ")
        match = MEMBER_MERGE.match(subject)
        if match:
            found.setdefault(match.group(1), sha)
        elif not BASE_MERGE.match(subject):
            report.findings.append(f"{sha[:10]} is a merge this gate cannot account for: {subject!r}")
    return found


def changed(base: str, head: str) -> list[tuple[str, str]]:
    """``(status, path)`` per file; NUL-separated, so no path is quoted or split."""
    fields = _git("diff", "--name-status", "--no-renames", "-z", base, head).split("\0")
    return list(zip(fields[0::2], fields[1::2]))


def _exists_at(commit: str, path: str) -> bool:
    return bool(_git("ls-tree", commit, "--", path).strip())


def _added_lines(base: str, head: str, path: str) -> list[str]:
    diff = _git("diff", "--unified=0", "--no-renames", base, head, "--", path).splitlines()
    added = (line[1:].strip() for line in diff if line.startswith("+") and not line.startswith("+++"))
    return [line for line in added if len(line) >= MIN_LINE and FLOOR_LINE not in line]


def _judge_file(status: str, path: str, base: str, head: str, merge: str, report: ContentReport) -> str | None:
    """Why *path* did not take effect at *merge*, or None."""
    if status == "D":
        return "deleted by the member, still present" if _exists_at(merge, path) else None
    if not _exists_at(merge, path):
        return "missing"
    added = _added_lines(base, head, path)
    if not added:
        return None
    present = {line.strip() for line in _git("show", f"{merge}:{path}").splitlines()}
    kept = sum(line in present for line in added)
    report.lines += len(added)
    return f"only {kept}/{len(added)} added lines present" if kept < len(added) * MIN_SURVIVAL else None


def check_range(rng: str, title: str = "") -> ContentReport:
    """Judge every member of the train in *rng* at its own merge commit."""
    report = ContentReport()
    merges = last_merges(rng, report)
    report.members = len(merges)
    if not merges:
        report.findings.append(f"no 'Merge #N @ sha' commit in {rng}: nothing was measured")
    for pr in sorted(set(DECLARED_MEMBER.findall(title)) - set(merges), key=int):
        report.findings.append(f"#{pr} is declared by the train and has no merge in {rng}")
    tip = rng.split("..")[-1]
    for pr, merge in sorted(merges.items(), key=lambda item: int(item[0])):
        head = f"{merge}^2"
        base = _git("merge-base", f"{merge}^1", head).strip()
        for status, path in changed(base, head):
            if RECOMPUTED.search(path):
                continue
            report.files += 1
            why = _judge_file(status, path, base, head, merge, report)
            if why:
                report.findings.append(f"#{pr} {path}: {why} at {merge[:10]}")
            elif status != "D" and not _exists_at(tip, path):
                report.notes.append(f"#{pr} {path}: present at its merge, gone by the tip")
        if not _git("diff", "--name-only", f"{merge}^1", merge).strip():
            report.notes.append(f"#{pr}: its merge changed nothing; its content was checked above")
    return report


def check_landed(merge: str) -> ContentReport:
    """A file the train changed and main did not must reach main byte-identical."""
    report = ContentReport(members=1)
    if len(_git("rev-list", "--parents", "-n", "1", merge).split()) != 3:
        report.findings.append(f"{merge[:10]} is not a two-parent merge, so it cannot be compared to the train's tip")
        return report
    main_before, tip = f"{merge}^1", f"{merge}^2"
    base = _git("merge-base", main_before, tip).strip()
    main_changed = {path for _, path in changed(base, main_before)}
    for _, path in changed(base, tip):
        if path in main_changed:
            continue
        report.files += 1
        if _git("diff", "--name-only", tip, merge, "--", path).strip():
            report.findings.append(f"{path}: differs from the train's tip at {merge[:10]}")
    if not report.files:
        report.findings.append(f"{merge[:10]}: no file to compare, so nothing was measured")
    return report


def _say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--range", help="BASE..TIP of a train branch")
    mode.add_argument("--landed", help="the merge commit that landed a train")
    parser.add_argument("--title", default="", help="the train PR's title, which lists its members")
    args = parser.parse_args(argv)
    try:
        report = check_range(args.range, args.title) if args.range else check_landed(args.landed)
    except subprocess.CalledProcessError as exc:
        _say(f"UNMEASURED: {' '.join(map(str, exc.cmd))}: {(exc.stderr or '').strip()}")
        return 2
    _say(f"examined {report.members} member(s), {report.files} file(s), {report.lines} added line(s)")
    for note in report.notes:
        _say(f"note: {note}")
    for finding in report.findings:
        _say(f"LOST: {finding}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    sys.exit(main())
