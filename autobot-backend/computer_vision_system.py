# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Computer Vision System - Backward Compatibility Facade

Issue #381: God class refactoring - Original 1,291 lines reduced to ~70 line facade.

This module is a thin wrapper that re-exports from the new src/computer_vision/
package for backward compatibility. All functionality has been extracted to:
- src/computer_vision/types.py: Core data classes (ElementType, UIElement, ScreenState)
- src/computer_vision/collections.py: UIElementCollection, ProcessingResultExtractor
- src/computer_vision/classifiers.py: ElementClassifier, TemplateMatchingEngine, ContextAnalyzer
- src/computer_vision/screen_analyzer.py: ScreenAnalyzer multimodal analysis
- src/computer_vision/system.py: ComputerVisionSystem coordinator

Advanced screen understanding and visual automation capabilities including:
- UI element detection and classification
- Screen state analysis with multimodal processing
- Automation opportunity detection
- Voice-guided element search

Feature Envy Refactoring (Issue #312):
- Enhanced UIElement with behavior methods (Tell, Don't Ask)
- Created ClassificationFeatures data class for feature analysis
- Enhanced ScreenState with analysis delegation methods
- Created InteractionMapping data class for interaction determination
- Refactored ElementClassifier to use data objects
- All changes maintain backward compatibility

DEPRECATED: Import directly from computer_vision instead.
"""

# Re-export everything from the new package for backward compatibility
from computer_vision import (  # Types; Collections; Classifiers; Screen Analyzer; System
    FORM_SUBMISSION_KEYWORDS,
    ComputerVisionSystem,
    ContextAnalyzer,
    ElementClassifier,
    ElementType,
    InteractionType,
    ProcessingResultExtractor,
    ScreenAnalyzer,
    ScreenState,
    TemplateMatchingEngine,
    UIElement,
    UIElementCollection,
    computer_vision_system,
)

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
