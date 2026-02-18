# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Computer Vision Package

Issue #381: Extracted from computer_vision_system.py god class refactoring.
Provides advanced screen understanding and visual automation capabilities.

Package Structure:
- types.py: Core data classes (ElementType, InteractionType, UIElement, ScreenState)
- collections.py: UIElementCollection, ProcessingResultExtractor
- classifiers.py: ElementClassifier, TemplateMatchingEngine, ContextAnalyzer
- screen_analyzer.py: ScreenAnalyzer for multimodal screen analysis
- system.py: ComputerVisionSystem main coordinator
"""

# Re-export classifiers
from .classifiers import ContextAnalyzer, ElementClassifier, TemplateMatchingEngine

# Re-export collections
from .collections import ProcessingResultExtractor, UIElementCollection

# Re-export screen analyzer
from .screen_analyzer import ScreenAnalyzer

# Re-export main system
from .system import ComputerVisionSystem

# Re-export all public types for backward compatibility
from .types import (
    FORM_SUBMISSION_KEYWORDS,
    ElementType,
    InteractionType,
    ScreenState,
    UIElement,
)

# Global instance
computer_vision_system = ComputerVisionSystem()

__all__ = [
    # Types
    "ElementType",
    "InteractionType",
    "UIElement",
    "ScreenState",
    "FORM_SUBMISSION_KEYWORDS",
    # Collections
    "UIElementCollection",
    "ProcessingResultExtractor",
    # Classifiers
    "ElementClassifier",
    "TemplateMatchingEngine",
    "ContextAnalyzer",
    # Screen Analyzer
    "ScreenAnalyzer",
    # System
    "ComputerVisionSystem",
    "computer_vision_system",
]
