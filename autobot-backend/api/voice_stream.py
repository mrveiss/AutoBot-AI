# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.tts_client import get_tts_client
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)
router = APIRouter()

# Maximum TTS text length per chunk (characters)
_MAX_TTS_CHUNK_CHARS = 200


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


async def _synthesize_and_stream(
    ws: WebSocket,
    text: str,
    cancel_event: asyncio.Event,
    voice_id: str = "",
    language: str = "",
) -> None:
    """Synthesize TTS for text and stream audio chunks to client.

    Respects cancel_event for barge-in interruption.
    """
    chunks = _split_text_for_tts(text)
    total = len(chunks)

    await _send_json(ws, {"type": "tts_start", "text": text})

    tts = get_tts_client()
    # Pipeline synthesis: pre-fetch next chunk while sending current (#1527)
    next_task: asyncio.Task | None = None
    if total > 0 and not cancel_event.is_set():
        next_task = asyncio.create_task(
            tts.synthesize(chunks[0], voice_id=voice_id, language=language)
        )

    for i, chunk_text in enumerate(chunks):
        if cancel_event.is_set():
            logger.debug("TTS cancelled by barge-in at chunk %d/%d", i, total)
            if next_task and not next_task.done():
                next_task.cancel()
            break

        try:
            wav_bytes = await next_task if next_task else b""
            if not wav_bytes:
                break

            # Start synthesizing the NEXT chunk immediately
            next_task = None
            if i + 1 < total and not cancel_event.is_set():
                next_task = asyncio.create_task(
                    tts.synthesize(
                        chunks[i + 1],
                        voice_id=voice_id,
                        language=language,
                    )
                )

            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

            if cancel_event.is_set():
                if next_task and not next_task.done():
                    next_task.cancel()
                break

            sent = await _send_json(
                ws,
                {
                    "type": "tts_audio",
                    "data": audio_b64,
                    "chunk": i + 1,
                    "total": total,
                },
            )
            if not sent:
                if next_task and not next_task.done():
                    next_task.cancel()
                break
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("TTS synthesis error for chunk %d: %s", i, e)
            await _send_json(
                ws,
                {
                    "type": "error",
                    "message": f"TTS synthesis failed: {e}",
                },
            )
            if next_task and not next_task.done():
                next_task.cancel()
            break

    await _send_json(ws, {"type": "tts_end"})


async def _tts_queue_worker(
    ws: WebSocket,
    queue: asyncio.Queue,
    cancel_event: asyncio.Event,
) -> None:
    """Drain sentence queue, synthesizing and streaming each sequentially.

    Runs as background task per WS connection. Receives
    (text, voice_id, language) tuples; None is the flush sentinel
    that triggers tts_end.
    """
    while True:
        item = await queue.get()
        if item is None:
            await _send_json(ws, {"type": "tts_end"})
            continue
        text, voice_id, language = item
        if cancel_event.is_set():
            continue
        try:
            tts = get_tts_client()
            wav_bytes = await tts.synthesize(text, voice_id=voice_id, language=language)
            if cancel_event.is_set():
                continue
            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
            await _send_json(
                ws,
                {
                    "type": "tts_audio",
                    "data": audio_b64,
                },
            )
        except Exception as e:
            logger.error("Sentence TTS error: %s", e)
            await _send_json(
                ws,
                {
                    "type": "error",
                    "message": f"Sentence TTS failed: {e}",
                },
            )


async def _cancel_active_tts(
    cancel_event: asyncio.Event,
    tts_task: Optional[asyncio.Task],
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
) -> Optional[asyncio.Task]:
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


async def _handle_ws_message(
    msg: dict,
    ws: WebSocket,
    ctx: dict,
) -> Optional[asyncio.Task]:
    """Dispatch a single WebSocket message. Returns updated tts_task.

    ctx keys: cancel_tts, tts_task, sentence_queue, current_state,
    set_state, get_state.
    """
    msg_type = msg.get("type", "")
    tts_task = ctx["tts_task"]

    if msg_type == "barge_in":
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
        ctx["queue_worker_task"] = asyncio.create_task(
            _tts_queue_worker(ws, ctx["sentence_queue"], ctx["cancel_tts"])
        )
        await ctx["set_state"]("listening")

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
    queue_worker_task: Optional[asyncio.Task],
    cancel_tts: asyncio.Event,
    tts_task: Optional[asyncio.Task],
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
async def voice_stream_ws(websocket: WebSocket) -> None:
    """Full-duplex voice conversation WebSocket (#1031, #1319)."""
    await websocket.accept()
    logger.info("Voice stream WebSocket connected")

    cancel_tts = asyncio.Event()
    tts_task: Optional[asyncio.Task] = None
    sentence_queue: asyncio.Queue = asyncio.Queue()
    queue_worker_task: Optional[asyncio.Task] = None
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
        queue_worker_task = asyncio.create_task(
            _tts_queue_worker(websocket, sentence_queue, cancel_tts)
        )
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
        await _send_json(websocket, {"type": "error", "message": str(e)})
    finally:
        await _cleanup_ws_tasks(ctx.get("queue_worker_task"), cancel_tts, tts_task)
        logger.info("Voice stream WebSocket closed")
