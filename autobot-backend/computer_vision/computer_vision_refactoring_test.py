# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test suite for computer vision system refactoring (Issue #312)
Verifies Tell Don't Ask pattern implementation and backward compatibility
"""

from unittest.mock import patch

import numpy as np
import pytest

from computer_vision_system import (
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
        """Test application type detection for form applications.

        Pre-existing red test found while converting this file (#13311): the
        shared fixture carries ONE input field, but ``detect_application_type``
        requires ``input_count > 3 and button_count > 1``, so it returned
        "unknown". The heuristic is left alone -- lowering the threshold is a
        product decision -- and the test now supplies a screen that genuinely
        clears it.
        """
        form_fields = [
            UIElement(
                element_id=f"input_{i}",
                element_type=ElementType.INPUT_FIELD,
                bbox={"x": 10, "y": 100 + i * 40, "width": 200, "height": 30},
                center_point=(110, 115 + i * 40),
                confidence=0.85,
                text_content="",
                attributes={},
                possible_interactions=[InteractionType.CLICK, InteractionType.TYPE_TEXT],
            )
            for i in range(2, 6)
        ]
        collection = UIElementCollection(sample_elements + form_fields)
        screenshot = np.zeros((100, 400, 3), dtype=np.uint8)

        app_type = collection.detect_application_type(screenshot)

        assert app_type == "form_application", "Should detect form application with inputs and buttons"

    def test_detect_application_type_needs_more_than_three_inputs(self, sample_elements):
        """Pin the threshold the test above depends on, so a change to the
        heuristic surfaces here rather than as a mystery failure."""
        collection = UIElementCollection(sample_elements)

        assert collection.count_input_elements() == 1
        assert collection.detect_application_type(np.zeros((100, 400, 3), dtype=np.uint8)) == "unknown"

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

        assert readiness["readiness_score"] == 0.0, "Low confidence should result in 0% readiness"
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

        assert len(high_confidence) == 2, "Should have 2 elements with confidence >= 0.8"

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


# #13311: a module-level element set for the delegation tests below. The two
# per-class ``sample_elements`` fixtures above predate this file's split and are
# left untouched; this one is scoped to the Feature-Envy checks.
@pytest.fixture
def context_elements():
    """One clickable button and one typable input — enough for every branch."""
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
            possible_interactions=[InteractionType.CLICK, InteractionType.TYPE_TEXT],
        ),
    ]


class TestFeatureEnvyElimination:
    """Verify Feature Envy code smells are eliminated"""

    # Delegation is observed, not grepped (#13311): asserting
    # ``"collection.count_by_type" in inspect.getsource(...)`` passed for a
    # call sitting in a dead branch and failed for a rename that changed
    # nothing, and it never showed that the collection's answer is the one the
    # caller receives.
    DELEGATED = [
        ("detect_application_type", "application_type"),
        ("calculate_interaction_complexity", "interaction_complexity"),
        ("assess_automation_readiness", "automation_readiness"),
        ("count_by_type", "dominant_element_types"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method, context_key", DELEGATED)
    async def test_each_context_field_comes_from_the_collection(self, context_elements, method, context_key):
        """Stub one collection method and watch its value surface in the result."""
        import computer_vision.classifiers as classifiers_mod

        sentinel = f"sentinel-for-{method}"
        with patch.object(classifiers_mod.UIElementCollection, method, return_value=sentinel):
            context = await ContextAnalyzer().analyze_context(np.zeros((100, 400, 3), dtype=np.uint8), context_elements)

        assert context[context_key] == sentinel, (
            f"context['{context_key}'] did not come from "
            f"UIElementCollection.{method} — ContextAnalyzer computed it itself (Feature Envy)"
        )

    @pytest.mark.asyncio
    async def test_the_collection_is_built_from_the_caller_s_elements(self, context_elements):
        """Delegation to a collection built from *something else* would still
        pass the per-field checks above."""
        import computer_vision.classifiers as classifiers_mod

        seen = []
        original = classifiers_mod.UIElementCollection

        def _record(elements):
            seen.append(list(elements))
            return original(elements)

        with patch.object(classifiers_mod, "UIElementCollection", _record):
            await ContextAnalyzer().analyze_context(np.zeros((100, 400, 3), dtype=np.uint8), context_elements)

        assert seen == [list(context_elements)]

    def test_ui_element_collection_encapsulates_behavior(self):
        """Verify UIElementCollection owns element analysis logic"""

        collection_methods = [method for method in dir(UIElementCollection) if not method.startswith("_")]

        # Should have analysis methods, not just data accessors
        assert "detect_application_type" in collection_methods
        assert "assess_automation_readiness" in collection_methods
        assert "calculate_interaction_complexity" in collection_methods
        assert "count_by_type" in collection_methods
        assert "filter_by_confidence" in collection_methods
        assert "find_interactive_elements" in collection_methods

    def test_no_thin_wrapper_methods(self):
        """Verify ContextAnalyzer has no thin wrapper methods"""

        analyzer_methods = [method for method in dir(ContextAnalyzer) if not method.startswith("__")]

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
