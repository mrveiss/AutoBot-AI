# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import logging
import os
import tempfile

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.services.tts_client import get_tts_client

router = APIRouter()
logger = logging.getLogger(__name__)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_listen_api",
    error_code_prefix="VOICE",
)
@router.post("/listen")
async def voice_listen_api(request: Request, user_role: str = Form("user")):
    """Listen and convert speech to text"""
    security_layer = request.app.state.security_layer
    voice_interface = request.app.state.voice_interface
    if not security_layer.check_permission(user_role, "allow_voice_listen"):
        security_layer.audit_log(
            "voice_listen", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to listen via voice."},
        )

    result = await voice_interface.listen_and_convert_to_text()
    if result["status"] == "success":
        security_layer.audit_log(
            "voice_listen", user_role, "success", {"text": result["text"]}
        )
        return {"message": "Speech recognized.", "text": result["text"]}
    else:
        security_layer.audit_log(
            "voice_listen", user_role, "failure", {"reason": result.get("message")}
        )
        return JSONResponse(
            status_code=500,
            content={"message": f"Speech recognition failed: {result['message']}"},
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_speak_api",
    error_code_prefix="VOICE",
)
@router.post("/speak")
async def voice_speak_api(
    request: Request, text: str = Form(...), user_role: str = Form("user")
):
    """Converts text to speech and plays it."""
    security_layer = request.app.state.security_layer
    voice_interface = request.app.state.voice_interface
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
        security_layer.audit_log(
            "voice_speak", user_role, "success", {"text_preview": text[:50]}
        )
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_synthesize_api",
    error_code_prefix="VOICE",
)
@router.post("/synthesize")
async def voice_synthesize_api(
    request: Request,
    text: str = Form(...),
    user_role: str = Form("user"),
):
    """Synthesize speech via Kani-TTS-2 worker. Returns audio/wav stream."""
    security_layer = request.app.state.security_layer
    if not security_layer.check_permission(user_role, "allow_voice_speak"):
        security_layer.audit_log(
            "voice_synthesize", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to synthesize voice."},
        )

    tts = get_tts_client()
    wav_bytes = await tts.synthesize(text)
    security_layer.audit_log(
        "voice_synthesize", user_role, "success", {"text_preview": text[:50]}
    )
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=speech.wav"},
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_clone_api",
    error_code_prefix="VOICE",
)
@router.post("/clone-voice")
async def voice_clone_api(
    request: Request,
    text: str = Form(...),
    reference_audio: UploadFile = File(...),
    user_role: str = Form("user"),
):
    """Zero-shot voice cloning via Kani-TTS-2. Returns audio/wav stream."""
    security_layer = request.app.state.security_layer
    if not security_layer.check_permission(user_role, "allow_voice_speak"):
        security_layer.audit_log(
            "voice_clone", user_role, "denied", {"reason": "permission_denied"}
        )
        return JSONResponse(
            status_code=403,
            content={"message": "Permission denied to clone voice."},
        )

    ref_bytes = await reference_audio.read()
    tts = get_tts_client()
    wav_bytes = await tts.clone_voice(text, ref_bytes)
    security_layer.audit_log(
        "voice_clone", user_role, "success", {"text_preview": text[:50]}
    )
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=cloned_speech.wav"},
    )


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


def _whisper_sync(pipe, audio_bytes: bytes, suffix: str) -> dict:
    """Blocking Whisper inference — call via asyncio.to_thread (#1030)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        output = pipe(tmp_path, return_timestamps=False)
        text = output.get("text", "").strip() if isinstance(output, dict) else ""
        language = (
            output.get("language", "unknown") if isinstance(output, dict) else "unknown"
        )
        confidence = 0.9 if text else 0.0
        return {"text": text, "language": language, "confidence": confidence}
    except Exception as exc:
        logger.warning("Whisper transcription failed: %s", exc)
        return {"text": "", "language": "unknown", "confidence": 0.0}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _transcribe_with_whisper(audio_bytes: bytes, content_type: str) -> dict:
    """Run Whisper transcription in a background thread (#1030)."""
    from media.audio.pipeline import _get_whisper_pipeline

    pipe = _get_whisper_pipeline()
    if not pipe:
        return {"text": "", "language": "unknown", "confidence": 0.0}

    ct = content_type.split(";")[0].strip()
    suffix = _MIME_TO_SUFFIX.get(ct, ".wav")
    return await asyncio.to_thread(_whisper_sync, pipe, audio_bytes, suffix)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="voice_transcribe_api",
    error_code_prefix="VOICE",
)
@router.post("/transcribe")
async def voice_transcribe_api(
    request: Request,
    audio: UploadFile = File(...),
):
    """Transcribe audio blob to text via Whisper (#1030)."""
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

    result = await _transcribe_with_whisper(
        audio_bytes, audio.content_type or "audio/webm"
    )
    security_layer.audit_log(
        "voice_transcribe",
        "user",
        "success",
        {"text_preview": result.get("text", "")[:50]},
    )
    return result
