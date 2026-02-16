#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multi-Modal AI Processing API Endpoints
Provides REST API access to GPU-accelerated multi-modal AI capabilities
"""

import logging
import time
import uuid
from typing import Dict, List, Optional, Union

import torch
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.type_defs.common import Metadata
from ai_hardware_accelerator import HardwareDevice, accelerated_embedding_generation
from auth_middleware import get_current_user
from backend.constants.threshold_constants import QueryDefaults
from multimodal_processor import (
    ModalityType,
    MultiModalInput,
    ProcessingIntent,
    unified_processor,
)

# Import AutoBot multi-modal components
from npu_semantic_search import get_npu_search_engine
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(tags=["multimodal"])


# Pydantic models for request/response
class CrossModalSearchRequest(BaseModel):
    query: Union[str, bytes]
    query_modality: str = Field(..., description="Type of query: text, image, audio")
    target_modalities: Optional[List[str]] = Field(
        default=None, description="Target modalities to search"
    )
    limit: int = Field(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=100,
        description="Maximum results per modality",
    )
    similarity_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class TextProcessingRequest(BaseModel):
    text: str = Field(..., description="Text content to process")
    intent: str = Field(default="analysis", description="Processing intent")
    metadata: Optional[Metadata] = Field(default=None)


class EmbeddingRequest(BaseModel):
    content: Union[str, bytes]
    modality: str = Field(..., description="Content modality: text, image, audio")
    preferred_device: Optional[str] = Field(
        default=None, description="Preferred processing device"
    )


class MultiModalResponse(BaseModel):
    success: bool
    result_id: str
    modality: str
    processing_time: float
    confidence: float
    result_data: Metadata
    device_used: Optional[str] = None
    error_message: Optional[str] = None


class CrossModalSearchResponse(BaseModel):
    query: str
    query_modality: str
    results: Dict[str, List[Metadata]]
    total_found: int
    processing_time: float


# Helper functions
def _get_processing_intent(intent_str: str) -> ProcessingIntent:
    """Convert string intent to ProcessingIntent enum."""
    intent_mapping = {
        "analysis": ProcessingIntent.SCREEN_ANALYSIS,
        "visual_qa": ProcessingIntent.VISUAL_QA,
        "voice_command": ProcessingIntent.VOICE_COMMAND,
        "automation": ProcessingIntent.AUTOMATION_TASK,
        "content_generation": ProcessingIntent.CONTENT_GENERATION,
        "decision_making": ProcessingIntent.DECISION_MAKING,
    }
    return intent_mapping.get(intent_str.lower(), ProcessingIntent.SCREEN_ANALYSIS)


def _get_modality_type(modality_str: str) -> ModalityType:
    """Convert string modality to ModalityType enum."""
    modality_mapping = {
        "text": ModalityType.TEXT,
        "image": ModalityType.IMAGE,
        "audio": ModalityType.AUDIO,
        "video": ModalityType.VIDEO,
        "combined": ModalityType.COMBINED,
    }
    return modality_mapping.get(modality_str.lower(), ModalityType.TEXT)


# API Endpoints


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="process_image",
    error_code_prefix="MULTIMODAL",
)
@router.post("/process/image", response_model=MultiModalResponse)
async def process_image(
    file: UploadFile = File(...),
    intent: str = Form(default="analysis"),
    question: Optional[str] = Form(default=None),
    current_user: dict = Depends(get_current_user),
):
    """
    Process uploaded image with GPU-accelerated vision models.

    Issue #744: Requires authenticated user.
    """
    start_time = time.time()

    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        # Read image data
        image_data = await file.read()
        if len(image_data) == 0:
            raise HTTPException(status_code=400, detail="Empty image file")

        # Create multi-modal input
        input_id = f"image_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        metadata = {"filename": file.filename, "content_type": file.content_type}
        if question:
            metadata["question"] = question

        modal_input = MultiModalInput(
            input_id=input_id,
            modality_type=ModalityType.IMAGE,
            intent=_get_processing_intent(intent),
            data=image_data,
            metadata=metadata,
        )

        # Process with unified processor
        result = await unified_processor.process(modal_input)

        processing_time = time.time() - start_time

        return MultiModalResponse(
            success=result.success,
            result_id=result.result_id,
            modality=result.modality_type.value,
            processing_time=processing_time,
            confidence=result.confidence,
            result_data=result.result_data or {},
            device_used=result.metadata.get("device_used") if result.metadata else None,
            error_message=result.error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Image processing failed: %s", e)
        processing_time = time.time() - start_time
        return MultiModalResponse(
            success=False,
            result_id=f"error_{int(time.time())}",
            modality="image",
            processing_time=processing_time,
            confidence=0.0,
            result_data={},
            error_message=str(e),
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="process_audio",
    error_code_prefix="MULTIMODAL",
)
@router.post("/process/audio", response_model=MultiModalResponse)
async def process_audio(
    file: UploadFile = File(...),
    intent: str = Form(default="voice_command"),
    current_user: dict = Depends(get_current_user),
):
    """
    Process uploaded audio with GPU-accelerated speech models.

    Issue #744: Requires authenticated user.
    """
    start_time = time.time()

    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="File must be an audio file")

        # Read audio data
        audio_data = await file.read()
        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        # Create multi-modal input
        input_id = f"audio_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        metadata = {"filename": file.filename, "content_type": file.content_type}

        modal_input = MultiModalInput(
            input_id=input_id,
            modality_type=ModalityType.AUDIO,
            intent=_get_processing_intent(intent),
            data=audio_data,
            metadata=metadata,
        )

        # Process with unified processor
        result = await unified_processor.process(modal_input)

        processing_time = time.time() - start_time

        return MultiModalResponse(
            success=result.success,
            result_id=result.result_id,
            modality=result.modality_type.value,
            processing_time=processing_time,
            confidence=result.confidence,
            result_data=result.result_data or {},
            device_used=result.metadata.get("device_used") if result.metadata else None,
            error_message=result.error_message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Audio processing failed: %s", e)
        processing_time = time.time() - start_time
        return MultiModalResponse(
            success=False,
            result_id=f"error_{int(time.time())}",
            modality="audio",
            processing_time=processing_time,
            confidence=0.0,
            result_data={},
            error_message=str(e),
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="process_text",
    error_code_prefix="MULTIMODAL",
)
@router.post("/process/text", response_model=MultiModalResponse)
async def process_text(
    request: TextProcessingRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Process text with contextual understanding.

    Issue #744: Requires authenticated user.
    """
    start_time = time.time()

    try:
        # Create multi-modal input
        input_id = f"text_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        modal_input = MultiModalInput(
            input_id=input_id,
            modality_type=ModalityType.TEXT,
            intent=_get_processing_intent(request.intent),
            data=request.text,
            metadata=request.metadata or {},
        )

        # Process with unified processor
        result = await unified_processor.process(modal_input)

        processing_time = time.time() - start_time

        return MultiModalResponse(
            success=result.success,
            result_id=result.result_id,
            modality=result.modality_type.value,
            processing_time=processing_time,
            confidence=result.confidence,
            result_data=result.result_data or {},
            device_used=result.metadata.get("device_used") if result.metadata else None,
            error_message=result.error_message,
        )

    except Exception as e:
        logger.error("Text processing failed: %s", e)
        processing_time = time.time() - start_time
        return MultiModalResponse(
            success=False,
            result_id=f"error_{int(time.time())}",
            modality="text",
            processing_time=processing_time,
            confidence=0.0,
            result_data={},
            error_message=str(e),
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_embedding",
    error_code_prefix="MULTIMODAL",
)
@router.post("/embeddings/generate")
async def generate_embedding(
    request: EmbeddingRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Generate embeddings for any modality.

    Issue #744: Requires authenticated user.
    """
    start_time = time.time()

    try:
        # Map device preference
        device_preference = None
        if request.preferred_device:
            device_mapping = {
                "gpu": HardwareDevice.GPU,
                "npu": HardwareDevice.NPU,
                "cpu": HardwareDevice.CPU,
            }
            device_preference = device_mapping.get(request.preferred_device.lower())

        # Generate embedding
        embedding = await accelerated_embedding_generation(
            content=request.content,
            modality=request.modality,
            preferred_device=device_preference,
        )

        processing_time = time.time() - start_time

        return {
            "success": True,
            "embedding": embedding.tolist(),
            "dimension": len(embedding),
            "modality": request.modality,
            "processing_time": processing_time,
            "device_used": str(device_preference) if device_preference else "auto",
        }

    except Exception as e:
        logger.error("Embedding generation failed: %s", e)
        processing_time = time.time() - start_time
        return {"success": False, "error": str(e), "processing_time": processing_time}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cross_modal_search",
    error_code_prefix="MULTIMODAL",
)
@router.post("/search/cross-modal", response_model=CrossModalSearchResponse)
async def cross_modal_search(
    request: CrossModalSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Perform cross-modal similarity search.

    Issue #744: Requires authenticated user.
    """
    start_time = time.time()

    try:
        # Get NPU search engine
        search_engine = await get_npu_search_engine()

        # Perform cross-modal search
        results = await search_engine.cross_modal_search(
            query=request.query,
            query_modality=request.query_modality,
            target_modalities=request.target_modalities,
            limit=request.limit,
            similarity_threshold=request.similarity_threshold,
        )

        # Convert results to serializable format
        serialized_results = {}
        total_found = 0

        for modality, modality_results in results.items():
            serialized_modality_results = []
            for result in modality_results:
                serialized_modality_results.append(
                    {
                        "content": result.content,
                        "modality": result.modality,
                        "metadata": result.metadata,
                        "score": result.score,
                        "doc_id": result.doc_id,
                        "source_modality": result.source_modality,
                        "fusion_confidence": result.fusion_confidence,
                    }
                )
            serialized_results[modality] = serialized_modality_results
            total_found += len(serialized_modality_results)

        processing_time = time.time() - start_time

        return CrossModalSearchResponse(
            query=str(request.query),
            query_modality=request.query_modality,
            results=serialized_results,
            total_found=total_found,
            processing_time=processing_time,
        )

    except Exception as e:
        logger.error("Cross-modal search failed: %s", e)
        processing_time = time.time() - start_time
        return CrossModalSearchResponse(
            query=str(request.query),
            query_modality=request.query_modality,
            results={},
            total_found=0,
            processing_time=processing_time,
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_multimodal_stats",
    error_code_prefix="MULTIMODAL",
)
@router.get("/stats")
async def get_multimodal_stats(
    current_user: dict = Depends(get_current_user),
):
    """
    Get multi-modal processing statistics and system status.

    Issue #744: Requires authenticated user.
    """
    try:
        # Get unified processor stats
        processor_stats = unified_processor.get_stats()

        # Get GPU status
        gpu_available = torch.cuda.is_available()
        gpu_stats = {}
        if gpu_available:
            gpu_stats = {
                "gpu_memory_allocated_mb": torch.cuda.memory_allocated() / 1024 / 1024,
                "gpu_memory_reserved_mb": torch.cuda.memory_reserved() / 1024 / 1024,
                "gpu_device_count": torch.cuda.device_count(),
                "gpu_device_name": (
                    torch.cuda.get_device_name(0)
                    if torch.cuda.device_count() > 0
                    else None
                ),
            }

        # Get search engine status
        search_engine_status = {}
        try:
            search_engine = await get_npu_search_engine()
            search_engine_status = await search_engine.get_health_status()
        except Exception as e:
            search_engine_status = {"error": str(e), "status": "unavailable"}

        # Issue #675: Extract model availability for top-level access
        model_availability = processor_stats.get("model_availability", {})
        vision_available = model_availability.get("vision", {}).get(
            "clip_available", False
        ) or model_availability.get("vision", {}).get("blip_available", False)
        voice_available = model_availability.get("voice", {}).get(
            "whisper_available", False
        )

        return {
            "success": True,
            "timestamp": time.time(),
            "processor_stats": processor_stats,
            "gpu_available": gpu_available,
            "gpu_stats": gpu_stats,
            "search_engine_status": search_engine_status,
            # Issue #675: Add top-level model availability flags for easy frontend access
            "vision_models_available": vision_available,
            "audio_models_available": voice_available,
            "model_availability": model_availability,
            "system_status": "healthy",
        }

    except Exception as e:
        logger.error("Failed to get multimodal stats: %s", e)
        return {
            "success": False,
            "error": str(e),
            "timestamp": time.time(),
            # Issue #675: Include model unavailable status in error response
            "vision_models_available": False,
            "audio_models_available": False,
            "system_status": "error",
        }


def _create_text_input(text: str, intent: str) -> MultiModalInput:
    """Create MultiModalInput for text data (Issue #398: extracted)."""
    return MultiModalInput(
        input_id=f"text_{int(time.time() * 1000)}",
        modality_type=ModalityType.TEXT,
        intent=_get_processing_intent(intent),
        data=text,
    )


async def _create_image_input(image_file: UploadFile, intent: str) -> MultiModalInput:
    """Create MultiModalInput for image file (Issue #398: extracted)."""
    image_data = await image_file.read()
    return MultiModalInput(
        input_id=f"image_{int(time.time() * 1000)}",
        modality_type=ModalityType.IMAGE,
        intent=_get_processing_intent(intent),
        data=image_data,
        metadata={"filename": image_file.filename},
    )


async def _create_audio_input(audio_file: UploadFile, intent: str) -> MultiModalInput:
    """Create MultiModalInput for audio file (Issue #398: extracted)."""
    audio_data = await audio_file.read()
    return MultiModalInput(
        input_id=f"audio_{int(time.time() * 1000)}",
        modality_type=ModalityType.AUDIO,
        intent=_get_processing_intent(intent),
        data=audio_data,
        metadata={"filename": audio_file.filename},
    )


async def _collect_modal_inputs(
    text: Optional[str],
    image_file: Optional[UploadFile],
    audio_file: Optional[UploadFile],
    intent: str,
) -> List[MultiModalInput]:
    """Collect all modal inputs from form data (Issue #398: extracted)."""
    inputs = []

    if text:
        inputs.append(_create_text_input(text, intent))

    if image_file:
        inputs.append(await _create_image_input(image_file, intent))

    if audio_file:
        inputs.append(await _create_audio_input(audio_file, intent))

    return inputs


def _create_combined_input(
    text: Optional[str],
    image_file: Optional[UploadFile],
    audio_file: Optional[UploadFile],
    intent: str,
) -> MultiModalInput:
    """Create combined MultiModalInput for fusion (Issue #398: extracted)."""
    return MultiModalInput(
        input_id=f"combined_{int(time.time() * 1000)}",
        modality_type=ModalityType.COMBINED,
        intent=_get_processing_intent(intent),
        data="",  # Not used for combined
        metadata={
            "image": image_file.filename if image_file else None,
            "audio": audio_file.filename if audio_file else None,
            "text_preview": text[:100] if text else None,
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="combine_multimodal_inputs",
    error_code_prefix="MULTIMODAL",
)
@router.post("/fusion/combine")
async def combine_multimodal_inputs(
    text: Optional[str] = Form(default=None),
    image_file: Optional[UploadFile] = File(default=None),
    audio_file: Optional[UploadFile] = File(default=None),
    intent: str = Form(default="decision_making"),
    current_user: dict = Depends(get_current_user),
):
    """
    Combine multiple modalities using attention-based fusion (Issue #398: refactored).

    Issue #744: Requires authenticated user.
    """
    start_time = time.time()

    try:
        # Collect all modal inputs using helper
        inputs = await _collect_modal_inputs(text, image_file, audio_file, intent)

        if not inputs:
            raise HTTPException(
                status_code=400, detail="At least one input modality required"
            )

        # Process all inputs
        results = [
            await unified_processor.process(modal_input) for modal_input in inputs
        ]

        # Create combined input and process fusion
        combined_input = _create_combined_input(text, image_file, audio_file, intent)
        fusion_result = await unified_processor._process_combined(combined_input)

        processing_time = time.time() - start_time

        return {
            "success": fusion_result.success,
            "fusion_result": fusion_result.result_data,
            "individual_results": [
                {
                    "modality": r.modality_type.value,
                    "confidence": r.confidence,
                    "data": r.result_data,
                }
                for r in results
            ],
            "processing_time": processing_time,
            "fusion_confidence": fusion_result.confidence,
            "modalities_combined": len(inputs),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Multi-modal fusion failed: %s", e)
        processing_time = time.time() - start_time
        return {"success": False, "error": str(e), "processing_time": processing_time}


# Performance monitoring endpoints
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_stats",
    error_code_prefix="MULTIMODAL",
)
@router.get("/performance/stats")
async def get_performance_stats(
    current_user: dict = Depends(get_current_user),
):
    """
    Get comprehensive performance statistics for multi-modal processing.

    Issue #744: Requires authenticated user.
    """
    try:
        # Get performance metrics from monitor
        performance_metrics = (
            await unified_processor.performance_monitor.monitor_processing_performance()
        )

        # Get processor-specific stats
        processor_stats = unified_processor.get_stats()

        # Combine all performance data
        return {
            "success": True,
            "timestamp": time.time(),
            "performance_metrics": performance_metrics,
            "processor_stats": processor_stats,
            "optimization_status": {
                "auto_optimization_enabled": True,
                "mixed_precision_enabled": unified_processor.use_amp,
                "device": str(unified_processor.device),
                "batch_sizes": unified_processor.performance_monitor.batch_sizes,
            },
        }

    except Exception as e:
        logger.error("Failed to get performance stats: %s", e)
        return {"success": False, "error": str(e), "timestamp": time.time()}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="optimize_performance",
    error_code_prefix="MULTIMODAL",
)
@router.post("/performance/optimize")
async def optimize_performance(
    current_user: dict = Depends(get_current_user),
):
    """
    Manually trigger performance optimization.

    Issue #744: Requires authenticated user.
    """
    try:
        optimization_result = (
            await unified_processor.performance_monitor.optimize_gpu_memory()
        )

        return {
            "success": True,
            "timestamp": time.time(),
            "optimization_result": optimization_result,
            "message": "Performance optimization completed",
        }

    except Exception as e:
        logger.error("Performance optimization failed: %s", e)
        return {"success": False, "error": str(e), "timestamp": time.time()}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_summary",
    error_code_prefix="MULTIMODAL",
)
@router.get("/performance/summary")
async def get_performance_summary(
    current_user: dict = Depends(get_current_user),
):
    """
    Get a concise performance summary.

    Issue #744: Requires authenticated user.
    """
    try:
        summary = unified_processor.performance_monitor.get_performance_summary()

        return {"success": True, "timestamp": time.time(), "summary": summary}

    except Exception as e:
        logger.error("Failed to get performance summary: %s", e)
        return {"success": False, "error": str(e), "timestamp": time.time()}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_batch_size",
    error_code_prefix="MULTIMODAL",
)
@router.post("/performance/batch-size")
async def update_batch_size(
    modality: str,
    batch_size: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Update optimal batch size for a specific modality.

    Issue #744: Requires authenticated user.
    """
    try:
        if modality not in unified_processor.performance_monitor.batch_sizes:
            return {
                "success": False,
                "error": f"Unknown modality: {modality}",
                "available_modalities": list(
                    unified_processor.performance_monitor.batch_sizes.keys()
                ),
            }

        if batch_size < 1 or batch_size > 128:
            return {"success": False, "error": "Batch size must be between 1 and 128"}

        old_size = unified_processor.performance_monitor.batch_sizes[modality]
        unified_processor.performance_monitor.batch_sizes[modality] = batch_size

        return {
            "success": True,
            "timestamp": time.time(),
            "modality": modality,
            "old_batch_size": old_size,
            "new_batch_size": batch_size,
            "message": f"Updated {modality} batch size from {old_size} to {batch_size}",
        }

    except Exception as e:
        logger.error("Failed to update batch size: %s", e)
        return {"success": False, "error": str(e), "timestamp": time.time()}


# Health check endpoint
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="MULTIMODAL",
)
@router.get("/health")
async def health_check(
    current_user: dict = Depends(get_current_user),
):
    """
    Health check for multi-modal API.

    Issue #744: Requires authenticated user.
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "gpu_available": torch.cuda.is_available(),
        "processor_ready": unified_processor is not None,
        "performance_monitoring": unified_processor.performance_monitor is not None,
        "mixed_precision_enabled": getattr(unified_processor, "use_amp", False),
    }
