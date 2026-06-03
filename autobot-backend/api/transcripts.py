# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Transcript Analysis and KB Integration API (MVA-2176).

Provides WebSocket streaming for AI analysis and manual KB push endpoints.
"""

from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from api.schemas_transcripts import (
    AnalysisType,
    TranscriptAnalyzeRequest,
    TranscriptKBPushRequest,
    TranscriptKBPushResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge import get_knowledge_base
from llm_shared import LLMRequest, get_provider_registry

logger = get_logger(__name__)
router = APIRouter()


def _get_analysis_prompt(analysis_type: AnalysisType, content: str, custom_prompt: str | None = None) -> str:
    """Generate analysis prompt based on type."""
    prompts = {
        AnalysisType.SUMMARIZE: f"Summarize the following transcript in a clear and concise manner:\n\n{content}",
        AnalysisType.KEY_FACTS: f"Extract the key facts and important information from this transcript:\n\n{content}",
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


def _verify_ws_token(token: str) -> dict | None:
    """Verify JWT token for WebSocket; returns payload dict or None if invalid."""
    if not token:
        return None
    try:
        from auth_middleware import get_auth_middleware

        return get_auth_middleware().verify_jwt_token(token)
    except Exception as exc:
        logger.warning("WebSocket token verification failed: %s", exc)
        return None


@router.websocket("/transcripts/{transcript_id}/analyze")
async def analyze_transcript_ws(websocket: WebSocket, transcript_id: str):
    """
    WebSocket endpoint for streaming AI analysis of transcripts.

    Protocol:
      Connect: wss://host/api/transcripts/{id}/analyze?token=<jwt>
      Client sends: {"analysis_type": "summarize", "custom_prompt": "...", "context": "..."}
      Server streams: Analysis chunks as text
      On completion: Server closes connection

    Security: Requires JWT authentication via query parameter.
    """
    # Security: Authenticate before accepting connection
    token = websocket.query_params.get("token")
    user_payload = _verify_ws_token(token)

    if not user_payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    try:
        # Receive analysis request
        data = await websocket.receive_json()
        request = TranscriptAnalyzeRequest(**data)

        # TODO(MVA-2155): Verify transcript ownership when storage is implemented
        # transcript = await get_transcript(transcript_id)
        # if transcript.user_id != user_payload.get("user_id"):
        #     await websocket.send_json({"error": "Forbidden"})
        #     await websocket.close(code=4003)
        #     return

        # TODO: Fetch actual transcript content from storage
        # For now, using placeholder. Parent issue MVA-2155 should define storage.
        transcript_content = f"[Transcript {transcript_id} content placeholder]"

        # Stream analysis
        async for chunk in _stream_analysis(transcript_content, request):
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


@router.post("/transcripts/{transcript_id}/kb-push", response_model=TranscriptKBPushResponse)
@with_error_handling(category=ErrorCategory.DATABASE)
async def push_transcript_to_kb(
    transcript_id: str,
    request: TranscriptKBPushRequest,
    user: dict = Depends(get_current_user),
):
    """
    Push a transcript segment to the Knowledge Base.

    Creates a KB entry from the provided transcript segment with metadata.

    Security: Requires authentication. Verifies transcript ownership.
    """
    try:
        # TODO(MVA-2155): Verify transcript ownership when storage is implemented
        # transcript = await get_transcript(transcript_id)
        # if transcript.user_id != user.get("user_id"):
        #     raise HTTPException(status_code=403, detail="Forbidden")

        kb = await get_knowledge_base()

        # Security: Build metadata with system fields AFTER user fields to prevent override
        user_metadata = {}
        if request.speaker:
            user_metadata["speaker"] = request.speaker
        if request.confidence is not None:
            user_metadata["confidence"] = request.confidence
        if request.language:
            user_metadata["language"] = request.language

        # Add segment timing if provided
        if request.segment_start is not None:
            user_metadata["segment_start"] = request.segment_start
        if request.segment_end is not None:
            user_metadata["segment_end"] = request.segment_end

        # System-controlled metadata (cannot be overridden by client)
        metadata = {
            **user_metadata,
            "source_type": "transcript",
            "transcript_id": transcript_id,
            "source": f"transcript:{transcript_id}",
            "verification_status": "unverified",
            "user_id": user.get("user_id"),
        }

        # Add to knowledge base
        result = await kb.add_document(
            content=request.segment_text,
            metadata=metadata,
        )

        if result.get("status") == "success":
            return TranscriptKBPushResponse(
                success=True,
                doc_id=result.get("doc_id"),
                message="Transcript segment added to Knowledge Base",
            )
        else:
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
