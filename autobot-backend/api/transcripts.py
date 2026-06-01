# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Transcript Analysis and KB Integration API (MVA-2176).

Provides WebSocket streaming for AI analysis and manual KB push endpoints.
"""

import asyncio
import json
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
from llm_shared.models import LLMRequest
from llm_shared.provider_registry import get_provider_registry

logger = get_logger(__name__)
router = APIRouter()


def _get_analysis_prompt(analysis_type: AnalysisType, content: str, custom_prompt: str | None = None) -> str:
    """Generate analysis prompt based on type."""
    prompts = {
        AnalysisType.SUMMARIZE: f"Summarize the following transcript in a clear and concise manner:\n\n{content}",
        AnalysisType.KEY_FACTS: f"Extract the key facts and important information from this transcript:\n\n{content}",
        AnalysisType.PROTOCOL: f"Identify any protocols, procedures, or standard processes mentioned in this transcript:\n\n{content}",
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

        if request.context:
            prompt = f"Context: {request.context}\n\n{prompt}"

        # Create LLM request
        llm_request = LLMRequest(
            messages=[{"role": "user", "content": prompt}],
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
        logger.error("Analysis streaming failed: %s", e)
        yield f"\n\n[ERROR: Analysis failed - {str(e)}]"


@router.websocket("/transcripts/{transcript_id}/analyze")
async def analyze_transcript_ws(websocket: WebSocket, transcript_id: str):
    """
    WebSocket endpoint for streaming AI analysis of transcripts.

    Protocol:
      Connect: wss://host/api/transcripts/{id}/analyze
      Client sends: {"analysis_type": "summarize", "custom_prompt": "...", "context": "..."}
      Server streams: Analysis chunks as text
      On completion: Server closes connection
    """
    await websocket.accept()

    try:
        # Receive analysis request
        data = await websocket.receive_json()
        request = TranscriptAnalyzeRequest(**data)

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
@with_error_handling(category=ErrorCategory.KNOWLEDGE_OPERATION)
async def push_transcript_to_kb(
    transcript_id: str,
    request: TranscriptKBPushRequest,
    user: dict = Depends(get_current_user),
):
    """
    Push a transcript segment to the Knowledge Base.

    Creates a KB entry from the provided transcript segment with metadata.
    """
    try:
        kb = await get_knowledge_base()

        # Build metadata
        metadata = {
            "source_type": "transcript",
            "transcript_id": transcript_id,
            "source": f"transcript:{transcript_id}",
            "verification_status": "unverified",
            **request.metadata,
        }

        # Add segment timing if provided
        if request.segment_start is not None:
            metadata["segment_start"] = request.segment_start
        if request.segment_end is not None:
            metadata["segment_end"] = request.segment_end

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
        logger.error("KB push failed for transcript %s: %s", transcript_id, e, exc_info=True)
        return TranscriptKBPushResponse(
            success=False,
            message=f"KB push failed: {str(e)}",
        )
