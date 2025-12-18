# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Element Classification and Context Analysis

Issue #381: Extracted from computer_vision_system.py god class refactoring.
Contains classifiers for UI elements, template matching, and context analysis.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from .collections import UIElementCollection
from .types import ElementType, UIElement

logger = logging.getLogger(__name__)


class ElementClassifier:
    """Classifies UI elements based on visual features"""

    def __init__(self):
        """Initialize classifier with default classification rules."""
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
            logger.debug("Element classification failed: %s", e)
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
        """Initialize engine with loaded UI element templates."""
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
        matches: List[Dict[str, Any]] = []

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
        """Initialize context analyzer for screen state analysis."""
        logger.info("Context Analyzer initialized")

    async def analyze_context(
        self, screenshot: np.ndarray, ui_elements: List[UIElement]
    ) -> Dict[str, Any]:
        """Analyze screen context and determine application state (Tell, Don't Ask)"""
        try:
            # Use UIElementCollection for all element analysis (Tell, Don't Ask)
            collection = UIElementCollection(ui_elements)

            context = {
                "screen_size": {
                    "width": screenshot.shape[1],
                    "height": screenshot.shape[0],
                },
                "element_count": len(ui_elements),
                "application_type": collection.detect_application_type(screenshot),
                "interaction_complexity": collection.calculate_interaction_complexity(),
                "automation_readiness": collection.assess_automation_readiness(),
                "dominant_element_types": collection.count_by_type(),
            }

            return context

        except Exception as e:
            logger.error("Context analysis failed: %s", e)
            return {"error": str(e)}
