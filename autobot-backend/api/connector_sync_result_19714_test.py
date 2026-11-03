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
    return client


def test_only_the_time_changes_on_the_current_record() -> None:
    store = {"k": json.dumps({"name": "edited during the sync", "config": {"host": "h"}})}
    assert result._write_last_sync(_redis(store), "k", "T") is True
    assert json.loads(store["k"]) == {"name": "edited during the sync", "config": {"host": "h"}, "last_sync_at": "T"}


def test_a_connector_deleted_during_the_sync_stays_deleted() -> None:
    store: dict = {}
    assert result._write_last_sync(_redis(store), "k", "T") is False
    assert store == {}


def test_an_edit_racing_the_write_is_retried_on_the_new_record() -> None:
    store = {"k": json.dumps({"name": "n"})}
    assert result._write_last_sync(_redis(store, conflicts=1), "k", "T") is True
    assert json.loads(store["k"])["last_sync_at"] == "T"


def test_it_gives_up_rather_than_spinning() -> None:
    store = {"k": json.dumps({"name": "n"})}
    assert result._write_last_sync(_redis(store, conflicts=99), "k", "T") is None, "exists, but nothing was written"
    assert "last_sync_at" not in json.loads(store["k"])


@pytest.mark.asyncio
async def test_the_live_instance_is_not_told_a_sync_redis_never_stored() -> None:
    """Retries exhausted: the connector still exists, but the status route must not show an unsaved time."""
    store = {"k": json.dumps({"name": "n"})}
    instance = SimpleNamespace(config=SimpleNamespace(last_sync_at=None))
    done = SimpleNamespace(completed_at=datetime(2026, 11, 3, tzinfo=timezone.utc))
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
        assert await result.record_last_sync(instance, "k", SimpleNamespace(completed_at=_WHEN)) is True
    assert instance.config.last_sync_at == _WHEN
