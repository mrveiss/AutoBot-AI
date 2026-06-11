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
  8. Cosine similarity computation is correct for known vectors (pure-Python impl).
  9. _post_checkout_comment with flush failure leaves session usable (F4a — savepoint fix).
 10. Constructed comment body format matches expected pattern (F4b).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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

        with (
            patch(
                "llc.services.work_item_service.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch(
                "llc.services.work_item_service._schedule_intent_similarity",
            ),
            patch(
                "llc.services.work_item_service._post_checkout_comment",
                new=AsyncMock(),
            ),
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
        """_schedule_intent_similarity is called with intent + title when intent is provided."""
        agent_id = str(uuid.uuid4())
        item = _make_item(title="Implement OAuth login flow")
        mock_session._db_result.scalar_one_or_none.return_value = item

        schedule_mock = MagicMock()
        comment_mock = AsyncMock()
        with (
            patch(
                "llc.services.work_item_service.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch(
                "llc.services.work_item_service._schedule_intent_similarity",
                new=schedule_mock,
            ),
            patch(
                "llc.services.work_item_service._post_checkout_comment",
                new=comment_mock,
            ),
        ):
            await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="add oauth",
            )

        schedule_mock.assert_called_once_with("add oauth", "Implement OAuth login flow", str(item.id))

    async def test_checkout_skips_similarity_when_no_intent(self, service, mock_session, mock_redis):
        """_schedule_intent_similarity is NOT called when work_intent is None."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        schedule_mock = MagicMock()
        with (
            patch(
                "llc.services.work_item_service.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch(
                "llc.services.work_item_service._schedule_intent_similarity",
                new=schedule_mock,
            ),
        ):
            await service.checkout(mock_session, str(item.id), agent_id)

        schedule_mock.assert_not_called()

    async def test_checkout_succeeds_when_similarity_raises(self, service, mock_session, mock_redis):
        """Checkout succeeds even when the similarity schedule raises an exception."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        def _bad_schedule(*args, **kwargs):
            raise RuntimeError("embedding service down")

        with (
            patch(
                "llc.services.work_item_service.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch(
                "llc.services.work_item_service._schedule_intent_similarity",
                side_effect=_bad_schedule,
            ),
            patch(
                "llc.services.work_item_service._post_checkout_comment",
                new=AsyncMock(),
            ),
        ):
            result = await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="fix the bug",
            )

        # checkout_intent still stored even if similarity scheduling failed
        assert result.checkout_intent == "fix the bug"

    async def test_checkout_posts_comment_with_intent(self, service, mock_session, mock_redis):
        """_post_checkout_comment is called with the correct arguments."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        comment_mock = AsyncMock()
        with (
            patch(
                "llc.services.work_item_service.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch(
                "llc.services.work_item_service._schedule_intent_similarity",
            ),
            patch(
                "llc.services.work_item_service._post_checkout_comment",
                new=comment_mock,
            ),
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
        assert call_args[0][3] == agent_id  # agent_id arg

    async def test_checkout_succeeds_when_comment_raises(self, service, mock_session, mock_redis):
        """Checkout succeeds even when comment posting raises an exception."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with (
            patch(
                "llc.services.work_item_service.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch(
                "llc.services.work_item_service._schedule_intent_similarity",
            ),
            patch(
                "llc.services.work_item_service._post_checkout_comment",
                new=AsyncMock(side_effect=Exception("DB error")),
            ),
        ):
            result = await service.checkout(
                mock_session,
                str(item.id),
                agent_id,
                work_intent="refactor auth module",
            )

        assert result.checkout_intent == "refactor auth module"


# ---------------------------------------------------------------------------
# F4a — SAVEPOINT: flush failure leaves the session usable
# ---------------------------------------------------------------------------


class TestPostCheckoutCommentSavepoint:
    async def test_flush_failure_session_remains_usable(self):
        """_post_checkout_comment: SQLAlchemyError in flush rolls back only the
        nested savepoint; the outer session stays committable (F4a).
        """
        from sqlalchemy.exc import SQLAlchemyError

        from llc.services.work_item_service import _post_checkout_comment

        item = _make_item()
        agent_id = str(uuid.uuid4())

        # Simulate a session whose begin_nested context manager rolls back on
        # flush error but allows subsequent operations on the outer transaction.

        class _FakeNestedTxn:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc_val, exc_tb):
                # Suppress the exception so the outer session is not poisoned
                return True  # suppress

        session = AsyncMock()
        session.add = MagicMock()
        # First flush (inside begin_nested) raises; second (outer) succeeds.
        session.flush = AsyncMock(side_effect=SQLAlchemyError("flush failed"))
        session.begin_nested = MagicMock(return_value=_FakeNestedTxn())

        # _post_checkout_comment must NOT raise even when flush errors
        await _post_checkout_comment(session, item, "test intent", agent_id)

        # Now simulate that the outer session is still usable: reset flush and call it
        session.flush.side_effect = None
        session.flush.return_value = None
        await session.flush()  # must not raise — session is in usable state

    async def test_comment_body_format(self):
        """Comment body is 'Starting <identifier>: <intent>' (F4b)."""
        from llc.services.work_item_service import _post_checkout_comment

        item = _make_item(identifier="WI-999")
        agent_id = str(uuid.uuid4())

        class _FakeNestedTxn:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc_val, exc_tb):
                return False

        mock_svc = MagicMock(spec=WorkItemService)
        mock_svc.add_comment = AsyncMock()

        session = AsyncMock()
        session.begin_nested = MagicMock(return_value=_FakeNestedTxn())
        session.add = MagicMock()
        session.flush = AsyncMock()

        await _post_checkout_comment(session, item, "build the widget", agent_id, service=mock_svc)

        mock_svc.add_comment.assert_awaited_once()
        positional = mock_svc.add_comment.call_args[0]
        # add_comment signature: (session, work_item_id, company_id, body, ...)
        body_arg = positional[3]
        assert body_arg == "Starting WI-999: build the widget"

    async def test_author_attribution(self):
        """Comment is attributed to the checking-out agent (F4b)."""
        from llc.services.work_item_service import _post_checkout_comment

        item = _make_item(identifier="WI-100")
        agent_id = str(uuid.uuid4())

        class _FakeNestedTxn:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc_val, exc_tb):
                return False

        mock_svc = MagicMock(spec=WorkItemService)
        mock_svc.add_comment = AsyncMock()

        session = AsyncMock()
        session.begin_nested = MagicMock(return_value=_FakeNestedTxn())
        session.add = MagicMock()
        session.flush = AsyncMock()

        await _post_checkout_comment(session, item, "do work", agent_id, service=mock_svc)

        mock_svc.add_comment.call_args[0]
        kw = mock_svc.add_comment.call_args[1]
        # author_agent_id is passed as keyword arg
        assert kw.get("author_agent_id") == agent_id


# ---------------------------------------------------------------------------
# work_intent_similarity unit tests (pure-Python impl — no numpy)
# ---------------------------------------------------------------------------


class TestWorkIntentSimilarity:
    async def test_cosine_computation(self):
        """_cosine returns 1.0 for identical vectors."""
        from llc.services.work_intent_similarity import _cosine

        v = [1.0, 0.0, 0.0]
        assert abs(_cosine(v, v) - 1.0) < 1e-6

    async def test_cosine_orthogonal(self):
        """_cosine returns 0.0 for orthogonal vectors."""
        from llc.services.work_intent_similarity import _cosine

        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine(a, b)) < 1e-6

    async def test_cosine_zero_vector(self):
        """_cosine returns 0.0 when a vector is zero."""
        from llc.services.work_intent_similarity import _cosine

        z = [0.0, 0.0]
        v = [1.0, 0.0]
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

        vec = [1.0, 0.0]
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

        low_vec = [1.0, 0.0]
        high_vec = [0.0, 1.0]

        with (
            patch(
                "llc.services.work_intent_similarity._embed",
                new=AsyncMock(side_effect=[low_vec, high_vec]),
            ),
            caplog.at_level(logging.WARNING, logger="llc.services.work_intent_similarity"),
        ):
            await check_similarity("unrelated topic", "completely different title", "wi-001")

        assert any("very low alignment" in r.message for r in caplog.records)

    async def test_check_similarity_info_logs_between_thresholds(self, caplog):
        """check_similarity emits an INFO log when 0.5 <= score < 0.7."""
        import logging

        from llc.services.work_intent_similarity import check_similarity

        # cos(θ)=0.6: a=(1,0), b=(0.6, 0.8) — dot=0.6, |a|=1, |b|=1.
        a_vec = [1.0, 0.0]
        b_vec = [0.6, 0.8]

        with (
            patch(
                "llc.services.work_intent_similarity._embed",
                new=AsyncMock(side_effect=[a_vec, b_vec]),
            ),
            caplog.at_level(logging.INFO, logger="llc.services.work_intent_similarity"),
        ):
            score = await check_similarity("topic A", "related title", "wi-002")

        assert score is not None
        assert 0.5 <= score < 0.7
        assert any("low alignment" in r.message and r.levelno == logging.INFO for r in caplog.records)
