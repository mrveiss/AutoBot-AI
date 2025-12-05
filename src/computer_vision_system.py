# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Computer Vision System for AutoBot
Advanced screen understanding and visual automation capabilities
"""

import asyncio
import base64
import io
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from src.desktop_streaming_manager import desktop_streaming
from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority

# Import correct classes for multimodal processing
from src.task_execution_tracker import task_tracker
from src.unified_multimodal_processor import (
    ModalityType,
    MultiModalInput,
    ProcessingIntent,
    unified_processor,
)

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for form submission button keywords (Issue #326)
FORM_SUBMISSION_KEYWORDS = {"submit", "save", "ok", "apply", "next"}


class ElementType(Enum):
    """Types of UI elements that can be detected"""

    BUTTON = "button"
    INPUT_FIELD = "input_field"
    CHECKBOX = "checkbox"
    RADIO_BUTTON = "radio_button"
    DROPDOWN = "dropdown"
    LINK = "link"
    IMAGE = "image"
    TEXT = "text"
    MENU = "menu"
    DIALOG = "dialog"
    WINDOW = "window"
    ICON = "icon"
    TOOLBAR = "toolbar"
    STATUS_BAR = "status_bar"
    UNKNOWN = "unknown"


class InteractionType(Enum):
    """Types of interactions possible with UI elements"""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    DRAG = "drag"
    TYPE_TEXT = "type_text"
    SELECT = "select"
    SCROLL = "scroll"
    HOVER = "hover"


@dataclass
class UIElement:
    """Detected UI element with properties and interaction capabilities"""

    element_id: str
    element_type: ElementType
    bbox: Dict[str, int]  # {"x": int, "y": int, "width": int, "height": int}
    center_point: Tuple[int, int]
    confidence: float
    text_content: str
    attributes: Dict[str, Any]
    possible_interactions: List[InteractionType]
    screenshot_region: Optional[np.ndarray] = None
    ocr_data: Optional[Dict[str, Any]] = None


@dataclass
class ScreenState:
    """Complete screen state analysis"""

    timestamp: float
    screenshot: np.ndarray
    ui_elements: List[UIElement]
    text_regions: List[Dict[str, Any]]
    dominant_colors: List[Dict[str, Any]]
    layout_structure: Dict[str, Any]
    automation_opportunities: List[Dict[str, Any]]
    context_analysis: Dict[str, Any]
    confidence_score: float
    multimodal_analysis: Optional[List[Dict[str, Any]]] = (
        None  # New field for multi-modal processing results
    )


class ScreenAnalyzer:
    """Advanced screen analysis and understanding system"""

    def __init__(self):
        self.template_matcher = TemplateMatchingEngine()
        self.element_classifier = ElementClassifier()
        self.context_analyzer = ContextAnalyzer()

        # Multi-modal processor integration
        self.multimodal_processor = unified_processor
        self.enable_multimodal_analysis = True

        # Cache recent screenshots for comparison
        self.screenshot_cache: List[Tuple[float, np.ndarray]] = []
        self.cache_size = 5

        logger.info("Screen Analyzer initialized with multi-modal processing")

    async def analyze_current_screen(
        self, session_id: Optional[str] = None, context_audio: Optional[bytes] = None
    ) -> ScreenState:
        """Analyze the current screen state comprehensively"""

        async with task_tracker.track_task(
            "Screen Analysis",
            "Comprehensive analysis of current screen state",
            agent_type="computer_vision",
            priority=TaskPriority.HIGH,
            inputs={"session_id": session_id},
        ) as task_context:
            try:
                # Capture screenshot
                screenshot = await self._capture_screenshot(session_id)
                if screenshot is None:
                    raise RuntimeError("Failed to capture screenshot")

                # Process with enhanced multi-modal processor
                modal_inputs = []

                # Always process screenshot with unified processor
                image_input = MultiModalInput(
                    input_id=f"screen_vision_{int(time.time())}",
                    modality_type=ModalityType.IMAGE,
                    intent=ProcessingIntent.SCREEN_ANALYSIS,
                    data=screenshot,
                    metadata={"session_id": session_id},
                )
                modal_inputs.append(image_input)

                # Add audio context if provided (e.g., voice commands about screen)
                if context_audio and self.enable_multimodal_analysis:
                    audio_input = MultiModalInput(
                        input_id=f"screen_audio_{int(time.time())}",
                        modality_type=ModalityType.AUDIO,
                        intent=ProcessingIntent.VOICE_COMMAND,
                        data=context_audio,
                        metadata={
                            "session_id": session_id,
                            "context": "screen_analysis",
                        },
                    )
                    modal_inputs.append(audio_input)

                # Process all modalities
                processing_results = []
                for modal_input in modal_inputs:
                    result = await self.multimodal_processor.process(modal_input)
                    processing_results.append(result)

                # Combine results if multi-modal
                primary_result = processing_results[0]  # Image processing result
                if len(processing_results) > 1:
                    combined_input = MultiModalInput(
                        input_id=f"screen_combined_{int(time.time())}",
                        modality_type=ModalityType.COMBINED,
                        intent=ProcessingIntent.SCREEN_ANALYSIS,
                        data="",  # Not used for combined
                        metadata={
                            "image_result": processing_results[0].result_data,
                            "audio_result": processing_results[1].result_data,
                            "session_id": session_id,
                        },
                    )
                    combined_result = await self.multimodal_processor.process(
                        combined_input
                    )
                    # Use combined result as primary if successful
                    if combined_result.success:
                        primary_result = combined_result

                # Extract UI elements with advanced classification
                ui_elements = await self._detect_and_classify_elements(
                    screenshot, primary_result.result_data or {}
                )

                # Enhanced context analysis with multi-modal understanding
                context_analysis = await self.context_analyzer.analyze_context(
                    screenshot, ui_elements
                )

                # Add multi-modal context if available
                if len(processing_results) > 1 and processing_results[1].result_data:
                    voice_intent = processing_results[1].result_data.get(
                        "transcribed_text", ""
                    )
                    context_analysis["multimodal_understanding"] = (
                        primary_result.result_data
                    )
                    context_analysis["cross_modal_confidence"] = (
                        primary_result.confidence
                    )
                    context_analysis["voice_intent"] = voice_intent

                automation_opportunities = await self._find_automation_opportunities(
                    ui_elements, context_analysis
                )

                # Create comprehensive screen state
                screen_state = ScreenState(
                    timestamp=time.time(),
                    screenshot=screenshot,
                    ui_elements=ui_elements,
                    text_regions=(
                        primary_result.result_data.get("text_content", {}).get(
                            "text_regions", []
                        )
                        if primary_result.result_data
                        else []
                    ),
                    dominant_colors=(
                        primary_result.result_data.get("dominant_colors", [])
                        if primary_result.result_data
                        else []
                    ),
                    layout_structure=(
                        primary_result.result_data.get("layout_analysis", {})
                        if primary_result.result_data
                        else {}
                    ),
                    automation_opportunities=automation_opportunities,
                    context_analysis=context_analysis,
                    confidence_score=max(r.confidence for r in processing_results),
                    multimodal_analysis=[
                        {
                            "modality": (
                                r.modality_type.value
                                if hasattr(r.modality_type, "value")
                                else str(r.modality_type)
                            ),
                            "confidence": r.confidence,
                            "data": r.result_data,
                            "success": r.success,
                            "processing_time": getattr(r, "processing_time", 0.0),
                        }
                        for r in processing_results
                    ],
                )

                # Update screenshot cache
                self._update_screenshot_cache(screenshot)

                task_context.set_outputs(
                    {
                        "elements_detected": len(ui_elements),
                        "text_regions": len(screen_state.text_regions),
                        "automation_opportunities": len(automation_opportunities),
                        "confidence_score": screen_state.confidence_score,
                    }
                )

                logger.info(
                    f"Screen analysis completed: {len(ui_elements)} elements, confidence {screen_state.confidence_score:.2f}"
                )
                return screen_state

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Screen analysis failed: {e}")
                raise

    async def _capture_screenshot(
        self, session_id: Optional[str] = None
    ) -> Optional[np.ndarray]:
        """Capture screenshot from desktop streaming or system"""
        try:
            if session_id:
                # Use desktop streaming to get screenshot
                session_info = desktop_streaming.vnc_manager.get_session_info(
                    session_id
                )
                if session_info:
                    screenshot_base64 = await desktop_streaming._get_session_screenshot(
                        session_id
                    )
                    if screenshot_base64:
                        screenshot_bytes = base64.b64decode(screenshot_base64)
                        image = Image.open(io.BytesIO(screenshot_bytes))
                        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

            # Fallback to system screenshot using X11
            try:
                proc = await asyncio.create_subprocess_exec(
                    "import", "-window", "root", "png:-",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                    if proc.returncode == 0:
                        image = Image.open(io.BytesIO(stdout))
                        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    logger.warning("X11 screenshot command timed out")
            except Exception as e:
                logger.warning(f"X11 screenshot failed: {e}")

            # Generate test pattern if no screenshot available
            logger.warning("Using test pattern instead of real screenshot")
            test_image = np.zeros((600, 800, 3), dtype=np.uint8)
            cv2.putText(
                test_image,
                "Test Screenshot",
                (250, 300),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 255),
                2,
            )
            return test_image

        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return None

    async def _detect_and_classify_elements(
        self, screenshot: np.ndarray, processing_results: Dict[str, Any]
    ) -> List[UIElement]:
        """Detect and classify UI elements using advanced computer vision"""
        ui_elements = []

        try:
            # Get basic UI elements from multi-modal processor
            detected_elements = processing_results.get("ui_elements", [])

            # Enhance with advanced classification
            for i, element in enumerate(detected_elements):
                bbox = element.get("bbox", {})
                if not bbox:
                    continue

                # Extract element region
                x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
                element_region = (
                    screenshot[y : y + h, x : x + w]
                    if (y + h <= screenshot.shape[0] and x + w <= screenshot.shape[1])
                    else None
                )

                # Classify element type
                element_type = await self.element_classifier.classify_element(
                    element_region, bbox
                )

                # Determine possible interactions
                interactions = self._determine_interactions(
                    element_type, element_region
                )

                # Extract text from element
                text_content = await self._extract_element_text(element_region)

                # Create UI element
                ui_element = UIElement(
                    element_id=f"element_{i}_{int(time.time())}",
                    element_type=element_type,
                    bbox=bbox,
                    center_point=(x + w // 2, y + h // 2),
                    confidence=element.get("confidence", 0.7),
                    text_content=text_content,
                    attributes={
                        "area": element.get("area", w * h),
                        "aspect_ratio": element.get(
                            "aspect_ratio", w / h if h > 0 else 1.0
                        ),
                        "perimeter": element.get("perimeter", 2 * (w + h)),
                    },
                    possible_interactions=interactions,
                    screenshot_region=element_region,
                    ocr_data=None,
                )

                ui_elements.append(ui_element)

            # Add template matching results
            template_matches = await self.template_matcher.find_common_elements(
                screenshot
            )
            for match in template_matches:
                ui_element = UIElement(
                    element_id=f"template_{match['template_name']}_{int(time.time())}",
                    element_type=ElementType(match.get("element_type", "unknown")),
                    bbox=match["bbox"],
                    center_point=match["center"],
                    confidence=match["confidence"],
                    text_content=match.get("text", ""),
                    attributes=match.get("attributes", {}),
                    possible_interactions=[InteractionType.CLICK],
                    screenshot_region=None,
                )
                ui_elements.append(ui_element)

            return ui_elements

        except Exception as e:
            logger.error(f"Element detection and classification failed: {e}")
            return []

    def _determine_interactions(
        self, element_type: ElementType, element_region: Optional[np.ndarray]
    ) -> List[InteractionType]:
        """Determine possible interactions based on element type"""
        interaction_map = {
            ElementType.BUTTON: [InteractionType.CLICK, InteractionType.HOVER],
            ElementType.INPUT_FIELD: [
                InteractionType.CLICK,
                InteractionType.TYPE_TEXT,
                InteractionType.SELECT,
            ],
            ElementType.CHECKBOX: [InteractionType.CLICK],
            ElementType.RADIO_BUTTON: [InteractionType.CLICK],
            ElementType.DROPDOWN: [InteractionType.CLICK, InteractionType.SELECT],
            ElementType.LINK: [
                InteractionType.CLICK,
                InteractionType.RIGHT_CLICK,
                InteractionType.HOVER,
            ],
            ElementType.IMAGE: [InteractionType.CLICK, InteractionType.RIGHT_CLICK],
            ElementType.MENU: [InteractionType.CLICK, InteractionType.HOVER],
            ElementType.WINDOW: [InteractionType.DRAG],
            ElementType.UNKNOWN: [InteractionType.CLICK],
        }

        return interaction_map.get(element_type, [InteractionType.CLICK])

    async def _extract_element_text(self, element_region: Optional[np.ndarray]) -> str:
        """Extract text from element region using OCR"""
        if element_region is None or element_region.size == 0:
            return ""

        try:
            # Use pytesseract if available
            import pytesseract

            text = pytesseract.image_to_string(element_region).strip()
            return text
        except ImportError:
            return ""
        except Exception as e:
            logger.debug(f"Text extraction failed: {e}")
            return ""

    async def _find_automation_opportunities(
        self, ui_elements: List[UIElement], context_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find automation opportunities based on detected elements and context"""
        opportunities = []

        for element in ui_elements:
            # Check for common automation patterns
            if element.element_type == ElementType.BUTTON:
                if any(
                    word in element.text_content.lower()
                    for word in FORM_SUBMISSION_KEYWORDS
                ):
                    opportunities.append(
                        {
                            "type": "form_submission",
                            "element_id": element.element_id,
                            "action": "click",
                            "confidence": element.confidence * 0.9,
                            "description": f"Click {element.text_content} button",
                        }
                    )

            elif element.element_type == ElementType.INPUT_FIELD:
                opportunities.append(
                    {
                        "type": "data_entry",
                        "element_id": element.element_id,
                        "action": "type_text",
                        "confidence": element.confidence * 0.8,
                        "description": "Enter text in input field",
                    }
                )

            elif element.element_type == ElementType.LINK:
                opportunities.append(
                    {
                        "type": "navigation",
                        "element_id": element.element_id,
                        "action": "click",
                        "confidence": element.confidence * 0.7,
                        "description": f"Navigate via {element.text_content} link",
                    }
                )

        # Context-based opportunities
        if context_analysis.get("application_type") == "web_browser":
            opportunities.append(
                {
                    "type": "web_automation",
                    "description": "Web page automation detected",
                    "confidence": 0.8,
                    "suggested_actions": ["extract_data", "fill_forms", "navigate"],
                }
            )

        return opportunities

    def _update_screenshot_cache(self, screenshot: np.ndarray):
        """Update the screenshot cache for comparison"""
        self.screenshot_cache.append((time.time(), screenshot.copy()))

        # Keep only recent screenshots
        if len(self.screenshot_cache) > self.cache_size:
            self.screenshot_cache = self.screenshot_cache[-self.cache_size :]

    async def detect_screen_changes(self, threshold: float = 0.1) -> Dict[str, Any]:
        """Detect changes in screen since last analysis"""
        if len(self.screenshot_cache) < 2:
            return {"changes_detected": False, "reason": "insufficient_cache"}

        try:
            current_screenshot = self.screenshot_cache[-1][1]
            previous_screenshot = self.screenshot_cache[-2][1]

            # Calculate difference
            diff = cv2.absdiff(current_screenshot, previous_screenshot)
            diff_score = np.mean(diff) / 255.0

            changes_detected = diff_score > threshold

            return {
                "changes_detected": changes_detected,
                "difference_score": float(diff_score),
                "threshold": threshold,
                "timestamp": self.screenshot_cache[-1][0],
                "change_regions": (
                    await self._identify_change_regions(diff)
                    if changes_detected
                    else []
                ),
            }

        except Exception as e:
            logger.error(f"Change detection failed: {e}")
            return {"changes_detected": False, "error": str(e)}

    async def _identify_change_regions(
        self, diff_image: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Identify regions where changes occurred"""
        try:
            # Convert to grayscale
            gray_diff = cv2.cvtColor(diff_image, cv2.COLOR_BGR2GRAY)

            # Threshold to get binary image
            _, binary = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)

            # Find contours
            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            change_regions = []
            for contour in contours:
                if cv2.contourArea(contour) > 100:  # Filter small changes
                    x, y, w, h = cv2.boundingRect(contour)
                    change_regions.append(
                        {
                            "bbox": {
                                "x": int(x),
                                "y": int(y),
                                "width": int(w),
                                "height": int(h),
                            },
                            "area": int(cv2.contourArea(contour)),
                            "change_intensity": float(
                                np.mean(gray_diff[y : y + h, x : x + w])
                            ),
                        }
                    )

            return change_regions

        except Exception as e:
            logger.error(f"Change region identification failed: {e}")
            return []

    async def find_elements_by_voice_description(
        self, voice_description: str, screenshot: np.ndarray
    ) -> List[UIElement]:
        """Find UI elements matching voice description using cross-modal search"""
        try:
            # Import npu_semantic_search for cross-modal capabilities
            from src.npu_semantic_search import NPUSearchEngine

            # Get NPU search engine instance
            search_engine = NPUSearchEngine()

            # Use cross-modal search to find UI elements matching voice description
            search_results = await search_engine.cross_modal_search(
                query=voice_description,
                query_modality="text",
                target_modalities=["image"],
                limit=10,
                similarity_threshold=0.7,
            )

            # Map search results back to UI elements on current screen
            matched_elements = await self._map_search_to_ui_elements(
                search_results, screenshot
            )

            logger.info(
                f"Found {len(matched_elements)} elements matching voice description: '{voice_description}'"
            )
            return matched_elements

        except Exception as e:
            logger.error(f"Voice-guided element detection failed: {e}")
            return []

    async def _map_search_to_ui_elements(
        self, search_results: Dict[str, List[Dict[str, Any]]], screenshot: np.ndarray
    ) -> List[UIElement]:
        """Map cross-modal search results to UI elements on current screen"""
        matched_elements = []

        try:
            # Process image search results
            image_results = search_results.get("image", [])

            for i, result in enumerate(image_results):
                # Extract metadata for UI element construction
                content = result.get("content", "")
                metadata = result.get("metadata", {})
                score = result.get("score", 0.0)

                # Create bounding box estimate (in real implementation,
                # would use more sophisticated mapping)
                # For now, create a centered bounding box as placeholder
                h, w = screenshot.shape[:2]
                bbox = {"x": w // 4, "y": h // 4, "width": w // 2, "height": h // 2}

                # Create UI element from search result
                ui_element = UIElement(
                    element_id=f"voice_detected_{i}_{int(time.time())}",
                    element_type=ElementType.UNKNOWN,  # Would need classification
                    bbox=bbox,
                    center_point=(
                        bbox["x"] + bbox["width"] // 2,
                        bbox["y"] + bbox["height"] // 2,
                    ),
                    confidence=score,
                    text_content=content,
                    attributes={
                        "voice_description_match": True,
                        "search_score": score,
                        "source_modality": result.get("source_modality", "image"),
                    },
                    possible_interactions=[InteractionType.CLICK],
                    screenshot_region=None,
                    ocr_data=metadata,
                )

                matched_elements.append(ui_element)

            return matched_elements

        except Exception as e:
            logger.error(f"Search result mapping failed: {e}")
            return []


class ElementClassifier:
    """Classifies UI elements based on visual features"""

    def __init__(self):
        self.classification_rules = self._load_classification_rules()
        logger.info("Element Classifier initialized")

    def _load_classification_rules(self) -> Dict[str, Any]:
        """Load classification rules for different element types"""
        return {
            "button": {
                "aspect_ratio_range": (0.2, 5.0),
                "min_area": 400,
                "max_area": 50000,
                "typical_words": ["click", "submit", "ok", "cancel", "apply", "save"],
            },
            "input_field": {
                "aspect_ratio_range": (2.0, 20.0),
                "min_area": 200,
                "border_detection": True,
            },
            "checkbox": {
                "aspect_ratio_range": (0.8, 1.2),
                "max_area": 1000,
                "square_like": True,
            },
        }

    async def classify_element(
        self, element_region: Optional[np.ndarray], bbox: Dict[str, int]
    ) -> ElementType:
        """Classify an element based on its visual features"""
        if element_region is None:
            return ElementType.UNKNOWN

        try:
            # Calculate features
            width, height = bbox["width"], bbox["height"]
            aspect_ratio = width / height if height > 0 else 1.0
            area = width * height

            # Apply classification rules
            if self._matches_button_criteria(aspect_ratio, area, element_region):
                return ElementType.BUTTON
            elif self._matches_input_criteria(aspect_ratio, area, element_region):
                return ElementType.INPUT_FIELD
            elif self._matches_checkbox_criteria(aspect_ratio, area, element_region):
                return ElementType.CHECKBOX
            else:
                return ElementType.UNKNOWN

        except Exception as e:
            logger.debug(f"Element classification failed: {e}")
            return ElementType.UNKNOWN

    def _matches_button_criteria(
        self, aspect_ratio: float, area: int, region: np.ndarray
    ) -> bool:
        """Check if element matches button criteria"""
        rules = self.classification_rules["button"]

        if not (
            rules["aspect_ratio_range"][0]
            <= aspect_ratio
            <= rules["aspect_ratio_range"][1]
        ):
            return False

        if not (rules["min_area"] <= area <= rules["max_area"]):
            return False

        return True

    def _matches_input_criteria(
        self, aspect_ratio: float, area: int, region: np.ndarray
    ) -> bool:
        """Check if element matches input field criteria"""
        rules = self.classification_rules["input_field"]

        if not (
            rules["aspect_ratio_range"][0]
            <= aspect_ratio
            <= rules["aspect_ratio_range"][1]
        ):
            return False

        if area < rules["min_area"]:
            return False

        return True

    def _matches_checkbox_criteria(
        self, aspect_ratio: float, area: int, region: np.ndarray
    ) -> bool:
        """Check if element matches checkbox criteria"""
        rules = self.classification_rules["checkbox"]

        if not (
            rules["aspect_ratio_range"][0]
            <= aspect_ratio
            <= rules["aspect_ratio_range"][1]
        ):
            return False

        if area > rules["max_area"]:
            return False

        return True


class TemplateMatchingEngine:
    """Template matching for common UI elements"""

    def __init__(self):
        self.templates = self._load_templates()
        logger.info("Template Matching Engine initialized")

    def _load_templates(self) -> Dict[str, Any]:
        """Load common UI element templates"""
        # In a real implementation, this would load actual template images
        return {
            "close_button": {
                "template_path": "templates/close_button.png",
                "element_type": "button",
                "threshold": 0.8,
            },
            "minimize_button": {
                "template_path": "templates/minimize_button.png",
                "element_type": "button",
                "threshold": 0.8,
            },
        }

    async def find_common_elements(
        self, screenshot: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Find common UI elements using template matching"""
        matches = []

        # For now, return empty list as templates need to be created
        # In a real implementation, this would:
        # 1. Load template images
        # 2. Use cv2.matchTemplate() to find matches
        # 3. Apply non-maximum suppression
        # 4. Return matches with confidence scores

        return matches


class ContextAnalyzer:
    """Analyzes screen context and application state"""

    def __init__(self):
        logger.info("Context Analyzer initialized")

    async def analyze_context(
        self, screenshot: np.ndarray, ui_elements: List[UIElement]
    ) -> Dict[str, Any]:
        """Analyze screen context and determine application state"""
        try:
            context = {
                "screen_size": {
                    "width": screenshot.shape[1],
                    "height": screenshot.shape[0],
                },
                "element_count": len(ui_elements),
                "application_type": await self._detect_application_type(
                    screenshot, ui_elements
                ),
                "interaction_complexity": self._calculate_interaction_complexity(
                    ui_elements
                ),
                "automation_readiness": self._assess_automation_readiness(ui_elements),
                "dominant_element_types": self._analyze_element_distribution(
                    ui_elements
                ),
            }

            return context

        except Exception as e:
            logger.error(f"Context analysis failed: {e}")
            return {"error": str(e)}

    async def _detect_application_type(
        self, screenshot: np.ndarray, ui_elements: List[UIElement]
    ) -> str:
        """Detect the type of application being displayed"""
        # Simple heuristics for application type detection
        button_count = sum(
            1 for el in ui_elements if el.element_type == ElementType.BUTTON
        )
        input_count = sum(
            1 for el in ui_elements if el.element_type == ElementType.INPUT_FIELD
        )

        if input_count > 3 and button_count > 1:
            return "form_application"
        elif button_count > 5:
            return "desktop_application"
        elif any("http" in el.text_content.lower() for el in ui_elements):
            return "web_browser"
        else:
            return "unknown"

    def _calculate_interaction_complexity(self, ui_elements: List[UIElement]) -> str:
        """Calculate the complexity of possible interactions"""
        total_interactions = sum(len(el.possible_interactions) for el in ui_elements)

        if total_interactions < 10:
            return "low"
        elif total_interactions < 25:
            return "medium"
        else:
            return "high"

    def _assess_automation_readiness(
        self, ui_elements: List[UIElement]
    ) -> Dict[str, Any]:
        """Assess how ready the screen is for automation"""
        interactive_elements = [
            el
            for el in ui_elements
            if InteractionType.CLICK in el.possible_interactions
        ]
        high_confidence_elements = [el for el in ui_elements if el.confidence > 0.8]

        readiness_score = (
            len(high_confidence_elements) / max(len(ui_elements), 1)
        ) * 100

        return {
            "readiness_score": readiness_score,
            "interactive_elements": len(interactive_elements),
            "high_confidence_elements": len(high_confidence_elements),
            "recommendation": "ready" if readiness_score > 70 else "needs_improvement",
        }

    def _analyze_element_distribution(
        self, ui_elements: List[UIElement]
    ) -> Dict[str, int]:
        """Analyze the distribution of element types"""
        distribution = {}
        for element in ui_elements:
            element_type = element.element_type.value
            distribution[element_type] = distribution.get(element_type, 0) + 1

        return distribution


class ComputerVisionSystem:
    """Main computer vision system coordinator"""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.screen_analyzer = ScreenAnalyzer()

        # Analysis history
        self.analysis_history: List[ScreenState] = []
        self.max_history = 10

        logger.info("Computer Vision System initialized")

    async def analyze_and_understand_screen(
        self, session_id: Optional[str] = None, context_audio: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """Comprehensive screen analysis and understanding"""

        async with task_tracker.track_task(
            "Computer Vision Analysis",
            "Complete screen understanding and element detection",
            agent_type="computer_vision_system",
            priority=TaskPriority.HIGH,
            inputs={"session_id": session_id},
        ) as task_context:
            try:
                # Perform comprehensive screen analysis
                screen_state = await self.screen_analyzer.analyze_current_screen(
                    session_id, context_audio
                )

                # Detect changes from previous analysis
                changes = await self.screen_analyzer.detect_screen_changes()

                # Store in history
                self.analysis_history.append(screen_state)
                if len(self.analysis_history) > self.max_history:
                    self.analysis_history = self.analysis_history[-self.max_history :]

                # Prepare comprehensive results
                results = {
                    "screen_analysis": {
                        "timestamp": screen_state.timestamp,
                        "confidence_score": screen_state.confidence_score,
                        "elements_detected": len(screen_state.ui_elements),
                        "text_regions": len(screen_state.text_regions),
                        "automation_opportunities": len(
                            screen_state.automation_opportunities
                        ),
                    },
                    "ui_elements": [
                        {
                            "id": el.element_id,
                            "type": el.element_type.value,
                            "bbox": el.bbox,
                            "center": el.center_point,
                            "confidence": el.confidence,
                            "text": el.text_content,
                            "interactions": [i.value for i in el.possible_interactions],
                        }
                        for el in screen_state.ui_elements
                    ],
                    "context_analysis": screen_state.context_analysis,
                    "automation_opportunities": screen_state.automation_opportunities,
                    "change_detection": changes,
                    "recommendations": await self._generate_recommendations(
                        screen_state
                    ),
                }

                task_context.set_outputs(
                    {
                        "elements_detected": len(screen_state.ui_elements),
                        "confidence": screen_state.confidence_score,
                        "opportunities": len(screen_state.automation_opportunities),
                        "changes_detected": changes.get("changes_detected", False),
                    }
                )

                logger.info(
                    f"Computer vision analysis completed: {len(screen_state.ui_elements)} elements detected"
                )
                return results

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Computer vision analysis failed: {e}")
                raise

    async def _generate_recommendations(
        self, screen_state: ScreenState
    ) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []

        # Automation recommendations
        if len(screen_state.automation_opportunities) > 0:
            recommendations.append(
                {
                    "type": "automation",
                    "priority": "high",
                    "description": (
                        f"Found {len(screen_state.automation_opportunities)} automation opportunities"
                    ),
                    "actions": ["create_automation_workflow", "test_interactions"],
                }
            )

        # UI improvement recommendations
        low_confidence_elements = [
            el for el in screen_state.ui_elements if el.confidence < 0.6
        ]
        if len(low_confidence_elements) > 0:
            recommendations.append(
                {
                    "type": "ui_analysis",
                    "priority": "medium",
                    "description": (
                        f"{len(low_confidence_elements)} elements have low detection confidence"
                    ),
                    "actions": ["improve_detection", "manual_verification"],
                }
            )

        # Context recommendations
        context_readiness = screen_state.context_analysis.get(
            "automation_readiness", {}
        )
        if context_readiness.get("recommendation") == "needs_improvement":
            recommendations.append(
                {
                    "type": "preparation",
                    "priority": "medium",
                    "description": "Screen may need preparation for automation",
                    "actions": ["optimize_screen_state", "enhance_element_visibility"],
                }
            )

        return recommendations

    def get_analysis_summary(self) -> Dict[str, Any]:
        """Get summary of recent computer vision analysis"""
        if not self.analysis_history:
            return {"status": "no_analysis_available"}

        latest_analysis = self.analysis_history[-1]

        return {
            "latest_analysis": {
                "timestamp": latest_analysis.timestamp,
                "elements_detected": len(latest_analysis.ui_elements),
                "confidence": latest_analysis.confidence_score,
                "automation_ready": (
                    latest_analysis.context_analysis.get(
                        "automation_readiness", {}
                    ).get("recommendation")
                    == "ready"
                ),
            },
            "history_count": len(self.analysis_history),
            "trending_confidence": (
                np.mean([a.confidence_score for a in self.analysis_history[-5:]])
                if len(self.analysis_history) >= 5
                else latest_analysis.confidence_score
            ),
        }


# Global instance
computer_vision_system = ComputerVisionSystem()
