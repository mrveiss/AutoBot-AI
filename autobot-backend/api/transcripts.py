# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Transcript Analysis and KB Integration API (MVA-2176, #9863).

Provides WebSocket streaming for AI analysis and per-segment KB push
endpoints on top of the transcriber recording storage (GH#9044).
"""

from typing import AsyncIterator

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.datastructures import State
from starlette.websockets import WebSocketState

from api.schemas_transcripts import (
    AnalysisType,
    TranscriptAnalyzeRequest,
    TranscriptKBPushRequest,
    TranscriptKBPushResponse,
)
from auth_middleware import authenticate_websocket, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge import get_knowledge_base
from llm_shared import LLMRequest, get_provider_registry
from transcriber.ai.context import build_context
from transcriber.deps import DEFAULT_USER
from transcriber.routes.export import _build_segment_list

logger = get_logger(__name__)
router = APIRouter()


def _resolve_user_id(user: dict) -> str:
    """Map an auth payload to the transcriber user-id convention."""
    return str(user.get("user_id") or user.get("username") or DEFAULT_USER)


def _check_ownership(rec: dict, caller_id: str) -> None:
    """Reject access to recordings owned by another (non-default) user."""
    owner = rec.get("user_id") or DEFAULT_USER
    if owner not in (DEFAULT_USER, caller_id):
        raise HTTPException(status_code=404, detail="Transcript not found")


async def _load_recording(state: State, transcript_id: str, caller_id: str) -> dict:
    """Fetch the transcriber recording backing a transcript id."""
    db = getattr(state, "transcriber_db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Transcriber storage unavailable")
    try:
        recording_id = int(transcript_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Transcript not found") from None
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Transcript not found")
    _check_ownership(rec, caller_id)
    return rec


async def _load_transcript_content(state: State, transcript_id: str, caller_id: str) -> str:
    """Build the full transcript text for a recording (segments + speakers)."""
    rec = await _load_recording(state, transcript_id, caller_id)
    if rec["status"] != "complete":
        raise HTTPException(status_code=400, detail="Recording not yet transcribed")
    segments = await _build_segment_list(int(transcript_id), state.transcriber_db)
    return build_context(segments)


def _get_analysis_prompt(analysis_type: AnalysisType, content: str, custom_prompt: str | None = None) -> str:
    """Generate analysis prompt based on type."""
    prompts = {
        AnalysisType.SUMMARIZE: f"Summarize the following transcript in a clear and concise manner:\n\n{content}",
        AnalysisType.KEY_FACTS: (f"Extract the key facts and important information from this transcript:\n\n{content}"),
        AnalysisType.PROTOCOL: (
            f"Identify any protocols, procedures, or standard processes " f"mentioned in this transcript:\n\n{content}"
        ),
    }

    if analysis_type == AnalysisType.CUSTOM:
        if not custom_prompt:
            raise ValueError("Custom analysis requires a custom_prompt")
        return f"{custom_prompt}\n\nTranscript:\n{content}"

    return prompts[analysis_type]


async def _stream_analysis(transcript_content: str, request: TranscriptAnalyzeRequest) -> AsyncIterator[str]:
    """Stream AI analysis of transcript content using llm_shared."""
    try:
        # Build LLM prompt
        prompt = _get_analysis_prompt(request.analysis_type, transcript_content, request.custom_prompt)

        # Security: Pass context as separate system message boundary instead of concatenating
        messages = []
        if request.context:
            messages.append({"role": "system", "content": f"Context: {request.context}"})
        messages.append({"role": "user", "content": prompt})

        # Create LLM request
        llm_request = LLMRequest(
            messages=messages,
            model=None,  # Use default model from provider
            stream=True,
        )

        # Get provider and stream response
        registry = get_provider_registry()
        provider = await registry.get_default_provider()

        if not provider:
            raise HTTPException(status_code=503, detail="No LLM provider available")

        # Stream tokens
        async for token in provider.stream_completion(llm_request):
            yield token

    except Exception as e:
        # Security: Log full error but only send generic message to client
        logger.error("Analysis streaming failed: %s", e, exc_info=True)
        yield "\n\n[ERROR: Analysis failed. Please try again later.]"


@router.websocket("/transcripts/{transcript_id}/analyze")
async def analyze_transcript_ws(websocket: WebSocket, transcript_id: str):
    """
    WebSocket endpoint for streaming AI analysis of transcripts.

    Protocol:
      Connect: wss://host/api/transcripts/{id}/analyze?token=<jwt>
      Client sends: {"analysis_type": "summarize", "custom_prompt": "...", "context": "..."}
      Server streams: Analysis chunks as text
      On completion: Server closes connection

    Security: Requires JWT authentication (Issue #2818 handshake-level rejection).
    """
    user = await authenticate_websocket(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    try:
        # Receive analysis request
        data = await websocket.receive_json()
        request = TranscriptAnalyzeRequest(**data)

        try:
            content = await _load_transcript_content(websocket.app.state, transcript_id, _resolve_user_id(user))
        except HTTPException as exc:
            await websocket.send_json({"error": exc.detail})
            await websocket.close(code=4004 if exc.status_code == 404 else 1008)
            return

        # Stream analysis
        async for chunk in _stream_analysis(content, request):
            if websocket.client_state == WebSocketState.DISCONNECTED:
                break
            await websocket.send_text(chunk)

        # Close connection after streaming completes
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()

    except WebSocketDisconnect:
        logger.info("Client disconnected from transcript analysis WebSocket: %s", transcript_id)
    except ValueError as e:
        logger.warning("Invalid analysis request: %s", e)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"error": str(e)})
            await websocket.close(code=1008)
    except Exception as e:
        logger.error("Transcript analysis WebSocket error: %s", e, exc_info=True)
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json({"error": "Internal server error"})
            await websocket.close(code=1011)


def _build_kb_metadata(request: TranscriptKBPushRequest, transcript_id: str, caller_id: str) -> dict:
    """Build KB metadata; system fields last so clients cannot override them."""
    user_metadata = {}
    if request.speaker:
        user_metadata["speaker"] = request.speaker
    if request.confidence is not None:
        user_metadata["confidence"] = request.confidence
    if request.language:
        user_metadata["language"] = request.language
    if request.segment_start is not None:
        user_metadata["segment_start"] = request.segment_start
    if request.segment_end is not None:
        user_metadata["segment_end"] = request.segment_end

    return {
        **user_metadata,
        "source_type": "transcript",
        "transcript_id": transcript_id,
        "source": f"transcript:{transcript_id}",
        "verification_status": "unverified",
        "user_id": caller_id,
    }


@router.post("/transcripts/{transcript_id}/kb-push", response_model=TranscriptKBPushResponse)
@with_error_handling(category=ErrorCategory.DATABASE)
async def push_transcript_to_kb(
    transcript_id: str,
    request: TranscriptKBPushRequest,
    raw_request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Push a transcript segment to the Knowledge Base.

    Creates a KB entry from the provided transcript segment with metadata.

    Security: Requires authentication. Verifies the backing recording
    exists and is accessible to the caller before indexing.
    """
    caller_id = _resolve_user_id(user)
    await _load_recording(raw_request.app.state, transcript_id, caller_id)

    try:
        kb = await get_knowledge_base()
        result = await kb.add_document(
            content=request.segment_text,
            metadata=_build_kb_metadata(request, transcript_id, caller_id),
        )

        if result.get("status") == "success":
            return TranscriptKBPushResponse(
                success=True,
                doc_id=result.get("doc_id"),
                message="Transcript segment added to Knowledge Base",
            )
        return TranscriptKBPushResponse(
            success=False,
            message=result.get("message", "Failed to add to Knowledge Base"),
        )

    except Exception as e:
        # Security: Log full error but only send generic message to client
        logger.error("KB push failed for transcript %s: %s", transcript_id, e, exc_info=True)
        return TranscriptKBPushResponse(
            success=False,
            message="KB push failed. Please try again later.",
        )
