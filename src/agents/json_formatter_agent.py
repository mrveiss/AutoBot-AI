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
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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

        # Common patterns for broken JSON
        self.cleanup_patterns = [
            (r'"\s*":\s*"', '"placeholder":"'),  # Empty keys
            (r'"\s*":\s*([^"]*)', '"placeholder":\1'),  # Empty keys with values
            (r'{\s*""\s*:', '{"'),  # Leading empty key
            (r':\s*""\s*}', ':""}'),  # Trailing empty value
        ]

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
        self.parse_attempts += 1

        if not response or not response.strip():
            return JSONParseResult(
                success=False,
                data={},
                original_text=response,
                method_used="empty_input",
                confidence=0.0,
                warnings=["Empty or whitespace-only input"],
            )

        # Strategy 1: Direct JSON parsing
        try:
            parsed = json.loads(response.strip())
            if isinstance(parsed, dict):
                self.successful_parses += 1
                return JSONParseResult(
                    success=True,
                    data=parsed,
                    original_text=response,
                    method_used="direct_parse",
                    confidence=1.0,
                    warnings=[],
                )
        except json.JSONDecodeError:
            pass

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
        fallback_result = self._create_fallback_json(response, expected_schema)

        return fallback_result

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
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and parsed:  # Valid non-empty dict
                        self.successful_parses += 1
                        confidence = 0.9 if len(matches) == 1 else 0.7
                        if len(matches) > 1:
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
                except json.JSONDecodeError:
                    continue

        return JSONParseResult(
            success=False,
            data={},
            original_text=text,
            method_used="text_extraction_failed",
            confidence=0.0,
            warnings=["No valid JSON found in text"],
        )

    def _fix_malformed_json(self, text: str) -> JSONParseResult:
        """Attempt to fix common JSON formatting errors"""
        warnings = []

        # Start with the original text
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

        # Fix common issues
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

        # Try parsing the fixed JSON
        try:
            parsed = json.loads(json_content)
            if isinstance(parsed, dict):
                self.successful_parses += 1
                confidence = 0.8 - (
                    len(fixes_applied) * 0.1
                )  # Lower confidence for more fixes
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

        return JSONParseResult(
            success=False,
            data={},
            original_text=text,
            method_used="malformed_json_fix_failed",
            confidence=0.0,
            warnings=warnings,
        )

    def _reconstruct_from_patterns(
        self, text: str, expected_schema: Optional[Dict[str, Any]] = None
    ) -> JSONParseResult:
        """Reconstruct JSON from known patterns like empty keys"""
        warnings = []

        if not expected_schema:
            return JSONParseResult(
                success=False,
                data={},
                original_text=text,
                method_used="no_schema_for_reconstruction",
                confidence=0.0,
                warnings=["No schema provided for reconstruction"],
            )

        # Look for empty key patterns like {"":"value1","":"value2",...}
        empty_key_pattern = r'"\s*":\s*"([^"]*)"'
        matches = re.findall(empty_key_pattern, text)

        if not matches:
            # Try with non-string values
            empty_key_pattern = r'"\s*":\s*([^,}]+)'
            matches = re.findall(empty_key_pattern, text)

        if matches and len(matches) >= 2:
            # Get field names from schema
            field_names = list(expected_schema.keys())

            if len(matches) <= len(field_names):
                reconstructed = {}

                for i, value in enumerate(matches):
                    if i < len(field_names):
                        field_name = field_names[i]
                        expected_type = expected_schema[field_name]

                        # Convert value to expected type
                        try:
                            typed_value = self._convert_to_type(
                                value.strip('"'), expected_type
                            )
                            reconstructed[field_name] = typed_value
                        except Exception as e:
                            warnings.append(f"Failed to convert {field_name}: {e}")
                            reconstructed[field_name] = value.strip('"')

                if reconstructed:
                    self.successful_parses += 1
                    warnings.append(
                        f"Reconstructed from {len(matches)} empty key patterns"
                    )

                    return JSONParseResult(
                        success=True,
                        data=reconstructed,
                        original_text=text,
                        method_used="pattern_reconstruction",
                        confidence=0.6,
                        warnings=warnings,
                    )

        return JSONParseResult(
            success=False,
            data={},
            original_text=text,
            method_used="pattern_reconstruction_failed",
            confidence=0.0,
            warnings=["Could not reconstruct from patterns"],
        )

    def _create_fallback_json(
        self, text: str, expected_schema: Optional[Dict[str, Any]] = None
    ) -> JSONParseResult:
        """Create a minimal valid JSON as last resort"""
        warnings = ["Using fallback JSON creation"]

        if expected_schema:
            # Create JSON with default values based on schema
            fallback = {}
            for field, expected_type in expected_schema.items():
                fallback[field] = self._get_default_value(expected_type)

            # Try to extract any meaningful values from the text
            for field in expected_schema.keys():
                # Look for field mentions in text
                pattern = rf'{field}["\s]*:\s*["\s]*([^",}}]+)'
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        value = match.group(1).strip('"')
                        typed_value = self._convert_to_type(
                            value, expected_schema[field]
                        )
                        fallback[field] = typed_value
                        warnings.append(f"Extracted {field} from text")
                    except Exception:
                        pass
        else:
            # Create minimal JSON
            fallback = {"error": "failed_to_parse", "original_text": text[:100]}

        return JSONParseResult(
            success=True,  # Consider this a success with low confidence
            data=fallback,
            original_text=text,
            method_used="fallback_creation",
            confidence=0.2,
            warnings=warnings,
        )

    def _convert_to_type(self, value: str, expected_type: type) -> Any:
        """Convert string value to expected type"""
        if expected_type == str:
            return value
        elif expected_type == int:
            return int(float(value)) if value.replace(".", "").isdigit() else 0
        elif expected_type == float:
            return (
                float(value)
                if value.replace(".", "").replace("-", "").isdigit()
                else 0.0
            )
        elif expected_type == bool:
            return value.lower() in ("true", "1", "yes", "on")
        elif expected_type == list:
            # Try to parse as list or create single-item list
            try:
                return json.loads(value) if value.startswith("[") else [value]
            except Exception:
                return [value]
        else:
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
