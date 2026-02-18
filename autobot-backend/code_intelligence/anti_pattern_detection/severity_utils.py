# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anti-Pattern Severity Calculation Utilities

Contains helper functions for calculating anti-pattern severity levels
based on various metrics and thresholds.

Part of Issue #381 - God Class Refactoring
"""

from .types import AntiPatternSeverity


def get_god_class_severity(method_count: int) -> AntiPatternSeverity:
    """
    Calculate severity based on class method count.

    Args:
        method_count: Number of methods in the class

    Returns:
        Appropriate severity level based on thresholds
    """
    if method_count > 50:
        return AntiPatternSeverity.CRITICAL
    elif method_count > 35:
        return AntiPatternSeverity.HIGH
    elif method_count > 25:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_param_severity(param_count: int) -> AntiPatternSeverity:
    """
    Calculate severity based on function parameter count.

    Args:
        param_count: Number of parameters in the function

    Returns:
        Appropriate severity level based on thresholds
    """
    if param_count > 10:
        return AntiPatternSeverity.HIGH
    elif param_count > 7:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_large_file_severity(line_count: int) -> AntiPatternSeverity:
    """
    Calculate severity based on file line count.

    Args:
        line_count: Number of lines in the file

    Returns:
        Appropriate severity level based on thresholds
    """
    if line_count > 3000:
        return AntiPatternSeverity.CRITICAL
    elif line_count > 2000:
        return AntiPatternSeverity.HIGH
    elif line_count > 1500:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_long_method_severity(line_count: int) -> AntiPatternSeverity:
    """
    Calculate severity based on method line count.

    Args:
        line_count: Number of lines in the method

    Returns:
        Appropriate severity level based on thresholds
    """
    if line_count > 150:
        return AntiPatternSeverity.HIGH
    elif line_count > 100:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_nesting_severity(depth: int) -> AntiPatternSeverity:
    """
    Calculate severity based on code nesting depth.

    Args:
        depth: Maximum nesting depth in the code

    Returns:
        Appropriate severity level based on thresholds
    """
    if depth > 7:
        return AntiPatternSeverity.HIGH
    elif depth > 5:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_message_chain_severity(chain_length: int) -> AntiPatternSeverity:
    """
    Calculate severity based on method chain length.

    Args:
        chain_length: Length of the method call chain

    Returns:
        Appropriate severity level based on thresholds
    """
    if chain_length > 6:
        return AntiPatternSeverity.HIGH
    elif chain_length > 5:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_complex_conditional_severity(condition_count: int) -> AntiPatternSeverity:
    """
    Calculate severity based on conditional complexity.

    Args:
        condition_count: Number of conditions in a boolean expression

    Returns:
        Appropriate severity level based on thresholds
    """
    if condition_count > 5:
        return AntiPatternSeverity.HIGH
    elif condition_count > 4:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_lazy_class_severity(method_count: int, line_count: int) -> AntiPatternSeverity:
    """
    Calculate severity for lazy class based on size metrics.

    Args:
        method_count: Number of methods in the class
        line_count: Number of lines in the class

    Returns:
        Appropriate severity level
    """
    if method_count <= 1 and line_count < 30:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_feature_envy_severity(external_calls: int) -> AntiPatternSeverity:
    """
    Calculate severity based on external call count.

    Args:
        external_calls: Number of calls to external class methods

    Returns:
        Appropriate severity level based on thresholds
    """
    if external_calls > 7:
        return AntiPatternSeverity.HIGH
    elif external_calls > 5:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def get_data_clump_severity(occurrence_count: int) -> AntiPatternSeverity:
    """
    Calculate severity based on data clump occurrences.

    Args:
        occurrence_count: Number of times the same parameter group appears

    Returns:
        Appropriate severity level based on thresholds
    """
    if occurrence_count > 5:
        return AntiPatternSeverity.HIGH
    elif occurrence_count > 4:
        return AntiPatternSeverity.MEDIUM
    return AntiPatternSeverity.LOW


def severity_to_numeric(severity: AntiPatternSeverity) -> int:
    """
    Convert severity to numeric value for sorting/comparison.

    Args:
        severity: The severity level

    Returns:
        Numeric value (0-4) for comparison
    """
    mapping = {
        AntiPatternSeverity.INFO: 0,
        AntiPatternSeverity.LOW: 1,
        AntiPatternSeverity.MEDIUM: 2,
        AntiPatternSeverity.HIGH: 3,
        AntiPatternSeverity.CRITICAL: 4,
    }
    return mapping.get(severity, 0)
