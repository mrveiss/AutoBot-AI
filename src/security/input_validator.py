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
from typing import Any, Dict, List
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for URL scheme validation
_VALID_URL_SCHEMES = frozenset({"http", "https"})

# Issue #380: Pre-compiled regex patterns for frequently used operations
_SCRIPT_TAG_RE = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_EVENT_HANDLER_RE = re.compile(r'\s*on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
_DANGEROUS_LINK_RE = re.compile(
    r'href\s*=\s*["\'](?:javascript:|data:|vbscript:)[^"\']*["\']', re.IGNORECASE
)
_URL_EXTRACT_RE = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)
_WHITESPACE_RE = re.compile(r"\s+")


class InputValidationError(Exception):
    """Exception raised when input validation fails"""


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
        """Initialize input validator with compiled regex patterns for security checks."""
        # Compile dangerous patterns for performance
        self.dangerous_pattern_compiled = []
        for pattern in self.DANGEROUS_PATTERNS:
            try:
                self.dangerous_pattern_compiled.append(
                    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                )
            except re.error as e:
                logger.warning("Failed to compile regex pattern %s: %s", pattern, e)

        # Compile suspicious keyword patterns
        self.suspicious_keyword_patterns = []
        for keyword in self.SUSPICIOUS_KEYWORDS:
            try:
                pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
                self.suspicious_keyword_patterns.append((keyword, pattern))
            except re.error as e:
                logger.warning("Failed to compile keyword pattern %s: %s", keyword, e)

    def _create_query_result(self, query: str) -> Dict[str, Any]:
        """Create initial query validation result structure."""
        return {
            "safe": True, "sanitized_query": query, "threats_detected": [],
            "risk_level": "low", "warnings": [], "metadata": {},
        }

    def _check_empty_query(self, query: str) -> tuple:
        """Check for empty query. Returns (query, error_result or None)."""
        if not query or not query.strip():
            return None, {"safe": False, "threats_detected": ["EMPTY_QUERY"], "risk_level": "medium"}
        return query.strip(), None

    def _check_query_length(self, query: str, max_length: int, result: Dict) -> str:
        """Check and truncate query if too long. Updates result warnings."""
        if len(query) > max_length:
            result["warnings"].append(f"Query length ({len(query)}) exceeds maximum ({max_length})")
            query = query[:max_length]
            result["sanitized_query"] = query
        return query

    def _check_encoding(self, query: str) -> Dict[str, Any]:
        """Check UTF-8 encoding. Returns error result if invalid, None if valid."""
        try:
            query.encode("utf-8")
            return None
        except UnicodeEncodeError:
            return {"safe": False, "threats_detected": ["INVALID_ENCODING"], "risk_level": "medium"}

    def _check_dangerous_patterns(self, query: str) -> tuple:
        """Check for dangerous patterns. Returns (matches, error_result or None)."""
        dangerous_matches = []
        for pattern in self.dangerous_pattern_compiled:
            matches = pattern.findall(query)
            if matches:
                dangerous_matches.extend(matches)
        if dangerous_matches:
            logger.warning("Dangerous patterns detected in query: %s", dangerous_matches)
            return dangerous_matches, {
                "safe": False, "threats_detected": ["DANGEROUS_PATTERNS"], "risk_level": "high",
                "metadata": {"dangerous_patterns": dangerous_matches[:5]},
            }
        return dangerous_matches, None

    def _check_suspicious_keywords(self, query: str, result: Dict) -> Dict[str, Any]:
        """Check for suspicious keywords. Returns error result if high risk, None otherwise."""
        suspicious_matches = [kw for kw, pat in self.suspicious_keyword_patterns if pat.search(query)]
        if suspicious_matches:
            if len(suspicious_matches) >= 3:
                return {
                    "safe": False, "threats_detected": ["MULTIPLE_SUSPICIOUS_KEYWORDS"],
                    "risk_level": "high", "metadata": {"suspicious_keywords": suspicious_matches},
                }
            result["warnings"].append(f"Potentially sensitive keywords: {', '.join(suspicious_matches)}")
            result["risk_level"] = "medium"
            result["metadata"]["suspicious_keywords"] = suspicious_matches
        return None

    def _check_urls_in_query(self, query: str) -> Dict[str, Any]:
        """Check URLs in query. Returns error result if dangerous URL found, None otherwise."""
        for url in self._extract_urls(query):
            url_result = self._validate_url_in_query(url)
            if not url_result["safe"]:
                return {
                    "safe": False, "threats_detected": ["DANGEROUS_URL_IN_QUERY"],
                    "risk_level": "high", "metadata": {"dangerous_urls": [url_result]},
                }
        return None

    def _create_url_result(self, url: str) -> Dict[str, Any]:
        """Create initial URL validation result structure."""
        return {
            "safe": True, "sanitized_url": url, "threats_detected": [],
            "warnings": [], "metadata": {},
        }

    def _check_empty_url(self, url: str) -> tuple:
        """Check for empty URL. Returns (url, error_result or None)."""
        if not url or not url.strip():
            return None, {"safe": False, "threats_detected": ["EMPTY_URL"]}
        return url.strip(), None

    def _parse_url(self, url: str) -> tuple:
        """Parse URL. Returns (parsed, error_result or None)."""
        try:
            parsed = urlparse(url)
            return parsed, None
        except Exception as e:
            return None, {
                "safe": False, "threats_detected": ["INVALID_URL_FORMAT"],
                "metadata": {"error": str(e)},
            }

    def _validate_url_scheme(self, parsed) -> Dict[str, Any]:
        """Validate URL scheme. Returns error result if invalid, None if valid."""
        if parsed.scheme not in _VALID_URL_SCHEMES:
            return {
                "safe": False, "threats_detected": ["INVALID_SCHEME"],
                "metadata": {"scheme": parsed.scheme},
            }
        return None

    def _validate_url_hostname(self, parsed) -> Dict[str, Any]:
        """Validate URL hostname. Returns error result if missing, None if valid."""
        if not parsed.hostname:
            return {"safe": False, "threats_detected": ["NO_HOSTNAME"]}
        return None

    def _check_dangerous_url_patterns(self, url: str) -> Dict[str, Any]:
        """Check for dangerous URL patterns. Returns error result if found, None otherwise."""
        dangerous_url_patterns = [
            r"javascript:", r"data:", r"vbscript:", r"file://",
            r"ftp://", r"ldap://", r"gopher://",
        ]
        for pattern in dangerous_url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return {
                    "safe": False, "threats_detected": ["DANGEROUS_URL_SCHEME"],
                    "metadata": {"pattern": pattern},
                }
        return None

    def _check_url_length(self, url: str, result: Dict) -> str:
        """Check URL length. Updates result warnings and returns sanitized URL."""
        if len(url) > 2000:
            result["warnings"].append(f"Very long URL ({len(url)} characters)")
            result["sanitized_url"] = url[:2000]
        return url

    def _check_suspicious_url_patterns(self, url: str, result: Dict) -> None:
        """Check for suspicious URL patterns. Updates result warnings."""
        suspicious_url_patterns = [
            r"%[0-9a-f]{2}%[0-9a-f]{2}%[0-9a-f]{2}",  # Multiple URL encoding
            r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}",  # IP addresses
            r"(localhost|127\.0\.0\.1|0\.0\.0\.0)",  # Local addresses
        ]
        for pattern in suspicious_url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                result["warnings"].append(f"Suspicious URL pattern detected: {pattern}")

    def validate_research_query(self, query: str, max_length: int = 500) -> Dict[str, Any]:
        """Validate and analyze a research query for safety."""
        result = self._create_query_result(query)
        try:
            query, error = self._check_empty_query(query)
            if error:
                result.update(error)
                return result

            query = self._check_query_length(query, max_length, result)
            if error := self._check_encoding(query):
                result.update(error)
                return result
            _, error = self._check_dangerous_patterns(query)
            if error:
                result.update(error)
                return result
            if error := self._check_suspicious_keywords(query, result):
                result.update(error)
                return result
            if error := self._check_urls_in_query(query):
                result.update(error)
                return result

            sanitized_query = self._sanitize_query(query)
            if sanitized_query != query:
                result["sanitized_query"] = sanitized_query
                result["warnings"].append("Query was sanitized to remove potentially dangerous content")
            if result["warnings"] and result["risk_level"] == "low":
                result["risk_level"] = "medium"

            logger.debug("Query validation completed: risk=%s, safe=%s", result['risk_level'], result['safe'])
            return result
        except Exception as e:
            logger.error("Error validating research query: %s", e)
            return {
                "safe": False, "sanitized_query": "", "threats_detected": ["VALIDATION_ERROR"],
                "risk_level": "high", "warnings": [f"Validation error: {str(e)}"], "metadata": {},
            }

    def validate_url(self, url: str) -> Dict[str, Any]:
        """Validate a URL for safety before accessing."""
        result = self._create_url_result(url)
        try:
            url, error = self._check_empty_url(url)
            if error:
                result.update(error)
                return result

            parsed, error = self._parse_url(url)
            if error:
                result.update(error)
                return result

            if error := self._validate_url_scheme(parsed):
                result.update(error)
                return result
            if error := self._validate_url_hostname(parsed):
                result.update(error)
                return result
            if error := self._check_dangerous_url_patterns(url):
                result.update(error)
                return result

            self._check_url_length(url, result)
            self._check_suspicious_url_patterns(url, result)

            result["metadata"]["parsed"] = {
                "scheme": parsed.scheme, "hostname": parsed.hostname,
                "port": parsed.port, "path": parsed.path[:100],
            }
            return result
        except Exception as e:
            logger.error("Error validating URL %s: %s", url, e)
            return {
                "safe": False, "sanitized_url": "", "threats_detected": ["URL_VALIDATION_ERROR"],
                "warnings": [f"Validation error: {str(e)}"], "metadata": {},
            }

    def _create_content_result(self, content: str) -> Dict[str, Any]:
        """Create initial content sanitization result structure."""
        return {
            "safe": True, "sanitized_content": content, "threats_detected": [],
            "warnings": [], "metadata": {"original_length": len(content)},
        }

    def _validate_content_type(self, content_type: str, result: Dict) -> None:
        """Validate content type. Updates result warnings."""
        if content_type not in self.SAFE_CONTENT_TYPES:
            result["warnings"].append(f"Potentially unsafe content type: {content_type}")

    def _truncate_content(self, content: str, result: Dict, max_length: int = 1_000_000) -> str:
        """Truncate content if too long. Updates result warnings."""
        if len(content) > max_length:
            result["warnings"].append(f"Content truncated from {len(content)} to {max_length} chars")
            return content[:max_length]
        return content

    def _remove_script_tags(self, content: str, result: Dict) -> str:
        """Remove dangerous script tags. Updates result metadata."""
        # Use pre-compiled pattern (Issue #380)
        scripts_removed = len(_SCRIPT_TAG_RE.findall(content))
        if scripts_removed > 0:
            content = _SCRIPT_TAG_RE.sub("", content)
            result["threats_detected"].append("SCRIPT_TAGS_REMOVED")
            result["metadata"]["scripts_removed"] = scripts_removed
        return content

    def _remove_event_handlers(self, content: str, result: Dict) -> str:
        """Remove dangerous event handlers. Updates result metadata."""
        # Use pre-compiled pattern (Issue #380)
        events_removed = len(_EVENT_HANDLER_RE.findall(content))
        if events_removed > 0:
            content = _EVENT_HANDLER_RE.sub("", content)
            result["threats_detected"].append("EVENT_HANDLERS_REMOVED")
            result["metadata"]["events_removed"] = events_removed
        return content

    def _remove_dangerous_links(self, content: str, result: Dict) -> str:
        """Remove dangerous links. Updates result metadata."""
        # Use pre-compiled pattern (Issue #380)
        dangerous_links = len(_DANGEROUS_LINK_RE.findall(content))
        if dangerous_links > 0:
            content = _DANGEROUS_LINK_RE.sub('href="#"', content)
            result["threats_detected"].append("DANGEROUS_LINKS_REMOVED")
            result["metadata"]["dangerous_links_removed"] = dangerous_links
        return content

    def _encode_dangerous_patterns(self, content: str, content_type: str, result: Dict) -> str:
        """Encode remaining dangerous patterns in HTML. Updates result warnings."""
        if content_type != "text/html":
            return content
        dangerous_chars = ["<script", "</script", "javascript:", "vbscript:", "onload=", "onclick=", "onerror="]
        for char_pattern in dangerous_chars:
            if char_pattern in content.lower():
                content = content.replace(char_pattern, html.escape(char_pattern))
                result["warnings"].append(f"Encoded dangerous pattern: {char_pattern}")
        return content

    def _check_remaining_threats(self, content: str, result: Dict) -> None:
        """Check for remaining suspicious patterns. Updates result warnings."""
        remaining_threats = [p.pattern for p in self.dangerous_pattern_compiled[:10] if p.search(content)]
        if remaining_threats:
            result["warnings"].append(f"Suspicious patterns still present after sanitization: {len(remaining_threats)}")
            result["metadata"]["remaining_threats"] = remaining_threats[:3]

    def sanitize_web_content(self, content: str, content_type: str = "text/html") -> Dict[str, Any]:
        """Sanitize web content before processing or storage."""
        result = self._create_content_result(content)
        try:
            if not content:
                return result

            self._validate_content_type(content_type, result)
            content = self._truncate_content(content, result)

            # Apply sanitization chain
            sanitized = self._remove_script_tags(content, result)
            sanitized = self._remove_event_handlers(sanitized, result)
            sanitized = self._remove_dangerous_links(sanitized, result)
            sanitized = self._encode_dangerous_patterns(sanitized, content_type, result)
            self._check_remaining_threats(sanitized, result)

            result["sanitized_content"] = sanitized
            result["metadata"]["final_length"] = len(sanitized)
            result["metadata"]["size_reduction"] = len(content) - len(sanitized)

            if result["threats_detected"]:
                result["safe"] = len(result["threats_detected"]) <= 2
            return result
        except Exception as e:
            logger.error("Error sanitizing web content: %s", e)
            return {
                "safe": False, "sanitized_content": "", "threats_detected": ["SANITIZATION_ERROR"],
                "warnings": [f"Sanitization failed: {str(e)}"], "metadata": {"original_length": len(content)},
            }

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text"""
        # Use pre-compiled pattern (Issue #380)
        return _URL_EXTRACT_RE.findall(text)

    def _validate_url_in_query(self, url: str) -> Dict[str, Any]:
        """Validate a URL found within a query"""
        return self.validate_url(url)

    def _sanitize_query(self, query: str) -> str:
        """Basic query sanitization"""
        # Remove null bytes
        sanitized = query.replace("\x00", "")

        # Remove excessive whitespace using pre-compiled pattern (Issue #380)
        sanitized = _WHITESPACE_RE.sub(" ", sanitized)

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


# Create default validator instance (thread-safe)
import threading

_default_validator = None
_default_validator_lock = threading.Lock()


def get_input_validator() -> WebResearchInputValidator:
    """Get shared input validator instance (thread-safe)"""
    global _default_validator
    if _default_validator is None:
        with _default_validator_lock:
            # Double-check after acquiring lock
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
