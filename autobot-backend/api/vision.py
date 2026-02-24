# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Computer Vision API Endpoints
Provides REST API access to screen analysis, element detection, and visual automation

Issue #52 - Enhanced Computer Vision for GUI Automation
Author: mrveiss
"""

import logging
from typing import Dict, List, Optional

from auth_middleware import get_current_user
from computer_vision_system import ElementType, InteractionType, ScreenAnalyzer
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from type_defs.common import Metadata

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter(tags=["vision", "gui-automation"])
logger = logging.getLogger(__name__)

# Global screen analyzer instance (thread-safe)
import threading

_screen_analyzer: Optional[ScreenAnalyzer] = None
_screen_analyzer_lock = threading.Lock()


def get_screen_analyzer() -> ScreenAnalyzer:
    """Get or create screen analyzer instance (thread-safe)"""
    global _screen_analyzer
    if _screen_analyzer is None:
        with _screen_analyzer_lock:
            # Double-check after acquiring lock
            if _screen_analyzer is None:
                _screen_analyzer = ScreenAnalyzer()
                logger.info("Screen analyzer initialized")
    return _screen_analyzer


# Request/Response Models
class ScreenAnalysisRequest(BaseModel):
    """Request for screen analysis"""

    session_id: Optional[str] = Field(
        None, description="Optional session ID for context"
    )
    include_multimodal: bool = Field(True, description="Include multi-modal analysis")


class ElementDetectionRequest(BaseModel):
    """Request for element detection"""

    element_type: Optional[str] = Field(None, description="Filter by element type")
    min_confidence: float = Field(
        0.5, ge=0.0, le=1.0, description="Minimum confidence threshold"
    )
    session_id: Optional[str] = None


class OCRRequest(BaseModel):
    """Request for OCR text extraction"""

    region: Optional[Dict[str, int]] = Field(
        None,
        description=(
            "Region to extract text from {x, y, width, height}. If None,"
            "analyzes full screen."
        ),
    )
    session_id: Optional[str] = None


class ElementInteractionRequest(BaseModel):
    """Request for element interaction validation"""

    element_id: str = Field(..., description="ID of element to interact with")
    interaction_type: str = Field(..., description="Type of interaction to perform")
    parameters: Optional[Metadata] = Field(
        None, description="Additional interaction parameters"
    )


class UIElementResponse(BaseModel):
    """Response model for UI element"""

    element_id: str
    element_type: str
    bbox: Dict[str, int]
    center_point: List[int]
    confidence: float
    text_content: str
    attributes: Metadata
    possible_interactions: List[str]


class ScreenAnalysisResponse(BaseModel):
    """Response model for screen analysis"""

    timestamp: float
    ui_elements: List[UIElementResponse]
    text_regions: List[Metadata]
    dominant_colors: List[Metadata]
    layout_structure: Metadata
    automation_opportunities: List[Metadata]
    context_analysis: Metadata
    confidence_score: float
    multimodal_analysis: Optional[List[Metadata]] = None


class VisionHealthResponse(BaseModel):
    """Health check response"""

    status: str
    analyzer_ready: bool
    capabilities: List[str]
    element_types_supported: List[str]
    interaction_types_supported: List[str]


# API Endpoints
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="vision_health_check",
    error_code_prefix="VISION",
)
@router.get("/health", response_model=VisionHealthResponse)
async def vision_health_check(
    current_user: dict = Depends(get_current_user),
):
    """
    Health check for computer vision service.

    Issue #744: Requires authenticated user.
    """
    try:
        analyzer = get_screen_analyzer()
        # Verify analyzer is properly initialized
        analyzer_ready = analyzer is not None
        return VisionHealthResponse(
            status="healthy" if analyzer_ready else "degraded",
            analyzer_ready=analyzer_ready,
            capabilities=[
                "screen_capture",
                "element_detection",
                "ocr_text_extraction",
                "template_matching",
                "context_analysis",
                "multimodal_processing",
            ],
            element_types_supported=[e.value for e in ElementType],
            interaction_types_supported=[i.value for i in InteractionType],
        )
    except Exception as e:
        logger.error("Vision health check failed: %s", e)
        return VisionHealthResponse(
            status="unhealthy",
            analyzer_ready=False,
            capabilities=[],
            element_types_supported=[],
            interaction_types_supported=[],
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_screen",
    error_code_prefix="VISION",
)
@router.post("/analyze", response_model=ScreenAnalysisResponse)
async def analyze_screen(
    request: ScreenAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Perform comprehensive screen analysis.

    Returns detected UI elements, text regions, layout structure,
    and automation opportunities.

    Issue #744: Requires authenticated user.
    """
    try:
        analyzer = get_screen_analyzer()
        analyzer.enable_multimodal_analysis = request.include_multimodal

        screen_state = await analyzer.analyze_current_screen(
            session_id=request.session_id
        )

        # Convert UIElements to response format
        ui_elements_response = []
        for element in screen_state.ui_elements:
            ui_elements_response.append(
                UIElementResponse(
                    element_id=element.element_id,
                    element_type=element.element_type.value,
                    bbox=element.bbox,
                    center_point=list(element.center_point),
                    confidence=element.confidence,
                    text_content=element.text_content,
                    attributes=element.attributes,
                    possible_interactions=[
                        i.value for i in element.possible_interactions
                    ],
                )
            )

        return ScreenAnalysisResponse(
            timestamp=screen_state.timestamp,
            ui_elements=ui_elements_response,
            text_regions=screen_state.text_regions,
            dominant_colors=screen_state.dominant_colors,
            layout_structure=screen_state.layout_structure,
            automation_opportunities=screen_state.automation_opportunities,
            context_analysis=screen_state.context_analysis,
            confidence_score=screen_state.confidence_score,
            multimodal_analysis=screen_state.multimodal_analysis,
        )
    except Exception as e:
        logger.error("Screen analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Screen analysis failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_elements",
    error_code_prefix="VISION",
)
@router.post("/elements")
async def detect_elements(
    request: ElementDetectionRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Detect UI elements on the current screen.

    Optionally filter by element type and confidence threshold.

    Issue #744: Requires authenticated user.
    """
    try:
        analyzer = get_screen_analyzer()
        screen_state = await analyzer.analyze_current_screen(
            session_id=request.session_id
        )

        # Filter elements based on request
        filtered_elements = []
        for element in screen_state.ui_elements:
            if element.confidence < request.min_confidence:
                continue
            if (
                request.element_type
                and element.element_type.value != request.element_type
            ):
                continue

            filtered_elements.append(
                {
                    "element_id": element.element_id,
                    "element_type": element.element_type.value,
                    "bbox": element.bbox,
                    "center_point": list(element.center_point),
                    "confidence": element.confidence,
                    "text_content": element.text_content,
                    "possible_interactions": [
                        i.value for i in element.possible_interactions
                    ],
                }
            )

        return {
            "total_detected": len(screen_state.ui_elements),
            "filtered_count": len(filtered_elements),
            "elements": filtered_elements,
            "filter_applied": {
                "element_type": request.element_type,
                "min_confidence": request.min_confidence,
            },
        }
    except Exception as e:
        logger.error("Element detection failed: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Element detection failed: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_text_ocr",
    error_code_prefix="VISION",
)
@router.post("/ocr")
async def extract_text_ocr(
    request: OCRRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Extract text from screen using OCR.

    Can extract from full screen or specified region.

    Issue #744: Requires authenticated user.
    """
    try:
        analyzer = get_screen_analyzer()
        screen_state = await analyzer.analyze_current_screen(
            session_id=request.session_id
        )

        # If region specified, filter text regions
        if request.region:
            # Filter text regions within specified bounds
            filtered_text = []
            for text_region in screen_state.text_regions:
                region_bbox = text_region.get("bbox", {})
                if (
                    region_bbox.get("x", 0) >= request.region.get("x", 0)
                    and region_bbox.get("y", 0) >= request.region.get("y", 0)
                    and region_bbox.get("x", 0) + region_bbox.get("width", 0)
                    <= request.region.get("x", 0) + request.region.get("width", 10000)
                    and region_bbox.get("y", 0) + region_bbox.get("height", 0)
                    <= request.region.get("y", 0) + request.region.get("height", 10000)
                ):
                    filtered_text.append(text_region)

            return {
                "region_specified": True,
                "region": request.region,
                "text_regions": filtered_text,
                "total_text_regions": len(filtered_text),
            }
        else:
            return {
                "region_specified": False,
                "text_regions": screen_state.text_regions,
                "total_text_regions": len(screen_state.text_regions),
            }
    except Exception as e:
        logger.error("OCR extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"OCR extraction failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_automation_opportunities",
    error_code_prefix="VISION",
)
@router.get("/automation-opportunities")
async def get_automation_opportunities(
    session_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Identify automation opportunities on the current screen.

    Returns interactive elements and suggested automation actions.

    Issue #744: Requires authenticated user.
    """
    try:
        analyzer = get_screen_analyzer()
        screen_state = await analyzer.analyze_current_screen(session_id=session_id)

        return {
            "opportunities": screen_state.automation_opportunities,
            "total_opportunities": len(screen_state.automation_opportunities),
            "context": screen_state.context_analysis,
            "confidence": screen_state.confidence_score,
        }
    except Exception as e:
        logger.error("Failed to identify automation opportunities: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to identify opportunities: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_element_types",
    error_code_prefix="VISION",
)
@router.get("/element-types")
async def get_element_types(
    current_user: dict = Depends(get_current_user),
):
    """
    Get list of supported UI element types.

    Issue #744: Requires authenticated user.
    """
    return {
        "element_types": [
            {
                "value": e.value,
                "name": e.name,
                "description": f"UI element of type {e.value}",
            }
            for e in ElementType
        ],
        "total_types": len(ElementType),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_interaction_types",
    error_code_prefix="VISION",
)
@router.get("/interaction-types")
async def get_interaction_types(
    current_user: dict = Depends(get_current_user),
):
    """
    Get list of supported interaction types.

    Issue #744: Requires authenticated user.
    """
    return {
        "interaction_types": [
            {
                "value": i.value,
                "name": i.name,
                "description": f"Interaction type: {i.value}",
            }
            for i in InteractionType
        ],
        "total_types": len(InteractionType),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_layout_analysis",
    error_code_prefix="VISION",
)
@router.get("/layout")
async def get_layout_analysis(
    session_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze the screen layout structure.

    Returns hierarchical layout information and structural patterns.

    Issue #744: Requires authenticated user.
    """
    try:
        analyzer = get_screen_analyzer()
        screen_state = await analyzer.analyze_current_screen(session_id=session_id)

        return {
            "layout_structure": screen_state.layout_structure,
            "dominant_colors": screen_state.dominant_colors,
            "timestamp": screen_state.timestamp,
        }
    except Exception as e:
        logger.error("Layout analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Layout analysis failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="vision_service_status",
    error_code_prefix="VISION",
)
@router.get("/status")
async def get_vision_status(
    current_user: dict = Depends(get_current_user),
):
    """
    Get overall vision service status.

    Issue #744: Requires authenticated user.
    """
    try:
        analyzer = get_screen_analyzer()
        return {
            "service": "computer_vision",
            "status": "operational",
            "features": {
                "screen_analysis": True,
                "element_detection": True,
                "ocr_extraction": True,
                "template_matching": True,
                "multimodal_processing": analyzer.enable_multimodal_analysis,
            },
            "supported_element_types": len(ElementType),
            "supported_interaction_types": len(InteractionType),
        }
    except Exception as e:
        logger.error("Failed to get vision status: %s", e)
        return {
            "service": "computer_vision",
            "status": "error",
            "error": str(e),
        }
