# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the LLC GitHub webhook handler + link-pr endpoint (GH#9625).

Covers:
- work item ID extraction from branch names and PR bodies
- strict GitHub PR URL validation
- HMAC-SHA256 signature verification (fail-closed)
- webhook endpoint security gates (503 no secret, 401 bad signature)
- PR auto-link + merge transition + close-without-merge comment
"""

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SECRET = "test-webhook-secret"
_WORK_ITEM_ID = "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------


class TestExtractFromBranch:
    def _fn(self):
        from llc.api.github_webhooks import extract_work_item_id_from_branch  # noqa: PLC0415

        return extract_work_item_id_from_branch

    def test_llc_slash_pattern(self):
        assert self._fn()(f"llc/{_WORK_ITEM_ID}") == _WORK_ITEM_ID

    def test_autobot_llc_pattern(self):
        assert self._fn()(f"autobot-llc/{_WORK_ITEM_ID}") == _WORK_ITEM_ID

    def test_llc_dash_pattern(self):
        assert self._fn()(f"llc-{_WORK_ITEM_ID}") == _WORK_ITEM_ID

    def test_case_insensitive(self):
        assert self._fn()(f"LLC/{_WORK_ITEM_ID.upper()}") == _WORK_ITEM_ID.upper()

    def test_non_matching_branch(self):
        assert self._fn()("feature/some-work") is None
        assert self._fn()("issue-9625") is None

    def test_trailing_garbage_rejected(self):
        assert self._fn()(f"llc/{_WORK_ITEM_ID}/extra") is None


class TestExtractFromBody:
    def _fn(self):
        from llc.api.github_webhooks import extract_work_item_id_from_body  # noqa: PLC0415

        return extract_work_item_id_from_body

    @pytest.mark.parametrize("verb", ["Closes", "Fixes", "Resolves", "closes"])
    def test_keywords(self, verb):
        assert self._fn()(f"Work done.\n\n{verb} #llc-{_WORK_ITEM_ID}") == _WORK_ITEM_ID

    def test_empty_body(self):
        assert self._fn()(None) is None
        assert self._fn()("") is None

    def test_plain_issue_ref_ignored(self):
        assert self._fn()("Closes #9625") is None


class TestValidatePrUrl:
    def _fn(self):
        from llc.api.github_webhooks import validate_github_pr_url  # noqa: PLC0415

        return validate_github_pr_url

    def test_valid_with_repo_match(self):
        assert self._fn()("https://github.com/owner/repo/pull/123", "owner/repo") is True

    def test_valid_without_expected_repo(self):
        assert self._fn()("https://github.com/owner/repo/pull/123") is True

    def test_repo_mismatch(self):
        assert self._fn()("https://github.com/evil/repo/pull/123", "owner/repo") is False

    def test_http_rejected(self):
        assert self._fn()("http://github.com/owner/repo/pull/1", "owner/repo") is False

    def test_subdomain_rejected(self):
        assert self._fn()("https://evil.github.com/owner/repo/pull/1", "owner/repo") is False

    def test_query_and_fragment_rejected(self):
        assert self._fn()("https://github.com/o/r/pull/1?x=1", "o/r") is False
        assert self._fn()("https://github.com/o/r/pull/1#frag", "o/r") is False

    def test_non_pull_path_rejected(self):
        assert self._fn()("https://github.com/o/r/issues/1", "o/r") is False

    def test_empty_url(self):
        assert self._fn()("", "o/r") is False


class TestVerifySignature:
    def _fn(self):
        from llc.api.github_webhooks import verify_webhook_signature  # noqa: PLC0415

        return verify_webhook_signature

    def test_valid_signature(self):
        body = b'{"a": 1}'
        sig = "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert self._fn()(body, sig, _SECRET) is True

    def test_wrong_secret(self):
        body = b'{"a": 1}'
        sig = "sha256=" + hmac.new(b"other", body, hashlib.sha256).hexdigest()
        assert self._fn()(body, sig, _SECRET) is False

    def test_missing_prefix(self):
        assert self._fn()(b"x", "deadbeef", _SECRET) is False

    def test_empty_signature(self):
        assert self._fn()(b"x", "", _SECRET) is False


# ---------------------------------------------------------------------------
# Webhook endpoint tests
# ---------------------------------------------------------------------------


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _make_webhook_app(item=None):
    """Build a test app with the webhooks router and a mocked session."""
    from llc.api.github_webhooks import router as gw_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(gw_router)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session
    return app, mock_session


def _mock_item(status="in_progress", linked_pr_urls=None):
    item = MagicMock()
    item.id = uuid.UUID(_WORK_ITEM_ID)
    item.company_id = uuid.uuid4()
    item.status = status
    item.linked_pr_urls = linked_pr_urls or []
    return item


def _pr_payload(action="opened", merged=False, branch=f"llc/{_WORK_ITEM_ID}", body=""):
    return {
        "action": action,
        "pull_request": {
            "html_url": "https://github.com/mrveiss/AutoBot-AI/pull/123",
            "number": 123,
            "merged": merged,
            "head": {"ref": branch},
            "body": body,
        },
        "repository": {"full_name": "mrveiss/AutoBot-AI"},
    }


def _post(client, payload, sign=True, event="pull_request"):
    body = json.dumps(payload).encode()
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if sign:
        headers["X-Hub-Signature-256"] = _sign(body)
    return client.post("/webhooks/github", content=body, headers=headers)


class TestWebhookEndpoint:
    def test_no_secret_configured_503(self, monkeypatch):
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        app, _ = _make_webhook_app()
        resp = _post(TestClient(app), _pr_payload())
        assert resp.status_code == 503

    def test_missing_signature_401(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        app, _ = _make_webhook_app()
        resp = _post(TestClient(app), _pr_payload(), sign=False)
        assert resp.status_code == 401

    def test_invalid_signature_401(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        app, _ = _make_webhook_app()
        body = json.dumps(_pr_payload()).encode()
        resp = TestClient(app).post(
            "/webhooks/github",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=" + "0" * 64,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    def test_non_pr_event_ignored(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        app, _ = _make_webhook_app()
        resp = _post(TestClient(app), {"zen": "ok"}, event="ping")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_no_work_item_pattern_ignored(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        app, _ = _make_webhook_app()
        resp = _post(TestClient(app), _pr_payload(branch="feature/foo"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_pr_opened_links_url_and_comments(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        item = _mock_item()
        app, session = _make_webhook_app(item)
        resp = _post(TestClient(app), _pr_payload(action="opened"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "processed"
        assert item.linked_pr_urls == ["https://github.com/mrveiss/AutoBot-AI/pull/123"]
        session.add.assert_called_once()  # link comment
        session.commit.assert_awaited_once()

    def test_body_pattern_links(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        item = _mock_item()
        app, _ = _make_webhook_app(item)
        payload = _pr_payload(branch="feature/foo", body=f"Closes #llc-{_WORK_ITEM_ID}")
        resp = _post(TestClient(app), payload)
        assert resp.json()["status"] == "processed"
        assert item.linked_pr_urls

    def test_merge_transitions_to_in_review(self, monkeypatch):
        from llc.models.enums import WorkItemStatus  # noqa: PLC0415

        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        item = _mock_item(status="in_progress")
        app, session = _make_webhook_app(item)
        resp = _post(TestClient(app), _pr_payload(action="closed", merged=True))
        assert resp.json()["status"] == "processed"
        assert item.status == WorkItemStatus.IN_REVIEW
        # Two comments: link + transition.
        assert session.add.call_count == 2

    def test_merge_does_not_touch_done_item(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        item = _mock_item(status="done")
        app, session = _make_webhook_app(item)
        resp = _post(TestClient(app), _pr_payload(action="closed", merged=True))
        assert resp.json()["status"] == "processed"
        assert item.status == "done"
        assert session.add.call_count == 1  # link comment only

    def test_close_without_merge_comments_only(self, monkeypatch):
        item = _mock_item(
            status="in_progress",
            linked_pr_urls=["https://github.com/mrveiss/AutoBot-AI/pull/123"],
        )
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        app, session = _make_webhook_app(item)
        resp = _post(TestClient(app), _pr_payload(action="closed", merged=False))
        assert resp.json()["status"] == "processed"
        assert item.status == "in_progress"
        assert session.add.call_count == 1  # close comment only (already linked)

    def test_mismatched_pr_url_rejected(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        item = _mock_item()
        app, _ = _make_webhook_app(item)
        payload = _pr_payload()
        payload["pull_request"]["html_url"] = "https://github.com/evil/repo/pull/123"
        resp = _post(TestClient(app), payload)
        assert resp.json()["status"] == "error"
        assert item.linked_pr_urls == []

    def test_work_item_not_found(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SECRET)
        app, _ = _make_webhook_app(item=None)
        resp = _post(TestClient(app), _pr_payload())
        assert resp.json()["status"] == "error"
