# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC GitHub webhooks handler for PR auto-linking (GH#9625).

Routes:
  POST   /api/llc/webhooks/github — receive GitHub webhook events

Security (fail-closed):
- Requires GITHUB_WEBHOOK_SECRET environment variable (503 if not set)
- Verifies HMAC-SHA256 signature on all requests (401 if invalid)
- Validates GitHub PR URLs with strict parsing and repo matching
"""

import json
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.webhook_signature import verify_webhook_signature
from llc.deps import session_dep

from ..models.enums import WorkItemStatus
from ..models.work_item import LLCWorkItem, LLCWorkItemComment
from ..services.accessors import get_handoff_service
from ..services.work_item_gated_done import ReviewRefused, hand_off_for_review
from ..services.work_item_service import _ALLOWED_TRANSITIONS

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["llc-github-webhooks"])

_BRANCH_PATTERNS = (
    r"^llc/([a-f0-9-]+)$",
    r"^autobot-llc/([a-f0-9-]+)$",
    r"^llc-([a-f0-9-]+)$",
)

_BODY_PATTERN = r"(?:Closes|Fixes|Resolves)\s+#llc-([a-f0-9-]+)"


def extract_work_item_id_from_branch(branch_name: str) -> Optional[str]:
    """Extract LLC work item ID from branch name patterns.

    Supported patterns: ``llc/{id}``, ``autobot-llc/{id}``, ``llc-{id}``.
    """
    for pattern in _BRANCH_PATTERNS:
        match = re.match(pattern, branch_name, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_work_item_id_from_body(pr_body: Optional[str]) -> Optional[str]:
    """Extract LLC work item ID from a PR body.

    Supported patterns: ``Closes|Fixes|Resolves #llc-{uuid}``.
    """
    if not pr_body:
        return None
    match = re.search(_BODY_PATTERN, pr_body, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def validate_github_pr_url(url: str, expected_repo: Optional[str] = None) -> bool:
    """Validate a GitHub PR URL with strict parsing (GH#9625 security review).

    - Requires exactly ``https://github.com`` (prevents homograph/subdomain
      attacks)
    - Validates path format: ``/owner/repo/pull/number``
    - Rejects query params and fragments
    - When ``expected_repo`` is given, verifies the URL's ``owner/repo``
      matches it (prevents cross-repo spoofing in webhook payloads)
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme != "https" or parsed.netloc != "github.com":
        return False

    if parsed.query or parsed.fragment:
        return False

    path_match = re.match(r"^/([^/]+)/([^/]+)/pull/(\d+)$", parsed.path)
    if not path_match:
        return False

    if expected_repo:
        owner, repo, _pr_num = path_match.groups()
        if f"{owner}/{repo}".lower() != expected_repo.lower():
            logger.warning(
                "PR URL repo mismatch: expected %s, got %s/%s",
                expected_repo,
                owner,
                repo,
            )
            return False

    return True


def _system_comment(item: LLCWorkItem, body: str) -> LLCWorkItemComment:
    return LLCWorkItemComment(
        company_id=item.company_id,
        work_item_id=item.id,
        body=body,
        author_agent_id=None,
        author_user_id=None,
    )


async def _load_item_locked(session: AsyncSession, work_item_id: UUID) -> Optional[LLCWorkItem]:
    """The item under its row lock (``_load_locked``'s shape), loaded BEFORE any change is made to it.

    A repeated or concurrent delivery waits here and then reads the item as the delivery before it left it. The
    lock comes first because the production session does not autoflush: a re-read after the link was set would
    overwrite it.
    """
    stmt = select(LLCWorkItem).where(LLCWorkItem.id == work_item_id).with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


#: Why a handoff was refused, as text for a comment: fixed wording, so no id or internal message reaches readers.
_REFUSAL_TEXT = {
    ReviewRefused.NO_SERVICE: "no handoff service is available",
    ReviewRefused.NO_REVIEWER: "it has no reviewer and no creator to hand it to",
    ReviewRefused.NOT_A_MEMBER: "its reviewer or creator is not a member of the company",
    ReviewRefused.NOT_THE_HOLDER: "the agent that held it no longer does",
    ReviewRefused.LACKS_ROLE: "its reviewer does not hold the role its review policy requires",
}


async def _hand_off(session: AsyncSession, item: LLCWorkItem) -> Optional[str]:
    """Hand the held item to its reviewer; ``None`` when it went, else the fixed text of why it did not."""
    try:
        await hand_off_for_review(
            get_handoff_service(), session, item, str(item.company_id), str(item.assignee_agent_id)
        )
    except ReviewRefused as exc:
        return _REFUSAL_TEXT.get(exc.reason, "the handoff was refused")
    return None


async def _review_after_merge(session: AsyncSession, item: LLCWorkItem, pr_number: Any) -> None:
    """A merged PR puts the item in review only through the review handoff, with a reviewer named (#21591).

    The reviewer rule is ``hand_off_for_review``'s: the item's reviewer, else its creator, who must be a
    company member. An item that is finished, may not enter review from its status, is held by no agent, or has
    no reviewer is left where it is, with a comment a person can read saying why.
    """
    current = WorkItemStatus(item.status)
    if current in (WorkItemStatus.DONE, WorkItemStatus.CANCELLED):
        return
    why = None
    if WorkItemStatus.IN_REVIEW not in _ALLOWED_TRANSITIONS.get(current, set()):
        why = f"review cannot start from {current.value}"
    elif item.assignee_agent_id is None:
        why = "no agent holds it, so there is no handoff to make"
    else:
        why = await _hand_off(session, item)
    if why is None:
        session.add(_system_comment(item, f"✅ PR #{pr_number} merged → handed to its reviewer for review"))
        logger.info("PR #%s merged: handed work item %s to review", pr_number, item.id)
        return
    session.add(_system_comment(item, f"✅ PR #{pr_number} merged; the item stays {current.value}: {why}"))
    logger.info("PR #%s merged: work item %s left in %s (%s)", pr_number, item.id, current.value, why)


def _require_valid_signature(body: bytes, signature: Optional[str]) -> None:
    """Fail closed: 503 without a configured secret, 401 on a missing or invalid signature."""
    webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("GITHUB_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(
            status_code=503,
            detail="Webhook endpoint not configured. Set GITHUB_WEBHOOK_SECRET.",
        )
    if not signature:
        logger.warning("GitHub webhook: missing signature header")
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    if not verify_webhook_signature(body, signature, webhook_secret):
        logger.warning("GitHub webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@router.post("/github")
async def handle_github_webhook(
    request: Request,
    session: AsyncSession = session_dep,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Handle GitHub ``pull_request`` webhook events for PR auto-linking.

    Auto-links the PR to a work item resolved from:
    1. Branch name: ``llc/{work_item_id}`` (and variants)
    2. PR body: ``Closes #llc-{work_item_id}``

    On PR merge → hand the work item to its reviewer through the review handoff, or leave it
    where it is with a comment saying why (#21591).
    On PR close without merge → add a comment to the work item.
    """
    body = await request.body()
    _require_valid_signature(body, x_hub_signature_256)

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": "Not a pull_request event"}

    payload = json.loads(body)
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    pr_url = pr.get("html_url")
    pr_number = pr.get("number")
    pr_merged = pr.get("merged", False)
    branch_name = pr.get("head", {}).get("ref", "")
    pr_body = pr.get("body", "")
    repo_full_name = payload.get("repository", {}).get("full_name", "")

    work_item_id_str = extract_work_item_id_from_branch(branch_name)
    if not work_item_id_str:
        work_item_id_str = extract_work_item_id_from_body(pr_body)

    if not work_item_id_str:
        logger.info(
            "GitHub webhook: no LLC work item ID found in branch '%s' or PR body",
            branch_name,
        )
        return {"status": "ignored", "reason": "No LLC work item ID pattern found"}

    try:
        work_item_uuid = UUID(work_item_id_str)
    except ValueError:
        logger.warning("Invalid UUID in branch/body: %s", work_item_id_str)
        return {"status": "error", "reason": "Invalid work item ID format"}

    if pr_url and not validate_github_pr_url(pr_url, repo_full_name):
        logger.warning(
            "Invalid or mismatched PR URL: %s (expected repo: %s)",
            pr_url,
            repo_full_name,
        )
        return {"status": "error", "reason": "Invalid or mismatched PR URL"}

    item = await _load_item_locked(session, work_item_uuid)
    if not item:
        logger.warning("Work item %s not found", work_item_uuid)
        return {"status": "error", "reason": "Work item not found"}

    current_urls = item.linked_pr_urls or []
    if pr_url and pr_url not in current_urls:
        item.linked_pr_urls = current_urls + [pr_url]
        session.add(_system_comment(item, f"🔗 GitHub PR #{pr_number} linked: {pr_url}"))
        logger.info("Linked PR #%s to work item %s", pr_number, work_item_uuid)

    if action == "closed" and pr_merged:
        await _review_after_merge(session, item, pr_number)
    elif action == "closed" and not pr_merged:
        session.add(_system_comment(item, f"❌ PR #{pr_number} closed without merge"))
        logger.info("PR #%s closed without merge", pr_number)

    await session.commit()

    return {
        "status": "processed",
        "work_item_id": str(work_item_uuid),
        "pr_url": pr_url,
        "action": action,
    }
