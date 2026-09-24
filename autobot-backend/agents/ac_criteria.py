# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading an issue's acceptance criteria, and checking a citation is real (#17090).

The two halves here are deliberately the ones with no model in them. Whether a
criterion is *met* is a judgement (`ac_verifier.py`); whether a criterion *was
written down*, and whether a cited `file:line` *exists in merged code*, are
facts, and facts a guess would be indistinguishable from.

The citation check is the one that earns its place. A verdict of "met" whose
evidence is `services/foo.py:412` is worth exactly as much as the existence of
that line: #17090's last criterion asks for a fabricated `file:line` to be
*rejected*, not merely noted, because an evidence-shaped string is the failure
mode that gets acted on. Everything read here comes from `origin/main` through
`git show`, never from the working tree, so a local edit cannot make a
criterion look delivered.

STATED BOUNDARY, because what this does not read matters as much as what it
does. Criteria are taken from the issue body's acceptance-criteria section and
from any COMMENT that restates a checkbox list of its own (an owner amending
the set in place). A free-prose ruling -- "criterion 2 no longer applies", "we
decided to do X instead" -- is **not** parsed, cannot be, and is reported as an
unread amendment by :func:`unparsed_amendment_hint` so the posted result says
so rather than quietly presenting a stale list as complete.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec B404 -- fixed argv, no shell; see _git_show
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import BASE_DIR_ENV, git_repo_root, scrubbed_git_env

logger = get_logger(__name__)

#: A heading that opens an acceptance-criteria section. Markdown headings and
#: bold "headings" both appear in this repo's issues, so both are matched.
_AC_HEADING = re.compile(r"^\s*(?:#{1,6}\s*|\*\*)\s*acceptance\s+criteria\b", re.I)

#: Any other heading -- what closes the section.
_ANY_HEADING = re.compile(r"^\s*(?:#{1,6}\s+|\*\*\s*[A-Za-z])")

#: A checkbox line. The capture is the criterion's own text.
_CHECKBOX = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(?P<text>.+?)\s*$")

#: A continuation line: indented, not itself a checkbox or a heading.
_CONTINUATION = re.compile(r"^\s{2,}\S")

#: `path/to/file.py:123`, the citation shape. The path is restricted to what a
#: repo path can contain so a sentence with a colon does not read as evidence.
_CITATION = re.compile(r"(?P<path>[A-Za-z0-9._/\-]+\.[A-Za-z0-9]+):(?P<line>\d+)")

#: Phrases that make a criterion answerable only on a running system. Matched
#: before any model sees it (#17090 AC 3): this verdict is a property of the
#: criterion's wording, so deciding it by rule is both cheaper and firmer than
#: asking. Over-matching here is safe -- it downgrades a verdict to "needs host
#: evidence", never up to "met".
_HOST_EVIDENCE_PHRASES = (
    "live install",
    "live system",
    "on the host",
    "on the live",
    "running system",
    "in production",
    "deployed",
    "after a deploy",
    "after deployment",
    # Path PREFIXES, not the deployment's own paths: the hardcoded-values rule
    # forbids naming `/opt/autobot` in code (and rightly -- production code reads
    # the install root from the SSOT), while what this list needs is the shape a
    # criterion's WORDING takes. `_configured_install_phrases` adds the real root
    # when one is configured, so a deployment that names its own path is matched
    # too.
    "/opt/",
    "/var/log/",
    "systemd",
    "restart the service",
    "smoke test on",
)


def _configured_install_phrases() -> tuple[str, ...]:
    """The deployed install's own path, when the environment names one."""
    configured = os.environ.get(BASE_DIR_ENV, "").strip().lower()
    return (configured,) if configured else ()


@dataclass(frozen=True)
class Criterion:
    """One acceptance criterion, as written."""

    index: int
    text: str
    checked: bool
    #: ``"body"`` or ``"comment:<id>"`` -- where this criterion was read from.
    source: str

    @property
    def needs_host_evidence(self) -> bool:
        """Is this answerable only against a running system? (#17090 AC 3)"""
        lowered = self.text.lower()
        phrases = _HOST_EVIDENCE_PHRASES + _configured_install_phrases()
        return any(phrase in lowered for phrase in phrases)


@dataclass(frozen=True)
class Citation:
    """A `path:line` a verdict rests on."""

    path: str
    line: int

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


def _section_lines(markdown: str) -> list[str]:
    """The lines under the acceptance-criteria heading, or []."""
    lines = markdown.splitlines()
    for start, line in enumerate(lines):
        if _AC_HEADING.match(line):
            body: list[str] = []
            for candidate in lines[start + 1 :]:
                if _ANY_HEADING.match(candidate) and not _CHECKBOX.match(candidate):
                    break
                body.append(candidate)
            return body
    return []


def _criteria_in(markdown: str, *, source: str, first_index: int) -> list[Criterion]:
    """Checkbox criteria under *markdown*'s AC heading, continuations folded in."""
    found: list[Criterion] = []
    for line in _section_lines(markdown):
        match = _CHECKBOX.match(line)
        if match:
            found.append(
                Criterion(
                    index=first_index + len(found),
                    text=match.group("text"),
                    checked=match.group(1).lower() == "x",
                    source=source,
                )
            )
        elif found and _CONTINUATION.match(line):
            previous = found[-1]
            folded = f"{previous.text} {line.strip()}"
            found[-1] = Criterion(previous.index, folded, previous.checked, previous.source)
    return found


def extract_criteria(body: str, comments: Sequence[tuple[str, str]] = ()) -> list[Criterion]:
    """Every acceptance criterion of an issue, body first then amendments.

    *comments* is a sequence of ``(comment_id, comment_body)``. A comment
    contributes criteria only when it restates a checkbox list under its own
    acceptance-criteria heading; see this module's stated boundary.
    """
    criteria = _criteria_in(body, source="body", first_index=1)
    for comment_id, comment_body in comments:
        amended = _criteria_in(comment_body, source=f"comment:{comment_id}", first_index=len(criteria) + 1)
        criteria.extend(amended)
    return criteria


def unparsed_amendment_hint(comments: Sequence[tuple[str, str]]) -> Optional[str]:
    """A warning to carry into the result when a comment may amend the ACs unread.

    Deliberately a hint, not a verdict: the point is that this module cannot
    read a prose ruling, so it says which comments *look like* one rather than
    pretending the criteria list is complete.
    """
    suspicious = [
        comment_id
        for comment_id, text in comments
        if re.search(r"\b(no longer applies|drop(?:ped)?\s+criteri|amend|supersede|instead of)\b", text, re.I)
        and not _criteria_in(text, source="x", first_index=1)
    ]
    if not suspicious:
        return None
    return (
        "comments " + ", ".join(suspicious) + " read like an amendment in prose, which this "
        "verifier does not parse; the criteria above are the ones written as checkboxes"
    )


def parse_citations(text: str) -> list[Citation]:
    """Every `path:line` in *text*, in order, de-duplicated."""
    seen: set[tuple[str, int]] = set()
    citations: list[Citation] = []
    for match in _CITATION.finditer(text or ""):
        key = (match.group("path"), int(match.group("line")))
        if key not in seen:
            seen.add(key)
            citations.append(Citation(path=key[0], line=key[1]))
    return citations


def _git_show(ref_path: str, *, repo_root: Path) -> Optional[str]:
    """`git show <ref>:<path>` from *repo_root*, or None when it does not exist.

    The environment is scrubbed of ambient git variables (`autobot_shared.paths`)
    because an inherited ``GIT_DIR`` outranks ``cwd=`` and would answer from
    another checkout -- a wrong answer with a successful exit, which is the one
    failure shape a citation check must not have.
    """
    try:
        result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell
            ["git", "show", ref_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(repo_root),
            env=scrubbed_git_env(),
            check=False,
            timeout=_GIT_SHOW_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ac_criteria: git show failed for %s (%s)", ref_path, type(exc).__name__)
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def file_reader(ref: str = "origin/main", repo_root: Path | None = None) -> Callable[[str], Optional[str]]:
    """A reader of *ref*'s files, for :func:`verify_citations`.

    A factory rather than a module-level function so a test supplies its own
    reader without patching subprocess, and so the ref is explicit at the call
    site: reading the working tree instead of merged code is exactly the mistake
    that would make an unmerged change look delivered.
    """
    root = repo_root or git_repo_root()

    def read(path: str) -> Optional[str]:
        return _git_show(f"{ref}:{path}", repo_root=root)

    return read


def verify_citations(
    citations: Iterable[Citation],
    read: Callable[[str], Optional[str]],
) -> tuple[list[Citation], list[str]]:
    """Split *citations* into the real ones and a reason per rejected one.

    A citation is real when the file exists at the read ref, the line number is
    within it, and that line is not blank. The blank check is not pedantry: a
    line number invented near the right area lands on whitespace often enough
    that accepting it would let a fabricated citation through the other two.
    """
    verified: list[Citation] = []
    rejected: list[str] = []
    for citation in citations:
        content = read(citation.path)
        if content is None:
            rejected.append(f"{citation}: no such file in merged code")
            continue
        lines = content.splitlines()
        if citation.line < 1 or citation.line > len(lines):
            rejected.append(f"{citation}: file has {len(lines)} line(s)")
            continue
        if not lines[citation.line - 1].strip():
            rejected.append(f"{citation}: that line is blank")
            continue
        verified.append(citation)
    return verified, rejected


#: Seconds a single `git show`/`git grep` may take. A read of one blob or one
#: tree scan: generous for a cold cache, short enough that a wedged git does not
#: hold a verification run.
_GIT_SHOW_TIMEOUT_S = 30
_GIT_GREP_TIMEOUT_S = 60

#: A backticked token in a criterion -- how this repo's issues name the thing a
#: criterion is about (`VALID_KINDS`, `api/live_events.py`, `publish_event`).
#: Searching for those is what turns "is this met" into a question with evidence
#: attached; a criterion with none gets no context and therefore no verdict.
_BACKTICKED = re.compile(r"`([^`\n]{2,80})`")

#: Hits shown per term. A ceiling, not a sample: a term matching hundreds of
#: lines is too generic to be evidence, and truncating it quietly would let the
#: model cite whatever happened to be first.
_MAX_HITS_PER_TERM = 12


def criterion_terms(criterion: Criterion) -> list[str]:
    """The searchable tokens a criterion names, in order, de-duplicated."""
    seen: set[str] = set()
    terms: list[str] = []
    for match in _BACKTICKED.finditer(criterion.text):
        term = match.group(1).strip()
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _git_grep(term: str, *, ref: str, repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell
            ["git", "grep", "-n", "-F", "--", term, ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(repo_root),
            env=scrubbed_git_env(),
            check=False,
            timeout=_GIT_GREP_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ac_criteria: git grep failed for %r (%s)", term, type(exc).__name__)
        return []
    if result.returncode not in (0, 1):  # 1 is "no match", not an error
        return []
    # `git grep <ref>` prefixes every hit with "<ref>:", which is noise in a
    # citation the model is asked to reproduce as `path:line`.
    prefix = f"{ref}:"
    return [line[len(prefix) :] if line.startswith(prefix) else line for line in result.stdout.splitlines()]


def code_searcher(
    ref: str = "origin/main",
    repo_root: Path | None = None,
) -> Callable[[Sequence[str]], str]:
    """A searcher of *ref* returning `path:line: content` hits for some terms.

    Returns the empty string when nothing matches, which is the input that makes
    a verdict "can't tell" -- deliberately, because no evidence found and no
    evidence looked for must reach the model as the same thing it reaches a
    reader as: nothing to cite.
    """
    root = repo_root or git_repo_root()

    def search(terms: Sequence[str]) -> str:
        blocks: list[str] = []
        for term in terms:
            hits = _git_grep(term, ref=ref, repo_root=root)
            if not hits:
                blocks.append(f"`{term}`: no match in {ref}")
                continue
            shown = hits[:_MAX_HITS_PER_TERM]
            more = "" if len(hits) <= _MAX_HITS_PER_TERM else f"\n  ... {len(hits) - _MAX_HITS_PER_TERM} more hit(s)"
            blocks.append(f"`{term}`: {len(hits)} hit(s) in {ref}\n  " + "\n  ".join(shown) + more)
        return "\n\n".join(blocks)

    return search


__all__ = [
    "Citation",
    "Criterion",
    "extract_criteria",
    "code_searcher",
    "criterion_terms",
    "file_reader",
    "parse_citations",
    "unparsed_amendment_hint",
    "verify_citations",
]
