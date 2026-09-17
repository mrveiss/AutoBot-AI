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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_pr_issue_batching import check as check_batching  # noqa: E402
from check_pr_template_sections import report as check_template_sections  # noqa: E402
import os

#: Fallback when the env var is unset or unparseable.
_DEFAULT_GH_TIMEOUT_SECONDS = 30


def _gh_timeout_seconds() -> int:
    """Seconds to wait for ``gh pr view``, overridable per environment.

    Not a module-level ``int(os.environ.get(...))``: a bare cast there raises
    ``ValueError`` at IMPORT on a malformed value, which `repo_tests/
    env_var_bare_cast_test.py` exists to prevent. A pre-push hook that cannot
    even be imported because someone exported a typo is worse than one that
    falls back.
    """
    raw = os.environ.get("AUTOBOT_PR_BODY_GH_TIMEOUT_SECONDS")
    if not raw:
        return _DEFAULT_GH_TIMEOUT_SECONDS
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_GH_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)


class PRLookupError(RuntimeError):
    """``gh pr view`` failed or returned something this script cannot use."""


def pr_fields(ref: str) -> dict[str, str]:
    """``{body, actor, branch, title}`` for the open PR named by *ref*.

    *ref* is whatever ``gh pr view`` accepts: a number or a branch name.
    Field names match ``pr-issue-validation.yml``'s ``PR_ACTOR``/``PR_BRANCH``/
    ``PR_TITLE`` exactly (``author.login``, ``headRefName``, ``title``) so a
    body checked here is judged by the same facts CI would use.
    """
    try:
        raw = subprocess.run(
            ["gh", "pr", "view", ref, "--json", "body,author,headRefName,title"],
            capture_output=True,
            text=True,
            timeout=_gh_timeout_seconds(),
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
    }


def validate(body: str, actor: str = "", branch: str = "", title: str = "") -> bool:
    """Run both gates against *body*, print their own output, return overall ok."""
    sections_ok, section_lines = check_template_sections(body)
    for line in section_lines:
        logger.info("%s", line)

    batching_ok, batching_message = check_batching(body, actor=actor, branch=branch, title=title)
    logger.info("%s", batching_message)

    return sections_ok and batching_ok


def main(argv: list[str] | None = None) -> int:
    # force=True: a repeated in-process call (this test suite calls main()
    # multiple times) must reconfigure the stream, not keep the first call's
    # now-stale handler pointed at a stdout capsys has since swapped out.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", metavar="PATH", help="local body file, checked before gh pr create --body-file")
    source.add_argument("--pr", metavar="REF", help="existing PR number or branch name, fetched via gh pr view")
    # Only meaningful with --file: --pr already carries the real branch/title/actor.
    parser.add_argument(
        "--branch", default="", help="branch name for the batching gate's hotfix-* exemption (--file only)"
    )
    parser.add_argument("--title", default="", help="PR title for the batching gate's revert exemption (--file only)")
    args = parser.parse_args(argv)

    if args.pr:
        try:
            fields = pr_fields(args.pr)
        except PRLookupError as exc:
            logger.error("::error::%s", exc)
            return 1
        ok = validate(fields["body"], actor=fields["actor"], branch=fields["branch"], title=fields["title"])
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
