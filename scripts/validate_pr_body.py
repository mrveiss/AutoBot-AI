# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run both PR-body gates locally, before CI ever sees the body (#16859).

``check_pr_template_sections.py`` and ``check_pr_issue_batching.py`` already run
standalone and exit non-zero with actionable text -- CI proves that on every PR.
What neither has is a way to run *before* the push: ``gh pr create --body-file``
never loads ``.github/PULL_REQUEST_TEMPLATE.md``, so a non-interactive author
starts from whatever headings they chose, pushes, burns a full CI run, and
learns the requirement from a red check afterwards (#16859's evidence: four
authors in one hour, including the author of the template-sections gate itself,
missing ``## Model Used`` on consecutive PRs).

This is a thin dispatcher, not a third implementation of either rule -- it
imports ``report()`` and ``check()`` directly, the same functions CI calls, so
a body that passes here passes there and the two can never disagree about what
counts as a violation.

Two ways to point it at a body:

* ``--file PATH`` -- a body written to disk before ``gh pr create --body-file``
  runs. This is the only mode that can catch the defect before the FIRST push:
  nothing (a git hook included) can read a PR body that has no PR yet.
* ``--pr REF`` -- an existing PR (number or branch name), fetched live via
  ``gh pr view``. Covers every push AFTER the PR exists, which is what
  ``tools/git-hooks/pre-push`` uses this for -- see its own comment for why it
  cannot cover the first push either, and says so rather than silently skipping.

Exit code is 0 only when both gates pass; each gate's own output is printed as
that gate already writes it; the failure summary above it is not invented here.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_pr_issue_batching import check as check_batching  # noqa: E402
from check_pr_template_sections import report as check_template_sections  # noqa: E402

#: Seconds to wait for `gh pr view`. Named rather than inline, per the repository's
#: hardcoded-value rule (#694/#14371), and matching the existing convention in
#: pipeline-scripts/ci_red_cause.py and ci_dispatch_watchdog.py.
DEFAULT_TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)


class PRLookupError(RuntimeError):
    """``gh pr view`` failed or returned something this script cannot use."""


def pr_fields(ref: str) -> dict[str, str]:
    """``{body, actor, branch, title, base}`` for the open PR named by *ref*.

    *ref* is whatever ``gh pr view`` accepts: a number or a branch name.
    Field names match ``pr-issue-validation.yml``'s ``PR_ACTOR``/``PR_BRANCH``/
    ``PR_TITLE`` exactly (``author.login``, ``headRefName``, ``title``) so a
    body checked here is judged by the same facts CI would use.
    """
    try:
        raw = subprocess.run(
            ["gh", "pr", "view", ref, "--json", "body,author,headRefName,title,baseRefName"],
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            check=True,
        )
    except FileNotFoundError as exc:
        raise PRLookupError("gh CLI not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise PRLookupError(f"gh pr view timed out for {ref!r}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise PRLookupError(f"gh pr view failed for {ref!r}: {stderr or 'no PR found'}") from exc

    try:
        data = json.loads(raw.stdout)
    except json.JSONDecodeError as exc:
        raise PRLookupError(f"gh pr view returned unparseable JSON for {ref!r}") from exc

    return {
        "body": data.get("body") or "",
        "actor": (data.get("author") or {}).get("login") or "",
        "branch": data.get("headRefName") or "",
        "title": data.get("title") or "",
        # #15473: the title gate judges a title as the squash subject it will
        # become, and a main -> release promotion is merged, not squashed.
        "base": data.get("baseRefName") or "",
    }


#: The commit-subject rule, LOADED from the one place it is written rather than
#: restated here (#15473). A squash merge takes its subject from the PR TITLE,
#: and nothing validated that: `fix(deps+security): ...` passed every local
#: hook, merged, and put a non-conforming subject on main that the range check
#: then failed for every PR afterwards — including a release promotion carrying
#: 682 commits. Local commit subjects were guarded; the one subject a human
#: never types directly was not. A second copy of the pattern here would have
#: rebuilt that same shape — two enforcers of one rule, free to drift — so the
#: shell script and this gate read the identical file.
_SUBJECT_ERE_FILE = Path(__file__).resolve().parent / "lib" / "commit-subject.ere"


def _load_subject_pattern(path: Path = _SUBJECT_ERE_FILE) -> re.Pattern[str]:
    """Read the single-source ERE, failing closed on anything unexpected.

    Raises rather than falling back to a built-in default: a default would make
    a missing or malformed rule file look exactly like a rule that passed, which
    is the defect this whole gate exists to prevent.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - exercised via the unreadable-path test
        raise RuntimeError(f"cannot read the commit-subject rule at {path}: {exc}") from exc
    lines = [ln for ln in (line.strip() for line in raw.splitlines()) if ln and not ln.startswith("#")]
    if len(lines) != 1:
        raise RuntimeError(f"{path} must hold exactly one pattern, found {len(lines)}")
    return re.compile(lines[0])


_SUBJECT_RE = _load_subject_pattern()

#: Subjects that reach main without passing through the title, exactly as
#: lint-conventions.sh exempts them in RANGE mode -- the mode that will judge
#: this title once it is a commit on main. Its commit-msg mode also exempts
#: `fixup!`/`squash!`, deliberately not mirrored here: those are local
#: work-in-progress forms, and a PR titled that way would pass this gate and
#: then fail the range check permanently, which is the exact failure this
#: function exists to prevent.
_SUBJECT_EXEMPT_PREFIXES = ("Merge ", "Revert ", "chore: claim worktree")


def check_title(title: str) -> tuple[bool, str]:
    """Whether *title* can become a conforming squash-merge subject.

    An empty title is not judged: `--file` mode has no PR to read one from, and
    refusing there would block the pre-push check that runs before the PR exists.
    """
    if not title or title.startswith(_SUBJECT_EXEMPT_PREFIXES):
        return True, "PR title: not checked (no title supplied, or an exempt form)"
    if not _SUBJECT_RE.match(title):
        return False, (
            f"PR title is not '<type>(scope): <description>': {title!r}\n"
            "  A squash merge uses this as the commit subject, so a title that fails here puts a\n"
            "  non-conforming commit on main permanently — it cannot be amended afterwards.\n"
            "  Scope accepts [a-z0-9._/,-] and must start alphanumeric; '+' is not a separator."
        )
    if not re.search(r"#[0-9]{3,}", title):
        return False, f"PR title carries no issue reference (#NNN): {title!r}"
    return True, "PR title conforms to the commit-subject convention"


def validate(body: str, actor: str = "", branch: str = "", title: str = "", base: str = "main") -> bool:
    """Run every gate, print each one's own output, return the overall verdict."""
    sections_ok, section_lines = check_template_sections(body)
    for line in section_lines:
        logger.info("%s", line)

    batching_ok, batching_message = check_batching(body, actor=actor, branch=branch, title=title)
    logger.info("%s", batching_message)

    # Defaults to "main" so --file mode, which has no PR to read a base from,
    # gets the gate rather than skipping it: main is where all but the promotion
    # PRs go, and a default that skipped would make the common case unguarded.
    if base == "main":
        title_ok, title_message = check_title(title)
    else:
        title_ok, title_message = True, (
            f"PR title: not checked -- base is {base!r}, not 'main'. A promotion is merged, "
            "not squashed, so its title never becomes a commit subject (#15473)."
        )
    logger.info("%s", title_message)

    return sections_ok and batching_ok and title_ok


def main(argv: list[str] | None = None) -> int:
    # force=True: a repeated in-process call (this test suite calls main()
    # multiple times) must reconfigure the stream, not keep the first call's
    # now-stale handler pointed at a stdout capsys has since swapped out.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", metavar="PATH", help="local body file, checked before gh pr create --body-file")
    source.add_argument("--pr", metavar="REF", help="existing PR number or branch name, fetched via gh pr view")
    # #15473: CI needs the title gate WITHOUT the body gates. pr-template-check
    # runs on `edited`, which is the only event that sees a title changed after
    # the last push -- and the title at merge time is the squash subject. Its
    # sections check is already covered there by check_pr_template_sections.py,
    # so re-running the body gates here would change what that job blocks on.
    source.add_argument("--title-only", metavar="TEXT", help="check just the PR title, as CI does on `edited`")
    # Only meaningful with --file: --pr already carries the real branch/title/actor.
    parser.add_argument(
        "--branch", default="", help="branch name for the batching gate's hotfix-* exemption (--file only)"
    )
    parser.add_argument(
        "--title",
        default="",
        help="PR title, for the batching gate's revert exemption and the title gate (--file only)",
    )
    args = parser.parse_args(argv)

    if args.title_only is not None:
        # Empty is FATAL here, and only here. check_title() treats "" as
        # "nothing to judge" because --file runs before a PR exists; CI always
        # has a title, so an empty one means the fetch failed. Passing on that
        # would be the governing defect -- a check that could not run reporting
        # clean -- on the one gate standing between a bad title and a permanent
        # commit subject.
        if not args.title_only.strip():
            logger.error(
                "::error::--title-only got an empty title: the PR title lookup failed, so the gate DID NOT RUN"
            )
            return 1
        ok, message = check_title(args.title_only)
        if ok:
            logger.info("%s", message)
            return 0
        logger.error("::error::%s", message)
        return 1

    if args.pr:
        try:
            fields = pr_fields(args.pr)
        except PRLookupError as exc:
            logger.error("::error::%s", exc)
            return 1
        ok = validate(
            fields["body"],
            actor=fields["actor"],
            branch=fields["branch"],
            title=fields["title"],
            base=fields["base"],
        )
    else:
        path = Path(args.file)
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("::error::could not read %s: %s", path, exc)
            return 1
        # No --actor: exemption() also keys on "dependabot[bot]", and --file has
        # nothing to fill that from. Deliberate, not an oversight -- dependabot
        # never runs a local hook or hand-authors a --file body, so the one
        # exemption this mode cannot express is also the one it never needs to.
        ok = validate(body, branch=args.branch, title=args.title)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
