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
    {"type": "tts_audio", "data": "<base64>", "chunk": N}
    {"type": "tts_end"}                     - TTS playback complete
    {"type": "error", "message": "..."}
    {"type": "pong"}
"""

import asyncio
import base64
from contextlib import aclosing

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from api.ws_security import enforce_ws_origin
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.personality_service import resolve_voice_id
from services.tts_client import get_tts_client

logger = get_logger(__name__)
router = APIRouter()


async def _send_json(ws: WebSocket, data: dict) -> bool:
    """Send JSON message to WebSocket client. Returns False if disconnected."""
    try:
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_json(data)
            return True
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
    return False


async def _stream_chunks_pipelined(
    ws: WebSocket,
    text: str,
    cancel_event: asyncio.Event,
    voice_id: str = "",
    language: str = "",
) -> None:
    """Stream TTS audio for *text*, forwarding each ~250ms mini-WAV chunk
    from the worker the instant it is produced (#12501).

    The TTS worker now streams incrementally (pocket-tts
    ``generate_audio_stream``, see ``tts_client.synthesize_stream``), so
    the client-side text pre-splitting and N-chunks-ahead pipelining this
    function used to do (#6752) are no longer needed for latency: the
    first audio arrives well under a second regardless of utterance
    length, straight from the worker's own chunking.

    Shared by both ``_synthesize_and_stream`` (full-duplex ``speak``)
    and ``_tts_queue_worker`` (streaming ``speak_sentence``).

    ``stream_or_synthesize`` (not ``synthesize_stream``) is used so a worker
    deployed before the streaming route existed degrades to the
    whole-utterance route instead of 404ing (#12886). That 404 used to be
    forwarded as an ``error`` frame with no audio, and the frontend only falls
    back to HTTP when the *socket* fails — never on a per-utterance server
    error — so the spoken reply was dropped in silence.

    Sends ``tts_start`` before the first chunk and ``tts_end`` after the
    last, keeping the WS protocol consistent (#1535, #1536).
    *cancel_event* is checked BETWEEN chunks so barge-in can interrupt
    mid-stream (#1527); the underlying HTTP stream to the worker is
    always closed via ``aclosing``, which the worker's
    ``_stream_synthesis_async`` uses to set a cooperative
    ``threading.Event`` cancel flag — so a cancelled/disconnected client
    does not leave the worker generating (and holding the model lock for)
    audio no one will hear (#12501).
    """
    await _send_json(ws, {"type": "tts_start", "text": text})

    if not text:
        await _send_json(ws, {"type": "tts_end"})
        return

    tts = get_tts_client()
    index = 0
    try:
        async with aclosing(tts.stream_or_synthesize(text, voice_id=voice_id, language=language)) as stream:
            async for wav_bytes in stream:
                if cancel_event.is_set():
                    logger.debug("TTS cancelled mid-stream at chunk %d", index)
                    break
                if not wav_bytes:
                    continue
                audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
                if not await _send_json(ws, {"type": "tts_audio", "data": audio_b64, "chunk": index + 1}):
                    break
                index += 1
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("TTS streaming error: %s", e)
        await _send_json(ws, {"type": "error", "message": f"TTS synthesis failed: {e}"})

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
    """Drain sentence queue, streaming each sentence's audio as it arrives (#1319, #12501).

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
        language = msg.get("language", "")
        result = await _start_tts_stream(
            ws,
            msg.get("text", "").strip(),
            ctx["cancel_tts"],
            ctx["set_state"],
            ctx["get_state"],
            voice_id=resolve_voice_id(msg.get("voice_id", ""), language),
            language=language,
        )
        if result is not None:
            tts_task = result

    elif msg_type == "speak_sentence":
        text = msg.get("text", "").strip()
        language = msg.get("language", "")
        voice_id = resolve_voice_id(msg.get("voice_id", ""), language)
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
    if not await enforce_ws_origin(websocket):
        return
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
