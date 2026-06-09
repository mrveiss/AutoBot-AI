# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for trigger_service.py (#2139)

Covers:
  - TriggerConfig validation (all trigger types)
  - Condition evaluation
  - Cron expression parsing and next-run calculation
  - Webhook HMAC signature validation
  - TriggerService.register_trigger / unregister_trigger / list_triggers
  - TriggerService.fire_trigger (condition pass and fail paths)
  - Redis persistence round-trip (via TriggerDefinition serialisation)
"""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from services.trigger_service import (
    TriggerConfig,
    TriggerDefinition,
    TriggerService,
    TriggerType,
    _evaluate_conditions,
    next_cron_run,
    validate_cron_expression,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(trigger_type: TriggerType, extra: Dict[str, Any] | None = None) -> TriggerConfig:
    cfg: Dict[str, Any] = {}
    if trigger_type == TriggerType.CRON:
        cfg["cron_expression"] = "*/5 * * * *"
    elif trigger_type == TriggerType.REDIS_PUBSUB:
        cfg["channel"] = "test-channel"
    elif trigger_type == TriggerType.FILE_WATCH:
        cfg["redis_key"] = "autobot:file:changed"
    elif trigger_type == TriggerType.AGENT_EVENT:
        cfg["event_name"] = "task_completed"
    if extra:
        cfg.update(extra)
    return TriggerConfig(trigger_type=trigger_type, workflow_id="wf-test-123", config=cfg)


def _fake_redis_store() -> MagicMock:
    """Return a MagicMock that mimics a Redis client with dict-based in-memory storage."""
    store: Dict[str, Any] = {}
    sets: Dict[str, set] = {}

    mock = MagicMock()
    mock.get.side_effect = lambda k: store.get(k)
    mock.setex.side_effect = lambda k, ttl, v: store.__setitem__(k, v)
    mock.delete.side_effect = lambda k: store.pop(k, None)
    mock.sadd.side_effect = lambda k, *vals: sets.setdefault(k, set()).update(vals)
    mock.srem.side_effect = lambda k, *vals: sets.get(k, set()).discard(vals[0])
    mock.smembers.side_effect = lambda k: sets.get(k, set())
    return mock


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


class TestEvaluateConditions:
    def test_empty_conditions_always_pass(self) -> None:
        assert _evaluate_conditions([], {"any": "data"}) is True

    def test_eq_pass(self) -> None:
        conds = [{"field": "status", "op": "eq", "value": "success"}]
        assert _evaluate_conditions(conds, {"status": "success"}) is True

    def test_eq_fail(self) -> None:
        conds = [{"field": "status", "op": "eq", "value": "success"}]
        assert _evaluate_conditions(conds, {"status": "failed"}) is False

    def test_ne_pass(self) -> None:
        conds = [{"field": "status", "op": "ne", "value": "error"}]
        assert _evaluate_conditions(conds, {"status": "success"}) is True

    def test_gt_pass(self) -> None:
        conds = [{"field": "count", "op": "gt", "value": 5}]
        assert _evaluate_conditions(conds, {"count": 10}) is True

    def test_gt_fail(self) -> None:
        conds = [{"field": "count", "op": "gt", "value": 5}]
        assert _evaluate_conditions(conds, {"count": 3}) is False

    def test_contains_pass(self) -> None:
        conds = [{"field": "tags", "op": "contains", "value": "urgent"}]
        assert _evaluate_conditions(conds, {"tags": ["urgent", "low"]}) is True

    def test_missing_field_fails(self) -> None:
        conds = [{"field": "missing_field", "op": "eq", "value": "x"}]
        assert _evaluate_conditions(conds, {"other": "y"}) is False

    def test_nested_field_path(self) -> None:
        conds = [{"field": "data.source", "op": "eq", "value": "github"}]
        assert _evaluate_conditions(conds, {"data": {"source": "github"}}) is True

    def test_multiple_conditions_all_must_pass(self) -> None:
        conds = [
            {"field": "status", "op": "eq", "value": "ok"},
            {"field": "count", "op": "gte", "value": 1},
        ]
        assert _evaluate_conditions(conds, {"status": "ok", "count": 5}) is True
        assert _evaluate_conditions(conds, {"status": "ok", "count": 0}) is False

    def test_unknown_op_passes_with_warning(self) -> None:
        # Unknown ops should not block execution
        conds = [{"field": "x", "op": "unknown_op", "value": 1}]
        assert _evaluate_conditions(conds, {"x": 1}) is True


# ---------------------------------------------------------------------------
# Cron expression parsing
# ---------------------------------------------------------------------------


class TestValidateCronExpression:
    def test_every_minute(self) -> None:
        assert validate_cron_expression("* * * * *") is True

    def test_every_5_minutes(self) -> None:
        assert validate_cron_expression("*/5 * * * *") is True

    def test_specific_time(self) -> None:
        assert validate_cron_expression("0 9 * * 1") is True  # Mon 09:00

    def test_range(self) -> None:
        assert validate_cron_expression("0-30 * * * *") is True

    def test_comma_list(self) -> None:
        assert validate_cron_expression("0,15,30,45 * * * *") is True

    def test_too_few_fields(self) -> None:
        assert validate_cron_expression("* * * *") is False

    def test_too_many_fields(self) -> None:
        assert validate_cron_expression("* * * * * *") is False

    def test_invalid_value(self) -> None:
        assert validate_cron_expression("60 * * * *") is False  # minute 60 out of range

    def test_empty_string(self) -> None:
        assert validate_cron_expression("") is False

    def test_dow_7_sunday_accepted(self) -> None:
        # Standard cron: 7 is an alias for Sunday (same as 0); must not raise
        assert validate_cron_expression("0 0 * * 7") is True

    def test_dow_0_sunday_accepted(self) -> None:
        assert validate_cron_expression("0 0 * * 0") is True

    def test_dow_range_1_to_7_accepted(self) -> None:
        # "1-7" used to corrupt to "1-0" (empty range -> ValueError); must now return True
        assert validate_cron_expression("0 0 * * 1-7") is True

    def test_dow_comma_list_with_7_accepted(self) -> None:
        # "0,7" should be normalised to "0,0" (both Sunday) and accepted
        assert validate_cron_expression("0 0 * * 0,7") is True

    def test_dow_range_step_1_to_7_accepted(self) -> None:
        # "1-7/2" — range-step spanning Sunday; must be normalised and accepted
        assert validate_cron_expression("0 0 * * 1-7/2") is True

    def test_dow_range_step_5_to_7_accepted(self) -> None:
        # "5-7/2" — range-step ending on 7; must be normalised and accepted
        assert validate_cron_expression("0 0 * * 5-7/2") is True

    def test_dow_range_step_1_to_7_fires_on_sunday(self) -> None:
        # "0 0 * * 1-7/2" fires Mon(1), Wed(3), Fri(5), Sun(0/7)
        # Saturday base → next fire should be Sunday
        base = datetime(2025, 6, 7, 23, 0, 0, tzinfo=timezone.utc)  # Saturday
        nxt = next_cron_run("0 0 * * 1-7/2", after=base)
        assert nxt.weekday() == 6, f"Expected Sunday (weekday=6), got weekday={nxt.weekday()}"

    def test_dow_range_step_0_to_7_accepted(self) -> None:
        # "0-7/2" — range-step from 0 to 7 with step; must be normalised and accepted
        assert validate_cron_expression("0 0 * * 0-7/2") is True


class TestNextCronRun:
    def test_every_minute_advances_by_one(self) -> None:
        base = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        nxt = next_cron_run("* * * * *", after=base)
        assert nxt.minute == 1
        assert nxt.hour == 12

    def test_every_5_minutes(self) -> None:
        base = datetime(2025, 6, 1, 12, 3, 0, tzinfo=timezone.utc)
        nxt = next_cron_run("*/5 * * * *", after=base)
        assert nxt.minute == 5
        assert nxt.hour == 12

    def test_crosses_hour_boundary(self) -> None:
        base = datetime(2025, 6, 1, 12, 58, 0, tzinfo=timezone.utc)
        nxt = next_cron_run("*/5 * * * *", after=base)
        # Next is 13:00 (12:59 not on 5-min boundary, so 13:00)
        assert nxt.hour == 13
        assert nxt.minute == 0

    def test_always_strictly_after_base(self) -> None:
        base = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        nxt = next_cron_run("* * * * *", after=base)
        assert nxt > base

    def test_invalid_expression_raises(self) -> None:
        with pytest.raises(ValueError):
            next_cron_run("bad expression")

    def test_dow_7_sunday_fires_same_day_as_dow_0(self) -> None:
        # Both "0 0 * * 7" and "0 0 * * 0" should fire on the same Sunday
        # Use a Saturday base so the next Sunday is one day away for both
        base = datetime(2025, 6, 7, 23, 0, 0, tzinfo=timezone.utc)  # Saturday
        nxt_7 = next_cron_run("0 0 * * 7", after=base)
        nxt_0 = next_cron_run("0 0 * * 0", after=base)
        assert nxt_7 == nxt_0, f"7=Sunday and 0=Sunday must fire at same time: {nxt_7} vs {nxt_0}"

    def test_dow_range_1_to_7_fires_on_sunday(self) -> None:
        # "0 0 * * 1-7" should fire Mon-Sun; verify it fires on Sunday (weekday 6)
        # Use Saturday 2025-06-07 23:00 UTC -- next fire should be Sunday 2025-06-08 00:00 UTC
        base = datetime(2025, 6, 7, 23, 0, 0, tzinfo=timezone.utc)  # Saturday
        nxt = next_cron_run("0 0 * * 1-7", after=base)
        assert nxt == datetime(2025, 6, 8, 0, 0, 0, tzinfo=timezone.utc), f"1-7 range should include Sunday; got {nxt}"
        assert nxt.weekday() == 6, f"Expected Sunday (weekday=6), got weekday={nxt.weekday()}"


# ---------------------------------------------------------------------------
# TriggerDefinition serialisation
# ---------------------------------------------------------------------------


class TestTriggerDefinitionSerialisation:
    def _make_def(self, trigger_type: TriggerType) -> TriggerDefinition:
        return TriggerDefinition(
            id="tid-001",
            trigger_type=trigger_type,
            workflow_id="wf-42",
            config={"channel": "events"},
            conditions=[],
            enabled=True,
            created_at="2025-01-01T00:00:00+00:00",
        )

    def test_round_trip_all_types(self) -> None:
        for t in TriggerType:
            tdef = self._make_def(t)
            serialised = tdef.to_dict()
            restored = TriggerDefinition.from_dict(serialised)
            assert restored.id == tdef.id
            assert restored.trigger_type == tdef.trigger_type
            assert restored.workflow_id == tdef.workflow_id

    def test_trigger_type_stored_as_string(self) -> None:
        tdef = self._make_def(TriggerType.CRON)
        d = tdef.to_dict()
        assert isinstance(d["trigger_type"], str)
        assert d["trigger_type"] == "cron"


# ---------------------------------------------------------------------------
# TriggerConfig validation
# ---------------------------------------------------------------------------


class TestTriggerConfigValidation:
    def _svc(self) -> TriggerService:
        return TriggerService()

    def test_valid_webhook(self) -> None:
        svc = self._svc()
        svc._validate_config(_make_config(TriggerType.WEBHOOK))  # should not raise

    def test_valid_cron(self) -> None:
        svc = self._svc()
        svc._validate_config(_make_config(TriggerType.CRON))

    def test_cron_missing_expression(self) -> None:
        svc = self._svc()
        cfg = TriggerConfig(trigger_type=TriggerType.CRON, workflow_id="wf-1", config={})
        with pytest.raises(ValueError, match="cron_expression"):
            svc._validate_config(cfg)

    def test_cron_invalid_expression(self) -> None:
        svc = self._svc()
        cfg = TriggerConfig(
            trigger_type=TriggerType.CRON,
            workflow_id="wf-1",
            config={"cron_expression": "not a cron"},
        )
        with pytest.raises(ValueError, match="Invalid cron expression"):
            svc._validate_config(cfg)

    def test_pubsub_missing_channel(self) -> None:
        svc = self._svc()
        cfg = TriggerConfig(trigger_type=TriggerType.REDIS_PUBSUB, workflow_id="wf-1", config={})
        with pytest.raises(ValueError, match="channel"):
            svc._validate_config(cfg)

    def test_filewatch_missing_key(self) -> None:
        svc = self._svc()
        cfg = TriggerConfig(trigger_type=TriggerType.FILE_WATCH, workflow_id="wf-1", config={})
        with pytest.raises(ValueError, match="redis_key"):
            svc._validate_config(cfg)

    def test_filewatch_bad_interval(self) -> None:
        svc = self._svc()
        cfg = TriggerConfig(
            trigger_type=TriggerType.FILE_WATCH,
            workflow_id="wf-1",
            config={"redis_key": "k", "poll_interval_seconds": 0},
        )
        with pytest.raises(ValueError, match="poll_interval_seconds"):
            svc._validate_config(cfg)

    def test_agent_event_missing_name(self) -> None:
        svc = self._svc()
        cfg = TriggerConfig(trigger_type=TriggerType.AGENT_EVENT, workflow_id="wf-1", config={})
        with pytest.raises(ValueError, match="event_name"):
            svc._validate_config(cfg)

    def test_empty_workflow_id_rejected(self) -> None:
        svc = self._svc()
        cfg = TriggerConfig(trigger_type=TriggerType.WEBHOOK, workflow_id="", config={})
        with pytest.raises(ValueError, match="workflow_id"):
            svc._validate_config(cfg)


# ---------------------------------------------------------------------------
# TriggerService — register / unregister / list (Redis mocked)
# ---------------------------------------------------------------------------


class TestTriggerServiceCRUD:
    @pytest.fixture()
    def fake_redis(self) -> MagicMock:
        return _fake_redis_store()

    @pytest.fixture()
    def svc(self) -> TriggerService:
        return TriggerService()

    @pytest.mark.asyncio
    async def test_register_webhook_returns_id_and_stores(self, svc: TriggerService, fake_redis: MagicMock) -> None:
        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = _make_config(TriggerType.WEBHOOK)
            trigger_id = await svc.register_trigger(cfg)

        assert trigger_id
        assert len(trigger_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_register_cron_trigger(self, svc: TriggerService, fake_redis: MagicMock) -> None:
        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = _make_config(TriggerType.CRON)
            trigger_id = await svc.register_trigger(cfg)
            triggers = await svc.list_triggers()

        assert any(t.id == trigger_id for t in triggers)

    @pytest.mark.asyncio
    async def test_list_by_workflow_id(self, svc: TriggerService, fake_redis: MagicMock) -> None:
        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg1 = _make_config(TriggerType.WEBHOOK)
            cfg2 = TriggerConfig(trigger_type=TriggerType.WEBHOOK, workflow_id="other-wf", config={})
            await svc.register_trigger(cfg1)
            await svc.register_trigger(cfg2)

            for_wf_test = await svc.list_triggers(workflow_id="wf-test-123")
            for_other = await svc.list_triggers(workflow_id="other-wf")

        assert all(t.workflow_id == "wf-test-123" for t in for_wf_test)
        assert all(t.workflow_id == "other-wf" for t in for_other)

    @pytest.mark.asyncio
    async def test_unregister_removes_from_list(self, svc: TriggerService, fake_redis: MagicMock) -> None:
        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = _make_config(TriggerType.WEBHOOK)
            trigger_id = await svc.register_trigger(cfg)
            await svc.unregister_trigger(trigger_id)
            triggers = await svc.list_triggers()

        assert not any(t.id == trigger_id for t in triggers)


# ---------------------------------------------------------------------------
# TriggerService — fire_trigger
# ---------------------------------------------------------------------------


class TestFireTrigger:
    @pytest.mark.asyncio
    async def test_fire_calls_launcher(self) -> None:
        svc = TriggerService()
        launched: list = []

        async def mock_launcher(workflow_id: str, payload: Dict[str, Any]) -> None:
            launched.append((workflow_id, payload))

        fake_redis = _fake_redis_store()

        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = _make_config(TriggerType.WEBHOOK)
            trigger_id = await svc.register_trigger(cfg)
            await svc.start(mock_launcher)

            result = await svc.fire_trigger(trigger_id, {"event": "push"})
            await svc.stop()

        assert result is True
        assert len(launched) == 1
        assert launched[0][0] == "wf-test-123"

    @pytest.mark.asyncio
    async def test_fire_fails_when_conditions_not_met(self) -> None:
        svc = TriggerService()
        launched: list = []

        async def mock_launcher(workflow_id: str, payload: Dict[str, Any]) -> None:
            launched.append(workflow_id)

        fake_redis = _fake_redis_store()

        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = TriggerConfig(
                trigger_type=TriggerType.WEBHOOK,
                workflow_id="wf-cond",
                config={},
                conditions=[{"field": "status", "op": "eq", "value": "success"}],
            )
            trigger_id = await svc.register_trigger(cfg)
            await svc.start(mock_launcher)

            result = await svc.fire_trigger(trigger_id, {"status": "failed"})
            await svc.stop()

        assert result is False
        assert not launched

    @pytest.mark.asyncio
    async def test_fire_nonexistent_trigger_returns_false(self) -> None:
        svc = TriggerService()

        async def noop(wf: str, p: Dict) -> None:
            pass

        await svc.start(noop)
        result = await svc.fire_trigger("nonexistent-id", {})
        await svc.stop()

        assert result is False

    @pytest.mark.asyncio
    async def test_fire_disabled_trigger_returns_false(self) -> None:
        svc = TriggerService()
        launched: list = []

        async def mock_launcher(wf: str, p: Dict) -> None:
            launched.append(wf)

        fake_redis = _fake_redis_store()

        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = TriggerConfig(
                trigger_type=TriggerType.WEBHOOK,
                workflow_id="wf-disabled",
                config={},
                enabled=False,
            )
            trigger_id = await svc.register_trigger(cfg)
            await svc.start(mock_launcher)

            result = await svc.fire_trigger(trigger_id, {"event": "x"})
            await svc.stop()

        assert result is False
        assert not launched


# ---------------------------------------------------------------------------
# Webhook HMAC validation
# ---------------------------------------------------------------------------


class TestWebhookSignatureValidation:
    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self) -> None:
        svc = TriggerService()
        fake_redis = _fake_redis_store()

        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = _make_config(TriggerType.WEBHOOK)
            trigger_id = await svc.register_trigger(cfg)

            secret = await svc._get_webhook_secret(trigger_id)
            assert secret is not None

            body = b'{"event": "push"}'
            sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

            assert await svc.validate_webhook_signature(trigger_id, body, sig) is True

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self) -> None:
        svc = TriggerService()
        fake_redis = _fake_redis_store()

        with patch("services.trigger_service.get_redis_client", return_value=fake_redis):
            cfg = _make_config(TriggerType.WEBHOOK)
            trigger_id = await svc.register_trigger(cfg)

            body = b'{"event": "push"}'
            bad_sig = "sha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

            assert await svc.validate_webhook_signature(trigger_id, body, bad_sig) is False

    @pytest.mark.asyncio
    async def test_no_secret_returns_false(self) -> None:
        svc = TriggerService()
        # No Redis mock — no secret stored
        result = await svc.validate_webhook_signature("nonexistent", b"body", "sha256=abc")
        assert result is False
