# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Voice Stream WebSocket Endpoint (#1031, #1319)

Provides a bidirectional WebSocket for voice conversations.
Supports full-duplex mode AND sentence-level streaming TTS for all modes.

Protocol (JSON messages):
  Client -> Server:
    {"type": "barge_in"}              - User interrupted TTS playback
    {"type": "transcript", "text": "...", "final": true/false}
    {"type": "start_listening"}       - Client started STT capture
    {"type": "stop_listening"}        - Client stopped STT capture
    {"type": "speak", "text": "..."}  - Full-text TTS (cancels active, for duplex)
    {"type": "speak_sentence", "text": "...", "voice_id": "..."}  - Queue sentence (#1319)
    {"type": "flush"}                 - Signal end of sentence stream (#1319)
    {"type": "ping"}

  Server -> Client:
    {"type": "state", "state": "idle|listening|processing|speaking"}
    {"type": "tts_start", "text": "..."}   - TTS synthesis beginning
    {"type": "tts_audio", "data": "<base64>", "chunk": N, "total": N}
    {"type": "tts_end"}                     - TTS playback complete
    {"type": "error", "message": "..."}
    {"type": "pong"}
"""

import asyncio
import base64
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.tts_client import get_tts_client

logger = get_logger(__name__)
router = APIRouter()

# Maximum TTS text length per chunk (characters). Override via AUTOBOT_TTS_MAX_CHUNK_CHARS.
_MAX_TTS_CHUNK_CHARS = env_int_clamped("AUTOBOT_TTS_MAX_CHUNK_CHARS", 200, 50, 1000)


def _split_text_for_tts(text: str) -> list[str]:
    """Split long text into sentence-boundary chunks for streaming TTS."""
    if len(text) <= _MAX_TTS_CHUNK_CHARS:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= _MAX_TTS_CHUNK_CHARS:
            chunks.append(remaining)
            break
        # Find sentence boundary within limit
        candidate = remaining[:_MAX_TTS_CHUNK_CHARS]
        last_break = max(
            candidate.rfind(". "),
            candidate.rfind("! "),
            candidate.rfind("? "),
        )
        if last_break > 50:
            split_at = last_break + 2
        else:
            # Fall back to word boundary
            last_space = candidate.rfind(" ")
            split_at = last_space if last_space > 0 else _MAX_TTS_CHUNK_CHARS
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [c for c in chunks if c]


async def _send_json(ws: WebSocket, data: dict) -> bool:
    """Send JSON message to WebSocket client. Returns False if disconnected."""
    try:
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_json(data)
            return True
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
    return False


async def _cancel_pending_task(task: "asyncio.Task | None") -> None:
    """Cancel a task if it exists and is not yet done. Ref: #2735."""
    if task and not task.done():
        task.cancel()


# Pipelining depth for TTS streaming (#6752, tuned in #6811).
# Pocket TTS calls run via run_in_executor and serialize on the GIL/model lock,
# so depth>2 only adds queue contention without true parallelism. depth=2 lets
# chunk N+1 synthesize while the client plays chunk N — enough to absorb
# typical jitter without piling backlog. Override with AUTOBOT_TTS_PIPELINE_DEPTH
# (clamped to 1..8 to prevent ops typos OOMing the worker).
def _resolve_tts_pipeline_depth() -> int:
    return env_int_clamped("AUTOBOT_TTS_PIPELINE_DEPTH", 2, 1, 8)


_TTS_PIPELINE_DEPTH = _resolve_tts_pipeline_depth()


async def _send_one_chunk(
    ws: WebSocket,
    i: int,
    total: int,
    task: "asyncio.Task",
    cancel_event: asyncio.Event,
) -> bool:
    """Await one pre-fetched TTS task and send the resulting audio.

    Returns True to continue the stream, False to stop (cancel, empty audio,
    send failure, or synthesis error). The caller owns pipeline maintenance —
    this helper only consumes one slot.
    """
    if cancel_event.is_set():
        logger.debug("TTS cancelled at chunk %d/%d", i, total)
        return False

    try:
        wav_bytes = await task
    except asyncio.CancelledError:
        return False
    except Exception as e:
        logger.error("TTS error chunk %d: %s", i, e)
        await _send_json(ws, {"type": "error", "message": f"TTS synthesis failed: {e}"})
        return False

    if not wav_bytes:
        return False
    if cancel_event.is_set():
        return False

    audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
    return await _send_json(ws, {"type": "tts_audio", "data": audio_b64, "chunk": i + 1, "total": total})


async def _stream_chunks_pipelined(
    ws: WebSocket,
    text: str,
    cancel_event: asyncio.Event,
    voice_id: str = "",
    language: str = "",
) -> None:
    """Split text and stream TTS audio with N-chunks-ahead pipelining (#6752).

    Maintains a sliding window of up to ``_TTS_PIPELINE_DEPTH`` pre-fetched
    synthesis tasks. As each chunk is sent, a new task is scheduled to keep
    the window full — hiding per-chunk TTS latency up to depth*chunk_duration
    of jitter without changing the wire protocol.

    Shared by both ``_synthesize_and_stream`` (full-duplex ``speak``)
    and ``_tts_queue_worker`` (streaming ``speak_sentence``).

    Sends ``tts_start`` before the first chunk and ``tts_end`` after the last,
    keeping the WS protocol consistent (#1535, #1536). Respects
    *cancel_event* for barge-in interruption (#1527).
    """
    chunks = _split_text_for_tts(text)
    total = len(chunks)

    await _send_json(ws, {"type": "tts_start", "text": text})

    if not chunks:
        await _send_json(ws, {"type": "tts_end"})
        return

    tts = get_tts_client()

    # Seed the pipeline with up to _TTS_PIPELINE_DEPTH synthesis tasks. Tasks
    # remain ordered by chunk index in the deque.
    pending: "deque[asyncio.Task]" = deque()
    next_to_schedule = 0
    while next_to_schedule < total and len(pending) < _TTS_PIPELINE_DEPTH:
        if cancel_event.is_set():
            break
        pending.append(
            asyncio.create_task(
                tts.synthesize(
                    chunks[next_to_schedule],
                    voice_id=voice_id,
                    language=language,
                )
            )
        )
        next_to_schedule += 1

    sent_index = 0
    while pending:
        task = pending.popleft()
        # Top up the window before awaiting so the next chunk starts
        # synthesizing immediately while we wait for this one to send.
        if next_to_schedule < total and not cancel_event.is_set():
            pending.append(
                asyncio.create_task(
                    tts.synthesize(
                        chunks[next_to_schedule],
                        voice_id=voice_id,
                        language=language,
                    )
                )
            )
            next_to_schedule += 1

        ok = await _send_one_chunk(ws, sent_index, total, task, cancel_event)
        sent_index += 1
        if not ok:
            # Cancel any still-pending pre-fetches so we do not waste worker
            # time after a cancel / disconnect / error.
            for t in pending:
                await _cancel_pending_task(t)
            pending.clear()
            break

    await _send_json(ws, {"type": "tts_end"})


async def _synthesize_and_stream(
    ws: WebSocket,
    text: str,
    cancel_event: asyncio.Event,
    voice_id: str = "",
    language: str = "",
) -> None:
    """Synthesize TTS for full text and stream to client (#1031)."""
    await _stream_chunks_pipelined(ws, text, cancel_event, voice_id=voice_id, language=language)


async def _tts_queue_worker(
    ws: WebSocket,
    queue: asyncio.Queue,
    cancel_event: asyncio.Event,
) -> None:
    """Drain sentence queue, streaming each with pipelining (#1319).

    Receives (text, voice_id, language) tuples; None is the flush
    sentinel (no-op since _stream_chunks_pipelined sends tts_end).
    """
    while True:
        item = await queue.get()
        if item is None:
            continue
        text, voice_id, language = item
        if cancel_event.is_set():
            continue
        await _stream_chunks_pipelined(
            ws,
            text,
            cancel_event,
            voice_id=voice_id,
            language=language,
        )


async def _cancel_active_tts(
    cancel_event: asyncio.Event,
    tts_task: asyncio.Task | None,
) -> None:
    """Cancel any active TTS task for barge-in interruption (#1031)."""
    cancel_event.set()
    if tts_task and not tts_task.done():
        tts_task.cancel()
        try:
            await tts_task
        except asyncio.CancelledError:
            pass
    cancel_event.clear()


async def _start_tts_stream(
    ws: WebSocket,
    text: str,
    cancel_event: asyncio.Event,
    set_state_fn,
    get_state_fn,
    voice_id: str = "",
    language: str = "",
) -> asyncio.Task | None:
    """Start TTS synthesis and stream audio to client (#1031)."""
    if not text:
        return None
    cancel_event.clear()
    await set_state_fn("speaking")
    task = asyncio.create_task(
        _synthesize_and_stream(
            ws,
            text,
            cancel_event,
            voice_id=voice_id,
            language=language,
        )
    )

    async def _on_done(t: asyncio.Task) -> None:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
        if get_state_fn() == "speaking":
            await set_state_fn("idle")

    asyncio.create_task(_on_done(task))
    return task


async def _drain_sentence_queue(queue: asyncio.Queue) -> None:
    """Clear pending sentences from queue on barge-in (#1319)."""
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break


async def _handle_barge_in(ws: WebSocket, ctx: dict, tts_task: "asyncio.Task | None") -> None:
    """Handle barge-in: cancel active TTS, drain queue, restart worker. Ref: #2735."""
    logger.debug("Barge-in received")
    await _cancel_active_tts(ctx["cancel_tts"], tts_task)
    # Cancel in-flight queue worker to interrupt synthesis (#1319)
    worker = ctx.get("queue_worker_task")
    if worker and not worker.done():
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
    await _drain_sentence_queue(ctx["sentence_queue"])
    # Restart queue worker for future sentences
    ctx["queue_worker_task"] = asyncio.create_task(_tts_queue_worker(ws, ctx["sentence_queue"], ctx["cancel_tts"]))
    await ctx["set_state"]("listening")


async def _handle_ws_message(
    msg: dict,
    ws: WebSocket,
    ctx: dict,
) -> asyncio.Task | None:
    """Dispatch a single WebSocket message. Returns updated tts_task.

    ctx keys: cancel_tts, tts_task, sentence_queue, current_state,
    set_state, get_state.
    """
    msg_type = msg.get("type", "")
    tts_task = ctx["tts_task"]

    if msg_type == "barge_in":
        await _handle_barge_in(ws, ctx, tts_task)

    elif msg_type == "start_listening":
        if ctx["get_state"]() == "speaking":
            await _cancel_active_tts(ctx["cancel_tts"], tts_task)
        await ctx["set_state"]("listening")

    elif msg_type == "stop_listening":
        await ctx["set_state"]("idle")

    elif msg_type == "transcript":
        text = msg.get("text", "").strip()
        if msg.get("final", False) and text:
            await ctx["set_state"]("processing")

    elif msg_type == "speak":
        result = await _start_tts_stream(
            ws,
            msg.get("text", "").strip(),
            ctx["cancel_tts"],
            ctx["set_state"],
            ctx["get_state"],
            voice_id=msg.get("voice_id", ""),
            language=msg.get("language", ""),
        )
        if result is not None:
            tts_task = result

    elif msg_type == "speak_sentence":
        text = msg.get("text", "").strip()
        voice_id = msg.get("voice_id", "")
        language = msg.get("language", "")
        if text:
            await ctx["sentence_queue"].put((text, voice_id, language))

    elif msg_type == "flush":
        await ctx["sentence_queue"].put(None)  # sentinel

    elif msg_type == "ping":
        await _send_json(ws, {"type": "pong"})

    return tts_task


async def _cleanup_ws_tasks(
    queue_worker_task: asyncio.Task | None,
    cancel_tts: asyncio.Event,
    tts_task: asyncio.Task | None,
) -> None:
    """Cancel background tasks on WebSocket close (#1319)."""
    if queue_worker_task and not queue_worker_task.done():
        queue_worker_task.cancel()
        try:
            await queue_worker_task
        except asyncio.CancelledError:
            pass
    cancel_tts.set()
    if tts_task and not tts_task.done():
        tts_task.cancel()


@router.websocket("/stream")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_stream_ws",
    error_code_prefix="VOICE_STREAM",
)
async def voice_stream_ws(websocket: WebSocket) -> None:
    """Full-duplex voice conversation WebSocket (#1031, #1319)."""
    await websocket.accept()
    logger.info("Voice stream WebSocket connected")

    cancel_tts = asyncio.Event()
    tts_task: asyncio.Task | None = None
    sentence_queue: asyncio.Queue = asyncio.Queue()
    queue_worker_task: asyncio.Task | None = None
    current_state = "idle"

    async def _set_state(new_state: str) -> None:
        nonlocal current_state
        current_state = new_state
        await _send_json(websocket, {"type": "state", "state": new_state})

    ctx = {
        "cancel_tts": cancel_tts,
        "tts_task": tts_task,
        "sentence_queue": sentence_queue,
        "queue_worker_task": queue_worker_task,
        "set_state": _set_state,
        "get_state": lambda: current_state,
    }

    try:
        queue_worker_task = asyncio.create_task(_tts_queue_worker(websocket, sentence_queue, cancel_tts))
        ctx["queue_worker_task"] = queue_worker_task
        await _set_state("idle")
        while True:
            msg = await websocket.receive_json()
            tts_task = await _handle_ws_message(msg, websocket, ctx)
            ctx["tts_task"] = tts_task

    except WebSocketDisconnect:
        logger.info("Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error("Voice stream WebSocket error: %s", e)
        await _send_json(websocket, {"type": "error", "message": "Operation failed"})
    finally:
        await _cleanup_ws_tasks(ctx.get("queue_worker_task"), cancel_tts, tts_task)
        logger.info("Voice stream WebSocket closed")
