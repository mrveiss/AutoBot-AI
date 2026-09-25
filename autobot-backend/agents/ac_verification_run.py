# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One issue number in, one posted verification out (#17090 AC 1).

The three pieces are separate modules on purpose -- `ac_criteria` reads,
`ac_verifier` judges, `ac_poster` talks to GitHub -- and this is the only place
that knows the order. It exists so a caller (the SLM queue in #17092, the
budgeted dev-loop gate in #17091) states an issue number and nothing else.

`publish=False` runs everything except the write. That is not a convenience: a
human triggering a verification from the queue should be able to see what would
be posted before it is, and a test of this module must not need a credential to
prove the ordering is right.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from agents.ac_poster import PostOutcome, fetch_issue, post_verification
from agents.ac_verifier import SUMMARY_BLOCK_TAG, IssueVerification, render_comment, verify_issue
from autobot_shared.logging_manager import get_logger
from services.github_service_credential import reset_env_cache

logger = get_logger(__name__)


@dataclass(frozen=True)
class RunOutcome:
    """What one verification run produced, published or not."""

    verification: IssueVerification
    comment: str
    post: PostOutcome

    def as_payload(self) -> dict:
        """The shape a queue page or a caller records (#17092)."""
        return {
            "issue": self.verification.issue_number,
            "counts": self.verification.counts(),
            "post": self.post.as_payload(),
        }


async def verify_and_post(
    issue_number: int,
    *,
    ref: str = "origin/main",
    publish: bool = True,
    repo_root: Optional[Path] = None,
    search: Callable[[Sequence[str]], str] | None = None,
    read: Callable[[str], Optional[str]] | None = None,
    force: bool = False,
) -> RunOutcome:
    """Verify *issue_number*'s acceptance criteria against *ref* and post the result.

    Raises:
        ac_poster.IssueUnreadable: the issue could not be read, so nothing was
            verified and nothing is posted -- deliberately not caught here, so a
            caller cannot mistake an unread issue for one with no criteria.
    """
    # FIRST, before any `gh` call: the credential cache is module-level and
    # shared with the audit worker, which resets it as the first statement of
    # every task for the reason #13859 records -- a token revoked or rotated
    # between runs otherwise keeps being used, and `vault_backed` is reported
    # True for a run that never resolved anything from the vault. This caller
    # inherited the cache and not the reset (review finding on merged #17090).
    reset_env_cache()

    body, comments = fetch_issue(issue_number, repo_root=repo_root)

    # `gh issue comment` is not idempotent: every call adds a comment. A caller
    # retrying after a reported failure -- which cannot distinguish "never sent"
    # from "sent but the local process did not see success" -- would post twice,
    # with two verdicts that may disagree if the code moved between them. The
    # comments are already in hand from the fetch above, so the check is free.
    already = [cid for cid, text in comments if SUMMARY_BLOCK_TAG in text]
    if already and not force:
        verification = await verify_issue(issue_number, body, comments, search=search, read=read, ref=ref)
        reason = (
            f"a verification comment is already on this issue ({', '.join(already[:3])}); "
            "pass force=True to post another"
        )
        logger.info("ac verification on #%s: %s", issue_number, reason)
        return RunOutcome(
            verification=verification,
            comment=render_comment(verification),
            post=PostOutcome(posted=False, reason=reason),
        )
    verification = await verify_issue(issue_number, body, comments, search=search, read=read, ref=ref)
    comment = render_comment(verification)

    if not publish:
        return RunOutcome(
            verification=verification,
            comment=comment,
            post=PostOutcome(posted=False, reason="publish=False: this run was a preview"),
        )

    outcome = post_verification(issue_number, comment, repo_root=repo_root)
    logger.info(
        "ac verification on #%s: %s, posted=%s",
        issue_number,
        verification.counts(),
        outcome.posted,
    )
    return RunOutcome(verification=verification, comment=comment, post=outcome)


__all__ = ["RunOutcome", "verify_and_post"]
