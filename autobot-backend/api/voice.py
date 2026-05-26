# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice/TTS and STT API endpoints.

Handles audio file upload for speech-to-text and text-to-speech synthesis,
bridging the FastAPI layer with the TTS/STT backend services.
"""

import asyncio
import os
import tempfile
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from api.schemas_agent import VoiceCreateResponse
from api.schemas_code import (
    VoiceDeleteResponse,
    VoiceListenResponse,
    VoiceSpeakResponse,
    VoiceTranscribeResponse,
)
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.realtime_mcp_bridge import get_realtime_bridge
from services.tts_client import get_tts_client

router = APIRouter(
    dependencies=[Depends(check_admin_permission)],
)
# Separate router for Realtime MCP endpoints — authenticated users (not admin-only)
realtime_router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Realtime MCP tool endpoints (Issue #7343)
# ---------------------------------------------------------------------------


class _RealtimeToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}


@realtime_router.get("/realtime/tools")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_realtime_list_tools",
    error_code_prefix="VOICE",
)
async def voice_realtime_list_tools(
    current_user: dict = Depends(get_current_user),
):
    """Return MCP tools as OpenAI Realtime function-tool schemas.

    The frontend calls this before ``session.update`` to populate the tools
    array for the Realtime session. Tools are filtered by voice bundle and
    the caller's RBAC role.
    """
    is_admin = current_user.get("role") == "admin"
    bridge = await get_realtime_bridge(is_admin=is_admin)
    tools = await bridge.list_realtime_tools()
    return {
        "tools": [
            {
                "type": t.type,
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ]
    }


@realtime_router.post("/realtime/tools/call")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_realtime_call_tool",
    error_code_prefix="VOICE",
)
async def voice_realtime_call_tool(
    body: _RealtimeToolCallRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Invoke an MCP tool by name and return the result envelope.

    Accepts ``{name, arguments}`` and proxies the call through MCPClient.
    Errors surface as ``{is_error: true, content: "<message>"}`` so the
    Realtime model can self-correct verbally without the session crashing.
    """
    from fastapi import HTTPException

    is_admin = current_user.get("role") == "admin"
    _id = current_user.get("id")
    user_id = _id if _id is not None else current_user.get("sub")
    session_id = request.headers.get("X-Session-Id")

    bridge = await get_realtime_bridge(is_admin=is_admin)
    allowed_tools = await bridge.list_realtime_tools()
    allowed_names = {t.name for t in allowed_tools}
    if body.name not in allowed_names:
        raise HTTPException(status_code=403, detail="Tool not permitted in active voice bundle")

    result = await bridge.call_tool(
        body.name,
        body.arguments,
        user_id=user_id,
        session_id=session_id,
    )
    return {"is_error": result.is_error, "content": result.content}


@router.post("/listen", response_model=VoiceListenResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_listen_api",
    error_code_prefix="VOICE",
)
async def voice_listen_api(request: Request, user_role: str = Form("user")):
    """Listen and convert speech to text"""
    security_layer = request.app.state.security_layer
    voice_interface = getattr(request.app.state, "voice_interface", None)
    if voice_interface is None:
        logger.warning("voice_listen called but voice_interface is not initialized")
        return JSONResponse(
            status_code=503,
            content={"message": "Voice interface is not available on this server."},
        )
    if not security_layer.check_permission(user_role, "allow_voice_listen"):
        security_layer.audit_log("voice_listen", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to listen via voice."},
        )

    result = await voice_interface.listen_and_convert_to_text()
    if result["status"] == "success":
        security_layer.audit_log("voice_listen", user_role, "success", {"text": result["text"]})
        return {"message": "Speech recognized.", "text": result["text"]}
    else:
        security_layer.audit_log("voice_listen", user_role, "failure", {"reason": result.get("message")})
        return JSONResponse(
            status_code=500,
            content={"message": f"Speech recognition failed: {result['message']}"},
        )


@router.post("/speak", response_model=VoiceSpeakResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_speak_api",
    error_code_prefix="VOICE",
)
async def voice_speak_api(request: Request, text: str = Form(...), user_role: str = Form("user")):
    """Converts text to speech and plays it."""
    security_layer = request.app.state.security_layer
    voice_interface = getattr(request.app.state, "voice_interface", None)
    if voice_interface is None:
        logger.warning("voice_speak called but voice_interface is not initialized")
        return JSONResponse(
            status_code=503,
            content={"message": "Voice interface is not available on this server."},
        )
    if not security_layer.check_permission(user_role, "allow_voice_speak"):
        security_layer.audit_log(
            "voice_speak",
            user_role,
            "denied",
            {"text_preview": text[:50], "reason": "permission_denied"},
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to speak via voice."},
        )

    result = await voice_interface.speak_text(text)
    if result["status"] == "success":
        security_layer.audit_log("voice_speak", user_role, "success", {"text_preview": text[:50]})
        return {"message": "Text spoken successfully."}
    else:
        security_layer.audit_log(
            "voice_speak",
            user_role,
            "failure",
            {"text_preview": text[:50], "reason": result.get("message")},
        )
        return JSONResponse(
            status_code=500,
            content={"message": f"Text-to-speech failed: {result['message']}"},
        )


@router.post("/synthesize", response_model=None)  # Returns audio/wav Response — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_synthesize_api",
    error_code_prefix="VOICE",
)
async def voice_synthesize_api(
    request: Request,
    text: str = Form(...),
    voice_id: str = Form(""),
    language: str = Form(""),
    user_role: str = Form("user"),
):
    """Synthesize speech via Pocket TTS worker. Returns audio/wav stream."""
    security_layer = request.app.state.security_layer
    if not security_layer.check_permission(user_role, "allow_voice_speak"):
        security_layer.audit_log("voice_synthesize", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to synthesize voice."},
        )

    tts = get_tts_client()
    wav_bytes = await tts.synthesize(text, voice_id=voice_id, language=language)
    security_layer.audit_log("voice_synthesize", user_role, "success", {"text_preview": text[:50]})
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=speech.wav"},
    )


@router.post("/clone-voice", response_model=None)  # Returns audio/wav Response — no Pydantic schema
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_clone_api",
    error_code_prefix="VOICE",
)
async def voice_clone_api(
    request: Request,
    text: str = Form(...),
    reference_audio: UploadFile = File(...),
    user_role: str = Form("user"),
):
    """Zero-shot voice cloning via TTS worker. Returns audio/wav stream."""
    security_layer = request.app.state.security_layer
    if not security_layer.check_permission(user_role, "allow_voice_speak"):
        security_layer.audit_log("voice_clone", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to clone voice."},
        )

    ref_bytes = await reference_audio.read()
    tts = get_tts_client()
    wav_bytes = await tts.clone_voice(text, ref_bytes)
    security_layer.audit_log("voice_clone", user_role, "success", {"text_preview": text[:50]})
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=cloned_speech.wav"},
    )


# ------------------------------------------------------------------
# Voice profile management (#1054)
# ------------------------------------------------------------------


@router.get("/voices", response_model=List[Dict[str, Any]])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_list_api",
    error_code_prefix="VOICE",
)
async def voice_list_api():
    """List available voice profiles from TTS worker."""
    tts = get_tts_client()
    voices = await tts.list_voices()
    return voices


@router.post("/voices/create", response_model=VoiceCreateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_create_api",
    error_code_prefix="VOICE",
)
async def voice_create_api(
    name: str = Form(...),
    audio: UploadFile = File(...),
):
    """Create a voice profile from reference audio."""
    audio_bytes = await audio.read()
    tts = get_tts_client()
    result = await tts.create_voice(name, audio_bytes, audio.filename or "ref.wav")
    return result


@router.delete("/voices/{voice_id}", response_model=VoiceDeleteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_delete_api",
    error_code_prefix="VOICE",
)
async def voice_delete_api(voice_id: str):
    """Delete a custom voice profile."""
    tts = get_tts_client()
    success = await tts.delete_voice(voice_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "Voice not found"})
    return {"deleted": voice_id}


# ------------------------------------------------------------------
# Audio transcription via Whisper (#1030)
# ------------------------------------------------------------------

_MIME_TO_SUFFIX = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
}


def _whisper_sync(pipe, audio_bytes: bytes, suffix: str, language: str = "") -> dict:
    """Blocking Whisper inference — call via asyncio.to_thread (#1030).

    Args:
        language: BCP-47 language hint (e.g. "en", "de"). Empty = auto-detect.
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        generate_kwargs = {}
        if language:
            generate_kwargs["language"] = language
        output = pipe(
            tmp_path,
            return_timestamps=False,
            generate_kwargs=generate_kwargs or None,
        )
        text = output.get("text", "").strip() if isinstance(output, dict) else ""
        detected_lang = output.get("language", "unknown") if isinstance(output, dict) else "unknown"
        confidence = 0.9 if text else 0.0
        return {
            "text": text,
            "language": detected_lang,
            "confidence": confidence,
        }
    except Exception as exc:
        logger.warning("Whisper transcription failed: %s", exc)
        return {"text": "", "language": "unknown", "confidence": 0.0}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _transcribe_with_whisper(audio_bytes: bytes, content_type: str, language: str = "") -> dict:
    """Run Whisper transcription in a background thread (#1030)."""
    from media.audio.pipeline import _get_whisper_pipeline

    pipe = _get_whisper_pipeline()
    if not pipe:
        return {"text": "", "language": "unknown", "confidence": 0.0}

    ct = content_type.split(";")[0].strip()
    suffix = _MIME_TO_SUFFIX.get(ct, ".wav")
    return await asyncio.to_thread(_whisper_sync, pipe, audio_bytes, suffix, language)


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_transcribe_api",
    error_code_prefix="VOICE",
)
async def voice_transcribe_api(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(""),
):
    """Transcribe audio blob to text via Whisper (#1030, #1329).

    Args:
        language: BCP-47 language hint (e.g. "en", "de"). Empty = auto-detect.
    """
    security_layer = request.app.state.security_layer
    if not security_layer.check_permission("user", "allow_voice_listen"):
        return JSONResponse(
            status_code=403,
            content={"text": "", "error": "Permission denied."},
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        return JSONResponse(
            status_code=400,
            content={"text": "", "error": "Empty audio file."},
        )

    result = await _transcribe_with_whisper(audio_bytes, audio.content_type or "audio/webm", language)
    security_layer.audit_log(
        "voice_transcribe",
        "user",
        "success",
        {"text_preview": result.get("text", "")[:50]},
    )
    return result
