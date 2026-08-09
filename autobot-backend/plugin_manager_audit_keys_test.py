# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /plugins/audit must render the real audit fields, not blanks (#13274).

The shared async client is ``decode_responses=True``
(``redis_management/connection_manager.py:500`` -> ``config.py:61,153``, no
per-database override), so ``xrevrange`` yields ``str`` field names.

``get_capability_audit_log`` looked every field up with a **bytes literal**::

    timestamp=data.get(b"timestamp", b"").decode("utf-8"),
    ...
    granted=data.get(b"granted", b"false").decode("utf-8") == "true",

Every ``.get(b"...")`` missed and returned the *default*, whose ``.decode()``
then succeeded trivially — so nothing raised and nothing was logged. The
endpoint emitted one row per real audit record with every string field empty and
``granted`` pinned to ``False``: the capability audit log reported every grant as
a denial.

Correcting the key type alone is not enough. The writer,
``CapabilityChecker._log_capability_use``, stores ``str(context.granted)`` —
i.e. ``"True"``/``"False"`` — so the reader's ``== "true"`` comparison must
casefold or grants still read denied. The writer/reader pairing is pinned by
``test_writer_mapping_round_trips`` below, which drives the real writer and
feeds exactly what it emitted back into the real reader.
"""

from datetime import datetime, timezone

import pytest

import plugin_manager
from autobot_shared.plugin_sdk.capabilities import (
    Capability,
    CapabilityChecker,
    CapabilityContext,
)

# The live wire shape: decode_responses=True means field names are str.
GRANTED_ENTRY = {
    "timestamp": "2026-08-02T07:00:00+00:00",
    "plugin_name": "demo-plugin",
    "capability": "kb:read",
    "granted": "True",  # str(True) — exactly what the writer stores
    "operation": "kb_query",
    "metadata": "{'query': 'hello'}",
}

DENIED_ENTRY = {
    "timestamp": "2026-08-02T07:00:01+00:00",
    "plugin_name": "rogue-plugin",
    "capability": "filesystem:delete",
    "granted": "False",
    "operation": "fs_delete",
    "metadata": "{}",
}


class _FakeAsyncRedis:
    """Minimal stand-in exposing only what the audit endpoint calls."""

    def __init__(self, entries):
        self._entries = entries
        self.xrevrange_calls = []
        self.xadd_calls = []

    async def xrevrange(self, name, count=None):
        self.xrevrange_calls.append((name, count))
        return self._entries

    async def xadd(self, name, fields, maxlen=None):
        self.xadd_calls.append((name, dict(fields), maxlen))
        return "1700000000000-0"


def _install(monkeypatch, entries, module=plugin_manager):
    fake = _FakeAsyncRedis(entries)

    async def _factory(*args, **kwargs):
        return fake

    monkeypatch.setattr(module, "get_async_redis_client", _factory)
    return fake


async def _call(limit=100):
    return await plugin_manager.get_capability_audit_log(limit=limit, admin_check=True)


@pytest.mark.asyncio
async def test_granted_entry_reads_back_granted(monkeypatch):
    """The live configuration. Pre-fix every field was "" and granted was False."""
    fake = _install(monkeypatch, [("1700000000000-0", GRANTED_ENTRY)])

    result = await _call()

    assert fake.xrevrange_calls == [("plugin:capability:audit", 100)]
    assert result["total"] == 1
    entry = result["entries"][0]
    assert entry.granted is True
    assert entry.plugin_name == "demo-plugin"
    assert entry.capability == "kb:read"
    assert entry.operation == "kb_query"
    assert entry.timestamp == "2026-08-02T07:00:00+00:00"
    assert entry.metadata == "{'query': 'hello'}"


@pytest.mark.asyncio
async def test_denied_entry_still_reads_denied(monkeypatch):
    """A real denial must stay a denial — the fix must not invert the flag."""
    _install(monkeypatch, [("1700000000001-0", DENIED_ENTRY)])

    result = await _call()

    entry = result["entries"][0]
    assert entry.granted is False
    assert entry.plugin_name == "rogue-plugin"
    assert entry.capability == "filesystem:delete"


@pytest.mark.asyncio
async def test_writer_mapping_round_trips(monkeypatch):
    """Drive the real writer, then feed its own mapping to the real reader.

    This is the pairing check: if either side changes its field-name or value
    shape without the other, this test fails.
    """
    import autobot_shared.plugin_sdk.capabilities as capabilities_module

    writer_redis = _install(monkeypatch, [], module=capabilities_module)
    context = CapabilityContext(
        plugin_name="demo-plugin",
        capability=Capability.KB_READ,
        granted=True,
        timestamp=datetime(2026, 8, 2, 7, 0, 0, tzinfo=timezone.utc),
        operation="kb_query",
        metadata={"query": "hello"},
    )

    await CapabilityChecker()._log_capability_use(context)

    assert writer_redis.xadd_calls, "the writer never reached xadd"
    stream, written, _maxlen = writer_redis.xadd_calls[0]
    assert stream == "plugin:capability:audit"

    _install(monkeypatch, [("1700000000000-0", written)])
    result = await _call()

    entry = result["entries"][0]
    assert entry.granted is True, f"writer wrote granted={written['granted']!r}, reader read False"
    assert entry.plugin_name == "demo-plugin"
    assert entry.capability == "kb:read"
    assert entry.operation == "kb_query"
    assert entry.timestamp == "2026-08-02T07:00:00+00:00"


@pytest.mark.asyncio
async def test_bytes_fields_still_work(monkeypatch):
    """A client without decode_responses must keep working."""
    _install(
        monkeypatch,
        [(b"1700000000000-0", {"plugin_name": b"legacy-plugin", "granted": b"true", "capability": b"llm:call"})],
    )

    result = await _call()

    entry = result["entries"][0]
    assert entry.granted is True
    assert entry.plugin_name == "legacy-plugin"
    assert entry.capability == "llm:call"


@pytest.mark.asyncio
async def test_missing_fields_fall_back_to_documented_defaults(monkeypatch):
    """An entry missing fields yields "" and granted=False, not a crash."""
    _install(monkeypatch, [("1700000000000-0", {"plugin_name": "partial"})])

    result = await _call()

    entry = result["entries"][0]
    assert entry.plugin_name == "partial"
    assert entry.timestamp == ""
    assert entry.capability == ""
    assert entry.operation == ""
    assert entry.metadata == ""
    assert entry.granted is False


@pytest.mark.asyncio
async def test_empty_stream_returns_no_entries(monkeypatch):
    """The only case that looked correct before the fix must still work."""
    _install(monkeypatch, [])

    result = await _call()

    assert result["total"] == 0
    assert result["entries"] == []
