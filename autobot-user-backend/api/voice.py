# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

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
