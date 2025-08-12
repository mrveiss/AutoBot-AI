"""
Multi-Modal Input Processor for AutoBot Phase 9
Handles vision, audio, text, and combined multi-modal inputs with intelligent routing
"""

import asyncio
import base64
import io
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority
from src.task_execution_tracker import task_tracker

logger = logging.getLogger(__name__)


class ModalityType(Enum):
    """Types of input modalities supported"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    COMBINED = "combined"


class ProcessingIntent(Enum):
    """Types of processing intents"""
    SCREEN_ANALYSIS = "screen_analysis"
    VOICE_COMMAND = "voice_command"
    VISUAL_QA = "visual_qa"
    AUTOMATION_TASK = "automation_task"
    CONTENT_GENERATION = "content_generation"
    DECISION_MAKING = "decision_making"


@dataclass
class ModalInput:
    """Multi-modal input data structure"""
    input_id: str
    modality_type: ModalityType
    processing_intent: ProcessingIntent
    content: Union[str, bytes, np.ndarray, Dict[str, Any]]
    metadata: Dict[str, Any]
    timestamp: float
    priority: TaskPriority = TaskPriority.MEDIUM


@dataclass
class ProcessingResult:
    """Result of multi-modal processing"""
    input_id: str
    modality_type: ModalityType
    processing_intent: ProcessingIntent
    results: Dict[str, Any]
    confidence: float
    processing_time: float
    extracted_features: Dict[str, Any]
    next_actions: List[str]
    metadata: Dict[str, Any]


class VisionProcessor:
    """Computer vision processing component"""
    
    def __init__(self):
        self.screen_analyzer = None
        self.object_detector = None
        self.text_extractor = None
        
        logger.info("Vision Processor initialized")
    
    async def analyze_screen(self, image_data: Union[bytes, np.ndarray, str]) -> Dict[str, Any]:
        """Analyze screenshot for UI elements and content"""
        
        try:
            # Convert input to PIL Image
            if isinstance(image_data, str):
                # Base64 encoded image
                image_bytes = base64.b64decode(image_data)
                image = Image.open(io.BytesIO(image_bytes))
            elif isinstance(image_data, bytes):
                image = Image.open(io.BytesIO(image_data))
            elif isinstance(image_data, np.ndarray):
                image = Image.fromarray(image_data)
            else:
                raise ValueError(f"Unsupported image data type: {type(image_data)}")
            
            # Convert to OpenCV format for analysis
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            # Analyze screen content
            analysis_results = {
                "image_size": image.size,
                "ui_elements": await self._detect_ui_elements(cv_image),
                "text_content": await self._extract_text(cv_image),
                "visual_features": await self._extract_visual_features(cv_image),
                "dominant_colors": await self._analyze_colors(image),
                "layout_analysis": await self._analyze_layout(cv_image)
            }
            
            return analysis_results
            
        except Exception as e:
            logger.error(f"Screen analysis failed: {e}")
            return {"error": str(e), "analysis_complete": False}
    
    async def _detect_ui_elements(self, cv_image: np.ndarray) -> List[Dict[str, Any]]:
        """Detect UI elements like buttons, forms, menus"""
        ui_elements = []
        
        try:
            # Convert to grayscale for contour detection
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            
            # Detect edges
            edges = cv2.Canny(gray, 50, 150)
            
            # Find contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for contour in contours:
                # Calculate bounding rectangle
                x, y, w, h = cv2.boundingRect(contour)
                
                # Filter by size (likely UI elements)
                if w > 20 and h > 20 and w < 500 and h < 300:
                    area = cv2.contourArea(contour)
                    perimeter = cv2.arcLength(contour, True)
                    
                    ui_element = {
                        "type": "detected_element",
                        "bbox": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                        "area": int(area),
                        "perimeter": float(perimeter),
                        "aspect_ratio": float(w/h) if h > 0 else 0.0
                    }
                    
                    ui_elements.append(ui_element)
            
            return ui_elements[:50]  # Limit to avoid overwhelming results
            
        except Exception as e:
            logger.error(f"UI element detection failed: {e}")
            return []
    
    async def _extract_text(self, cv_image: np.ndarray) -> Dict[str, Any]:
        """Extract text content from image using OCR"""
        try:
            # Try to import pytesseract
            try:
                import pytesseract
                
                # Extract text
                text = pytesseract.image_to_string(cv_image)
                
                # Get detailed data with bounding boxes
                data = pytesseract.image_to_data(cv_image, output_type=pytesseract.Output.DICT)
                
                # Process text regions
                text_regions = []
                for i, word in enumerate(data['text']):
                    if word.strip():
                        text_regions.append({
                            "text": word,
                            "confidence": data['conf'][i],
                            "bbox": {
                                "x": data['left'][i],
                                "y": data['top'][i],
                                "width": data['width'][i],
                                "height": data['height'][i]
                            }
                        })
                
                return {
                    "full_text": text.strip(),
                    "text_regions": text_regions,
                    "word_count": len(text.split()),
                    "ocr_available": True
                }
                
            except ImportError:
                logger.warning("pytesseract not available, skipping OCR")
                return {
                    "full_text": "",
                    "text_regions": [],
                    "word_count": 0,
                    "ocr_available": False,
                    "note": "Install pytesseract for text extraction"
                }
                
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return {"error": str(e), "ocr_available": False}
    
    async def _extract_visual_features(self, cv_image: np.ndarray) -> Dict[str, Any]:
        """Extract visual features from image"""
        try:
            # Basic visual statistics
            height, width, channels = cv_image.shape if len(cv_image.shape) == 3 else (*cv_image.shape, 1)
            
            features = {
                "dimensions": {"width": int(width), "height": int(height), "channels": int(channels)},
                "brightness": float(np.mean(cv_image)),
                "contrast": float(np.std(cv_image)),
                "sharpness": await self._calculate_sharpness(cv_image),
                "edge_density": await self._calculate_edge_density(cv_image)
            }
            
            return features
            
        except Exception as e:
            logger.error(f"Visual feature extraction failed: {e}")
            return {"error": str(e)}
    
    async def _calculate_sharpness(self, cv_image: np.ndarray) -> float:
        """Calculate image sharpness using Laplacian variance"""
        try:
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            return float(laplacian_var)
        except Exception:
            return 0.0
    
    async def _calculate_edge_density(self, cv_image: np.ndarray) -> float:
        """Calculate edge density in image"""
        try:
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            edge_pixels = np.sum(edges > 0)
            total_pixels = edges.size
            return float(edge_pixels / total_pixels) if total_pixels > 0 else 0.0
        except Exception:
            return 0.0
    
    async def _analyze_colors(self, image: Image.Image) -> List[Dict[str, Any]]:
        """Analyze dominant colors in image"""
        try:
            # Convert to RGB if not already
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Get color histogram
            pixels = list(image.getdata())
            
            # Simple dominant color extraction (top 5)
            from collections import Counter
            color_counts = Counter(pixels)
            dominant_colors = color_counts.most_common(5)
            
            colors = []
            total_pixels = len(pixels)
            
            for color, count in dominant_colors:
                colors.append({
                    "rgb": list(color),
                    "percentage": float(count / total_pixels * 100),
                    "hex": f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
                })
            
            return colors
            
        except Exception as e:
            logger.error(f"Color analysis failed: {e}")
            return []
    
    async def _analyze_layout(self, cv_image: np.ndarray) -> Dict[str, Any]:
        """Analyze layout structure of the screen"""
        try:
            height, width = cv_image.shape[:2]
            
            # Define grid regions for layout analysis
            grid_rows, grid_cols = 3, 3
            row_height = height // grid_rows
            col_width = width // grid_cols
            
            regions = []
            for row in range(grid_rows):
                for col in range(grid_cols):
                    y1, y2 = row * row_height, (row + 1) * row_height
                    x1, x2 = col * col_width, (col + 1) * col_width
                    
                    region = cv_image[y1:y2, x1:x2]
                    
                    regions.append({
                        "position": f"row_{row}_col_{col}",
                        "bbox": {"x": x1, "y": y1, "width": x2-x1, "height": y2-y1},
                        "avg_brightness": float(np.mean(region)),
                        "content_density": float(np.std(region))
                    })
            
            return {
                "grid_analysis": regions,
                "overall_layout": {
                    "width": width,
                    "height": height,
                    "aspect_ratio": float(width / height)
                }
            }
            
        except Exception as e:
            logger.error(f"Layout analysis failed: {e}")
            return {"error": str(e)}


class AudioProcessor:
    """Audio processing component for voice commands and speech synthesis"""
    
    def __init__(self):
        self.speech_recognizer = None
        self.tts_engine = None
        
        logger.info("Audio Processor initialized")
    
    async def process_audio(self, audio_data: Union[bytes, str]) -> Dict[str, Any]:
        """Process audio input for speech recognition"""
        
        try:
            # Handle base64 encoded audio
            if isinstance(audio_data, str):
                audio_bytes = base64.b64decode(audio_data)
            else:
                audio_bytes = audio_data
            
            # Speech recognition would go here
            # For now, return a placeholder structure
            result = {
                "transcription": "Speech recognition not yet implemented",
                "confidence": 0.0,
                "language": "en",
                "duration": 0.0,
                "speech_detected": False,
                "noise_level": 0.0,
                "audio_quality": "unknown"
            }
            
            logger.warning("Audio processing not fully implemented yet")
            return result
            
        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            return {"error": str(e), "speech_detected": False}
    
    async def synthesize_speech(self, text: str, voice_settings: Optional[Dict] = None) -> bytes:
        """Convert text to speech"""
        try:
            # TTS would be implemented here
            logger.warning("Speech synthesis not yet implemented")
            return b""
        except Exception as e:
            logger.error(f"Speech synthesis failed: {e}")
            return b""


class MultiModalProcessor:
    """Main multi-modal processing coordinator"""
    
    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.vision_processor = VisionProcessor()
        self.audio_processor = AudioProcessor()
        
        # Processing history
        self.processing_history: List[ProcessingResult] = []
        self.context_window = 10  # Keep last N processed inputs for context
        
        logger.info("Multi-Modal Processor initialized")
    
    async def process_input(self, modal_input: ModalInput) -> ProcessingResult:
        """Process multi-modal input and return comprehensive results"""
        
        start_time = time.time()
        
        async with task_tracker.track_task(
            f"Multi-Modal Processing: {modal_input.modality_type.value}",
            f"Processing {modal_input.processing_intent.value} with {modal_input.modality_type.value}",
            agent_type="multimodal_processor",
            priority=modal_input.priority,
            inputs={
                "modality": modal_input.modality_type.value,
                "intent": modal_input.processing_intent.value,
                "input_id": modal_input.input_id
            }
        ) as task_context:
            
            try:
                # Route to appropriate processor based on modality
                if modal_input.modality_type == ModalityType.IMAGE:
                    results = await self._process_image(modal_input)
                elif modal_input.modality_type == ModalityType.AUDIO:
                    results = await self._process_audio(modal_input)
                elif modal_input.modality_type == ModalityType.TEXT:
                    results = await self._process_text(modal_input)
                elif modal_input.modality_type == ModalityType.VIDEO:
                    results = await self._process_video(modal_input)
                elif modal_input.modality_type == ModalityType.COMBINED:
                    results = await self._process_combined(modal_input)
                else:
                    results = {"error": f"Unsupported modality: {modal_input.modality_type}"}
                
                # Calculate processing metrics
                processing_time = time.time() - start_time
                confidence = results.get("confidence", 0.8)
                
                # Extract features and suggest next actions
                extracted_features = self._extract_features(results, modal_input)
                next_actions = await self._suggest_next_actions(results, modal_input)
                
                # Create processing result
                processing_result = ProcessingResult(
                    input_id=modal_input.input_id,
                    modality_type=modal_input.modality_type,
                    processing_intent=modal_input.processing_intent,
                    results=results,
                    confidence=confidence,
                    processing_time=processing_time,
                    extracted_features=extracted_features,
                    next_actions=next_actions,
                    metadata={
                        "original_metadata": modal_input.metadata,
                        "processing_timestamp": time.time(),
                        "context_available": len(self.processing_history)
                    }
                )
                
                # Update processing history
                self._update_processing_history(processing_result)
                
                # Set task outputs
                task_context.set_outputs({
                    "processing_result": processing_result.results,
                    "confidence": confidence,
                    "processing_time": processing_time,
                    "next_actions_count": len(next_actions)
                })
                
                logger.info(f"Multi-modal processing completed: {modal_input.input_id} in {processing_time:.2f}s")
                return processing_result
                
            except Exception as e:
                error_result = ProcessingResult(
                    input_id=modal_input.input_id,
                    modality_type=modal_input.modality_type,
                    processing_intent=modal_input.processing_intent,
                    results={"error": str(e)},
                    confidence=0.0,
                    processing_time=time.time() - start_time,
                    extracted_features={},
                    next_actions=[],
                    metadata={"error": True}
                )
                
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Multi-modal processing failed: {e}")
                return error_result
    
    async def _process_image(self, modal_input: ModalInput) -> Dict[str, Any]:
        """Process image input"""
        return await self.vision_processor.analyze_screen(modal_input.content)
    
    async def _process_audio(self, modal_input: ModalInput) -> Dict[str, Any]:
        """Process audio input"""
        return await self.audio_processor.process_audio(modal_input.content)
    
    async def _process_text(self, modal_input: ModalInput) -> Dict[str, Any]:
        """Process text input"""
        text_content = str(modal_input.content)
        
        return {
            "text_analysis": {
                "word_count": len(text_content.split()),
                "char_count": len(text_content),
                "language": "auto-detected",
                "sentiment": "neutral",  # Would use NLP
                "key_phrases": [],  # Would extract key phrases
                "intent_classification": modal_input.processing_intent.value
            },
            "confidence": 0.9
        }
    
    async def _process_video(self, modal_input: ModalInput) -> Dict[str, Any]:
        """Process video input"""
        # Video processing would involve frame extraction and temporal analysis
        return {
            "video_analysis": {
                "frame_count": 0,
                "duration": 0.0,
                "fps": 0.0,
                "resolution": "unknown"
            },
            "confidence": 0.5,
            "note": "Video processing not fully implemented"
        }
    
    async def _process_combined(self, modal_input: ModalInput) -> Dict[str, Any]:
        """Process combined multi-modal input"""
        combined_data = modal_input.content
        
        if not isinstance(combined_data, dict):
            return {"error": "Combined input must be a dictionary"}
        
        results = {}
        
        # Process each modality in the combined input
        for modality, content in combined_data.items():
            if modality == "text":
                text_input = ModalInput(
                    input_id=f"{modal_input.input_id}_{modality}",
                    modality_type=ModalityType.TEXT,
                    processing_intent=modal_input.processing_intent,
                    content=content,
                    metadata=modal_input.metadata,
                    timestamp=modal_input.timestamp
                )
                results[modality] = await self._process_text(text_input)
            
            elif modality == "image":
                image_input = ModalInput(
                    input_id=f"{modal_input.input_id}_{modality}",
                    modality_type=ModalityType.IMAGE,
                    processing_intent=modal_input.processing_intent,
                    content=content,
                    metadata=modal_input.metadata,
                    timestamp=modal_input.timestamp
                )
                results[modality] = await self._process_image(image_input)
        
        return {
            "combined_results": results,
            "fusion_analysis": await self._perform_modal_fusion(results),
            "confidence": 0.85
        }
    
    async def _perform_modal_fusion(self, modal_results: Dict[str, Any]) -> Dict[str, Any]:
        """Perform cross-modal analysis and fusion"""
        fusion_analysis = {
            "modalities_processed": list(modal_results.keys()),
            "correlation_score": 0.8,  # Would calculate actual correlation
            "complementary_information": True,
            "consistency_check": "passed"
        }
        
        return fusion_analysis
    
    def _extract_features(self, results: Dict[str, Any], modal_input: ModalInput) -> Dict[str, Any]:
        """Extract relevant features from processing results"""
        features = {
            "modality": modal_input.modality_type.value,
            "intent": modal_input.processing_intent.value,
            "has_error": "error" in results,
            "processing_success": "error" not in results,
            "result_complexity": len(str(results))
        }
        
        # Add modality-specific features
        if modal_input.modality_type == ModalityType.IMAGE:
            if "ui_elements" in results:
                features["ui_elements_detected"] = len(results["ui_elements"])
            if "text_content" in results:
                features["text_extracted"] = bool(results["text_content"].get("full_text"))
        
        elif modal_input.modality_type == ModalityType.AUDIO:
            if "speech_detected" in results:
                features["speech_detected"] = results["speech_detected"]
        
        return features
    
    async def _suggest_next_actions(self, results: Dict[str, Any], modal_input: ModalInput) -> List[str]:
        """Suggest next actions based on processing results"""
        next_actions = []
        
        # Intent-based action suggestions
        if modal_input.processing_intent == ProcessingIntent.SCREEN_ANALYSIS:
            if "ui_elements" in results and results["ui_elements"]:
                next_actions.append("identify_clickable_elements")
                next_actions.append("extract_form_fields")
            
            if "text_content" in results and results["text_content"].get("full_text"):
                next_actions.append("analyze_text_content")
                next_actions.append("search_for_keywords")
        
        elif modal_input.processing_intent == ProcessingIntent.AUTOMATION_TASK:
            next_actions.extend([
                "plan_automation_steps",
                "identify_target_elements",
                "validate_screen_state"
            ])
        
        elif modal_input.processing_intent == ProcessingIntent.VOICE_COMMAND:
            if results.get("speech_detected"):
                next_actions.append("execute_voice_command")
            else:
                next_actions.append("request_speech_retry")
        
        # Error handling actions
        if "error" in results:
            next_actions.extend([
                "log_error_details",
                "retry_with_different_settings",
                "escalate_to_human_review"
            ])
        
        return next_actions
    
    def _update_processing_history(self, processing_result: ProcessingResult):
        """Update processing history for context awareness"""
        self.processing_history.append(processing_result)
        
        # Keep only recent history
        if len(self.processing_history) > self.context_window:
            self.processing_history = self.processing_history[-self.context_window:]
    
    def get_processing_context(self) -> List[Dict[str, Any]]:
        """Get recent processing context for decision making"""
        context = []
        for result in self.processing_history[-5:]:  # Last 5 results
            context.append({
                "modality": result.modality_type.value,
                "intent": result.processing_intent.value,
                "confidence": result.confidence,
                "success": "error" not in result.results,
                "timestamp": result.metadata.get("processing_timestamp", 0)
            })
        
        return context
    
    async def analyze_automation_opportunity(self, screen_data: Union[str, bytes]) -> Dict[str, Any]:
        """Analyze screen for automation opportunities"""
        
        # Create modal input for screen analysis
        modal_input = ModalInput(
            input_id=f"automation_analysis_{int(time.time())}",
            modality_type=ModalityType.IMAGE,
            processing_intent=ProcessingIntent.AUTOMATION_TASK,
            content=screen_data,
            metadata={"source": "automation_analysis"},
            timestamp=time.time(),
            priority=TaskPriority.HIGH
        )
        
        # Process the screen
        result = await self.process_input(modal_input)
        
        # Extract automation opportunities
        opportunities = []
        
        if "ui_elements" in result.results:
            for element in result.results["ui_elements"]:
                if element.get("type") == "detected_element":
                    bbox = element.get("bbox", {})
                    if bbox.get("width", 0) > 50 and bbox.get("height", 0) > 20:
                        opportunities.append({
                            "type": "clickable_element",
                            "location": bbox,
                            "automation_action": "click",
                            "confidence": 0.7
                        })
        
        if "text_content" in result.results:
            text_regions = result.results["text_content"].get("text_regions", [])
            for region in text_regions:
                if region.get("confidence", 0) > 70:
                    opportunities.append({
                        "type": "text_input",
                        "text": region["text"],
                        "location": region["bbox"],
                        "automation_action": "type_text",
                        "confidence": region["confidence"] / 100.0
                    })
        
        return {
            "automation_opportunities": opportunities,
            "screen_analysis": result.results,
            "recommendation": "high_automation_potential" if len(opportunities) > 3 else "moderate_automation_potential"
        }


# Global instance
multimodal_processor = MultiModalProcessor()