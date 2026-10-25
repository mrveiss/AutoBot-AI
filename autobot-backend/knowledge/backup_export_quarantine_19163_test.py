# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backup and export carry research-quarantined facts WITH their marker, audited (#19163).

``get_all_facts`` now excludes quarantined facts by default, so a backup or export that kept the default
would silently lose all research data. Each path reads everything through the audited opt-out and keeps
``metadata.collection`` so a restore re-imports the fact as quarantined, never as trusted.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import config
from knowledge.adapters.okf_adapter import OKFAdapter
from knowledge.bulk import BulkOperationsMixin
from knowledge.documents import DocumentsMixin
from knowledge.facts import FactsMixin
from knowledge.quarantine import BACKUP_AUDIT_ACTOR, EXPORT_AUDIT_ACTOR

_AUDIT = "knowledge.quarantine.audit_quarantine_read"
_RESEARCH = config.research_quarantine_collection


class _KB(FactsMixin, DocumentsMixin, BulkOperationsMixin):
    """The real mixins over a stubbed Redis holding one trusted and one quarantined fact."""

    def __init__(self) -> None:
        self._rows = {
            "fact:good": {b"content": b"ok", b"metadata": json.dumps({"category": "c"}).encode()},
            "fact:held": {
                b"content": b"held",
                b"metadata": json.dumps({"collection": _RESEARCH, "category": "c"}).encode(),
            },
        }
        self.vector_store = None

    def ensure_initialized(self) -> None:
        """No-op."""

    async def _scan_redis_keys_async(self, pattern):
        return list(self._rows)

    def redis(self):
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=list(self._rows.values()))
        client = MagicMock()
        client.pipeline.return_value = pipe
        return client

    async def get_stats(self):
        return {}


async def _read(path) -> str:
    return await asyncio.to_thread(path.read_text, encoding="utf-8")


def _marked(facts) -> dict:
    return {f["fact_id"]: (f.get("metadata") or {}).get("collection") for f in facts}


@pytest.mark.asyncio
async def test_backup_carries_the_quarantined_fact_with_its_marker_and_audits_once(tmp_path):
    with patch(_AUDIT, AsyncMock(return_value=True)) as audit:
        result = await _KB().create_backup(backup_dir=str(tmp_path), compression=False, include_embeddings=False)

    assert result["status"] == "success"
    saved = json.loads(await _read(next(tmp_path.glob("*"))))
    assert _marked(saved["facts"]) == {"good": None, "held": _RESEARCH}
    audit.assert_awaited_once_with(BACKUP_AUDIT_ACTOR, "kb.get_all_facts", ["held"])


@pytest.mark.asyncio
@pytest.mark.parametrize("include_metadata", [True, False])
async def test_export_facts_keeps_the_marker_even_when_metadata_is_dropped(include_metadata):
    with patch(_AUDIT, AsyncMock(return_value=True)) as audit:
        result = await _KB().export_facts(include_metadata=include_metadata, include_tags=False)

    exported = json.loads(result["content"] if "content" in result else result["data"])
    facts = exported["facts"] if isinstance(exported, dict) else exported
    assert _marked(facts)["held"] == _RESEARCH
    audit.assert_awaited_once_with(EXPORT_AUDIT_ACTOR, "kb.get_all_facts", ["held"])


@pytest.mark.asyncio
async def test_export_all_data_carries_the_quarantined_fact_and_audits_once(tmp_path):
    with patch(_AUDIT, AsyncMock(return_value=True)) as audit:
        result = await _KB().export_all_data(str(tmp_path))

    facts = json.loads(await _read(tmp_path / "facts.json"))
    assert result["facts_exported"] == 2
    assert _marked(facts) == {"good": None, "held": _RESEARCH}
    audit.assert_awaited_once_with(EXPORT_AUDIT_ACTOR, "kb.get_all_facts", ["held"])


@pytest.mark.asyncio
async def test_okf_export_carries_the_quarantined_fact_marker_and_audits_once(tmp_path):
    with patch(_AUDIT, AsyncMock(return_value=True)) as audit:
        result = await OKFAdapter(_KB()).export_from_kb(str(tmp_path))

    assert result["status"] == "success"
    written = "\n".join([await _read(p) for p in tmp_path.rglob("*.md")])
    assert f"collection: {_RESEARCH}" in written
    audit.assert_awaited_once_with(EXPORT_AUDIT_ACTOR, "kb.get_all_facts", ["held"])


@pytest.mark.asyncio
async def test_restore_stores_the_fact_with_its_marker_so_it_returns_quarantined():
    kb = _KB()
    kb.store_fact = AsyncMock(return_value={"status": "success"})
    kb._fact_exists = AsyncMock(return_value=False)
    fact = {"fact_id": "held", "content": "held", "metadata": {"collection": _RESEARCH}}

    await kb._restore_single_backup_fact(fact, asyncio.Semaphore(1), False, True, False)

    assert kb.store_fact.await_args.kwargs["metadata"]["collection"] == _RESEARCH


@pytest.mark.asyncio
async def test_json_import_stores_the_fact_with_its_marker():
    kb = _KB()
    kb.store_fact = AsyncMock(return_value={"status": "success", "fact_id": "held"})
    payload = json.dumps([{"fact_id": "held", "content": "held", "metadata": {"collection": _RESEARCH}}])

    result = await kb.import_facts(data=payload, skip_duplicates=False)

    assert result["status"] == "success"
    assert kb.store_fact.await_args.kwargs["metadata"]["collection"] == _RESEARCH


@pytest.mark.asyncio
async def test_okf_round_trip_reimports_the_fact_still_quarantined(tmp_path):
    with patch(_AUDIT, AsyncMock(return_value=True)):
        await OKFAdapter(_KB()).export_from_kb(str(tmp_path))
    target = _KB()
    target.store_fact = AsyncMock(return_value={"status": "success"})

    result = await OKFAdapter(target).import_into_kb(str(tmp_path))

    assert result["stored_count"] == 2 and result["error_count"] == 0
    stored = {c.args[2]: c.args[1].get("collection") for c in target.store_fact.await_args_list}
    assert stored == {"good": None, "held": _RESEARCH}
