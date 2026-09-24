# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading an issue and posting one verification comment, with an owned credential (#17090).

Two rules shape everything here, and both are refusals rather than behaviours.

This module is the whole GitHub surface of the verifier: it reads an issue
(`fetch_issue`) and writes one comment (`post_verification`), and nothing else
in the feature talks to GitHub at all.

**It comments; it never edits.** #17090's fourth criterion keeps ticking a
checkbox with a human or a reviewing agent, so the only write verb here is
`gh issue comment`; the only other verb is the read `gh issue view`.
`ac_poster_test.py::TestItNeverTicksABox` parses this file and asserts that,
because a rule held only by "nobody has written that call yet" is not held.

**It refuses ambient auth.** #13859 established that a background GitHub write
authenticates with a token the SYSTEM vault owns, never with whatever `gh` CLI
credential the host happens to carry: nothing owns ambient auth, nothing rotates
it, nothing audits it, and its absence shows up only as a log line. So when the
vault has no token this does not fall back and post anyway -- it returns
`PostOutcome(posted=False, reason=...)` and the caller reports a run that could
not publish its result. A verifier that silently posts as whoever the host is
logged in as would be the #13570 failure again, one layer up.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 -- fixed argv, no shell; see _run_gh
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.paths import git_repo_root
from services.github_service_credential import gh_env

logger = get_logger(__name__)

#: Long enough for a slow API round trip, short enough that a wedged `gh` does
#: not hold a worker: the same 60s the audit worker's own `gh` calls use.
_GH_TIMEOUT_S = 60

#: Said the same way whether reading or writing: the refusal is the credential
#: rule (#13859), not a property of the verb.
_NO_CREDENTIAL = (
    "no vault-owned GitHub credential is stored, and this will not fall back to ambient "
    "CLI auth (#13859); store one under the SYSTEM vault to let the verifier read and publish"
)


@dataclass(frozen=True)
class PostOutcome:
    """What happened to one comment, in a form a caller can report."""

    posted: bool
    #: Why not, when it did not. Empty on success.
    reason: str = ""
    #: Whether the credential came from the vault. False with `posted` True is
    #: impossible by construction -- the refusal above is what makes it so.
    vault_backed: bool = False

    def as_payload(self) -> dict:
        return {"posted": self.posted, "reason": self.reason, "vault_backed": self.vault_backed}


def _run_gh_capture(args: list[str], *, env: dict[str, str], cwd: Path) -> tuple[int, str, str]:
    """Run a READ-only `gh` call and return (code, stdout, stderr). Never raises."""
    try:
        result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(cwd),
            env=env,
            timeout=_GH_TIMEOUT_S,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", f"gh invocation failed ({type(exc).__name__})"


def _run_gh(args: list[str], *, body: str, env: dict[str, str], cwd: Path) -> tuple[int, str]:
    """Run `gh` with *body* on stdin. Never raises; returns (code, stderr)."""
    try:
        result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell
            ["gh", *args],
            input=body,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(cwd),
            env=env,
            timeout=_GH_TIMEOUT_S,
            check=False,
        )
        return result.returncode, result.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        # Class name only: this call's environment carries a token, and a
        # message that interpolated it would put it in the log.
        return 1, f"gh invocation failed ({type(exc).__name__})"


class IssueUnreadable(RuntimeError):
    """The issue could not be read, so there is nothing to verify.

    Raised rather than returning empty criteria: an issue whose body could not
    be fetched and an issue with no acceptance criteria are different facts,
    and reporting the first as the second would publish "nothing to verify"
    about an issue nobody read.
    """


def fetch_issue(issue_number: int, *, repo_root: Optional[Path] = None) -> tuple[str, list[tuple[str, str]]]:
    """*issue_number*'s body and its comments as ``(id, body)`` pairs (#17090 AC 1).

    Read with the same owned credential the comment is posted with, so the run
    cannot read as one identity and write as another.
    """
    env, vault_backed = gh_env()
    if not vault_backed:
        raise IssueUnreadable(_NO_CREDENTIAL)
    code, stdout, stderr = _run_gh_capture(
        ["issue", "view", str(issue_number), "--json", "body,comments"],
        env=env,
        cwd=repo_root or git_repo_root(),
    )
    if code != 0:
        raise IssueUnreadable(f"gh exited {code}: {stderr}")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise IssueUnreadable(f"gh returned unparseable JSON ({type(exc).__name__})") from exc
    comments = [
        (str(c.get("id", index)), str(c.get("body", ""))) for index, c in enumerate(payload.get("comments", []))
    ]
    return str(payload.get("body", "")), comments


def post_verification(issue_number: int, body: str, *, repo_root: Optional[Path] = None) -> PostOutcome:
    """Post *body* as ONE comment on *issue_number*, or say why it did not."""
    env, vault_backed = gh_env()
    if not vault_backed:
        logger.warning("ac_poster: refusing to post on #%s — %s", issue_number, _NO_CREDENTIAL)
        return PostOutcome(posted=False, reason=_NO_CREDENTIAL, vault_backed=False)

    code, stderr = _run_gh(
        ["issue", "comment", str(issue_number), "--body-file", "-"],
        body=body,
        env=env,
        cwd=repo_root or git_repo_root(),
    )
    if code != 0:
        logger.warning("ac_poster: gh refused the comment on #%s (%s)", issue_number, stderr)
        return PostOutcome(posted=False, reason=f"gh exited {code}: {stderr}", vault_backed=True)
    return PostOutcome(posted=True, vault_backed=True)


__all__ = ["IssueUnreadable", "PostOutcome", "fetch_issue", "post_verification"]
