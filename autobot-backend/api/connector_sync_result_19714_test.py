# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19714 review: a finished sync never writes credentials, undoes an edit, or revives a delete."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import WatchError

from api import _connector_sync_result as result
from api import knowledge_connectors as route
from knowledge.connectors.base import ConnectorConfig

_WHEN = datetime(2026, 11, 2, tzinfo=timezone.utc)


def _redis(store: dict, conflicts: int = 0) -> MagicMock:
    """A Redis whose pipeline reads and writes ``store``, raising WatchError for the first conflicts."""
    pipe = MagicMock()
    pipe.__enter__.return_value = pipe
    pipe.get.side_effect = store.get
    pending: dict = {}
    pipe.set.side_effect = lambda key, value: pending.update({key: value})
    left = [conflicts]

    def execute() -> None:
        if left[0]:
            left[0] -= 1
            raise WatchError()
        store.update(pending)

    pipe.execute.side_effect = execute
    client = MagicMock()
    client.pipeline.return_value = pipe
    client.exists.side_effect = lambda key: int(key in store)
    return client


def test_only_the_time_changes_on_the_current_record() -> None:
    store = {"k": json.dumps({"name": "edited during the sync", "config": {"host": "h"}})}
    assert result._write_last_sync(_redis(store), "k", _WHEN) == _WHEN
    assert json.loads(store["k"]) == {
        "name": "edited during the sync",
        "config": {"host": "h"},
        "last_sync_at": _WHEN.isoformat(),
    }


def test_a_connector_deleted_during_the_sync_stays_deleted() -> None:
    store: dict = {}
    assert result._write_last_sync(_redis(store), "k", _WHEN) is False
    assert store == {}


def test_an_edit_racing_the_write_is_retried_on_the_new_record() -> None:
    store = {"k": json.dumps({"name": "n"})}
    assert result._write_last_sync(_redis(store, conflicts=1), "k", _WHEN) == _WHEN
    assert json.loads(store["k"])["last_sync_at"] == _WHEN.isoformat()


def test_it_gives_up_rather_than_spinning() -> None:
    store = {"k": json.dumps({"name": "n"})}
    assert result._write_last_sync(_redis(store, conflicts=99), "k", _WHEN) is None, "exists, but nothing was written"
    assert "last_sync_at" not in json.loads(store["k"])


@pytest.mark.asyncio
async def test_the_live_instance_is_not_told_a_sync_redis_never_stored() -> None:
    """Retries exhausted: the connector still exists, but the status route must not show an unsaved time."""
    store = {"k": json.dumps({"name": "n"})}
    instance = SimpleNamespace(config=SimpleNamespace(last_sync_at=None))
    done = SimpleNamespace(completed_at=datetime(2026, 11, 3, tzinfo=timezone.utc), status="success")
    with patch.object(result, "get_redis_client", return_value=_redis(store, conflicts=99)):
        assert await result.record_last_sync(instance, "k", done) is True, "not deleted"
    assert instance.config.last_sync_at is None


class _SyncResult:
    """A finished sync: the two times, and a zero for every count the history row reads."""

    completed_at = started_at = _WHEN
    status = "success"
    errors: list = []

    def __getattr__(self, _name: str) -> int:
        return 0


async def _finish_a_sync(recorded: bool):
    """Run the background sync to its end. Returns the record and save mocks, the instance, the history mock."""
    stored = ConnectorConfig(connector_id="c", connector_type="t", name="n", config={}, secret_id="s")
    merged = ConnectorConfig(connector_id="c", connector_type="t", name="n", config={"token": "secret"}, secret_id="s")
    instance = AsyncMock()
    instance.sync.return_value = _SyncResult()
    with (
        patch.object(route, "_load_connector", AsyncMock(return_value=stored)),
        patch.object(route, "_cfg_with_credentials", AsyncMock(return_value=merged)),
        patch.object(route, "_load_or_create_instance", AsyncMock(return_value=instance)),
        patch.object(route, "_save_connector", AsyncMock()) as save,
        patch.object(route, "record_last_sync", AsyncMock(return_value=recorded)) as record,
        patch.object(route, "_append_history", AsyncMock()) as history,
    ):
        await getattr(route._run_sync_background, "__wrapped__", route._run_sync_background)("c", True)
    return record, save, instance, history


@pytest.mark.asyncio
async def test_the_sync_never_saves_the_config_holding_the_credentials() -> None:
    record, save, instance, history = await _finish_a_sync(recorded=True)
    save.assert_not_awaited()
    assert record.await_args.args[:2] == (instance, route._connector_key("c"))
    history.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_connector_deleted_during_the_sync_gets_no_history_row() -> None:
    _record, _save, _instance, history = await _finish_a_sync(recorded=False)
    history.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_live_instance_reports_the_new_time() -> None:
    instance = SimpleNamespace(config=SimpleNamespace(last_sync_at=None))
    with patch.object(result, "get_redis_client", return_value=_redis({"k": json.dumps({"name": "n"})})):
        assert (
            await result.record_last_sync(instance, "k", SimpleNamespace(completed_at=_WHEN, status="success")) is True
        )
    assert instance.config.last_sync_at == _WHEN


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "partial"])
async def test_a_run_that_did_not_reach_every_source_does_not_move_the_cursor(status: str) -> None:
    """#20556: last_sync_at is the next incremental `since`; moving it past unread sources skips them for good."""
    store = {"k": json.dumps({"name": "n", "last_sync_at": "2026-11-01T00:00:00+00:00"})}
    instance = SimpleNamespace(config=SimpleNamespace(last_sync_at=None))
    run = SimpleNamespace(completed_at=_WHEN, status=status)
    with patch.object(result, "get_redis_client", return_value=_redis(store)):
        assert await result.record_last_sync(instance, "k", run) is True, "the connector still exists"
    assert json.loads(store["k"])["last_sync_at"] == "2026-11-01T00:00:00+00:00"
    assert instance.config.last_sync_at is None


@pytest.mark.asyncio
async def test_a_stopped_run_of_a_deleted_connector_still_reads_as_deleted() -> None:
    run = SimpleNamespace(completed_at=_WHEN, status="failed")
    with patch.object(result, "get_redis_client", return_value=_redis({})):
        assert await result.record_last_sync(SimpleNamespace(config=SimpleNamespace()), "k", run) is False


# #20758: two overlapping runs can finish out of order; the stored and live times only move forward.
_EARLIER = datetime(2026, 11, 1, 12, 0)  # naive, as some connectors report it: read as UTC


def test_an_earlier_finishing_run_keeps_the_later_stored_time() -> None:
    store = {"k": json.dumps({"name": "n", "last_sync_at": _WHEN.isoformat()})}
    assert result._write_last_sync(_redis(store), "k", result._aware(_EARLIER)) == _WHEN, "it reports the time kept"
    assert json.loads(store["k"])["last_sync_at"] == _WHEN.isoformat()


def test_a_later_run_still_moves_the_stored_time_forward() -> None:
    """The control: an older stored time (written by an older format, with a Z) is replaced."""
    store = {"k": json.dumps({"name": "n", "last_sync_at": "2026-11-01T12:00:00Z"})}
    assert result._write_last_sync(_redis(store), "k", _WHEN) == _WHEN
    assert json.loads(store["k"])["last_sync_at"] == _WHEN.isoformat()


def test_an_unreadable_stored_time_is_replaced() -> None:
    store = {"k": json.dumps({"name": "n", "last_sync_at": "not a time"})}
    assert result._write_last_sync(_redis(store), "k", _WHEN) == _WHEN
    assert json.loads(store["k"])["last_sync_at"] == _WHEN.isoformat()


@pytest.mark.asyncio
async def test_out_of_order_completion_leaves_the_later_time_everywhere() -> None:
    """The newer run finishes first, then the older one: both the stored and the live time stay at
    the newer run's."""
    store = {"k": json.dumps({"name": "n"})}
    instance = SimpleNamespace(config=SimpleNamespace(last_sync_at=None))
    with patch.object(result, "get_redis_client", return_value=_redis(store)):
        for completed_at in (_WHEN, _EARLIER):
            run = SimpleNamespace(completed_at=completed_at, status="success")
            assert await result.record_last_sync(instance, "k", run) is True
    assert json.loads(store["k"])["last_sync_at"] == _WHEN.isoformat()
    assert instance.config.last_sync_at == _WHEN


@pytest.mark.asyncio
async def test_a_run_behind_the_stored_time_leaves_the_live_value_at_the_stored_one() -> None:
    """Review of #20801: the stored record and the live instance are separate. A later time already
    in Redis (from another worker's run) wins over this run's older one on the live value too, so
    the status route and Redis agree."""
    store = {"k": json.dumps({"name": "n", "last_sync_at": _WHEN.isoformat()})}
    instance = SimpleNamespace(config=SimpleNamespace(last_sync_at=None))
    run = SimpleNamespace(completed_at=_EARLIER, status="success")
    with patch.object(result, "get_redis_client", return_value=_redis(store)):
        assert await result.record_last_sync(instance, "k", run) is True
    assert json.loads(store["k"])["last_sync_at"] == _WHEN.isoformat()
    assert instance.config.last_sync_at == _WHEN, "the live value disagrees with Redis"


@pytest.mark.asyncio
async def test_an_equal_stored_time_is_kept_and_reported() -> None:
    """A tie is not later: Redis is left as it is, and the live value takes that same time."""
    stored = {"name": "n", "last_sync_at": _WHEN.isoformat(), "note": "untouched"}
    store = {"k": json.dumps(stored)}
    redis = _redis(store)
    instance = SimpleNamespace(config=SimpleNamespace(last_sync_at=None))
    with patch.object(result, "get_redis_client", return_value=redis):
        run = SimpleNamespace(completed_at=_WHEN, status="success")
        assert await result.record_last_sync(instance, "k", run) is True
    redis.pipeline.return_value.set.assert_not_called()
    assert json.loads(store["k"]) == stored, "a tie rewrote the record"
    assert instance.config.last_sync_at == _WHEN
