# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Catalog behind ``GET /api/anti-pattern/types`` (Issue #18099).

The set of advertised types is derived from the canonical ``AntiPatternType``
enum (GH#6757); only the per-type prose lives here. A member with neither an
entry in ``_TYPE_DETAILS`` nor a place in ``ALIAS_TYPES`` makes
``build_anti_pattern_type_definitions`` raise, and the guard test in
``anti_pattern_type_catalog_test.py`` fails first, so a new enum member can no
longer go unadvertised.

Thresholds are only stated where the detector actually uses one; the source is
named in the comment above the entry. Types whose detector has no threshold use
an empty dict.
"""

from typing import Any, Dict, Tuple

from code_analysis.src.anti_pattern_detector import AntiPatternType
from code_intelligence.anti_pattern_detection.types import Thresholds

# Migration aliases kept in the enum for input compatibility (GH#6757). They are
# accepted on input but not advertised: each duplicates a canonical member.
ALIAS_TYPES: frozenset = frozenset(
    {
        AntiPatternType.DATA_CLUMPS,  # legacy spelling of DATA_CLUMP
        AntiPatternType.DUPLICATE_ABSTRACTION,  # legacy name of DUPLICATE_CLASS_SHAPE
    }
)

_SMELL = "None (code smell)"


def _d(name: str, description: str, thresholds: dict, severity_range: list, principle: str) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "thresholds": thresholds,
        "severity_range": severity_range,
        "principle_violated": principle,
    }


# Issue #281: the first eight entries are the original hand-written ones, kept
# byte-identical and first so the response order of those eight is unchanged.
_TYPE_DETAILS: Dict[AntiPatternType, Dict[str, Any]] = {
    AntiPatternType.GOD_CLASS: _d(
        "God Class",
        "Classes with too many responsibilities",
        {"method_count": ">20", "attribute_count": ">15", "lines_of_code": ">500"},
        ["medium", "critical"],
        "Single Responsibility Principle",
    ),
    AntiPatternType.FEATURE_ENVY: _d(
        "Feature Envy",
        "Methods that use other classes more than their own",
        {"external_ref_ratio": ">3x self references"},
        ["medium", "high"],
        "Encapsulation",
    ),
    AntiPatternType.CIRCULAR_DEPENDENCY: _d(
        "Circular Dependency",
        "Modules that depend on each other in a cycle",
        {"cycle_detection": "DFS graph traversal"},
        ["medium", "high"],
        "Acyclic Dependencies Principle",
    ),
    AntiPatternType.LONG_METHOD: _d(
        "Long Method",
        "Methods that are too long to easily understand",
        {"lines": ">50"},
        ["medium", "high"],
        "Single Responsibility Principle",
    ),
    AntiPatternType.LONG_PARAMETER_LIST: _d(
        "Long Parameter List",
        "Methods with too many parameters",
        {"parameter_count": ">5"},
        ["medium", "high"],
        "Interface Segregation",
    ),
    AntiPatternType.LAZY_CLASS: _d(
        "Lazy Class",
        "Classes that don't do enough to justify existence",
        {"method_count": "<=2", "lines_of_code": "<=20"},
        ["low"],
        "None (code smell)",
    ),
    AntiPatternType.DEAD_CODE: _d(
        "Dead Code",
        "Unreferenced classes or functions",
        {"reference_count": "0"},
        ["low"],
        "None (housekeeping)",
    ),
    AntiPatternType.DATA_CLUMP: _d(
        "Data Clump",
        "Groups of parameters that appear together frequently",
        {"group_size": ">=3 parameters", "occurrences": ">=3 methods"},
        ["low", "medium"],
        "Don't Repeat Yourself (DRY)",
    ),
    # --- Issue #18099: the remaining canonical members, in enum order ---
    # Thresholds.LARGE_FILE_THRESHOLD (code_intelligence/anti_pattern_detection/types.py:60);
    # severity: severity_utils.get_large_file_severity.
    AntiPatternType.LARGE_FILE: _d(
        "Large File",
        "Source files with too many lines",
        {"lines": ">1000"},
        ["low", "critical"],
        _SMELL,
    ),
    # Thresholds.DEEP_NESTING_THRESHOLD (types.py:63); severity: get_nesting_severity.
    AntiPatternType.DEEP_NESTING: _d(
        "Deep Nesting",
        "Functions whose control-flow blocks are nested too deeply",
        {"nesting_depth": ">4"},
        ["low", "high"],
        _SMELL,
    ),
    # Thresholds.MESSAGE_CHAIN_THRESHOLD (types.py:69), compared with >= at
    # detectors/couplers.py:361; severity: get_message_chain_severity.
    AntiPatternType.MESSAGE_CHAINS: _d(
        "Message Chains",
        "Long chains of method calls such as a.b().c().d()",
        {"chain_length": ">=4"},
        ["low", "high"],
        "Law of Demeter",
    ),
    # Class-level constants _SHAPE_MIN_METHODS_STRICT / _SHAPE_JACCARD_THRESHOLD
    # (code_analysis/src/anti_pattern_detector.py:1640-1641, used at :1858-1866).
    AntiPatternType.DUPLICATE_CLASS_SHAPE: _d(
        "Duplicate Class Shape",
        "Classes with near-identical public method names that share no base class",
        {"method_name_jaccard": ">=0.7 (exact match below 5 public methods)"},
        ["low"],
        "Don't Repeat Yourself (DRY)",
    ),
    # _ENUM_JACCARD_THRESHOLD / _ENUM_MIN_VALUES (anti_pattern_detector.py:1650-1651).
    AntiPatternType.DUPLICATE_ENUM: _d(
        "Duplicate Enum",
        "Enums whose value sets overlap heavily",
        {"value_jaccard": ">=0.85", "min_enum_values": ">=3"},
        ["medium"],
        "Don't Repeat Yourself (DRY)",
    ),
    # No threshold: detectors/naming.py:124 flags any class mixing snake_case and camelCase methods.
    AntiPatternType.INCONSISTENT_NAMING: _d(
        "Inconsistent Naming",
        "Classes that mix snake_case and camelCase method names",
        {},
        ["low"],
        _SMELL,
    ),
    # No threshold: detectors/naming.py:195 flags single-letter names outside ACCEPTABLE_SINGLE_LETTER_VARS.
    AntiPatternType.SINGLE_LETTER_VARIABLE: _d(
        "Single Letter Variable",
        "Non-descriptive single-letter variable names",
        {},
        ["info"],
        _SMELL,
    ),
    # Thresholds.MAGIC_NUMBER_THRESHOLD (#18188): the NamingDetector default, compared with >= (naming.py:242).
    AntiPatternType.MAGIC_NUMBER: _d(
        "Magic Number",
        "Unexplained numeric literals repeated within a scope",
        {},  # filled at build time from _LIVE_THRESHOLDS
        ["low"],
        _SMELL,
    ),
    # Thresholds.COMPLEX_CONDITIONAL_THRESHOLD (types.py:82), compared with > at
    # detectors/naming.py:286; severity: get_complex_conditional_severity.
    AntiPatternType.COMPLEX_CONDITIONAL: _d(
        "Complex Conditional",
        "Boolean expressions combining too many conditions",
        {"condition_count": ">3"},
        ["low", "high"],
        _SMELL,
    ),
    # No threshold: detectors/naming.py:367,391 flags any public function or class without a docstring.
    AntiPatternType.MISSING_DOCSTRING: _d(
        "Missing Docstring",
        "Public functions and classes without a docstring",
        {},
        ["info", "low"],
        _SMELL,
    ),
    # No threshold: anti_pattern_detector.py:1505,1552 (sync/async or signature mismatch on an override).
    AntiPatternType.LSP_SIGNATURE_INCOMPATIBLE: _d(
        "LSP Signature Incompatible",
        "Overrides whose signature or sync/async kind differs from the parent method",
        {},
        ["high"],
        "Liskov Substitution Principle",
    ),
    # No threshold: anti_pattern_detector.py:1589 (override raises exceptions the parent neither raises nor documents).
    AntiPatternType.LSP_EXCEPTION_CONTRACT_CHANGED: _d(
        "LSP Exception Contract Changed",
        "Overrides that raise exception types the parent method neither raises nor documents",
        {},
        ["high"],
        "Liskov Substitution Principle",
    ),
    # _TRACKER_SCAN_LINES header scan; flagged only when no other module imports it
    # (anti_pattern_detector.py:1938, :2038).
    AntiPatternType.UNWIRED_TRACKER: _d(
        "Unwired Tracker",
        "Modules whose header cites an issue tracker but that have no production callers",
        {"production_callers": "0"},
        ["low"],
        "None (housekeeping)",
    ),
    # _COMPOSABLE_THRESHOLD (anti_pattern_detector.py:127), compared at :339.
    AntiPatternType.COMPOSABLE_OPPORTUNITY: _d(
        "Composable Opportunity",
        "Vue components repeating the same reactive boilerplate",
        {"component_count": ">=5"},
        ["low"],
        "Don't Repeat Yourself (DRY)",
    ),
}

# Thresholds read from the shared constant when the response is built, so they
# cannot drift from the detector's comparison (#18188).
_LIVE_THRESHOLDS = {AntiPatternType.MAGIC_NUMBER: lambda: {"occurrences": f">={Thresholds.MAGIC_NUMBER_THRESHOLD}"}}


def build_anti_pattern_type_definitions() -> Tuple[Dict[str, Any], ...]:
    """Return one definition per canonical type, aliases excluded.

    The 8 original types come first in their historical order, then the rest in
    enum order. Raises ``RuntimeError`` if a non-alias enum member has no entry.
    """
    missing = [m.name for m in AntiPatternType if m not in _TYPE_DETAILS and m not in ALIAS_TYPES]
    if missing:
        raise RuntimeError(f"AntiPatternType members without a catalog entry: {missing}")
    return tuple(
        {
            "type": member.value,
            **details,
            **({"thresholds": _LIVE_THRESHOLDS[member]()} if member in _LIVE_THRESHOLDS else {}),
        }
        for member, details in _TYPE_DETAILS.items()
    )
