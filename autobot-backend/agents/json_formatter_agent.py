# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
JSON Formatter Agent

A specialized agent responsible for parsing, validating, and formatting JSON responses
from other LLMs. This agent provides robust JSON handling with fallback mechanisms
and data type validation.
"""

import json
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.constants.threshold_constants import StringParsingConstants

logger = logging.getLogger(__name__)


@dataclass
class JSONParseResult:
    """Result of JSON parsing operation"""

    success: bool
    data: Dict[str, Any]
    original_text: str
    method_used: str
    confidence: float
    warnings: List[str]


class JSONFormatterAgent:
    """
    Specialized agent for handling JSON formatting and parsing.

    This agent provides multiple strategies for extracting and fixing
    malformed JSON from LLM responses.
    """

    def __init__(self):
        """Initialize the JSON formatter agent"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.parse_attempts = 0
        self.successful_parses = 0
        self._stats_lock = threading.Lock()  # Lock for thread-safe counter access

        # Common patterns for broken JSON
        self.cleanup_patterns = [
            (r'"\s*":\s*"', '"placeholder":"'),  # Empty keys
            (r'"\s*":\s*([^"]*)', '"placeholder":\1'),  # Empty keys with values
            (r'{\s*""\s*:', '{"'),  # Leading empty key
            (r':\s*""\s*}', ':""}'),  # Trailing empty value
        ]

    def _create_empty_input_result(self, response: str) -> JSONParseResult:
        """
        Create a failure result for empty or whitespace-only input.

        Args:
            response: The original empty/whitespace response

        Returns:
            JSONParseResult indicating empty input failure. Issue #620.
        """
        return JSONParseResult(
            success=False,
            data={},
            original_text=response,
            method_used="empty_input",
            confidence=0.0,
            warnings=["Empty or whitespace-only input"],
        )

    def _try_direct_json_parse(self, response: str) -> Optional[JSONParseResult]:
        """
        Attempt direct JSON parsing of the response.

        Args:
            response: Raw LLM response text

        Returns:
            JSONParseResult if successful, None otherwise. Issue #620.
        """
        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, dict):
                with self._stats_lock:
                    self.successful_parses += 1
                return JSONParseResult(
                    success=True,
                    data=parsed,
                    original_text=response,
                    method_used="direct_parse",
                    confidence=1.0,
                    warnings=[],
                )
        except json.JSONDecodeError as e:
            logger.debug("Direct JSON parse failed, trying extraction: %s", e)
        return None

    def parse_llm_response(
        self, response: str, expected_schema: Optional[Dict[str, Any]] = None
    ) -> JSONParseResult:
        """
        Parse JSON from an LLM response using multiple strategies.

        Args:
            response: Raw LLM response text
            expected_schema: Optional schema to validate against

        Returns:
            JSONParseResult with parsed data and metadata
        """
        with self._stats_lock:
            self.parse_attempts += 1

        if not response or not response.strip():
            return self._create_empty_input_result(response)

        # Strategy 1: Direct JSON parsing
        direct_result = self._try_direct_json_parse(response)
        if direct_result:
            return direct_result

        # Strategy 2: Extract JSON from mixed content
        json_result = self._extract_json_from_text(response)
        if json_result.success:
            return json_result

        # Strategy 3: Fix common JSON errors
        fixed_result = self._fix_malformed_json(response)
        if fixed_result.success:
            return fixed_result

        # Strategy 4: Pattern-based reconstruction
        reconstructed_result = self._reconstruct_from_patterns(
            response, expected_schema
        )
        if reconstructed_result.success:
            return reconstructed_result

        # Strategy 5: Last resort - create minimal valid JSON
        return self._create_fallback_json(response, expected_schema)

    def _try_parse_json_match(self, match: str) -> Optional[Dict[str, Any]]:
        """Try to parse a potential JSON match (Issue #334 - extracted helper)."""
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except json.JSONDecodeError:
            pass
        return None

    def _extract_json_from_text(self, text: str) -> JSONParseResult:
        """Extract JSON from text that may contain other content"""
        warnings = []

        # Find JSON-like structures
        json_patterns = [
            r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",  # Nested JSON
            r"\{[^{}]+\}",  # Simple JSON
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            # Cache len(matches) outside loop for O(1) access (Issue #323)
            matches_count = len(matches)
            for match in matches:
                parsed = self._try_parse_json_match(match)
                if parsed is None:
                    continue

                with self._stats_lock:
                    self.successful_parses += 1
                confidence = 0.9 if matches_count == 1 else 0.7
                if matches_count > 1:
                    warnings.append(
                        "Multiple JSON objects found, using first valid one"
                    )

                return JSONParseResult(
                    success=True,
                    data=parsed,
                    original_text=text,
                    method_used="text_extraction",
                    confidence=confidence,
                    warnings=warnings,
                )

        return JSONParseResult(
            success=False,
            data={},
            original_text=text,
            method_used="text_extraction_failed",
            confidence=0.0,
            warnings=["No valid JSON found in text"],
        )

    def _apply_json_fixes(self, json_content: str, warnings: List[str]) -> tuple:
        """Apply common JSON syntax fixes and return fixed content with fixes list (Issue #665: extracted helper)."""
        fixes_applied = []

        # Fix trailing commas
        if re.search(r",\s*}", json_content):
            json_content = re.sub(r",\s*}", "}", json_content)
            fixes_applied.append("removed_trailing_commas")

        # Fix missing quotes on keys
        json_content = re.sub(r"(\w+):", r'"\1":', json_content)
        if '"' in json_content:
            fixes_applied.append("added_missing_quotes")

        # Fix single quotes to double quotes
        if "'" in json_content:
            json_content = json_content.replace("'", '"')
            fixes_applied.append("converted_single_quotes")

        return json_content, fixes_applied

    def _try_parse_fixed_json(
        self,
        json_content: str,
        text: str,
        fixes_applied: List[str],
        warnings: List[str],
    ) -> Optional[JSONParseResult]:
        """Attempt to parse fixed JSON and return result if successful (Issue #665: extracted helper)."""
        try:
            parsed = json.loads(json_content)
            if isinstance(parsed, dict):
                with self._stats_lock:
                    self.successful_parses += 1
                confidence = 0.8 - (len(fixes_applied) * 0.1)
                warnings.extend([f"Applied fix: {fix}" for fix in fixes_applied])

                return JSONParseResult(
                    success=True,
                    data=parsed,
                    original_text=text,
                    method_used="malformed_json_fix",
                    confidence=max(confidence, 0.3),
                    warnings=warnings,
                )
        except json.JSONDecodeError as e:
            warnings.append(f"JSON fix failed: {e}")
        return None

    def _fix_malformed_json(self, text: str) -> JSONParseResult:
        """Attempt to fix common JSON formatting errors"""
        warnings = []
        fixed_text = text.strip()

        # Find potential JSON boundaries
        start_idx = fixed_text.find("{")
        end_idx = fixed_text.rfind("}")

        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            return JSONParseResult(
                success=False,
                data={},
                original_text=text,
                method_used="no_json_boundaries",
                confidence=0.0,
                warnings=["No JSON boundaries found"],
            )

        # Extract potential JSON content
        json_content = fixed_text[start_idx : end_idx + 1]

        # Apply cleanup patterns
        for pattern, replacement in self.cleanup_patterns:
            old_content = json_content
            json_content = re.sub(pattern, replacement, json_content)
            if old_content != json_content:
                warnings.append(f"Applied cleanup pattern: {pattern}")

        # Apply common fixes
        json_content, fixes_applied = self._apply_json_fixes(json_content, warnings)

        # Try parsing the fixed JSON
        result = self._try_parse_fixed_json(json_content, text, fixes_applied, warnings)
        if result:
            return result

        return JSONParseResult(
            success=False,
            data={},
            original_text=text,
            method_used="malformed_json_fix_failed",
            confidence=0.0,
            warnings=warnings,
        )

    def _find_empty_key_matches(self, text: str) -> list:
        """Find empty key pattern matches in text (Issue #334 - extracted helper)."""
        empty_key_pattern = r'"\s*":\s*"([^"]*)"'
        matches = re.findall(empty_key_pattern, text)
        if matches:
            return matches
        # Try with non-string values
        empty_key_pattern = r'"\s*":\s*([^,}]+)'
        return re.findall(empty_key_pattern, text)

    def _reconstruct_values_from_matches(
        self, matches: list, expected_schema: Dict[str, Any], warnings: list
    ) -> Dict[str, Any]:
        """Reconstruct values from pattern matches (Issue #334 - extracted helper)."""
        field_names = list(expected_schema.keys())
        reconstructed = {}

        for i, value in enumerate(matches):
            if i >= len(field_names):
                break
            field_name = field_names[i]
            expected_type = expected_schema[field_name]

            try:
                typed_value = self._convert_to_type(value.strip('"'), expected_type)
                reconstructed[field_name] = typed_value
            except Exception as e:
                warnings.append(f"Failed to convert {field_name}: {e}")
                reconstructed[field_name] = value.strip('"')

        return reconstructed

    def _create_failed_parse_result(
        self, text: str, method: str, warning_msg: str
    ) -> JSONParseResult:
        """
        Create a failed JSONParseResult with standard structure.

        Used for consistent failure responses in pattern reconstruction. Issue #620.
        """
        return JSONParseResult(
            success=False,
            data={},
            original_text=text,
            method_used=method,
            confidence=0.0,
            warnings=[warning_msg],
        )

    def _reconstruct_from_patterns(
        self, text: str, expected_schema: Optional[Dict[str, Any]] = None
    ) -> JSONParseResult:
        """Reconstruct JSON from known patterns like empty keys. Issue #620."""
        warnings = []

        if not expected_schema:
            return self._create_failed_parse_result(
                text,
                "no_schema_for_reconstruction",
                "No schema provided for reconstruction",
            )

        matches = self._find_empty_key_matches(text)

        # Need at least 2 matches and not more than schema fields
        if len(matches) < 2 or len(matches) > len(expected_schema):
            return self._create_failed_parse_result(
                text,
                "pattern_reconstruction_failed",
                "Could not reconstruct from patterns",
            )

        reconstructed = self._reconstruct_values_from_matches(
            matches, expected_schema, warnings
        )

        if not reconstructed:
            return self._create_failed_parse_result(
                text,
                "pattern_reconstruction_failed",
                "Could not reconstruct from patterns",
            )

        with self._stats_lock:
            self.successful_parses += 1
        warnings.append(f"Reconstructed from {len(matches)} empty key patterns")

        return JSONParseResult(
            success=True,
            data=reconstructed,
            original_text=text,
            method_used="pattern_reconstruction",
            confidence=0.6,
            warnings=warnings,
        )

    def _extract_field_value_from_text(
        self, text: str, field: str, expected_type: type, warnings: list
    ) -> Optional[Any]:
        """Extract field value from text (Issue #334 - extracted helper)."""
        pattern = rf'{field}["\s]*:\s*["\s]*([^",}}]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        try:
            value = match.group(1).strip('"')
            typed_value = self._convert_to_type(value, expected_type)
            warnings.append(f"Extracted {field} from text")
            return typed_value
        except Exception as e:
            logger.debug("Type conversion failed for field %s: %s", field, e)
            return None

    def _create_fallback_json(
        self, text: str, expected_schema: Optional[Dict[str, Any]] = None
    ) -> JSONParseResult:
        """Create a minimal valid JSON as last resort"""
        warnings = ["Using fallback JSON creation"]

        if not expected_schema:
            fallback = {"error": "failed_to_parse", "original_text": text[:100]}
            return JSONParseResult(
                success=True,
                data=fallback,
                original_text=text,
                method_used="fallback_creation",
                confidence=0.2,
                warnings=warnings,
            )

        # Create JSON with default values based on schema
        fallback = {}
        for field, expected_type in expected_schema.items():
            fallback[field] = self._get_default_value(expected_type)

        # Try to extract any meaningful values from the text
        for field, expected_type in expected_schema.items():
            extracted = self._extract_field_value_from_text(
                text, field, expected_type, warnings
            )
            if extracted is not None:
                fallback[field] = extracted

        return JSONParseResult(
            success=True,
            data=fallback,
            original_text=text,
            method_used="fallback_creation",
            confidence=0.2,
            warnings=warnings,
        )

    def _convert_int(self, value: str) -> int:
        """Convert string to int (Issue #334 - extracted helper)."""
        return int(float(value)) if value.replace(".", "").isdigit() else 0

    def _convert_float(self, value: str) -> float:
        """Convert string to float (Issue #334 - extracted helper)."""
        return (
            float(value) if value.replace(".", "").replace("-", "").isdigit() else 0.0
        )

    def _convert_list(self, value: str) -> list:
        """Convert string to list (Issue #334 - extracted helper)."""
        if not value.startswith("["):
            return [value]
        try:
            return json.loads(value)
        except Exception:
            return [value]

    def _convert_to_type(self, value: str, expected_type: type) -> Any:
        """Convert string value to expected type"""
        converters = {
            str: lambda v: v,
            int: self._convert_int,
            float: self._convert_float,
            bool: lambda v: v.lower() in StringParsingConstants.TRUTHY_STRING_VALUES,
            list: self._convert_list,
        }
        converter = converters.get(expected_type)
        if converter:
            return converter(value)
        return value

    def _get_default_value(self, expected_type: type) -> Any:
        """Get default value for a type"""
        defaults = {str: "unknown", int: 0, float: 0.0, bool: False, list: [], dict: {}}
        return defaults.get(expected_type, None)

    def validate_against_schema(
        self, data: Dict[str, Any], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and fix data against expected schema"""
        validated = {}

        for field, expected_type in schema.items():
            if field in data:
                try:
                    validated[field] = self._convert_to_type(
                        str(data[field]), expected_type
                    )
                except Exception:
                    validated[field] = self._get_default_value(expected_type)
            else:
                validated[field] = self._get_default_value(expected_type)

        return validated

    def get_statistics(self) -> Dict[str, Any]:
        """Get parsing statistics"""
        success_rate = (
            (self.successful_parses / self.parse_attempts)
            if self.parse_attempts > 0
            else 0
        )

        return {
            "total_attempts": self.parse_attempts,
            "successful_parses": self.successful_parses,
            "success_rate": success_rate,
            "failure_rate": 1 - success_rate,
        }


# Global instance for easy access
json_formatter = JSONFormatterAgent()


def parse_llm_json(
    response: str, expected_schema: Optional[Dict[str, Any]] = None
) -> JSONParseResult:
    """
    Convenience function to parse JSON from LLM response.

    Args:
        response: Raw LLM response text
        expected_schema: Optional schema for validation

    Returns:
        JSONParseResult with parsed data
    """
    return json_formatter.parse_llm_response(response, expected_schema)


# Example schemas for common use cases
CLASSIFICATION_SCHEMA = {
    "complexity": str,
    "confidence": float,
    "reasoning": str,
    "domain": str,
    "intent": str,
    "scope": str,
    "risk_level": str,
    "suggested_agents": list,
    "estimated_steps": int,
    "user_approval_needed": bool,
    "system_changes": bool,
    "requires_research": bool,
    "requires_installation": bool,
}

CHAT_RESPONSE_SCHEMA = {
    "response": str,
    "confidence": float,
    "sources": list,
    "follow_up_questions": list,
}

TASK_RESULT_SCHEMA = {
    "status": str,
    "result": str,
    "execution_time": float,
    "errors": list,
    "warnings": list,
}
