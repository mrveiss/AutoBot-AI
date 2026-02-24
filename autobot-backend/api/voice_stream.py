# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Stream WebSocket Endpoint (#1031)

Provides a bidirectional WebSocket for full-duplex voice conversations.
Handles control signaling (barge-in, state sync) and coordinates
TTS audio streaming between client and server.

Protocol (JSON messages):
  Client -> Server:
    {"type": "barge_in"}              - User interrupted TTS playback
    {"type": "transcript", "text": "...", "final": true/false}
    {"type": "start_listening"}       - Client started STT capture
    {"type": "stop_listening"}        - Client stopped STT capture

  Server -> Client:
    {"type": "state", "state": "idle|listening|processing|speaking"}
    {"type": "tts_start", "text": "..."}   - TTS synthesis beginning
    {"type": "tts_audio", "data": "<base64>", "chunk": N, "total": N}
    {"type": "tts_end"}                     - TTS playback complete
    {"type": "error", "message": "..."}
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
) -> None:
    """Synthesize TTS for text and stream audio chunks to client.

    Respects cancel_event for barge-in interruption.
    """
    chunks = _split_text_for_tts(text)
    total = len(chunks)

    await _send_json(ws, {"type": "tts_start", "text": text})

    for i, chunk_text in enumerate(chunks):
        if cancel_event.is_set():
            logger.debug("TTS cancelled by barge-in at chunk %d/%d", i, total)
            break

        try:
            tts = get_tts_client()
            wav_bytes = await tts.synthesize(chunk_text, voice_id=voice_id)
            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

            if cancel_event.is_set():
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
            break

    await _send_json(ws, {"type": "tts_end"})


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
) -> Optional[asyncio.Task]:
    """Start TTS synthesis and stream audio to client (#1031)."""
    if not text:
        return None
    cancel_event.clear()
    await set_state_fn("speaking")
    task = asyncio.create_task(
        _synthesize_and_stream(ws, text, cancel_event, voice_id=voice_id)
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


@router.websocket("/stream")
async def voice_stream_ws(websocket: WebSocket) -> None:
    """Full-duplex voice conversation WebSocket (#1031)."""
    await websocket.accept()
    logger.info("Voice stream WebSocket connected")

    cancel_tts = asyncio.Event()
    tts_task: Optional[asyncio.Task] = None
    current_state = "idle"

    async def _set_state(new_state: str) -> None:
        nonlocal current_state
        current_state = new_state
        await _send_json(websocket, {"type": "state", "state": new_state})

    try:
        await _set_state("idle")
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type", "")

            if msg_type == "barge_in":
                logger.debug("Barge-in received")
                await _cancel_active_tts(cancel_tts, tts_task)
                await _set_state("listening")

            elif msg_type == "start_listening":
                if current_state == "speaking":
                    await _cancel_active_tts(cancel_tts, tts_task)
                await _set_state("listening")

            elif msg_type == "stop_listening":
                await _set_state("idle")

            elif msg_type == "transcript":
                text = msg.get("text", "").strip()
                if msg.get("final", False) and text:
                    await _set_state("processing")

            elif msg_type == "speak":
                tts_task = await _start_tts_stream(
                    websocket,
                    msg.get("text", "").strip(),
                    cancel_tts,
                    _set_state,
                    lambda: current_state,
                    voice_id=msg.get("voice_id", ""),
                )

            elif msg_type == "ping":
                await _send_json(websocket, {"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error("Voice stream WebSocket error: %s", e)
        await _send_json(websocket, {"type": "error", "message": str(e)})
    finally:
        cancel_tts.set()
        if tts_task and not tts_task.done():
            tts_task.cancel()
        logger.info("Voice stream WebSocket closed")
