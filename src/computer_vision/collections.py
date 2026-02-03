# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
UI Element Collections and Processing Result Extractors

Issue #381: Extracted from computer_vision_system.py god class refactoring.
Contains collection classes for UI element analysis.
"""

from typing import Any, Dict, List, Optional

import numpy as np

from .types import UIElement


class UIElementCollection:
    """Collection of UI elements with analysis methods (Tell, Don't Ask pattern)

    Feature Envy fixes:
    - Uses delegated methods from UIElement instead of accessing properties
    - find_automation_opportunities now calls element.get_automation_opportunity()
    - Element type checks use is_button(), is_input_field(), is_link() methods
    """

    def __init__(self, elements: List[UIElement]):
        """Initialize collection with list of UI elements."""
        self.elements = elements

    def count_by_type(self) -> Dict[str, int]:
        """Count elements by type (Feature Envy fix)"""
        distribution: Dict[str, int] = {}
        for element in self.elements:
            element_type = element.element_type.value
            distribution[element_type] = distribution.get(element_type, 0) + 1
        return distribution

    def filter_by_confidence(self, threshold: float) -> List[UIElement]:
        """Get elements above confidence threshold"""
        return [el for el in self.elements if el.confidence > threshold]

    def find_interactive_elements(self) -> List[UIElement]:
        """Get all interactive elements"""
        return [el for el in self.elements if el.is_interactive()]

    def count_button_elements(self) -> int:
        """Count button elements (Feature Envy fix)"""
        return sum(1 for el in self.elements if el.is_button())

    def count_input_elements(self) -> int:
        """Count input field elements (Feature Envy fix)"""
        return sum(1 for el in self.elements if el.is_input_field())

    def count_link_elements(self) -> int:
        """Count link elements (Feature Envy fix)"""
        return sum(1 for el in self.elements if el.is_link())

    def has_web_content(self) -> bool:
        """Check if any element suggests web content (Feature Envy fix)"""
        return any("http" in el.text_content.lower() for el in self.elements)

    def calculate_interaction_complexity(self) -> str:
        """Calculate complexity of interactions"""
        total_interactions = sum(len(el.possible_interactions) for el in self.elements)
        if total_interactions < 10:
            return "low"
        elif total_interactions < 25:
            return "medium"
        return "high"

    def detect_application_type(self, screenshot: np.ndarray) -> str:
        """Detect the type of application being displayed (Feature Envy fix)

        Now uses delegated element methods instead of accessing properties directly.
        """
        button_count = self.count_button_elements()
        input_count = self.count_input_elements()

        # Apply heuristics based on element distribution
        if input_count > 3 and button_count > 1:
            return "form_application"
        elif button_count > 5:
            return "desktop_application"
        elif self.has_web_content():
            return "web_browser"
        else:
            return "unknown"

    def assess_automation_readiness(self) -> Dict[str, Any]:
        """Assess how ready the screen is for automation (Feature Envy fix)

        Now uses delegated element methods.
        """
        interactive_elements = self.find_interactive_elements()
        high_confidence_elements = self.filter_by_confidence(0.8)

        readiness_score = (
            len(high_confidence_elements) / max(len(self.elements), 1)
        ) * 100

        return {
            "readiness_score": readiness_score,
            "interactive_elements": len(interactive_elements),
            "high_confidence_elements": len(high_confidence_elements),
            "recommendation": "ready" if readiness_score > 70 else "needs_improvement",
        }

    def find_automation_opportunities(
        self, context_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find automation opportunities based on elements and context

        Feature Envy fix: Uses UIElement.get_automation_opportunity() instead of
        accessing element properties and building opportunities externally.
        """
        opportunities = []

        # Delegate to elements to identify their automation opportunities
        for element in self.elements:
            opportunity = element.get_automation_opportunity()
            if opportunity is not None:
                opportunities.append(opportunity)

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

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Convert all elements to dictionaries"""
        return [el.to_dict() for el in self.elements]


class ProcessingResultExtractor:
    """Extracts data from multimodal processing results (Tell, Don't Ask pattern)"""

    @staticmethod
    def extract_text_regions(
        result_data: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract text regions from processing results"""
        if not result_data:
            return []
        return result_data.get("text_content", {}).get("text_regions", [])

    @staticmethod
    def extract_dominant_colors(
        result_data: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract dominant colors from processing results"""
        if not result_data:
            return []
        return result_data.get("dominant_colors", [])

    @staticmethod
    def extract_layout_structure(
        result_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract layout analysis from processing results"""
        if not result_data:
            return {}
        return result_data.get("layout_analysis", {})

    @staticmethod
    def extract_ui_elements(
        result_data: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract detected UI elements from processing results"""
        if not result_data:
            return []
        return result_data.get("ui_elements", [])

    @staticmethod
    def to_multimodal_analysis(processing_results: List[Any]) -> List[Dict[str, Any]]:
        """Convert processing results to multimodal analysis format"""
        return [
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
        ]
