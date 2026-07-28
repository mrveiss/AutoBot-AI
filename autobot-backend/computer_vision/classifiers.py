# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Element Classification and Context Analysis

Issue #381: Extracted from computer_vision_system.py god class refactoring.
Contains classifiers for UI elements, template matching, and context analysis.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from autobot_shared.logging_manager import get_logger

from .collections import UIElementCollection
from .types import ElementType, UIElement

logger = get_logger(__name__)

# Issue #3016: lazy cv2 import to avoid startup cost; loaded on first match.
_cv2 = None


def _get_cv2():
    """Lazy-load cv2 on first use (mirrors screen_analyzer). Issue #3016."""
    global _cv2  # noqa: PLW0603
    if _cv2 is None:
        import cv2

        _cv2 = cv2
    return _cv2


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

    async def classify_element(self, element_region: np.ndarray | None, bbox: Dict[str, int]) -> ElementType:
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

    def _matches_button_criteria(self, aspect_ratio: float, area: int, region: np.ndarray) -> bool:
        """Check if element matches button criteria"""
        rules = self.classification_rules["button"]

        if not (rules["aspect_ratio_range"][0] <= aspect_ratio <= rules["aspect_ratio_range"][1]):
            return False

        if not (rules["min_area"] <= area <= rules["max_area"]):
            return False

        return True

    def _matches_input_criteria(self, aspect_ratio: float, area: int, region: np.ndarray) -> bool:
        """Check if element matches input field criteria"""
        rules = self.classification_rules["input_field"]

        if not (rules["aspect_ratio_range"][0] <= aspect_ratio <= rules["aspect_ratio_range"][1]):
            return False

        if area < rules["min_area"]:
            return False

        return True

    def _matches_checkbox_criteria(self, aspect_ratio: float, area: int, region: np.ndarray) -> bool:
        """Check if element matches checkbox criteria"""
        rules = self.classification_rules["checkbox"]

        if not (rules["aspect_ratio_range"][0] <= aspect_ratio <= rules["aspect_ratio_range"][1]):
            return False

        if area > rules["max_area"]:
            return False

        return True


class TemplateMatchingEngine:
    """Template matching for common UI elements.

    Discovers template images on disk and locates every occurrence in a
    screenshot with cv2.matchTemplate, then collapses overlapping detections
    via non-maximum suppression. Ships without bundled template images, so an
    empty result is legitimate until templates are added to the templates
    directory (it is no longer a silent stub — matching is really performed).
    """

    DEFAULT_MATCH_THRESHOLD = 0.8
    IOU_SUPPRESSION_THRESHOLD = 0.3

    def __init__(self, templates_dir: Optional[Path] = None) -> None:
        """Initialize engine, discovering available UI element templates."""
        self.templates_dir = Path(templates_dir) if templates_dir else Path(__file__).resolve().parent / "templates"
        self._template_cache: Dict[str, Any] = {}
        self.templates = self._load_templates()
        logger.info("Template Matching Engine initialized (%d templates)", len(self.templates))

    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """Discover UI element template PNGs available on disk."""
        templates: Dict[str, Dict[str, Any]] = {}
        if not self.templates_dir.is_dir():
            logger.debug("Templates directory not found: %s", self.templates_dir)
            return templates
        for path in sorted(self.templates_dir.glob("*.png")):
            name = path.stem
            templates[name] = {
                "template_path": str(path),
                "element_type": self._infer_element_type(name),
                "threshold": self.DEFAULT_MATCH_THRESHOLD,
            }
        return templates

    @staticmethod
    def _infer_element_type(name: str) -> str:
        """Infer element type from a template filename stem."""
        lowered = name.lower()
        if "checkbox" in lowered:
            return "checkbox"
        if "input" in lowered or "field" in lowered:
            return "input_field"
        if "button" in lowered or lowered in {"close", "minimize", "maximize"}:
            return "button"
        return "unknown"

    async def find_common_elements(self, screenshot: np.ndarray) -> List[Dict[str, Any]]:
        """Find common UI elements in a screenshot using template matching.

        Returns an empty list only when the screenshot is empty, no templates
        are configured, or nothing scores at/above a template's threshold.
        """
        if screenshot is None or getattr(screenshot, "size", 0) == 0:
            return []
        if not self.templates:
            logger.debug("No templates available for matching")
            return []

        cv2 = _get_cv2()
        gray_screenshot = self._to_gray(cv2, screenshot)
        matches: List[Dict[str, Any]] = []
        for name, meta in self.templates.items():
            matches.extend(self._match_template(cv2, gray_screenshot, name, meta))
        return self._suppress_overlaps(matches)

    def _match_template(
        self, cv2, gray_screenshot: np.ndarray, name: str, meta: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Run matchTemplate for one template and collect above-threshold hits."""
        template = self._load_template_image(cv2, name, meta["template_path"])
        if template is None:
            return []
        t_height, t_width = template.shape[:2]
        if gray_screenshot.shape[0] < t_height or gray_screenshot.shape[1] < t_width:
            return []
        threshold = float(meta.get("threshold", self.DEFAULT_MATCH_THRESHOLD))
        result = cv2.matchTemplate(gray_screenshot, template, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(result >= threshold)
        return [
            self._build_match(name, meta, int(x), int(y), t_width, t_height, float(result[y, x]))
            for y, x in zip(ys, xs)
        ]

    def _load_template_image(self, cv2, name: str, path: str) -> Optional[np.ndarray]:
        """Load a template image as grayscale, caching the result."""
        if name in self._template_cache:
            return self._template_cache[name]
        image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logger.warning("Failed to read template image: %s", path)
        self._template_cache[name] = image
        return image

    @staticmethod
    def _to_gray(cv2, image: np.ndarray) -> np.ndarray:
        """Return a single-channel grayscale view of an image."""
        if image.ndim == 3 and image.shape[2] >= 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    @staticmethod
    def _build_match(
        name: str, meta: Dict[str, Any], x: int, y: int, width: int, height: int, confidence: float
    ) -> Dict[str, Any]:
        """Build a match record in the shape expected by screen_analyzer."""
        return {
            "template_name": name,
            "element_type": meta.get("element_type", "unknown"),
            "bbox": {"x": x, "y": y, "width": width, "height": height},
            "center": (x + width // 2, y + height // 2),
            "confidence": confidence,
            "attributes": {"template_path": meta.get("template_path", "")},
        }

    def _suppress_overlaps(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Greedy non-maximum suppression keeping highest-confidence matches."""
        ordered = sorted(matches, key=lambda m: m["confidence"], reverse=True)
        kept: List[Dict[str, Any]] = []
        for candidate in ordered:
            if all(self._iou(candidate["bbox"], k["bbox"]) <= self.IOU_SUPPRESSION_THRESHOLD for k in kept):
                kept.append(candidate)
        return kept

    @staticmethod
    def _iou(a: Dict[str, int], b: Dict[str, int]) -> float:
        """Intersection-over-union of two {x, y, width, height} boxes."""
        ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
        bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
        inter_w = max(0, min(ax2, bx2) - max(a["x"], b["x"]))
        inter_h = max(0, min(ay2, by2) - max(a["y"], b["y"]))
        intersection = inter_w * inter_h
        union = a["width"] * a["height"] + b["width"] * b["height"] - intersection
        return intersection / union if union > 0 else 0.0


class ContextAnalyzer:
    """Analyzes screen context and application state"""

    def __init__(self):
        """Initialize context analyzer for screen state analysis."""
        logger.info("Context Analyzer initialized")

    async def analyze_context(self, screenshot: np.ndarray, ui_elements: List[UIElement]) -> Dict[str, Any]:
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
            return {"error": "Context analysis failed"}
