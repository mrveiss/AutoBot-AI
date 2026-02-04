# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Screen Analyzer for Advanced Screen Understanding

Issue #381: Extracted from computer_vision_system.py god class refactoring.
Contains the main screen analysis and multimodal processing logic.
"""

import asyncio
import base64
import io
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from src.desktop_streaming_manager import desktop_streaming
from src.enhanced_memory_manager import TaskPriority
from src.multimodal_processor import (
    ModalityType,
    MultiModalInput,
    ProcessingIntent,
    unified_processor,
)
from src.task_execution_tracker import task_tracker

from .classifiers import ContextAnalyzer, ElementClassifier, TemplateMatchingEngine
from .collections import ProcessingResultExtractor, UIElementCollection
from .types import ElementType, InteractionType, ScreenState, UIElement

logger = logging.getLogger(__name__)


class ScreenAnalyzer:
    """Advanced screen analysis and understanding system"""

    def __init__(self):
        """Initialize analyzer with template matcher and classifiers."""
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

    def _build_analysis_outputs(
        self, ui_elements: List[UIElement], screen_state: ScreenState
    ) -> Dict[str, Any]:
        """
        Build output dictionary for task tracking.

        Issue #620.
        """
        return {
            "elements_detected": len(ui_elements),
            "text_regions": len(screen_state.text_regions),
            "automation_opportunities": len(screen_state.automation_opportunities),
            "confidence_score": screen_state.confidence_score,
        }

    async def _perform_screen_analysis(
        self, session_id: Optional[str], context_audio: Optional[bytes]
    ) -> Tuple[ScreenState, List[UIElement]]:
        """
        Execute the core screen analysis pipeline stages.

        Issue #620.
        """
        # Stage 1: Capture screenshot
        screenshot = await self._capture_screenshot(session_id)
        if screenshot is None:
            raise RuntimeError("Failed to capture screenshot")

        # Stage 2: Process multimodal inputs
        processing_results, primary_result = await self._process_multimodal_inputs(
            screenshot, session_id, context_audio
        )

        # Stage 3: Detect and analyze UI elements
        ui_elements = await self._detect_and_classify_elements(
            screenshot, primary_result.result_data or {}
        )

        # Stage 4: Context analysis
        context_analysis = await self._build_context_analysis(
            screenshot, ui_elements, processing_results, primary_result
        )

        # Stage 5: Build screen state
        screen_state = self._build_screen_state(
            screenshot,
            ui_elements,
            context_analysis,
            processing_results,
            primary_result,
        )

        # Update cache
        self._update_screenshot_cache(screenshot)

        return screen_state, ui_elements

    async def analyze_current_screen(
        self, session_id: Optional[str] = None, context_audio: Optional[bytes] = None
    ) -> ScreenState:
        """
        Analyze the current screen state comprehensively.

        Issue #281: Refactored from 141 lines to use extracted helper methods.
        Issue #620: Further refactored to reduce function length.
        """
        async with task_tracker.track_task(
            "Screen Analysis",
            "Comprehensive analysis of current screen state",
            agent_type="computer_vision",
            priority=TaskPriority.HIGH,
            inputs={"session_id": session_id},
        ) as task_context:
            try:
                screen_state, ui_elements = await self._perform_screen_analysis(
                    session_id, context_audio
                )

                task_context.set_outputs(
                    self._build_analysis_outputs(ui_elements, screen_state)
                )
                logger.info(
                    "Screen analysis completed: %d elements, confidence %.2f",
                    len(ui_elements),
                    screen_state.confidence_score,
                )
                return screen_state

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Screen analysis failed: %s", e)
                raise

    async def _process_multimodal_inputs(
        self,
        screenshot: np.ndarray,
        session_id: Optional[str],
        context_audio: Optional[bytes],
    ) -> Tuple[List[Any], Any]:
        """Process screenshot and optional audio inputs. Issue #281: Extracted helper."""
        modal_inputs = [self._create_image_input(screenshot, session_id)]

        if context_audio and self.enable_multimodal_analysis:
            modal_inputs.append(self._create_audio_input(context_audio, session_id))

        # Process all modalities
        processing_results = []
        for modal_input in modal_inputs:
            result = await self.multimodal_processor.process(modal_input)
            processing_results.append(result)

        # Combine results if multi-modal
        primary_result = processing_results[0]
        if len(processing_results) > 1:
            primary_result = (
                await self._combine_multimodal_results(processing_results, session_id)
                or primary_result
            )

        return processing_results, primary_result

    def _create_image_input(
        self, screenshot: np.ndarray, session_id: Optional[str]
    ) -> MultiModalInput:
        """Create image input for multimodal processing. Issue #281: Extracted helper."""
        return MultiModalInput(
            input_id=f"screen_vision_{int(time.time())}",
            modality_type=ModalityType.IMAGE,
            intent=ProcessingIntent.SCREEN_ANALYSIS,
            data=screenshot,
            metadata={"session_id": session_id},
        )

    def _create_audio_input(
        self, context_audio: bytes, session_id: Optional[str]
    ) -> MultiModalInput:
        """Create audio input for multimodal processing. Issue #281: Extracted helper."""
        return MultiModalInput(
            input_id=f"screen_audio_{int(time.time())}",
            modality_type=ModalityType.AUDIO,
            intent=ProcessingIntent.VOICE_COMMAND,
            data=context_audio,
            metadata={"session_id": session_id, "context": "screen_analysis"},
        )

    async def _combine_multimodal_results(
        self, processing_results: List[Any], session_id: Optional[str]
    ) -> Optional[Any]:
        """Combine multimodal results if available. Issue #281: Extracted helper."""
        combined_input = MultiModalInput(
            input_id=f"screen_combined_{int(time.time())}",
            modality_type=ModalityType.COMBINED,
            intent=ProcessingIntent.SCREEN_ANALYSIS,
            data="",
            metadata={
                "image_result": processing_results[0].result_data,
                "audio_result": processing_results[1].result_data,
                "session_id": session_id,
            },
        )
        combined_result = await self.multimodal_processor.process(combined_input)
        return combined_result if combined_result.success else None

    async def _build_context_analysis(
        self,
        screenshot: np.ndarray,
        ui_elements: List[UIElement],
        processing_results: List[Any],
        primary_result: Any,
    ) -> Dict[str, Any]:
        """Build context analysis with multimodal understanding. Issue #281: Extracted helper."""
        context_analysis = await self.context_analyzer.analyze_context(
            screenshot, ui_elements
        )

        # Add multi-modal context if available
        if len(processing_results) > 1 and processing_results[1].result_data:
            voice_intent = processing_results[1].result_data.get("transcribed_text", "")
            context_analysis["multimodal_understanding"] = primary_result.result_data
            context_analysis["cross_modal_confidence"] = primary_result.confidence
            context_analysis["voice_intent"] = voice_intent

        return context_analysis

    def _build_screen_state(
        self,
        screenshot: np.ndarray,
        ui_elements: List[UIElement],
        context_analysis: Dict[str, Any],
        processing_results: List[Any],
        primary_result: Any,
    ) -> ScreenState:
        """Build comprehensive screen state object. Issue #281: Extracted helper."""
        extractor = ProcessingResultExtractor()
        automation_opportunities = UIElementCollection(
            ui_elements
        ).find_automation_opportunities(context_analysis)

        return ScreenState(
            timestamp=time.time(),
            screenshot=screenshot,
            ui_elements=ui_elements,
            text_regions=extractor.extract_text_regions(primary_result.result_data),
            dominant_colors=extractor.extract_dominant_colors(
                primary_result.result_data
            ),
            layout_structure=extractor.extract_layout_structure(
                primary_result.result_data
            ),
            automation_opportunities=automation_opportunities,
            context_analysis=context_analysis,
            confidence_score=max(r.confidence for r in processing_results),
            multimodal_analysis=extractor.to_multimodal_analysis(processing_results),
        )

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
                    "import",
                    "-window",
                    "root",
                    "png:-",
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
                logger.warning("X11 screenshot failed: %s", e)

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
            logger.error("Screenshot capture failed: %s", e)
            return None

    async def _detect_and_classify_elements(
        self, screenshot: np.ndarray, processing_results: Dict[str, Any]
    ) -> List[UIElement]:
        """Detect and classify UI elements (Issue #665: refactored)."""
        ui_elements: List[UIElement] = []

        try:
            # Get basic UI elements from multi-modal processor (Tell, Don't Ask)
            extractor = ProcessingResultExtractor()
            detected_elements = extractor.extract_ui_elements(processing_results)

            # Enhance with advanced classification
            for i, element in enumerate(detected_elements):
                ui_element = await self._classify_single_element(screenshot, element, i)
                if ui_element:
                    ui_elements.append(ui_element)

            # Add template matching results
            template_elements = await self._process_template_matches(screenshot)
            ui_elements.extend(template_elements)

            return ui_elements

        except Exception as e:
            logger.error("Element detection and classification failed: %s", e)
            return []

    async def _classify_single_element(
        self, screenshot: np.ndarray, element: Dict[str, Any], index: int
    ) -> Optional[UIElement]:
        """Classify a single detected element (Issue #665: extracted helper)."""
        bbox = element.get("bbox", {})
        if not bbox:
            return None

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
        interactions = self._determine_interactions(element_type, element_region)

        # Extract text from element
        text_content = await self._extract_element_text(element_region)

        # Create UI element
        return UIElement(
            element_id=f"element_{index}_{int(time.time())}",
            element_type=element_type,
            bbox=bbox,
            center_point=(x + w // 2, y + h // 2),
            confidence=element.get("confidence", 0.7),
            text_content=text_content,
            attributes={
                "area": element.get("area", w * h),
                "aspect_ratio": element.get("aspect_ratio", w / h if h > 0 else 1.0),
                "perimeter": element.get("perimeter", 2 * (w + h)),
            },
            possible_interactions=interactions,
            screenshot_region=element_region,
            ocr_data=None,
        )

    async def _process_template_matches(
        self, screenshot: np.ndarray
    ) -> List[UIElement]:
        """Process template matching results (Issue #665: extracted helper)."""
        template_elements = []
        template_matches = await self.template_matcher.find_common_elements(screenshot)
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
            template_elements.append(ui_element)
        return template_elements

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
            logger.debug("Text extraction failed: %s", e)
            return ""

    async def _find_automation_opportunities(
        self, ui_elements: List[UIElement], context_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find automation opportunities based on detected elements and context"""
        # Use UIElementCollection for analysis (Tell, Don't Ask)
        collection = UIElementCollection(ui_elements)
        return collection.find_automation_opportunities(context_analysis)

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
            logger.error("Change detection failed: %s", e)
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
            logger.error("Change region identification failed: %s", e)
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
                "Found %d elements matching voice description: '%s'",
                len(matched_elements),
                voice_description,
            )
            return matched_elements

        except Exception as e:
            logger.error("Voice-guided element detection failed: %s", e)
            return []

    async def _map_search_to_ui_elements(
        self, search_results: Dict[str, List[Dict[str, Any]]], screenshot: np.ndarray
    ) -> List[UIElement]:
        """Map cross-modal search results to UI elements on current screen"""
        matched_elements: List[UIElement] = []

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
            logger.error("Search result mapping failed: %s", e)
            return []
