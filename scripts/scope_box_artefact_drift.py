#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Report scope boxes whose named artefact disagrees with the tree (#15566).

An issue body is a *record*. A scope box that names a concrete artefact -- a
workflow file, a module, a check context -- makes a checkable claim about the
repository. Two ways that record and the tree can disagree, and this reports
both:

* **already present.** An UNCHECKED box asks for something to be created, and
  the thing it names is already there. #14353 sat labelled ``needs-decision``
  for weeks after the first of its three boxes had shipped; anyone picking it up
  would have re-scoped work that existed.
* **named but absent.** A box refers to an artefact as if it exists, and it does
  not. #13162 describes the Python suite running under a ``security-tests`` job;
  no workflow in the tree defines that job, and a reader would conclude the
  suite is not running at all. It is -- 13 jobs per pipeline, under other names.

The two are one rule read in opposite directions. Whether an artefact *should*
exist yet is decided by the language around the token, not by the token: a box
that says "add X" expects X to be absent, so X being present is the finding; a
box that merely refers to X expects it to be present, so X being absent is.
That single test is what makes the check quiet enough to read -- see
CALIBRATION below.

## Honest limits, stated because the acceptance criteria name two examples

#14353's first box reads "a path-filter complement for ``python-suite``,
modelled on ``frontend-required-context.yml``". The artefact that actually
shipped is ``.github/workflows/python-required-context.yml``, which **the box
never names**. No token-existence rule can catch that box on its merits; it is
caught here through its *second* box ("Add ``python-suite`` to the required
contexts"), whose named job does exist. The issue is surfaced. The reasoning
that surfaces it is not the reasoning its filing assumed, and pretending
otherwise would be the same defect this tool exists to report.

#13162 is **not** caught, and the reason is worth stating rather than glossing.
Its body carries no task-list checkbox at all -- the `security-tests` analysis
lives in prose bullets under "Suggested fix", and the corrective finding
(``grep -rln 'security-tests' .github/workflows/`` returns nothing) is in an
issue *comment*, which this tool never reads. ``iter_boxes()`` returns an empty
list for it, so no rule of this tool can fire.

The job-name resolution below is still what a #13162-shaped issue needs, and the
unit test exercises that rule against a constructed body -- but a constructed
body is what it is, and the two must not be confused. An earlier draft of this
docstring claimed #13162 was "caught on its merits"; it is not, and the claim
was checked against the live issue only in review.

What that says about the rule's reach: this tool sees issues written in
scope-box form. An issue whose findings live in prose, or in comments, is
outside it by construction. That is a real limit on the population, not a bug
to fix here -- widening to prose would trade a precise signal for a noisy one.

## Why this is a script and not a pytest gate

Three reasons, the same three ``umbrella_label_drift.py`` records, and the
middle one is decisive:

* it needs a GitHub token the sandboxed unit-test run does not have;
* **the state under test is not the state the commit changes.** A PR that
  touches no issue body can turn this red because someone edited an issue, and
  green because someone ticked a box. Gating a merge on an outcome the author
  cannot reach from the diff is a check nobody can act on, and the reflex it
  teaches is to ignore it;
* it reads every open issue body, which is not per-PR-gate cheap at CI's
  concurrency.

So it runs on demand or on a schedule, as a CLI, **reporting only**. It never
ticks a box: ticking is a claim about acceptance and needs code evidence per
this repository's closure rules, which a bot cannot supply. The pure core --
box parsing, token extraction, creation-shape, resolution -- takes plain
strings and an index, so ``scope_box_artefact_drift_test.py`` drives all of it
with no network and no repository state.

## CALIBRATION, measured over 786 open issues (2026-09-04)

2,657 boxes, 2,573 of them unchecked. Narrowed in this order:

* every backticked artefact token in an unchecked box, present in the tree:
  **141 findings** -- unreadable, and dominated by boxes naming the file they
  intend to *modify*, exactly the false positive #15566's AC3 predicts;
* requiring a creation verb anywhere in the box: **29** -- still wrong, because
  "add a chunker and measure it against ``search.py``" has a creation verb and
  a modification target in one sentence;
* requiring the creation verb to sit within 45 characters to the **left of the
  token**, so the token is the verb's object rather than a neighbour, and
  demoting a token that sits behind a preposition to an adjunct: **4**.

The final run reads 456 artefact tokens and reports **4** in the already-present
direction and **27** in the named-but-absent one. Thirty-one lines is a list a
human reads in a minute, which is what the first run is for; a report nobody
finishes reading is a report nobody acts on. Both counts are always printed
next to the reach that produced them, so a small number is read against what it
was drawn from rather than mistaken for a clean backlog.

Triaged by hand on the first run: of the four, #14353 is the motivating case and
the other three name an artefact their box acts *upon* (a shim published for an
existing job; a file being split). Of the twenty-seven, three separate issues
presuppose one baseline file that is not in the tree, one issue's own text says
the file it names does not exist, and the residue is npm script names read as
job names. Every finding is a pointer for a human, never an edit.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

# `pipeline-scripts` is not an importable package name, so the sibling module is
# reached by path -- the idiom `backfill_relationships.py` documents and
# `umbrella_label_drift.py` reuses. The matching `.dockerignore` entry keeps
# this shipped-tree module out of every image, because the transport it imports
# is excluded from the build context (#14127).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline-scripts"))
# The repository root too, for `autobot_shared.paths` -- the same one-line
# bootstrap `check_script_exec_bits.py` uses to reach it from `scripts/`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci_dispatch_watchdog import GitHubApi  # noqa: E402

from autobot_shared.paths import scrubbed_git_env  # noqa: E402

# Plain stdlib logging, deliberately (#1082): this runs as a bare CLI, where
# autobot_shared.logging_manager would pull in config a script does not have.
logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 200

#: Reach floors, in this repository's ``FIX THE SWEEP`` idiom. They bind to what
#: the sweep TOUCHED -- issues read, boxes parsed, tokens extracted -- never to
#: what it found, because a findings floor reports "clean" the moment the
#: markdown parser breaks. Measured 2026-09-04: 786 issues, 2,657 boxes, 352
#: tokens; each floor sits far enough below to survive ordinary backlog churn.
MIN_ISSUES_READ = 300
MIN_BOXES_PARSED = 900
MIN_TOKENS_EXTRACTED = 100

#: A markdown task-list item, checked or not.
_BOX = re.compile(r"^(\s*)[-*]\s+\[( |x|X)\]\s+(.*)$")

#: Backtick-quoted spans. This repository writes every artefact name in
#: backticks, so unquoted prose is not searched -- that is the single largest
#: source of noise avoided, and the convention is enforced by review habit
#: rather than by a rule, which is why the check reports rather than gates.
_QUOTED = re.compile(r"`([^`\n]+)`")

_SUFFIXES = "py|yml|yaml|ts|tsx|js|vue|sh|md|json|toml|txt|cfg|ini|service|conf|sql|html|css|j2|pyi"
_PATHISH = re.compile(rf"^[\w.\-/]+\.({_SUFFIXES})$")
_DOTTED = re.compile(r"^[a-z_]\w*(\.[a-z_]\w*)+$")
_JOBISH = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")

#: A trailing ``:12`` or ``:12-20`` -- a file:line reference names the file.
_LINE_SUFFIX = re.compile(r":\d+(-\d+)?$")

#: Creation verbs. Matched only in the 45 characters to the LEFT of a token, so
#: the token is the verb's object. "Add a chunker and measure it against
#: `search.py`" has a creation verb and a modification target in one sentence;
#: only proximity separates them, and 45 characters is what the calibration run
#: in the module docstring settled on.
_CREATION = re.compile(
    r"\b(add|adds|create|creates|creating|introduce|introduces|new|write|writes|build|builds|"
    r"land|lands|ship|ships|extract|extracts|publish|publishes|emit|emits|generate|generates|"
    r"render|renders|split|splits|move|moves|relocate|relocates|"
    r"a (?:new )?(?:check|test|guard|script|module|workflow|file|suite))\b",
    re.I,
)
_CREATION_WINDOW = 45

#: A preposition between the creation verb and the token demotes the token
#: from the verb's object to an adjunct: "New parity test (alongside `X`)"
#: creates a test and merely cites ``X``. Four of the eight findings the
#: first calibration run produced were this shape, and none of the true ones
#: was, so the rule costs nothing measurable and removes half the noise.
_ADJUNCT = re.compile(
    r"\b(alongside|outside|inside|following|against|from|for|in|on|with|than|per|via|"
    r"beside|near|like|matching|mirroring|see)\b[^`]*$",
    re.I,
)

#: An elided path (``autobot-infrastructure/.../foo.service``) names nothing
#: resolvable; reporting it absent reports on the ellipsis.
_ELIDED = "..."

#: A hyphenated lowercase word is only read as a CI job name when the text
#: around it says so. Without this, every npm package (`pytest-xdist`), config
#: key (`max-line-length`) and directory (`autobot-frontend`) in the backlog
#: resolves as a missing job.
_JOB_CONTEXT = re.compile(r"\b(job|jobs|context|contexts|check|checks|shim|workflow|required)\b", re.I)
_JOB_WINDOW = 60

DIRECTION_PRESENT = "already-present"
DIRECTION_ABSENT = "named-but-absent"


@dataclass(frozen=True)
class Box:
    """One task-list item, with its wrapped continuation lines folded in."""

    checked: bool
    text: str


@dataclass(frozen=True)
class Token:
    """One artefact-shaped name found inside a box, with the role its context gives it."""

    text: str
    kind: str
    creation_shaped: bool


@dataclass(frozen=True)
class Finding:
    """One disagreement between a record and the tree."""

    issue: int
    direction: str
    token: Token
    resolved: Optional[str]
    excerpt: str


@dataclass
class Reach:
    """What the sweep touched. Asserted on instead of the findings (see the floors)."""

    issues: int = 0
    boxes: int = 0
    unchecked: int = 0
    tokens: int = 0


def iter_boxes(body: Optional[str]) -> List[Box]:
    """Every task-list item in *body*, continuation lines folded into their item.

    Bodies in this repository wrap at ~78 columns and indent the remainder of a
    box, so a line-at-a-time reader would see only the first fragment of most
    boxes -- and #14353's artefact name sits on such a continuation line.
    """
    boxes: List[List[Any]] = []
    for line in (body or "").splitlines():
        matched = _BOX.match(line)
        if matched:
            boxes.append([matched.group(2).lower() == "x", matched.group(3).strip()])
        elif boxes and line.strip() and line[:1] in (" ", "\t"):
            boxes[-1][1] += " " + line.strip()
    return [Box(checked=checked, text=text) for checked, text in boxes]


def _token_kind(text: str) -> Optional[str]:
    """The artefact class a bare token belongs to, or ``None`` if it names nothing checkable.

    A leading dot with no directory in front of it is a naming *convention*
    (``.stories.ts``, stated as an acceptance criterion by two issues), not a
    file, and would otherwise read as forever missing. A leading dot WITH a
    directory (``.github/workflows/ci.yml``) is an ordinary path and must
    survive -- which is what the pair of tests around this rule pins.
    """
    if _PATHISH.match(text):
        if "/" not in text:
            return None if text.startswith(".") else "basename"
        return "path"
    if _DOTTED.match(text):
        return "module"
    if _JOBISH.match(text):
        return "job"
    return None


def iter_tokens(box_text: str) -> List[Token]:
    """Every artefact-shaped token in one box, tagged with the role its context gives it."""
    tokens: List[Token] = []
    for match in _QUOTED.finditer(box_text):
        text = _LINE_SUFFIX.sub("", match.group(1).strip().rstrip(".,;:"))
        kind = _token_kind(text)
        if kind is None or _ELIDED in text:
            continue
        if kind == "job" and not _JOB_CONTEXT.search(_window(box_text, match, _JOB_WINDOW)):
            continue
        left = box_text[max(0, match.start() - _CREATION_WINDOW) : match.start()]
        created = bool(_CREATION.search(left)) and not _ADJUNCT.search(left)
        tokens.append(Token(text=text, kind=kind, creation_shaped=created))
    return tokens


def _window(text: str, match: "re.Match[str]", size: int) -> str:
    """The *size* characters either side of *match*, clipped to *text*."""
    return text[max(0, match.start() - size) : match.end() + size]


class TreeIndex:
    """Answers "does the tree hold this?" for every token class.

    Built from plain lists so a test can construct one from four strings, and
    the CLI can build the same object from ``git ls-files`` plus the job names
    declared across the workflows.
    """

    def __init__(self, paths: Iterable[str], jobs: Iterable[str] = (), root: Optional[Path] = None) -> None:
        self.root = root
        self.paths: Set[str] = {p.replace("\\", "/") for p in paths}
        self.jobs: Set[str] = set(jobs)
        self.directories: Set[str] = set()
        self.basenames: Dict[str, str] = {}
        self.top_level: Set[str] = set()
        for path in self.paths:
            as_path = Path(path)
            self.basenames.setdefault(as_path.name, path)
            self.top_level.add(as_path.parts[0])
            self.directories.update(str(parent) for parent in as_path.parents if str(parent) != ".")

    def resolve(self, token: Token) -> Optional[str]:
        """The tree path (or job name) *token* refers to, or ``None`` when the tree has no such thing."""
        resolver = {
            "path": self._resolve_path,
            "basename": self._resolve_basename,
            "module": self._resolve_module,
            "job": self._resolve_job,
        }[token.kind]
        return resolver(token.text)

    def _resolve_path(self, text: str) -> Optional[str]:
        if text in self.paths or text in self.directories:
            return text
        # An untracked-by-design file (`.claude/settings.local.json`) is present
        # for every purpose an issue body means by "exists".
        on_disk = self.root / text if self.root else None
        return text if on_disk is not None and on_disk.exists() else None

    def _resolve_basename(self, text: str) -> Optional[str]:
        return self.basenames.get(text)

    def _resolve_module(self, text: str) -> Optional[str]:
        """Resolve a dotted name, shortening it until a module answers.

        ``autobot_shared.async_compat.fire_and_forget`` names a *symbol* in a
        module, and a reader writes it exactly the way they write a module. Only
        trying the full dotted path reports the module's own symbols missing.
        """
        parts = text.split(".")
        while parts:
            base = "/".join(parts)
            for candidate in (base + ".py", base + "/__init__.py"):
                if candidate in self.paths:
                    return candidate
            parts.pop()
        return None

    def _resolve_job(self, text: str) -> Optional[str]:
        """A job name, or a directory of the same shape -- ``autobot-slm-frontend`` is not a missing job."""
        if text in self.jobs:
            return text
        return text if text in self.top_level or text in self.directories else None

    def is_addressable(self, token: Token) -> bool:
        """False for a token this index cannot honestly answer for.

        A path whose first segment is not a top-level directory of this
        repository, or a dotted name whose first segment is not, is almost
        always a fragment (``security/session_ownership.py``) or a foreign
        module. Reporting it absent would be reporting on a question that was
        never asked here.
        """
        if token.kind == "path":
            return Path(token.text).parts[0] in self.top_level
        if token.kind == "module":
            return token.text.split(".")[0] in self.top_level
        return True


class ReachError(RuntimeError):
    """Raised when the sweep did not reach enough of the backlog for its answer to mean anything."""


def findings_for_issue(number: int, body: Optional[str], index: TreeIndex, reach: Reach) -> List[Finding]:
    """Every disagreement between one issue's unchecked boxes and the tree."""
    findings: List[Finding] = []
    boxes = iter_boxes(body)
    reach.boxes += len(boxes)
    for box in boxes:
        if box.checked:
            continue
        reach.unchecked += 1
        for token in iter_tokens(box.text):
            reach.tokens += 1
            findings.extend(_classify(number, box, token, index))
    return findings


def _classify(number: int, box: Box, token: Token, index: TreeIndex) -> List[Finding]:
    """The one rule, read in both directions. Returns at most one finding."""
    if not index.is_addressable(token):
        return []
    resolved = index.resolve(token)
    excerpt = box.text[:160]
    if token.creation_shaped and resolved:
        return [Finding(number, DIRECTION_PRESENT, token, resolved, excerpt)]
    if not token.creation_shaped and not resolved:
        return [Finding(number, DIRECTION_ABSENT, token, None, excerpt)]
    return []


def sweep(issues: Iterable[Dict[str, Any]], index: TreeIndex) -> Tuple[List[Finding], Reach]:
    """Every finding across a stream of issue payloads, alongside the reach that produced it."""
    reach = Reach()
    findings: List[Finding] = []
    for issue in issues:
        number = issue.get("number")
        if not isinstance(number, int):
            continue
        reach.issues += 1
        findings.extend(findings_for_issue(number, issue.get("body"), index, reach))
    return findings, reach


def enforce_reach(reach: Reach) -> None:
    """Raise unless the sweep touched enough of the backlog for a clean answer to assert anything.

    Bound to reach, never to findings: a run whose markdown parser broke reads
    zero findings, which is the same answer a healthy backlog gives.
    """
    for measured, floor, what in (
        (reach.issues, MIN_ISSUES_READ, "issue bodies read"),
        (reach.boxes, MIN_BOXES_PARSED, "scope boxes parsed"),
        (reach.tokens, MIN_TOKENS_EXTRACTED, "artefact tokens extracted"),
    ):
        if measured < floor:
            raise ReachError(
                f"FIX THE SWEEP: only {measured} {what}, floor is {floor}. "
                "A clean result below this floor asserts nothing about the backlog."
            )


#: Job ids and check-context names declared across the workflows.
_JOB_ID = re.compile(r"^  ([A-Za-z_][\w-]*):\s*$")
_JOB_NAME = re.compile(r"^\s*name:\s*['\"]?([^'\"#]+?)['\"]?\s*$")


def workflow_job_names(workflows_dir: Path) -> Set[str]:
    """Every job id and job ``name:`` declared under *workflows_dir*.

    Both are collected because a required check reports under whichever the
    workflow chose, and #13162's ``security-tests`` is exactly a name a reader
    would take for either.
    """
    names: Set[str] = set()
    for workflow in sorted(workflows_dir.glob("*.y*ml")):
        in_jobs = False
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if line.rstrip() == "jobs:":
                in_jobs = True
                continue
            if in_jobs and line[:1] not in (" ", "\t", "", "#"):
                in_jobs = False
            identifier = _JOB_ID.match(line)
            if in_jobs and identifier:
                names.add(identifier.group(1))
            titled = _JOB_NAME.match(line)
            if titled:
                names.add(titled.group(1).strip())
    return names


def index_from_checkout(repo_root: Path) -> TreeIndex:
    """A :class:`TreeIndex` over the tracked tree, plus the job names its workflows declare."""
    listed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        # An inherited GIT_DIR outranks `cwd=`, so without this the call
        # enumerates whatever checkout the environment points at and answers
        # confidently about the wrong tree -- no error, just a different repo.
        # Same defect class as #15176, and `check_git_toplevel_env_scrubbed`
        # is the guard that catches it.
        env=scrubbed_git_env(),
    )
    if listed.returncode != 0 or not listed.stdout.strip():
        raise ReachError(f"FIX THE SWEEP: git ls-files listed nothing in {repo_root}")
    paths = [line for line in listed.stdout.splitlines() if line.strip()]
    return TreeIndex(paths, workflow_job_names(repo_root / ".github" / "workflows"), root=repo_root)


def _paginate_open_issues(api: GitHubApi) -> Iterator[Dict[str, Any]]:
    """Every open, non-PR issue, reading the list endpoint to exhaustion."""
    for page in range(1, MAX_PAGES + 1):
        query = f"state=open&per_page={PAGE_SIZE}&page={page}"
        status, body = api.request("GET", f"/repos/{api.repository}/issues?{query}")
        if status >= 400 or not isinstance(body, list):
            raise ReachError(f"GET issues page {page} returned {status}")
        for item in body:
            if "pull_request" not in item:
                yield item
        if len(body) < PAGE_SIZE:
            return
    raise ReachError(f"issue list exceeded {MAX_PAGES} pages -- refusing a partial read")


def report_lines(findings: Sequence[Finding], reach: Reach) -> List[str]:
    """The human report: reach first, so a small finding count is read against what produced it."""
    present = [f for f in findings if f.direction == DIRECTION_PRESENT]
    absent = [f for f in findings if f.direction == DIRECTION_ABSENT]
    lines = [
        f"read {reach.issues} open issue(s): {reach.boxes} scope box(es), "
        f"{reach.unchecked} unchecked, {reach.tokens} artefact token(s)",
        "",
        f"{len(present)} unchecked box(es) name an artefact that ALREADY EXISTS "
        "-- either the box should be ticked, or it does not mean what it names:",
    ]
    lines.extend(f"  #{f.issue} [{f.token.kind}] {f.token.text} -> {f.resolved} | {f.excerpt}" for f in present)
    lines.append("")
    lines.append(f"{len(absent)} box(es) refer to an artefact the tree DOES NOT HOLD:")
    lines.extend(f"  #{f.issue} [{f.token.kind}] {f.token.text} | {f.excerpt}" for f in absent)
    return lines


def _as_payload(findings: Sequence[Finding], reach: Reach) -> Dict[str, Any]:
    return {
        "reach": {"issues": reach.issues, "boxes": reach.boxes, "unchecked": reach.unchecked, "tokens": reach.tokens},
        "findings": [
            {
                "issue": f.issue,
                "direction": f.direction,
                "kind": f.token.kind,
                "token": f.token.text,
                "resolved": f.resolved,
                "excerpt": f.excerpt,
            }
            for f in findings
        ],
    }


# Exit codes. A caller gating on "non-zero" must still tell an actionable
# finding from a run that measured nothing: a scheduled job would otherwise
# alert on a rate limit exactly as it alerts on drift, and the two need
# opposite responses. EXIT_READ_FAILED means NOTHING was measured; it is never
# a weaker EXIT_DRIFT_FOUND. Same split `umbrella_label_drift.py` documents.
EXIT_CLEAN = 0
EXIT_DRIFT_FOUND = 1
EXIT_USAGE = 2
EXIT_READ_FAILED = 3


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--json", action="store_true", help="emit machine-readable output instead of a report")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Report only. This tool never writes to an issue -- see the module docstring."""
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token or not args.repo:
        logger.error("GH_TOKEN and --repo (or GITHUB_REPOSITORY) are required")
        return EXIT_USAGE

    api = GitHubApi(token=token, repository=args.repo)
    try:
        index = index_from_checkout(Path(args.repo_root))
        findings, reach = sweep(_paginate_open_issues(api), index)
        enforce_reach(reach)
    except ReachError as exc:
        logger.error("refusing to report on a population this sweep did not reach: %s", exc)
        return EXIT_READ_FAILED

    if args.json:
        logger.info("%s", json.dumps(_as_payload(findings, reach)))
    else:
        for line in report_lines(findings, reach):
            logger.info("%s", line)
    return EXIT_DRIFT_FOUND if findings else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
