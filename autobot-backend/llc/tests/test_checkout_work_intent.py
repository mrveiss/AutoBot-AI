# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for workIntent field on work-item checkout (GH#9532).

Verifies:
  1. Checkout with work_intent stores it in checkout_intent field.
  2. Checkout without work_intent preserves existing behaviour (checkout_intent=None).
  3. Similarity helper is called with intent + title when intent is provided.
  4. Similarity check failure does NOT abort checkout.
  5. Comment is posted on successful checkout with intent.
  6. Comment posting failure does NOT abort checkout.
  7. work_intent_similarity.check_similarity degrades gracefully when embedding unavailable.
  8. Cosine similarity computation is correct for known vectors.
"""

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.work_item_service import WorkItemService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(**kwargs) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "identifier": "WI-532",
        "type": WorkItemType.TASK,
        "title": "Implement OAuth login flow",
        "status": WorkItemStatus.READY,
        "priority": WorkItemPriority.HIGH,
        "version": 1,
        "labels": [],
        "checkout_run_id": None,
        "checkout_locked_at": None,
        "checkout_intent": None,
        "assignee_agent_id": None,
        "assignee_user_id": None,
        "assignee_type": None,
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(kwargs)
    item = MagicMock(spec=LLCWorkItem)
    for k, v in defaults.items():
        setattr(item, k, v)
    return item


@pytest.fixture
def service():
    return WorkItemService()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    _db_result = MagicMock()
    session.execute = AsyncMock(return_value=_db_result)
    session._db_result = _db_result
    return session


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# CheckoutRequest field tests (service layer)
# ---------------------------------------------------------------------------


class TestWorkIntentCheckout:
    async def test_checkout_stores_intent(self, service, mock_session, mock_redis):
        """checkout() writes work_intent to checkout_intent field."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ), patch(
            "llc.services.work_item_service._run_intent_similarity",
            new=AsyncMock(),
        ), patch(
            "llc.services.work_item_service._post_checkout_comment",
            new=AsyncMock(),
        ):
            result = await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="implement OAuth login",
            )

        assert result.checkout_intent == "implement OAuth login"

    async def test_checkout_without_intent_leaves_none(self, service, mock_session, mock_redis):
        """checkout() without work_intent leaves checkout_intent as None."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await service.checkout(mock_session, str(item.id), agent_id)

        assert result.checkout_intent is None

    async def test_checkout_calls_similarity_when_intent_present(self, service, mock_session, mock_redis):
        """_run_intent_similarity is called with intent + title when intent is provided."""
        agent_id = str(uuid.uuid4())
        item = _make_item(title="Implement OAuth login flow")
        mock_session._db_result.scalar_one_or_none.return_value = item

        similarity_mock = AsyncMock()
        comment_mock = AsyncMock()
        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ), patch(
            "llc.services.work_item_service._run_intent_similarity",
            new=similarity_mock,
        ), patch(
            "llc.services.work_item_service._post_checkout_comment",
            new=comment_mock,
        ):
            await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="add oauth",
            )

        similarity_mock.assert_awaited_once_with("add oauth", "Implement OAuth login flow", str(item.id))

    async def test_checkout_skips_similarity_when_no_intent(self, service, mock_session, mock_redis):
        """_run_intent_similarity is NOT called when work_intent is None."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        similarity_mock = AsyncMock()
        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ), patch(
            "llc.services.work_item_service._run_intent_similarity",
            new=similarity_mock,
        ):
            await service.checkout(mock_session, str(item.id), agent_id)

        similarity_mock.assert_not_awaited()

    async def test_checkout_succeeds_when_similarity_raises(self, service, mock_session, mock_redis):
        """Checkout succeeds even when the similarity check raises an exception."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ), patch(
            "llc.services.work_item_service._run_intent_similarity",
            new=AsyncMock(side_effect=RuntimeError("embedding service down")),
        ), patch(
            "llc.services.work_item_service._post_checkout_comment",
            new=AsyncMock(),
        ):
            result = await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="fix the bug",
            )

        # checkout_intent still stored even if similarity failed
        assert result.checkout_intent == "fix the bug"

    async def test_checkout_posts_comment_with_intent(self, service, mock_session, mock_redis):
        """_post_checkout_comment is called with the correct arguments."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        comment_mock = AsyncMock()
        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ), patch(
            "llc.services.work_item_service._run_intent_similarity",
            new=AsyncMock(),
        ), patch(
            "llc.services.work_item_service._post_checkout_comment",
            new=comment_mock,
        ):
            await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="fix login bug",
            )

        comment_mock.assert_awaited_once()
        call_args = comment_mock.call_args
        assert call_args[0][2] == "fix login bug"  # work_intent arg
        assert call_args[0][3] == agent_id          # agent_id arg

    async def test_checkout_succeeds_when_comment_raises(self, service, mock_session, mock_redis):
        """Checkout succeeds even when comment posting raises an exception."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ), patch(
            "llc.services.work_item_service._run_intent_similarity",
            new=AsyncMock(),
        ), patch(
            "llc.services.work_item_service._post_checkout_comment",
            new=AsyncMock(side_effect=Exception("DB error")),
        ):
            result = await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="refactor auth module",
            )

        assert result.checkout_intent == "refactor auth module"


# ---------------------------------------------------------------------------
# work_intent_similarity unit tests
# ---------------------------------------------------------------------------


class TestWorkIntentSimilarity:
    async def test_cosine_computation(self):
        """_cosine returns 1.0 for identical vectors."""
        from llc.services.work_intent_similarity import _cosine

        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert abs(_cosine(v, v) - 1.0) < 1e-6

    async def test_cosine_orthogonal(self):
        """_cosine returns 0.0 for orthogonal vectors."""
        from llc.services.work_intent_similarity import _cosine

        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert abs(_cosine(a, b)) < 1e-6

    async def test_cosine_zero_vector(self):
        """_cosine returns 0.0 when a vector is zero."""
        from llc.services.work_intent_similarity import _cosine

        z = np.array([0.0, 0.0], dtype=np.float32)
        v = np.array([1.0, 0.0], dtype=np.float32)
        assert _cosine(z, v) == 0.0

    async def test_check_similarity_returns_none_when_embedding_unavailable(self):
        """check_similarity returns None when embedding function returns None."""
        from llc.services.work_intent_similarity import check_similarity

        with patch(
            "llc.services.work_intent_similarity._embed",
            new=AsyncMock(return_value=None),
        ):
            result = await check_similarity("do X", "title Y", "wi-001")

        assert result is None

    async def test_check_similarity_returns_score_on_success(self):
        """check_similarity returns a float when embeddings are available."""
        from llc.services.work_intent_similarity import check_similarity

        vec = np.array([1.0, 0.0], dtype=np.float32)
        with patch(
            "llc.services.work_intent_similarity._embed",
            new=AsyncMock(return_value=vec),
        ):
            result = await check_similarity("do X", "title Y", "wi-001")

        assert isinstance(result, float)
        assert abs(result - 1.0) < 1e-6  # identical vectors

    async def test_check_similarity_never_raises(self):
        """check_similarity returns None (not raises) when embedding raises."""
        from llc.services.work_intent_similarity import check_similarity

        with patch(
            "llc.services.work_intent_similarity._embed",
            new=AsyncMock(side_effect=RuntimeError("service unavailable")),
        ):
            result = await check_similarity("intent", "title", "wi-001")

        assert result is None

    async def test_check_similarity_warns_below_alert_threshold(self, caplog):
        """check_similarity emits a WARNING when score < 0.5."""
        import logging

        from llc.services.work_intent_similarity import check_similarity

        low_vec = np.array([1.0, 0.0], dtype=np.float32)
        high_vec = np.array([0.0, 1.0], dtype=np.float32)

        with patch(
            "llc.services.work_intent_similarity._embed",
            new=AsyncMock(side_effect=[low_vec, high_vec]),
        ), caplog.at_level(logging.WARNING, logger="llc.services.work_intent_similarity"):
            await check_similarity("unrelated topic", "completely different title", "wi-001")

        assert any("very low alignment" in r.message for r in caplog.records)

    async def test_check_similarity_info_logs_between_thresholds(self, caplog):
        """check_similarity emits an INFO log when 0.5 <= score < 0.7."""
        import logging

        from llc.services.work_intent_similarity import check_similarity

        # Vectors at ~60° produce cosine ~0.5; use exact 0.6 via known angle.
        # cos(θ)=0.6: a=(1,0), b=(0.6, 0.8) — dot=0.6, |a|=1, |b|=1.
        a_vec = np.array([1.0, 0.0], dtype=np.float32)
        b_vec = np.array([0.6, 0.8], dtype=np.float32)

        with patch(
            "llc.services.work_intent_similarity._embed",
            new=AsyncMock(side_effect=[a_vec, b_vec]),
        ), caplog.at_level(logging.INFO, logger="llc.services.work_intent_similarity"):
            score = await check_similarity("topic A", "related title", "wi-002")

        assert score is not None
        assert 0.5 <= score < 0.7
        assert any(
            "low alignment" in r.message and r.levelno == logging.INFO
            for r in caplog.records
        )
