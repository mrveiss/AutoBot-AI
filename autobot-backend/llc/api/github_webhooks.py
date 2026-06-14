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

import hashlib
import hmac
import json
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from llc.deps import get_session

from ..models.enums import WorkItemStatus
from ..models.work_item import LLCWorkItem, LLCWorkItemComment

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


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify a GitHub webhook HMAC-SHA256 signature.

    Prevents spoofed webhook payloads from untrusted sources.
    """
    if not signature or not signature.startswith("sha256="):
        return False

    expected_sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


def _system_comment(item: LLCWorkItem, body: str) -> LLCWorkItemComment:
    return LLCWorkItemComment(
        company_id=item.company_id,
        work_item_id=item.id,
        body=body,
        author_agent_id=None,
        author_user_id=None,
    )


@router.post("/github")
async def handle_github_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Handle GitHub ``pull_request`` webhook events for PR auto-linking.

    Auto-links the PR to a work item resolved from:
    1. Branch name: ``llc/{work_item_id}`` (and variants)
    2. PR body: ``Closes #llc-{work_item_id}``

    On PR merge → transition the work item to ``in_review``.
    On PR close without merge → add a comment to the work item.
    """
    webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("GITHUB_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(
            status_code=503,
            detail="Webhook endpoint not configured. Set GITHUB_WEBHOOK_SECRET.",
        )

    body = await request.body()
    if not x_hub_signature_256:
        logger.warning("GitHub webhook: missing signature header")
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    if not verify_webhook_signature(body, x_hub_signature_256, webhook_secret):
        logger.warning("GitHub webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

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

    stmt = select(LLCWorkItem).where(LLCWorkItem.id == work_item_uuid)
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        logger.warning("Work item %s not found", work_item_uuid)
        return {"status": "error", "reason": "Work item not found"}

    current_urls = item.linked_pr_urls or []
    if pr_url and pr_url not in current_urls:
        item.linked_pr_urls = current_urls + [pr_url]
        session.add(_system_comment(item, f"🔗 GitHub PR #{pr_number} linked: {pr_url}"))
        logger.info("Linked PR #%s to work item %s", pr_number, work_item_uuid)

    if action == "closed" and pr_merged:
        current_status = WorkItemStatus(item.status)
        if current_status not in (WorkItemStatus.DONE, WorkItemStatus.CANCELLED):
            item.status = WorkItemStatus.IN_REVIEW
            session.add(
                _system_comment(
                    item,
                    f"✅ PR #{pr_number} merged → transitioned from " f"{current_status.value} to in_review",
                )
            )
            logger.info(
                "PR #%s merged: transitioned work item %s to in_review",
                pr_number,
                work_item_uuid,
            )
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
