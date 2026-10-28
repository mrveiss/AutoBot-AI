#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Landing notes on the issues a PR or merge train merged to main references (#19520).

Run by `.github/workflows/issue-landing-notes.yml`. Two subcommands:

``merged``   on ``pull_request: closed`` with ``merged == true`` into main.
  * Members. A train PR (head ``train-*``) resolves its members from its OWN commits: every
    merge commit's second parent is a frozen member head, mapped to the PR whose head it is,
    first through ``commits/{sha}/pulls`` and then through a ``sha:`` PR search confirmed by
    the candidate's head SHA. Once the train is on the default branch the first endpoint
    returns only the train itself, so the search is what usually answers. The ``| #N |``
    table in the train body is the fallback, used only when a merge commit stays unresolved.
    A table member whose PR is not merged is skipped: a train body can list a member it
    dropped. The source of every member is logged. A plain PR is its own single member; a
    plain PR that landed inside a train defers to the train's run, which posts for it.
  * References. ``Closes/Fixes/Resolves #N`` (every form GitHub accepts) and ``Refs #N`` in
    each member's body and the train's own body, deduplicated per issue. ``Part of #N`` is
    NOT a reference: #19520 scopes the note to Closes/Fixes/Resolves and Refs, and ``Part
    of`` names an umbrella, whose own children carry the Closes/Refs lines that land.
  * One comment per issue, carrying ``<!-- landing-note:<merge sha> -->``. An existing
    bot comment with that marker means no second note.
  * A CLOSED issue referenced with a closing keyword gets ``needs-ac-evidence``, applied
    BEFORE the note, so a failed label never leaves a note behind. A rerun that finds the
    note but not the label re-applies the label, unless a trusted AC evidence comment
    already cleared it: every step is retry-safe.

``evidence`` on ``issue_comment: created``: a comment holding an AC evidence table, by a
non-bot whose ``author_association`` is OWNER, MEMBER or COLLABORATOR, removes
``needs-ac-evidence``. The workflow's ``if:`` gates on the same set; the script re-checks it.
An AC evidence table is a markdown table whose header row has a cell reading ``AC``/``ACs``/
``AC #``/``Acceptance criterion``/``Acceptance criteria`` and a cell starting with ``Evidence``
(both case-insensitive), followed by a delimiter row and at least one body row. Tables inside
code are not tables.

Never ticks a checkbox, closes, reopens or edits an issue body: evidence stays a person's or
agent's job. Stdlib only; HTTP goes through ``github_api.GitHubApi`` and comment pages are
read by the one comment reader, ``.github/actions/upsert-pr-comment`` (#12984).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_api import TRUSTED_ASSOCIATIONS, build_api  # noqa: E402
from issue_api import IssueApiError, IssueClient, ensure_label, load_upsert  # noqa: E402

logger = logging.getLogger(__name__)

EVIDENCE_LABEL = "needs-ac-evidence"
EVIDENCE_LABEL_COLOR = "d93f0b"
EVIDENCE_LABEL_DESCRIPTION = "Closed by a merge keyword; awaits an AC evidence table comment (#19520)"
TRAIN_PREFIX = "train-"
MARKER_TEMPLATE = "<!-- landing-note:{sha} -->"
COMMITS_PAGE_SIZE = 100
COMMITS_MAX_PAGES = 3  # pulls/{n}/commits stops at 250 commits
SOURCE_COMMIT_PULLS = "commit-pulls"
SOURCE_COMMIT_SEARCH = "commit-search"
SOURCE_BODY_TABLE = "body-table"
SOURCE_TRAIN_MERGE = "train-merge-commit"
SOURCE_SELF = "self"

_UPSERT = load_upsert()


class LandingNoteError(IssueApiError):
    """The API answered with something this script cannot act on."""


# ---- parsing -------------------------------------------------------------------------------

_TARGET = r"(?:(?P<repo>[\w.-]+/[\w.-]+))?#(?P<num>\d+)\b"
_CLOSING_RE = re.compile(rf"(?<![\w-])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+{_TARGET}", re.I)
_REFS_RE = re.compile(
    r"(?<![\w-])refs?:?\s+((?:[\w.-]+/[\w.-]+)?#\d+(?:(?:\s*,\s*|\s+)(?:and\s+)?(?:[\w.-]+/[\w.-]+)?#\d+)*)", re.I
)
_TARGET_RE = re.compile(_TARGET)
_CODE_AND_COMMENTS_RE = re.compile(r"<!--.*?-->|```.*?```|~~~.*?~~~|`[^`\n]*`", re.S)
_TABLE_MEMBER_RE = re.compile(r"^\s*\|\s*#(\d+)\s*\|", re.M)


def strip_code_and_comments(body: str) -> str:
    """Remove HTML comments and code: GitHub links no keyword inside them."""
    return _CODE_AND_COMMENTS_RE.sub(" ", body or "")


def _same_repo(qualifier: Optional[str], repo: str) -> bool:
    return not qualifier or qualifier.lower() == repo.lower()


def parse_references(body: str, repo: str) -> Dict[int, bool]:
    """Issue number -> True when referenced with a closing keyword, False for ``Refs`` only.

    As on GitHub, a closing keyword takes the one reference after it; ``Refs`` takes a list.
    """
    text = strip_code_and_comments(body)
    refs: Dict[int, bool] = {}
    for match in _CLOSING_RE.finditer(text):
        if _same_repo(match.group("repo"), repo):
            refs[int(match.group("num"))] = True
    for match in _REFS_RE.finditer(text):
        for target in _TARGET_RE.finditer(match.group(1)):
            if _same_repo(target.group("repo"), repo):
                refs.setdefault(int(target.group("num")), False)
    return refs


def table_members(body: str) -> List[int]:
    """``| #N |`` first cells of the train body's member table, in order, deduplicated."""
    return list(dict.fromkeys(int(n) for n in _TABLE_MEMBER_RE.findall(strip_code_and_comments(body))))


# ---- member resolution from data -------------------------------------------------------------


@dataclass(frozen=True)
class Member:
    number: int
    body: str
    source: str


def merge_second_parents(commits: Iterable[Dict[str, Any]]) -> List[str]:
    """The second parent of every merge commit, in commit order."""
    return [c["parents"][1]["sha"] for c in commits if len(c.get("parents") or []) >= 2]


def merged_in_train(commits: Iterable[Dict[str, Any]], branch: str) -> Set[int]:
    """Members the train merged itself: ``Merge #N @ <sha> into <branch>`` merge commits (#19572).

    A member the trainmaster landed at a re-frozen head is closed unmerged on GitHub, yet
    its merge commit is in the train's range. A member pulled from the train has none.
    """
    pattern = re.compile(rf"^Merge #(\d+) @ [0-9a-f]{{7,40}} into {re.escape(branch)}$")
    found: Set[int] = set()
    for commit in commits:
        if len(commit.get("parents") or []) < 2:
            continue
        subject = ((commit.get("commit") or {}).get("message") or "").split("\n", 1)[0].strip()
        match = pattern.match(subject)
        if match:
            found.add(int(match.group(1)))
    return found


def pick_head_match(prs: Iterable[Dict[str, Any]], sha: str, exclude: int) -> Optional[Dict[str, Any]]:
    """The PR whose head is ``sha``, never the train itself."""
    for pr in prs:
        if pr.get("number") != exclude and (pr.get("head") or {}).get("sha") == sha:
            return pr
    return None


# ---- note text, marker, evidence table, bots ------------------------------------------------


@dataclass(frozen=True)
class Landing:
    pr_number: int
    merge_sha: str
    branch: str
    body: str

    @property
    def is_train(self) -> bool:
        return self.branch.startswith(TRAIN_PREFIX)

    @property
    def marker(self) -> str:
        return MARKER_TEMPLATE.format(sha=self.merge_sha)


@dataclass
class Target:
    closing: bool = False
    via: List[int] = field(default_factory=list)


def landing_from_pr(pr: Dict[str, Any]) -> Landing:
    sha = pr.get("merge_commit_sha") or ""
    if not pr.get("merged_at") and not pr.get("merged"):
        raise LandingNoteError(f"#{pr.get('number')} is not merged")
    if not sha:
        raise LandingNoteError(f"#{pr.get('number')} has no merge commit SHA")
    return Landing(int(pr["number"]), sha, pr["head"]["ref"], pr.get("body") or "")


def note_text(landing: Landing, via: Sequence[int]) -> str:
    short = landing.merge_sha[:10]
    if landing.is_train:
        line = f"Landed in train {landing.branch} (#{landing.pr_number}, merge `{short}`)"
        if via:
            line += " via " + ", ".join(f"#{n}" for n in via)
    else:
        line = f"Landed in #{landing.pr_number}, merge `{short}`"
    return f"{landing.marker}\n{line}"


def has_note(comments: Iterable[Dict[str, Any]], marker: str) -> bool:
    """A bot comment carrying the marker; a person quoting it does not count (#12984 rule)."""
    return any(_UPSERT.is_ours(comment, marker) for comment in comments)


def needs_evidence_label(issue: Dict[str, Any], closing: bool) -> bool:
    return closing and issue.get("state") == "closed"


def is_bot(user: Optional[Dict[str, Any]]) -> bool:
    user = user or {}
    return user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]")


_AC_HEADER_RE = re.compile(r"^(?:acs?|ac\s*#|acceptance\s+criteri(?:on|a))$", re.I)
_EVIDENCE_HEADER_RE = re.compile(r"^evidence\b", re.I)
_DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")


def _cells(line: str) -> Optional[List[str]]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _is_evidence_header(cells: List[str]) -> bool:
    return any(_AC_HEADER_RE.match(c) for c in cells) and any(_EVIDENCE_HEADER_RE.match(c) for c in cells)


def has_evidence_table(body: str) -> bool:
    """A header with an AC cell and an Evidence cell, a delimiter row, and one body row."""
    lines = strip_code_and_comments(body).splitlines()
    for index in range(len(lines) - 2):
        header, delimiter, row = (_cells(line) for line in lines[index : index + 3])
        if header is None or delimiter is None or row is None:
            continue
        if all(_DELIMITER_CELL_RE.match(c) for c in delimiter) and _is_evidence_header(header):
            return True
    return False


def has_evidence_label(issue: Dict[str, Any]) -> bool:
    return EVIDENCE_LABEL in {label.get("name") for label in issue.get("labels") or []}


def is_trusted_evidence(comment: Dict[str, Any]) -> bool:
    """An AC evidence table from a non-bot OWNER/MEMBER/COLLABORATOR; anyone else is ignored."""
    if is_bot(comment.get("user")) or comment.get("author_association") not in TRUSTED_ASSOCIATIONS:
        return False
    return has_evidence_table(comment.get("body") or "")


def should_clear_label(event: Dict[str, Any]) -> bool:
    """Re-checks the workflow's ``if:``: the script never trusts the gate alone."""
    issue, comment = event.get("issue") or {}, event.get("comment") or {}
    if issue.get("pull_request") or not has_evidence_label(issue):
        return False
    return is_trusted_evidence(comment)


# ---- the thin API layer ---------------------------------------------------------------------


class LandingClient(IssueClient):
    """The shared issue client, raising ``LandingNoteError``, plus a soft GET."""

    error = LandingNoteError

    def try_get(self, path: str) -> Optional[Any]:
        status, body = self.api.request("GET", path, None)
        if status != 200:
            logger.warning("GET %s: HTTP %s (%s); treated as unresolved", path, status, body)
            return None
        return body


def pr_commits(client: LandingClient, number: int) -> List[Dict[str, Any]]:
    commits: List[Dict[str, Any]] = []
    for page in range(1, COMMITS_MAX_PAGES + 1):
        query = urllib.parse.urlencode({"per_page": COMMITS_PAGE_SIZE, "page": page})
        batch = client.call("GET", f"/repos/{client.repo}/pulls/{number}/commits?{query}")
        commits.extend(batch)
        if len(batch) < COMMITS_PAGE_SIZE:
            break
    return commits


def _member_by_commit_pulls(client: LandingClient, sha: str, train: int) -> Optional[Dict[str, Any]]:
    prs = client.try_get(f"/repos/{client.repo}/commits/{sha}/pulls")
    return pick_head_match(prs or [], sha, train)


def _member_by_search(client: LandingClient, sha: str, train: int) -> Optional[Dict[str, Any]]:
    query = urllib.parse.urlencode({"q": f"repo:{client.repo} is:pr sha:{sha}", "per_page": 20})
    found = client.try_get(f"/search/issues?{query}") or {}
    for item in found.get("items") or []:
        if item.get("number") == train:
            continue
        pr = client.try_get(f"/repos/{client.repo}/pulls/{item['number']}")
        if pr and pick_head_match([pr], sha, train):
            return pr
    return None


def _member_for_head(client: LandingClient, sha: str, train: int) -> Optional[Member]:
    pr = _member_by_commit_pulls(client, sha, train)
    if pr is not None:
        return Member(int(pr["number"]), pr.get("body") or "", SOURCE_COMMIT_PULLS)
    pr = _member_by_search(client, sha, train)
    if pr is not None:
        return Member(int(pr["number"]), pr.get("body") or "", SOURCE_COMMIT_SEARCH)
    logger.warning("merge parent %s maps to no PR head", sha[:10])
    return None


def _table_member(client: LandingClient, number: int, in_train: Set[int]) -> Optional[Member]:
    """A table member that landed: merged on GitHub, or merged by the train itself (#19572)."""
    pr = client.call("GET", f"/repos/{client.repo}/pulls/{number}")
    if pr.get("merged_at") or pr.get("merged"):
        return Member(number, pr.get("body") or "", SOURCE_BODY_TABLE)
    if number in in_train:
        logger.info("table member #%s is closed unmerged but the train merged it; landed", number)
        return Member(number, pr.get("body") or "", SOURCE_TRAIN_MERGE)
    logger.warning("table member #%s is not merged and has no train merge commit; skipped", number)
    return None


def _table_fallback(
    client: LandingClient, landing: Landing, known: Dict[int, Member], in_train: Set[int]
) -> List[Member]:
    extra = []
    for number in table_members(landing.body):
        if number not in known and number != landing.pr_number:
            member = _table_member(client, number, in_train)
            if member is not None:
                extra.append(member)
    return extra


def resolve_members(client: LandingClient, landing: Landing) -> List[Member]:
    """The PRs a merge carried. A train from its merge commits, else the body table."""
    if not landing.is_train:
        return [Member(landing.pr_number, landing.body, SOURCE_SELF)]
    commits = pr_commits(client, landing.pr_number)
    resolved: Dict[int, Member] = {}
    unresolved = 0
    for sha in merge_second_parents(commits):
        member = _member_for_head(client, sha, landing.pr_number)
        if member is None:
            unresolved += 1
        else:
            resolved.setdefault(member.number, member)
    members = list(resolved.values())
    if unresolved or not members:
        members += _table_fallback(client, landing, resolved, merged_in_train(commits, landing.branch))
    for member in members:
        logger.info("member #%s (source: %s)", member.number, member.source)
    return members


def collect_targets(landing: Landing, members: Sequence[Member], repo: str) -> Dict[int, Target]:
    """Every referenced issue once, with the members that referenced it."""
    skip = {landing.pr_number, *(m.number for m in members)}
    targets: Dict[int, Target] = {}
    sources: List[Tuple[Optional[int], str]] = [(m.number, m.body) for m in members]
    if landing.is_train:
        sources.append((None, landing.body))
    for via, body in sources:
        for number, closing in parse_references(body, repo).items():
            if number in skip:
                continue
            target = targets.setdefault(number, Target())
            target.closing = target.closing or closing
            if via is not None and via not in target.via:
                target.via.append(via)
    return targets


def landed_via_train(client: LandingClient, landing: Landing) -> Optional[int]:
    """The train a plain PR landed inside, whose own run posts the notes."""
    for pr in client.try_get(f"/repos/{client.repo}/commits/{landing.merge_sha}/pulls") or []:
        head = (pr.get("head") or {}).get("ref", "")
        if pr.get("number") != landing.pr_number and head.startswith(TRAIN_PREFIX):
            return int(pr["number"])
    return None


def apply_label(client: LandingClient, number: int) -> None:
    ensure_label(client, EVIDENCE_LABEL, EVIDENCE_LABEL_COLOR, EVIDENCE_LABEL_DESCRIPTION)
    client.call("POST", f"/repos/{client.repo}/issues/{number}/labels", {"labels": [EVIDENCE_LABEL]})


def _note_present(
    client: LandingClient, number: int, label: bool, comments: List[Dict[str, Any]], dry_run: bool
) -> str:
    """The note landed earlier; a label that failed then is re-applied unless evidence cleared it."""
    if not label or any(is_trusted_evidence(c) for c in comments):
        return "skipped (note present)"
    if dry_run:
        return "would re-apply label (note present)"
    apply_label(client, number)
    return "label re-applied (note present)"


def land_issue(client: LandingClient, landing: Landing, number: int, target: Target, dry_run: bool) -> str:
    """Label first, then note: each step is safe to retry, and a rerun repairs a missing label."""
    issue = client.call("GET", f"/repos/{client.repo}/issues/{number}")
    if issue.get("pull_request"):
        return "skipped (a pull request)"
    comments = client.comments(number)
    label = needs_evidence_label(issue, target.closing) and not has_evidence_label(issue)
    if has_note(comments, landing.marker):
        return _note_present(client, number, label, comments, dry_run)
    if dry_run:
        return f"would post{' + label' if label else ''}: {note_text(landing, target.via).splitlines()[1]}"
    if label:
        apply_label(client, number)
    body = {"body": note_text(landing, target.via)}
    client.call("POST", f"/repos/{client.repo}/issues/{number}/comments", body, ok=(201,))
    return "posted + label" if label else "posted"


def run_merged(client: LandingClient, landing: Landing, dry_run: bool = False) -> Dict[int, str]:
    """Issue number -> outcome. Raises after the loop if any issue failed."""
    if not landing.is_train:
        train = landed_via_train(client, landing)
        if train is not None:
            logger.info("#%s landed inside train #%s; that run posts its notes", landing.pr_number, train)
            return {}
    targets = collect_targets(landing, resolve_members(client, landing), client.repo)
    outcomes: Dict[int, str] = {}
    for number, target in sorted(targets.items()):
        try:
            outcomes[number] = land_issue(client, landing, number, target, dry_run)
        except LandingNoteError as exc:
            outcomes[number] = f"FAILED: {exc}"
        logger.info("#%s: %s", number, outcomes[number])
    failed = [n for n, outcome in outcomes.items() if outcome.startswith("FAILED")]
    if failed:
        raise LandingNoteError(f"landing note failed on {failed}")
    return outcomes


def run_evidence(client: LandingClient, event: Dict[str, Any]) -> bool:
    """Remove ``needs-ac-evidence`` when the comment holds an AC evidence table."""
    if not should_clear_label(event):
        return False
    number = int(event["issue"]["number"])
    name = urllib.parse.quote(EVIDENCE_LABEL)
    client.call("DELETE", f"/repos/{client.repo}/issues/{number}/labels/{name}", ok=(200, 404))
    logger.info("#%s: %s removed (AC evidence table posted)", number, EVIDENCE_LABEL)
    return True


def _landing_for(client: LandingClient, args: argparse.Namespace) -> Landing:
    if args.pr:
        return landing_from_pr(client.call("GET", f"/repos/{client.repo}/pulls/{args.pr}"))
    with open(args.event, encoding="utf-8") as handle:
        return landing_from_pr(json.load(handle)["pull_request"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("merged", "evidence"))
    parser.add_argument("--event", help="GITHUB_EVENT_PATH")
    parser.add_argument("--pr", type=int, help="merged only: read this PR from the API instead of --event")
    parser.add_argument("--dry-run", action="store_true", help="merged only: read, resolve and print; write nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = LandingClient(build_api())
    if args.command == "evidence":
        with open(args.event, encoding="utf-8") as handle:
            run_evidence(client, json.load(handle))
        return 0
    try:
        run_merged(client, _landing_for(client, args), dry_run=args.dry_run)
    except LandingNoteError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
