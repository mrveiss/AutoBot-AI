# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Switch the embedding model: rebuild into a new collection in the background, then cut over (#19379).

- **Start** (admins only): takes the switch claim in the work-claim registry whose TTL is the build's heartbeat, so
  exactly one build runs fleet-wide and a build whose worker died is visible as ``stale`` once the
  lock expires -- a new start, or a cancel, recovers from it. Each attempt writes a NEW collection
  (``<base>__<model>__<attempt>``), so switching A→B→A never reopens an abandoned A collection.
- **Build:** every fact from the system of record (``fact_store.iter_facts``, PostgreSQL) is
  re-embedded with the TARGET model into the new collection, stamped with its provenance. Search and
  writes keep the active collection. Facts written, updated or deleted meanwhile are noted by
  ``fact_store`` (``note_write``) and replayed, in rounds, until none are pending and the new
  collection holds exactly one vector per recorded fact.
- **Cutover**, only on a complete build with zero failures (maintainer decision, 2026-10-25): the
  record (model + collection) is written once -- this module is the only caller of
  ``set_embedding_model_override`` -- and this process rebinds; others rebind on their next KB
  operation (``embedding_space_binding``). Writes keep being noted through a settling window, then
  replayed once more. A step that fails AFTER the record is written cannot undo the switch, so it
  reports ``completed_with_warnings``, never ``failed``.
- **Failure, cancel, deadline:** the active model and collection stay as they were and the state
  says why. The abandoned collection is left for the deletion proposal (#19380).
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.coordination.work_claims import ClaimUnavailable
from autobot_shared.embedding_model import active_embedding_model, is_embedding_model_id, set_embedding_model_override
from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.slug import sanitize_token
from knowledge import embedding_switch_lock as lock

logger = get_logger(__name__)

STATE_KEY = "autobot:kb:embedding_switch"
PENDING_KEY = "autobot:kb:embedding_switch:pending"
#: Facts embedded per round trip to the embedding provider.
SWITCH_BATCH_SIZE = env_int_clamped("AUTOBOT_EMBEDDING_SWITCH_BATCH_SIZE", 64, 1, 1000)
#: A build that has not heartbeat for this long is stale: its worker is presumed dead.
SWITCH_STALE_S = env_float_clamped("AUTOBOT_EMBEDDING_SWITCH_STALE_SECONDS", 300.0, 30.0, 86400.0, positive_finite=True)
#: The whole build, start to cutover, must finish within this.
SWITCH_DEADLINE_S = env_float_clamped(
    "AUTOBOT_EMBEDDING_SWITCH_DEADLINE_SECONDS", 21600.0, 60.0, 604800.0, positive_finite=True
)
#: Added to the two cache windows when waiting for every process to rebind after cutover.
SWITCH_SETTLE_MARGIN_S = env_float_clamped("AUTOBOT_EMBEDDING_SWITCH_SETTLE_MARGIN_SECONDS", 2.0, 0.0, 300.0)
#: Replay rounds before cutover gives up on writes that keep arriving.
SWITCH_REPLAY_ROUNDS = env_int_clamped("AUTOBOT_EMBEDDING_SWITCH_REPLAY_ROUNDS", 5, 1, 100)
#: Failed fact ids kept in the state for the operator; the count is always exact.
_FAILED_IDS_SHOWN = 50
#: While building, and while settling after cutover, every write is noted for replay.
_ACTIVE = ("building", "settling")
#: Set the cancel flag only while the build is still before cutover; 0 once it is settling or done.
_CANCEL_IF_BUILDING_LUA = """
if redis.call('HGET', KEYS[1], 'state') == 'building' then
  redis.call('HSET', KEYS[1], 'cancel', '1')
  return 1
end
return 0
"""
#: Enter cutover only if no cancel was accepted; one step, so a cancel lands before it or is refused.
#: -1, writing nothing, when this run no longer owns the record: it expired or a newer switch took it.
_SETTLE_UNLESS_CANCELLED_LUA = """
if redis.call('HGET', KEYS[1], 'owner') ~= ARGV[1] then
  return -1
end
if redis.call('HGET', KEYS[1], 'cancel') == '1' then
  return 0
end
redis.call('HSET', KEYS[1], 'state', 'settling')
return 1
"""


_SETTLE_LOST_RECORD = -1


class SwitchRefused(ValueError):
    """A switch request that cannot start (bad model, one already running, already active)."""


class _DeadlineExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class _Run:
    owner: str
    model: str
    collection: str
    started: float


def target_collection(base: str, model: str, attempt: str) -> str:
    """A per-attempt collection name within ChromaDB's rules (3-63 chars, alphanumeric ends)."""
    slug = sanitize_token(model, replacement="_", case="lower", strip_edges="_", max_length=28)
    return f"{base[:20]}__{slug}__{attempt[:8]}"


async def _redis():
    from autobot_shared.redis_client import get_async_redis_client

    return await get_async_redis_client(database="knowledge", decode_responses=True)


async def switch_status() -> Dict[str, Any]:
    """The current or last switch; an active one whose heartbeat lock expired reads ``stale``."""
    client = await _redis()
    status: Dict[str, Any] = dict((await client.hgetall(STATE_KEY)) or {}) if client is not None else {}
    for key in ("done", "total", "failed", "previous_vectors"):
        if key in status:
            status[key] = int(status[key])
    status["failed_ids"] = json.loads(status.get("failed_ids", "[]"))
    status.setdefault("state", "idle")
    if status["state"] in _ACTIVE and client is not None and await lock.holder() is None:
        status["state"] = "stale"
        status["reason"] = "the build stopped heartbeating; its worker is presumed gone"
    return status


async def _set_state(**fields: Any) -> None:
    client = await _redis()
    if client is None:
        raise RuntimeError("the embedding-switch state cannot be written: no Redis")
    await client.hset(STATE_KEY, mapping={k: str(v) for k, v in fields.items()})


async def start_switch(kb, model: str, actor: str = "unknown") -> Dict[str, Any]:
    """Start a background rebuild for *model*; refuses rather than queueing a second one."""
    if not is_embedding_model_id(model):
        raise SwitchRefused(f"{model!r} is not an embedding model")
    if model == active_embedding_model():
        raise SwitchRefused(f"{model!r} is already the active embedding model")
    if kb is None or not getattr(kb, "chromadb_collection", None):
        raise SwitchRefused("the knowledge base is not available")
    collection = target_collection(kb.chromadb_collection.split("__", 1)[0], model, uuid.uuid4().hex)
    client = await _redis()
    owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    if client is None:
        raise SwitchRefused("the knowledge base state store is not available")
    try:
        acquired = await lock.acquire(owner, int(SWITCH_STALE_S))
    except ClaimUnavailable as exc:
        raise SwitchRefused(f"the claim registry is not available: {exc}") from exc
    if not acquired:
        raise SwitchRefused("a switch is already running")
    run = _Run(owner, model, collection, time.monotonic())
    try:
        await client.delete(STATE_KEY, PENDING_KEY)
        now = datetime.now(tz=timezone.utc).isoformat()
        await _set_state(
            state="building", owner=owner, model=model, collection=collection, done=0, total=0, failed=0, started=now
        )
        _audit(actor, "switch_start", model, collection)
        fire_and_forget(run_switch(kb, run), name=f"embedding-switch:{model}")
    except BaseException:
        await lock.release(owner)  # a start that failed must not block the next one
        raise
    return await switch_status()


async def request_switch_cancel(actor: str = "unknown") -> str:
    """Cancel a running build at its next batch, or force-close a stale one; ``none`` when idle."""
    status = await switch_status()
    if status["state"] == "stale":
        await _finish(None, "failed", reason="force-closed: the build stopped heartbeating")
        _audit(actor, "switch_force_close", status.get("model"), status.get("collection"))
        return "force_closed"
    if status["state"] not in _ACTIVE:
        return "none"
    if not await (await _redis()).eval(_CANCEL_IF_BUILDING_LUA, 1, STATE_KEY):
        return "too_late"  # settling: past the cutover boundary, the record is being or has been written
    _audit(actor, "switch_cancel", status.get("model"), status.get("collection"))
    return "cancel_requested"


def _audit(actor: str, phase: str, model: str | None, collection: str | None) -> None:
    from services.audit.audit import audit_record
    from services.audit.taxonomy import AuditAction

    meta = {"phase": phase, "collection": collection}
    audit_record(
        user_id=actor,
        action=AuditAction.CONFIG_UPDATE,
        resource_type="embedding_model",
        resource_id=model,
        metadata=meta,
    )


async def note_write(fact_id: str) -> None:
    """Record a fact written, updated or deleted while a build runs, for replay before cutover."""
    try:
        client = await _redis()
        if client is not None and await client.hget(STATE_KEY, "state") in _ACTIVE:
            await client.sadd(PENDING_KEY, fact_id)
    except Exception as exc:  # noqa: BLE001 - a write must not fail because the switch log did
        logger.error("embedding switch could not note write %s (%s); the build will fail its count check", fact_id, exc)


async def _heartbeat(run: _Run, **fields: Any) -> None:
    """Keep the lock (this owner only), record progress, and enforce the overall deadline."""
    if time.monotonic() - run.started > SWITCH_DEADLINE_S:
        raise _DeadlineExceeded(f"the build exceeded its {SWITCH_DEADLINE_S:.0f}s deadline")
    if not await lock.extend_claim(run.owner, int(SWITCH_STALE_S)):
        raise RuntimeError("the build lost its lock (force-closed or expired)")
    await _set_state(heartbeat=datetime.now(tz=timezone.utc).isoformat(), **fields)


async def run_switch(kb, run: _Run) -> None:
    """The background build; until the record is written, any failure leaves everything as it was."""
    try:
        store, failed_ids, _done = await _build(kb, run)
        if store is None:
            return  # cancelled; the state already says so
        converged, failed_ids, reason = await _converge(store, run, failed_ids)
        if failed_ids:
            reason = f"{len(failed_ids)} fact(s) failed to embed; cutover needs zero failures"
        if failed_ids or not converged:
            await _finish(run, "failed", reason=reason, failed=len(failed_ids), failed_ids=failed_ids)
            return
    except Exception as exc:  # noqa: BLE001 - recorded, not raised: nobody awaits a background job
        logger.exception("embedding switch to %s failed", run.model)
        await _finish(run, "failed", reason=f"{type(exc).__name__}: {exc}")
        return
    await _cut_over(kb, store, run)


async def _finish(run: _Run | None, state: str, *, reason: str = "", failed: int | None = None, failed_ids=()) -> None:
    client = await _redis()
    if run is not None and await client.hget(STATE_KEY, "owner") != run.owner:
        # a newer switch owns the state, or the record is gone: leave it alone, but never keep our lock
        logger.warning("embedding switch %s finished as %s after losing ownership; state left as is", run.owner, state)
        await lock.release(run.owner)
        return
    fields: Dict[str, Any] = {"state": state, "finished": datetime.now(tz=timezone.utc).isoformat(), "reason": reason}
    if failed is not None:
        fields["failed"] = failed
    fields["failed_ids"] = json.dumps(list(failed_ids)[:_FAILED_IDS_SHOWN])
    await _set_state(**fields)
    if run is None:
        await lock.force_release()  # force-close: the owner is gone
    else:
        await lock.release(run.owner)


async def _build(kb, run: _Run) -> Tuple[Any, List[str], int]:
    from knowledge import fact_store

    previous = await asyncio.to_thread(kb.vector_store._collection.count) if kb.vector_store is not None else 0
    await _heartbeat(run, total=await fact_store.count_facts(), previous_vectors=previous)
    store, failed_ids, done = None, [], 0
    async for batch in fact_store.iter_facts(batch_size=SWITCH_BATCH_SIZE):
        if (await switch_status()).get("cancel") == "1":
            await _finish(run, "cancelled", reason="cancelled by request")
            return None, [], done
        await _heartbeat(run)  # before the batch too: one batch of embeddings can outlast a short TTL
        nodes, failed = await _embed(run.model, batch)
        if nodes:
            store = store or await _open_collection(kb, run.collection, run.model, len(nodes[0].embedding))
            await asyncio.to_thread(store.add, nodes)
        failed_ids += failed
        done += len(batch)
        await _heartbeat(run, done=done, failed=len(failed_ids))
    return store or await _open_collection(kb, run.collection, run.model, None), failed_ids, done


async def _embed(model: str, batch: List[Dict[str, Any]]) -> Tuple[list, List[str]]:
    """TextNodes for the facts that embedded, plus the ids of those that did not.

    One vector per fact, as the KB's own write path stores it; the fact's metadata travels as is,
    so the visibility and quarantine fields the search filters read survive the switch.
    """
    from llama_index.core.schema import TextNode

    from knowledge.utils import sanitize_metadata_for_chromadb
    from services.npu_client import generate_embeddings_batch_with_fallback

    vectors = await generate_embeddings_batch_with_fallback([f["content"] for f in batch], model_name=model)
    nodes, failed = [], []
    for fact, vector in zip(batch, vectors):
        if not vector:
            failed.append(fact["fact_id"])
            continue
        meta = sanitize_metadata_for_chromadb(
            {**fact["metadata"], "fact_id": fact["fact_id"], "embedding_model": model}
        )
        nodes.append(TextNode(id_=fact["fact_id"], text=fact["content"], embedding=vector, metadata=meta))
    return nodes, failed


async def _open_collection(kb, collection: str, model: str, dim: int | None):
    """The new collection's LlamaIndex store, stamped with the model and dimension it holds."""
    from llama_index.vector_stores.chroma import ChromaVectorStore

    from autobot_shared.embedding_provenance import EmbeddingProvenance, provenance_to_metadata
    from knowledge.backends import get_default_client

    client = await asyncio.to_thread(
        get_default_client, db_path=str(kb.chromadb_path), allow_reset=False, anonymized_telemetry=False
    )
    meta = {**kb._build_hnsw_metadata(), **(provenance_to_metadata(EmbeddingProvenance(model, dim)) if dim else {})}
    raw = await asyncio.to_thread(client.get_or_create_collection, name=collection, metadata=meta)
    return ChromaVectorStore(chroma_collection=getattr(raw, "_raw", raw))


async def _replay_pending(store, run: _Run) -> List[str]:
    """Re-project every fact noted so far; returns the ids that failed to embed."""
    from knowledge import fact_store

    client = await _redis()
    failed: List[str] = []
    replayed = 0
    while fact_id := await client.spop(PENDING_KEY):
        replayed += 1
        if replayed % SWITCH_BATCH_SIZE == 0:
            await _heartbeat(run)  # a long replay must not outlast the lock's TTL
        fact = await fact_store.load_fact(fact_id)
        # by id on the raw collection: LlamaIndex's delete() matches ref_doc_id, which these nodes lack
        await asyncio.to_thread(store._collection.delete, ids=[fact_id])
        if fact is not None:
            nodes, bad = await _embed(run.model, [{"fact_id": fact_id, **fact}])
            if nodes:
                await asyncio.to_thread(store.add, nodes)
            failed += bad
    return failed


async def _converge(store, run: _Run, failed_ids: List[str]) -> Tuple[bool, List[str], str]:
    """Replay in rounds until nothing is pending and every recorded fact has exactly one vector."""
    from knowledge import fact_store

    client, reason = await _redis(), ""
    for _ in range(SWITCH_REPLAY_ROUNDS):
        failed_ids = failed_ids + await _replay_pending(store, run)
        held, expected = await asyncio.to_thread(store._collection.count), await fact_store.count_facts()
        if held == expected and not await client.scard(PENDING_KEY):
            return True, failed_ids, ""
        reason = (
            f"the new collection holds {held} vectors for {expected} facts after {SWITCH_REPLAY_ROUNDS} replay round(s)"
        )
        await _heartbeat(run)
    return False, failed_ids, reason


def _settle_seconds() -> float:
    """Long enough for every process to read the new record and rebind (both caches, plus margin)."""
    from autobot_shared.embedding_model import EMBEDDING_OVERRIDE_CACHE_S
    from knowledge.embedding_space_binding import SPACE_CHECK_INTERVAL_S

    return EMBEDDING_OVERRIDE_CACHE_S + SPACE_CHECK_INTERVAL_S + SWITCH_SETTLE_MARGIN_S


async def _cut_over(kb, store, run: _Run) -> None:
    """Write the record once; whatever fails after that is a warning, never an undone switch."""
    from knowledge.embedding_space_binding import rebind

    try:
        await _heartbeat(run)
        settled = await (await _redis()).eval(_SETTLE_UNLESS_CANCELLED_LUA, 1, STATE_KEY, run.owner)
        if settled == _SETTLE_LOST_RECORD:
            await _finish(run, "failed", reason="cutover did not happen: the run no longer owns the state record")
            return
        if not settled:
            await _finish(run, "cancelled", reason="cancelled by request before cutover")
            return
        # settling from here: a cancel request is refused (too_late)
        space = await asyncio.to_thread(set_embedding_model_override, run.model, run.collection)
    except Exception as exc:  # noqa: BLE001 - the record was not written: nothing switched
        await _finish(run, "failed", reason=f"cutover did not happen: {type(exc).__name__}: {exc}")
        return
    try:
        await rebind(kb, space)
        await asyncio.sleep(_settle_seconds())  # every process has noticed the record by now
        await _heartbeat(run)  # still the owner before the final replay
        converged, late, reason = await _converge(store, run, [])
        held = await asyncio.to_thread(store._collection.count)
        if late or not converged:
            note = f"{len(late)} late write(s) failed to embed" if late else reason
            await _finish(
                run,
                "completed_with_warnings",
                reason=f"switched to {run.model}; {note}",
                failed=len(late),
                failed_ids=late,
            )
        else:
            await _finish(run, "completed", reason=f"{held} facts re-embedded with {run.model}")
    except Exception as exc:  # noqa: BLE001 - the switch happened; say what did not
        logger.exception("embedding switch to %s: a post-cutover step failed", run.model)
        reason = f"switched to {run.model}; after cutover: {type(exc).__name__}: {exc}"
        await _finish(run, "completed_with_warnings", reason=reason)
    logger.warning("Embedding model switched to %s in %s (#19379)", run.model, run.collection)
