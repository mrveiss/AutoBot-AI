# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Input Validation and Sanitization for AutoBot Web Research

Provides comprehensive input validation to prevent injection attacks,
malicious queries, and dangerous content processing.
"""

import html
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class InputValidationError(Exception):
    """Exception raised when input validation fails"""

    pass


class WebResearchInputValidator:
    """Validates and sanitizes inputs for web research operations"""

    # Dangerous patterns that could indicate malicious intent
    DANGEROUS_PATTERNS = [
        # Script injection patterns
        r"<script[^>]*>",
        r"</script>",
        r"javascript:",
        r"vbscript:",
        r"data:text/html",
        r"data:application/javascript",
        # Event handlers
        r"on\w+\s*=",
        r"onclick\s*=",
        r"onload\s*=",
        r"onerror\s*=",
        # SQL injection patterns
        r"(union|select|insert|update|delete|drop|create|alter)\s+",
        r";\s*(union|select|insert|update|delete|drop|create|alter)\s+",
        r"(\'\s*or\s*\'|\"\s*or\s*\")",
        r"(\'\s*and\s*\'|\"\s*and\s*\")",
        # Command injection patterns
        r"[;&|`$]",
        r"\$\([^)]+\)",
        r"`[^`]+`",
        r"\|\s*(curl|wget|nc|telnet|ssh)",
        # Path traversal
        r"\.\./+",
        r"\.\.\\+",
        r"/etc/passwd",
        r"/etc/shadow",
        r"\\windows\\system32",
        # Server-side template injection
        r"\{\{[^}]+\}\}",
        r"\{%[^%]+%\}",
        r"\$\{[^}]+\}",
        # XXE patterns
        r"<!ENTITY",
        r"<!DOCTYPE[^>]+ENTITY",
        # Protocol handlers that could be dangerous
        r"(file|ftp|gopher|ldap|dict|finger|imap|pop3)://",
    ]

    # Suspicious keywords that might indicate malicious research intent
    SUSPICIOUS_KEYWORDS = [
        # Hacking/exploitation related
        "exploit",
        "vulnerability",
        "backdoor",
        "rootkit",
        "malware",
        "keylogger",
        "trojan",
        "virus",
        "worm",
        "ransomware",
        "sql injection",
        "xss",
        "csrf",
        "buffer overflow",
        "privilege escalation",
        "remote code execution",
        "password cracking",
        "brute force",
        "dictionary attack",
        # Personal information gathering
        "social security number",
        "credit card number",
        "bank account",
        "password list",
        "leaked passwords",
        "data breach",
        "personal information",
        "doxxing",
        "identity theft",
        # Illegal activities
        "illegal download",
        "pirated software",
        "counterfeit",
        "drug trafficking",
        "weapons",
        "explosives",
        "human trafficking",
        "child exploitation",
        # Phishing/scam related
        "phishing kit",
        "fake login",
        "credential harvesting",
        "scam template",
        "fraud scheme",
        "fake website",
    ]

    # Content types that are generally safe for research
    SAFE_CONTENT_TYPES = [
        "text/html",
        "text/plain",
        "text/xml",
        "text/css",
        "application/json",
        "application/xml",
        "application/rss+xml",
        "application/atom+xml",
        "application/xhtml+xml",
    ]

    def __init__(self):
        # Compile dangerous patterns for performance
        self.dangerous_pattern_compiled = []
        for pattern in self.DANGEROUS_PATTERNS:
            try:
                self.dangerous_pattern_compiled.append(
                    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                )
            except re.error as e:
                logger.warning(f"Failed to compile regex pattern {pattern}: {e}")

        # Compile suspicious keyword patterns
        self.suspicious_keyword_patterns = []
        for keyword in self.SUSPICIOUS_KEYWORDS:
            try:
                pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
                self.suspicious_keyword_patterns.append((keyword, pattern))
            except re.error as e:
                logger.warning(f"Failed to compile keyword pattern {keyword}: {e}")

    def validate_research_query(
        self, query: str, max_length: int = 500
    ) -> Dict[str, Any]:
        """
        Validate and analyze a research query for safety

        Args:
            query: The research query to validate
            max_length: Maximum allowed query length

        Returns:
            Dict containing validation results:
            - safe: bool - Whether query is safe
            - sanitized_query: str - Cleaned version of query
            - threats_detected: List[str] - Detected threats
            - risk_level: str - low, medium, high
            - warnings: List[str] - Non-blocking warnings
        """
        result = {
            "safe": True,
            "sanitized_query": query,
            "threats_detected": [],
            "risk_level": "low",
            "warnings": [],
            "metadata": {},
        }

        try:
            if not query or not query.strip():
                result.update(
                    {
                        "safe": False,
                        "threats_detected": ["EMPTY_QUERY"],
                        "risk_level": "medium",
                    }
                )
                return result

            original_query = query
            query = query.strip()

            # Length validation
            if len(query) > max_length:
                result["warnings"].append(
                    f"Query length ({len(query)}) exceeds maximum ({max_length})"
                ),
                query = query[:max_length]
                result["sanitized_query"] = query

            # Character encoding validation
            try:
                query.encode("utf-8")
            except UnicodeEncodeError:
                result.update(
                    {
                        "safe": False,
                        "threats_detected": ["INVALID_ENCODING"],
                        "risk_level": "medium",
                    }
                )
                return result

            # Dangerous pattern detection
            dangerous_matches = []
            for pattern in self.dangerous_pattern_compiled:
                matches = pattern.findall(query)
                if matches:
                    dangerous_matches.extend(matches)

            if dangerous_matches:
                result.update(
                    {
                        "safe": False,
                        "threats_detected": ["DANGEROUS_PATTERNS"],
                        "risk_level": "high",
                        "metadata": {
                            "dangerous_patterns": dangerous_matches[:5]
                        },  # Limit to first 5
                    }
                )
                logger.warning(
                    f"Dangerous patterns detected in query: {dangerous_matches}"
                )
                return result

            # Suspicious keyword detection
            suspicious_matches = []
            for keyword, pattern in self.suspicious_keyword_patterns:
                if pattern.search(query):
                    suspicious_matches.append(keyword)

            if suspicious_matches:
                if len(suspicious_matches) >= 3:
                    # Multiple suspicious keywords = high risk
                    result.update(
                        {
                            "safe": False,
                            "threats_detected": ["MULTIPLE_SUSPICIOUS_KEYWORDS"],
                            "risk_level": "high",
                            "metadata": {"suspicious_keywords": suspicious_matches},
                        }
                    )
                    return result
                else:
                    # Single suspicious keyword = warning
                    result["warnings"].append(
                        f"Potentially sensitive keywords: {', '.join(suspicious_matches)}"
                    )
                    result["risk_level"] = "medium"
                    result["metadata"]["suspicious_keywords"] = suspicious_matches

            # URL extraction and validation
            urls_in_query = self._extract_urls(query)
            if urls_in_query:
                url_validation_results = []
                for url in urls_in_query:
                    url_result = self._validate_url_in_query(url)
                    url_validation_results.append(url_result)
                    if not url_result["safe"]:
                        result.update(
                            {
                                "safe": False,
                                "threats_detected": ["DANGEROUS_URL_IN_QUERY"],
                                "risk_level": "high",
                                "metadata": {"dangerous_urls": [url_result]},
                            }
                        )
                        return result

            # Content sanitization
            sanitized_query = self._sanitize_query(query)
            if sanitized_query != query:
                result["sanitized_query"] = sanitized_query
                result["warnings"].append(
                    "Query was sanitized to remove potentially dangerous content"
                )

            # Final risk assessment
            if result["warnings"] and result["risk_level"] == "low":
                result["risk_level"] = "medium"

            logger.debug(
                f"Query validation completed: risk={result['risk_level']}, safe={result['safe']}"
            )
            return result

        except Exception as e:
            logger.error(f"Error validating research query: {e}")
            return {
                "safe": False,
                "sanitized_query": "",
                "threats_detected": ["VALIDATION_ERROR"],
                "risk_level": "high",
                "warnings": [f"Validation error: {str(e)}"],
                "metadata": {},
            }

    def validate_url(self, url: str) -> Dict[str, Any]:
        """
        Validate a URL for safety before accessing

        Args:
            url: URL to validate

        Returns:
            Dict with validation results
        """
        result = {
            "safe": True,
            "sanitized_url": url,
            "threats_detected": [],
            "warnings": [],
            "metadata": {},
        }

        try:
            if not url or not url.strip():
                result.update({"safe": False, "threats_detected": ["EMPTY_URL"]})
                return result

            url = url.strip()

            # Basic URL format validation
            try:
                parsed = urlparse(url)
            except Exception as e:
                result.update(
                    {
                        "safe": False,
                        "threats_detected": ["INVALID_URL_FORMAT"],
                        "metadata": {"error": str(e)},
                    }
                )
                return result

            # Scheme validation
            if parsed.scheme not in ["http", "https"]:
                result.update(
                    {
                        "safe": False,
                        "threats_detected": ["INVALID_SCHEME"],
                        "metadata": {"scheme": parsed.scheme},
                    }
                )
                return result

            # Hostname validation
            if not parsed.hostname:
                result.update({"safe": False, "threats_detected": ["NO_HOSTNAME"]})
                return result

            # Check for dangerous URL patterns
            dangerous_url_patterns = [
                r"javascript:",
                r"data:",
                r"vbscript:",
                r"file://",
                r"ftp://",
                r"ldap://",
                r"gopher://",
            ]

            for pattern in dangerous_url_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    result.update(
                        {
                            "safe": False,
                            "threats_detected": ["DANGEROUS_URL_SCHEME"],
                            "metadata": {"pattern": pattern},
                        }
                    )
                    return result

            # URL length validation
            if len(url) > 2000:  # URLs longer than 2000 chars are suspicious
                result["warnings"].append(f"Very long URL ({len(url)} characters)")
                # Truncate for safety
                result["sanitized_url"] = url[:2000]

            # Check for suspicious URL patterns
            suspicious_url_patterns = [
                r"%[0-9a-f]{2}%[0-9a-f]{2}%[0-9a-f]{2}",  # Multiple URL encoding
                r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}",  # IP addresses
                r"(localhost|127\.0\.0\.1|0\.0\.0\.0)",  # Local addresses
            ]

            for pattern in suspicious_url_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    result["warnings"].append(
                        f"Suspicious URL pattern detected: {pattern}"
                    )

            result["metadata"]["parsed"] = {
                "scheme": parsed.scheme,
                "hostname": parsed.hostname,
                "port": parsed.port,
                "path": parsed.path[:100],  # Limit path length for logging
            }

            return result

        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return {
                "safe": False,
                "sanitized_url": "",
                "threats_detected": ["URL_VALIDATION_ERROR"],
                "warnings": [f"Validation error: {str(e)}"],
                "metadata": {},
            }

    def sanitize_web_content(
        self, content: str, content_type: str = "text/html"
    ) -> Dict[str, Any]:
        """
        Sanitize web content before processing or storage

        Args:
            content: Raw web content
            content_type: MIME type of content

        Returns:
            Dict with sanitized content and safety information
        """
        result = {
            "safe": True,
            "sanitized_content": content,
            "threats_detected": [],
            "warnings": [],
            "metadata": {"original_length": len(content)},
        }

        try:
            if not content:
                return result

            # Content type validation
            if content_type not in self.SAFE_CONTENT_TYPES:
                result["warnings"].append(
                    f"Potentially unsafe content type: {content_type}"
                )

            # Length validation
            max_content_length = 1_000_000  # 1MB max
            if len(content) > max_content_length:
                result["warnings"].append(
                    f"Content truncated from {len(content)} to {max_content_length} chars"
                ),
                content = content[:max_content_length]

            sanitized_content = content

            # Remove dangerous script tags
            script_pattern = re.compile(
                r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL
            ),
            scripts_removed = len(script_pattern.findall(sanitized_content))
            if scripts_removed > 0:
                sanitized_content = script_pattern.sub("", sanitized_content)
                result["threats_detected"].append("SCRIPT_TAGS_REMOVED")
                result["metadata"]["scripts_removed"] = scripts_removed

            # Remove dangerous event handlers
            event_pattern = re.compile(
                r'\s*on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE
            ),
            events_removed = len(event_pattern.findall(sanitized_content))
            if events_removed > 0:
                sanitized_content = event_pattern.sub("", sanitized_content)
                result["threats_detected"].append("EVENT_HANDLERS_REMOVED")
                result["metadata"]["events_removed"] = events_removed

            # Remove dangerous links
            dangerous_link_pattern = re.compile(
                r'href\s*=\s*["\'](?:javascript:|data:|vbscript:)[^"\']*["\']',
                re.IGNORECASE,
            ),
            dangerous_links = len(dangerous_link_pattern.findall(sanitized_content))
            if dangerous_links > 0:
                sanitized_content = dangerous_link_pattern.sub(
                    'href="#"', sanitized_content
                )
                result["threats_detected"].append("DANGEROUS_LINKS_REMOVED")
                result["metadata"]["dangerous_links_removed"] = dangerous_links

            # HTML entity encoding for remaining content
            if content_type == "text/html":
                # Only encode specific dangerous characters, preserve HTML structure
                dangerous_chars = [
                    "<script",
                    "</script",
                    "javascript:",
                    "vbscript:",
                    "onload=",
                    "onclick=",
                    "onerror=",
                ]
                for char_pattern in dangerous_chars:
                    if char_pattern in sanitized_content.lower():
                        sanitized_content = sanitized_content.replace(
                            char_pattern, html.escape(char_pattern)
                        )
                        result["warnings"].append(
                            f"Encoded dangerous pattern: {char_pattern}"
                        )

            # Check for remaining suspicious patterns
            remaining_threats = []
            for pattern in self.dangerous_pattern_compiled[
                :10
            ]:  # Check first 10 patterns
                if pattern.search(sanitized_content):
                    remaining_threats.append(pattern.pattern)

            if remaining_threats:
                result["warnings"].append(
                    f"Suspicious patterns still present after sanitization: {len(remaining_threats)}"
                )
                result["metadata"]["remaining_threats"] = remaining_threats[
                    :3
                ]  # Limit to first 3

            result["sanitized_content"] = sanitized_content
            result["metadata"]["final_length"] = len(sanitized_content)
            result["metadata"]["size_reduction"] = len(content) - len(sanitized_content)

            # Overall safety assessment
            if result["threats_detected"]:
                result["safe"] = (
                    len(result["threats_detected"]) <= 2
                )  # Allow minor threats if cleaned

            return result

        except Exception as e:
            logger.error(f"Error sanitizing web content: {e}")
            return {
                "safe": False,
                "sanitized_content": "",
                "threats_detected": ["SANITIZATION_ERROR"],
                "warnings": [f"Sanitization failed: {str(e)}"],
                "metadata": {"original_length": len(content)},
            }

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text"""
        url_pattern = re.compile(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
        )
        return url_pattern.findall(text)

    def _validate_url_in_query(self, url: str) -> Dict[str, Any]:
        """Validate a URL found within a query"""
        return self.validate_url(url)

    def _sanitize_query(self, query: str) -> str:
        """Basic query sanitization"""
        # Remove null bytes
        sanitized = query.replace("\x00", "")

        # Remove excessive whitespace
        sanitized = re.sub(r"\s+", " ", sanitized)

        # Remove dangerous characters
        dangerous_chars = ["<", ">", '"', "'", "&", "\n", "\r", "\t"]
        for char in dangerous_chars:
            if char in sanitized:
                sanitized = sanitized.replace(char, " ")

        # Normalize whitespace
        sanitized = " ".join(sanitized.split())

        return sanitized

    def validate_content_type(self, content_type: str) -> bool:
        """Validate if content type is safe for processing"""
        if not content_type:
            return False

        # Extract main type and subtype
        main_type = content_type.split(";")[0].strip().lower()

        return main_type in self.SAFE_CONTENT_TYPES

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics"""
        return {
            "dangerous_patterns": len(self.DANGEROUS_PATTERNS),
            "suspicious_keywords": len(self.SUSPICIOUS_KEYWORDS),
            "safe_content_types": len(self.SAFE_CONTENT_TYPES),
            "compiled_patterns": len(self.dangerous_pattern_compiled),
            "keyword_patterns": len(self.suspicious_keyword_patterns),
        }


# Create default validator instance
_default_validator = None


def get_input_validator() -> WebResearchInputValidator:
    """Get shared input validator instance"""
    global _default_validator
    if _default_validator is None:
        _default_validator = WebResearchInputValidator()
    return _default_validator


# Convenience functions
def validate_research_query(query: str, max_length: int = 500) -> Dict[str, Any]:
    """Validate a research query"""
    return get_input_validator().validate_research_query(query, max_length)


def validate_url(url: str) -> Dict[str, Any]:
    """Validate a URL"""
    return get_input_validator().validate_url(url)


def sanitize_web_content(
    content: str, content_type: str = "text/html"
) -> Dict[str, Any]:
    """Sanitize web content"""
    return get_input_validator().sanitize_web_content(content, content_type)
