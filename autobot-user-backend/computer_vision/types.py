# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Computer Vision Types and Data Classes

Issue #381: Extracted from computer_vision_system.py god class refactoring.
Contains core data structures for UI element detection and screen state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    from .collections import UIElementCollection

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
    """Detected UI element with properties and interaction capabilities

    Enhanced with behavior methods to reduce Feature Envy (Tell, Don't Ask).
    Clients should call methods on this object rather than accessing properties
    and performing logic externally.
    """

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

    def matches_automation_pattern(self, keywords: set) -> bool:
        """Check if element matches automation keywords"""
        return any(word in self.text_content.lower() for word in keywords)

    def has_low_confidence(self, threshold: float = 0.6) -> bool:
        """Check if confidence is below threshold"""
        return self.confidence < threshold

    def is_interactive(self) -> bool:
        """Check if element supports click interaction"""
        return InteractionType.CLICK in self.possible_interactions

    def is_button(self) -> bool:
        """Check if element is a button type (Feature Envy fix)"""
        return self.element_type == ElementType.BUTTON

    def is_input_field(self) -> bool:
        """Check if element is an input field (Feature Envy fix)"""
        return self.element_type == ElementType.INPUT_FIELD

    def is_link(self) -> bool:
        """Check if element is a link (Feature Envy fix)"""
        return self.element_type == ElementType.LINK

    def get_area(self) -> int:
        """Get element area from dimensions (Feature Envy fix)"""
        return self.bbox.get("width", 0) * self.bbox.get("height", 0)

    def get_aspect_ratio(self) -> float:
        """Get element aspect ratio from dimensions (Feature Envy fix)"""
        width = self.bbox.get("width", 1)
        height = self.bbox.get("height", 1)
        return width / height if height > 0 else 1.0

    def get_perimeter(self) -> int:
        """Get element perimeter from dimensions (Feature Envy fix)"""
        width = self.bbox.get("width", 0)
        height = self.bbox.get("height", 0)
        return 2 * (width + height)

    def get_automation_opportunity(self) -> Optional[Dict[str, Any]]:
        """Generate automation opportunity if this element is automatable

        Returns None if no automation opportunity exists.
        (Feature Envy fix - moved logic from UIElementCollection)
        """
        if self.is_button() and self.matches_automation_pattern(FORM_SUBMISSION_KEYWORDS):
            return {
                "type": "form_submission",
                "element_id": self.element_id,
                "action": "click",
                "confidence": self.confidence * 0.9,
                "description": f"Click {self.text_content} button",
            }
        elif self.is_input_field():
            return {
                "type": "data_entry",
                "element_id": self.element_id,
                "action": "type_text",
                "confidence": self.confidence * 0.8,
                "description": "Enter text in input field",
            }
        elif self.is_link():
            return {
                "type": "navigation",
                "element_id": self.element_id,
                "action": "click",
                "confidence": self.confidence * 0.7,
                "description": f"Navigate via {self.text_content} link",
            }
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "id": self.element_id,
            "type": self.element_type.value,
            "bbox": self.bbox,
            "center": self.center_point,
            "confidence": self.confidence,
            "text": self.text_content,
            "interactions": [i.value for i in self.possible_interactions],
        }


@dataclass
class ScreenState:
    """Complete screen state analysis

    Enhanced to reduce Feature Envy by delegating analysis to UI elements.
    """

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

    def get_element_collection(self) -> "UIElementCollection":
        """Get UI elements as a collection with analysis methods"""
        # Import here to avoid circular dependency
        from .collections import UIElementCollection

        return UIElementCollection(self.ui_elements)

    def count_low_confidence_elements(self, threshold: float = 0.6) -> int:
        """Count elements with low confidence (Feature Envy fix)"""
        return sum(1 for el in self.ui_elements if el.has_low_confidence(threshold))

    def get_low_confidence_elements(self, threshold: float = 0.6) -> List[UIElement]:
        """Get all low-confidence elements (Feature Envy fix)"""
        return [el for el in self.ui_elements if el.has_low_confidence(threshold)]

    def get_automation_readiness(self) -> Dict[str, Any]:
        """Get automation readiness from context (Feature Envy fix)"""
        return self.context_analysis.get("automation_readiness", {})

    def is_automation_ready(self) -> bool:
        """Check if screen is automation ready (Feature Envy fix)"""
        readiness = self.get_automation_readiness()
        return readiness.get("recommendation") == "ready"

    def generate_recommendations(self) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on analysis"""
        recommendations = []

        # Automation recommendations
        if len(self.automation_opportunities) > 0:
            recommendations.append(
                {
                    "type": "automation",
                    "priority": "high",
                    "description": (
                        f"Found {len(self.automation_opportunities)} automation opportunities"
                    ),
                    "actions": ["create_automation_workflow", "test_interactions"],
                }
            )

        # UI improvement recommendations (Feature Envy fix - use delegated method)
        low_confidence_count = self.count_low_confidence_elements()
        if low_confidence_count > 0:
            recommendations.append(
                {
                    "type": "ui_analysis",
                    "priority": "medium",
                    "description": (
                        f"{low_confidence_count} elements have low detection confidence"
                    ),
                    "actions": ["improve_detection", "manual_verification"],
                }
            )

        # Context recommendations (Feature Envy fix - use delegated method)
        readiness = self.get_automation_readiness()
        if readiness.get("recommendation") == "needs_improvement":
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
        """Get summary of screen analysis"""
        return {
            "timestamp": self.timestamp,
            "confidence_score": self.confidence_score,
            "elements_detected": len(self.ui_elements),
            "text_regions": len(self.text_regions),
            "automation_opportunities": len(self.automation_opportunities),
        }
