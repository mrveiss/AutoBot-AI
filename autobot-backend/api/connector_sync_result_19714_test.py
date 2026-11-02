# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19714 review: a finished sync never writes credentials, undoes an edit, or revives a delete."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import WatchError

from api import _connector_sync_result as result
from api import knowledge_connectors as route
from knowledge.connectors.base import ConnectorConfig

_WHEN = datetime(2026, 11, 2, tzinfo=timezone.utc)


class _Pipe:
    def __init__(self, store: dict, conflicts: int = 0) -> None:
        self.store, self.conflicts = store, conflicts

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def watch(self, _key) -> None: ...

    def unwatch(self) -> None: ...

    def multi(self) -> None: ...

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value) -> None:
        self.pending = (key, value)

    def execute(self) -> None:
        if self.conflicts:
            self.conflicts -= 1
            raise WatchError()
        self.store[self.pending[0]] = self.pending[1]


class _Redis:
    def __init__(self, store: dict, conflicts: int = 0) -> None:
        self._pipe = _Pipe(store, conflicts)

    def pipeline(self):
        return self._pipe


def test_only_the_time_changes_on_the_current_record() -> None:
    store = {"k": json.dumps({"name": "edited during the sync", "config": {"host": "h"}})}
    assert result._write_last_sync(_Redis(store), "k", "T") is True
    assert json.loads(store["k"]) == {"name": "edited during the sync", "config": {"host": "h"}, "last_sync_at": "T"}


def test_a_connector_deleted_during_the_sync_stays_deleted() -> None:
    store: dict = {}
    assert result._write_last_sync(_Redis(store), "k", "T") is False
    assert store == {}


def test_an_edit_racing_the_write_is_retried_on_the_new_record() -> None:
    store = {"k": json.dumps({"name": "n"})}
    assert result._write_last_sync(_Redis(store, conflicts=1), "k", "T") is True
    assert json.loads(store["k"])["last_sync_at"] == "T"


def test_it_gives_up_rather_than_spinning() -> None:
    store = {"k": json.dumps({"name": "n"})}
    assert result._write_last_sync(_Redis(store, conflicts=99), "k", "T") is False
    assert "last_sync_at" not in json.loads(store["k"])


class _SyncResult:
    """A finished sync: the two times, and a zero for every count the history row reads."""

    completed_at = started_at = _WHEN
    status = "success"
    errors: list = []

    def __getattr__(self, _name: str) -> int:
        return 0


@pytest.mark.asyncio
async def test_the_sync_never_saves_the_config_holding_the_credentials() -> None:
    stored = ConnectorConfig(connector_id="c", connector_type="t", name="n", config={}, secret_id="s")
    merged = ConnectorConfig(connector_id="c", connector_type="t", name="n", config={"token": "secret"}, secret_id="s")
    instance = AsyncMock()
    instance.sync.return_value = _SyncResult()
    with (
        patch.object(route, "_load_connector", AsyncMock(return_value=stored)),
        patch.object(route, "_cfg_with_credentials", AsyncMock(return_value=merged)),
        patch.object(route, "_load_or_create_instance", AsyncMock(return_value=instance)),
        patch.object(route, "_save_connector", AsyncMock()) as save,
        patch.object(route, "record_last_sync", AsyncMock()) as record,
        patch.object(route, "get_redis_client"),
    ):
        await getattr(route._run_sync_background, "__wrapped__", route._run_sync_background)("c", True)
    save.assert_not_awaited()
    record.assert_awaited_once()
    assert record.await_args.args[1] == _WHEN
