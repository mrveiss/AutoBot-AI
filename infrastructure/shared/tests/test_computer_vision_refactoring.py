# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test suite for computer vision system refactoring (Issue #312)
Verifies Tell Don't Ask pattern implementation and backward compatibility
"""

import numpy as np
import pytest
from src.computer_vision_system import (
    ContextAnalyzer,
    ElementType,
    InteractionType,
    UIElement,
    UIElementCollection,
)


class TestUIElementCollection:
    """Test UIElementCollection with new Tell Don't Ask methods"""

    @pytest.fixture
    def sample_elements(self):
        """Create sample UI elements for testing"""
        return [
            UIElement(
                element_id="button_1",
                element_type=ElementType.BUTTON,
                bbox={"x": 10, "y": 20, "width": 100, "height": 30},
                center_point=(60, 35),
                confidence=0.9,
                text_content="Submit",
                attributes={},
                possible_interactions=[InteractionType.CLICK],
            ),
            UIElement(
                element_id="input_1",
                element_type=ElementType.INPUT_FIELD,
                bbox={"x": 10, "y": 60, "width": 200, "height": 30},
                center_point=(110, 75),
                confidence=0.85,
                text_content="",
                attributes={},
                possible_interactions=[
                    InteractionType.CLICK,
                    InteractionType.TYPE_TEXT,
                ],
            ),
            UIElement(
                element_id="button_2",
                element_type=ElementType.BUTTON,
                bbox={"x": 220, "y": 20, "width": 100, "height": 30},
                center_point=(270, 35),
                confidence=0.75,
                text_content="Cancel",
                attributes={},
                possible_interactions=[InteractionType.CLICK],
            ),
        ]

    def test_detect_application_type_form(self, sample_elements):
        """Test application type detection for form applications"""
        collection = UIElementCollection(sample_elements)
        screenshot = np.zeros((100, 400, 3), dtype=np.uint8)

        app_type = collection.detect_application_type(screenshot)

        assert (
            app_type == "form_application"
        ), "Should detect form application with inputs and buttons"

    def test_detect_application_type_web(self):
        """Test application type detection for web browsers"""
        web_element = UIElement(
            element_id="link_1",
            element_type=ElementType.LINK,
            bbox={"x": 10, "y": 20, "width": 100, "height": 20},
            center_point=(60, 30),
            confidence=0.8,
            text_content="http://example.com",
            attributes={},
            possible_interactions=[InteractionType.CLICK],
        )

        collection = UIElementCollection([web_element])
        screenshot = np.zeros((100, 400, 3), dtype=np.uint8)

        app_type = collection.detect_application_type(screenshot)

        assert app_type == "web_browser", "Should detect web browser from URL"

    def test_assess_automation_readiness_high(self, sample_elements):
        """Test automation readiness assessment with high confidence elements"""
        collection = UIElementCollection(sample_elements)

        readiness = collection.assess_automation_readiness()

        assert "readiness_score" in readiness
        assert "interactive_elements" in readiness
        assert "high_confidence_elements" in readiness
        assert "recommendation" in readiness

        # All elements have confidence >= 0.75, two are >= 0.8
        assert readiness["readiness_score"] > 0
        assert readiness["interactive_elements"] == 3
        assert readiness["recommendation"] in ["ready", "needs_improvement"]

    def test_assess_automation_readiness_low(self):
        """Test automation readiness assessment with low confidence elements"""
        low_confidence_element = UIElement(
            element_id="button_1",
            element_type=ElementType.BUTTON,
            bbox={"x": 10, "y": 20, "width": 100, "height": 30},
            center_point=(60, 35),
            confidence=0.5,  # Low confidence
            text_content="Click",
            attributes={},
            possible_interactions=[InteractionType.CLICK],
        )

        collection = UIElementCollection([low_confidence_element])

        readiness = collection.assess_automation_readiness()

        assert (
            readiness["readiness_score"] == 0.0
        ), "Low confidence should result in 0% readiness"
        assert readiness["recommendation"] == "needs_improvement"

    def test_count_by_type(self, sample_elements):
        """Test element type counting"""
        collection = UIElementCollection(sample_elements)

        distribution = collection.count_by_type()

        assert distribution["button"] == 2
        assert distribution["input_field"] == 1

    def test_filter_by_confidence(self, sample_elements):
        """Test confidence filtering"""
        collection = UIElementCollection(sample_elements)

        high_confidence = collection.filter_by_confidence(0.8)

        assert (
            len(high_confidence) == 2
        ), "Should have 2 elements with confidence >= 0.8"

    def test_find_interactive_elements(self, sample_elements):
        """Test finding interactive elements"""
        collection = UIElementCollection(sample_elements)

        interactive = collection.find_interactive_elements()

        assert len(interactive) == 3, "All elements support CLICK interaction"

    def test_calculate_interaction_complexity(self, sample_elements):
        """Test interaction complexity calculation"""
        collection = UIElementCollection(sample_elements)

        complexity = collection.calculate_interaction_complexity()

        assert complexity in ["low", "medium", "high"]
        # 2 buttons (2 interactions each) + 1 input (2 interactions) = 6 total
        assert complexity == "low", "6 total interactions should be low complexity"


class TestContextAnalyzer:
    """Test ContextAnalyzer using Tell Don't Ask pattern"""

    @pytest.fixture
    def sample_elements(self):
        """Create sample UI elements for testing"""
        return [
            UIElement(
                element_id="button_1",
                element_type=ElementType.BUTTON,
                bbox={"x": 10, "y": 20, "width": 100, "height": 30},
                center_point=(60, 35),
                confidence=0.9,
                text_content="Submit",
                attributes={},
                possible_interactions=[InteractionType.CLICK],
            ),
            UIElement(
                element_id="input_1",
                element_type=ElementType.INPUT_FIELD,
                bbox={"x": 10, "y": 60, "width": 200, "height": 30},
                center_point=(110, 75),
                confidence=0.85,
                text_content="",
                attributes={},
                possible_interactions=[
                    InteractionType.CLICK,
                    InteractionType.TYPE_TEXT,
                ],
            ),
        ]

    @pytest.mark.asyncio
    async def test_analyze_context_structure(self, sample_elements):
        """Test context analysis returns correct structure"""
        analyzer = ContextAnalyzer()
        screenshot = np.zeros((100, 400, 3), dtype=np.uint8)

        context = await analyzer.analyze_context(screenshot, sample_elements)

        # Verify all expected keys are present
        assert "screen_size" in context
        assert "element_count" in context
        assert "application_type" in context
        assert "interaction_complexity" in context
        assert "automation_readiness" in context
        assert "dominant_element_types" in context

        # Verify structure
        assert context["screen_size"]["width"] == 400
        assert context["screen_size"]["height"] == 100
        assert context["element_count"] == 2

    @pytest.mark.asyncio
    async def test_analyze_context_backward_compatibility(self, sample_elements):
        """Test backward compatibility of context analysis"""
        analyzer = ContextAnalyzer()
        screenshot = np.zeros((100, 400, 3), dtype=np.uint8)

        context = await analyzer.analyze_context(screenshot, sample_elements)

        # Verify automation_readiness structure hasn't changed
        readiness = context["automation_readiness"]
        assert isinstance(readiness, dict)
        assert "readiness_score" in readiness
        assert "interactive_elements" in readiness
        assert "high_confidence_elements" in readiness
        assert "recommendation" in readiness

        # Verify dominant_element_types structure hasn't changed
        distribution = context["dominant_element_types"]
        assert isinstance(distribution, dict)
        assert "button" in distribution
        assert "input_field" in distribution


class TestFeatureEnvyElimination:
    """Verify Feature Envy code smells are eliminated"""

    def test_context_analyzer_uses_collection(self):
        """Verify ContextAnalyzer delegates to UIElementCollection (Tell Don't Ask)"""
        import inspect

        source = inspect.getsource(ContextAnalyzer.analyze_context)

        # Should create UIElementCollection and use its methods
        assert (
            "UIElementCollection" in source
        ), "Should use UIElementCollection for analysis"

        # Should NOT directly access element internals in loops
        assert (
            "for el in ui_elements" not in source
        ), "Should NOT iterate elements directly - use collection methods"

        # Should use collection methods
        assert "collection.detect_application_type" in source
        assert "collection.calculate_interaction_complexity" in source
        assert "collection.assess_automation_readiness" in source
        assert "collection.count_by_type" in source

    def test_ui_element_collection_encapsulates_behavior(self):
        """Verify UIElementCollection owns element analysis logic"""

        collection_methods = [
            method for method in dir(UIElementCollection) if not method.startswith("_")
        ]

        # Should have analysis methods, not just data accessors
        assert "detect_application_type" in collection_methods
        assert "assess_automation_readiness" in collection_methods
        assert "calculate_interaction_complexity" in collection_methods
        assert "count_by_type" in collection_methods
        assert "filter_by_confidence" in collection_methods
        assert "find_interactive_elements" in collection_methods

    def test_no_thin_wrapper_methods(self):
        """Verify ContextAnalyzer has no thin wrapper methods"""

        analyzer_methods = [
            method for method in dir(ContextAnalyzer) if not method.startswith("__")
        ]

        # Should NOT have thin wrapper private methods
        assert (
            "_detect_application_type" not in analyzer_methods
        ), "Thin wrapper removed - logic moved to UIElementCollection"
        assert (
            "_calculate_interaction_complexity" not in analyzer_methods
        ), "Thin wrapper removed - logic moved to UIElementCollection"
        assert (
            "_assess_automation_readiness" not in analyzer_methods
        ), "Thin wrapper removed - logic moved to UIElementCollection"
        assert (
            "_analyze_element_distribution" not in analyzer_methods
        ), "Thin wrapper removed - logic moved to UIElementCollection"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
