# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security constants, enums, and OWASP mappings.

Issue #712: Extracted from security_analyzer.py for modularity.
"""

from enum import Enum
from typing import FrozenSet

# Performance optimization: O(1) lookup for placeholder patterns (Issue #326)
PLACEHOLDER_PATTERNS = {"example", "placeholder", "your_", "xxx", "changeme", "todo"}

# Issue #380: Module-level frozensets for security pattern checking
HTTP_METHODS: FrozenSet[str] = frozenset(
    {"get", "post", "put", "delete", "patch", "route"}
)
INSECURE_RANDOM_FUNCS: FrozenSet[str] = frozenset(
    {"random", "randint", "choice", "shuffle"}
)
PICKLE_MODULES: FrozenSet[str] = frozenset({"pickle", "cPickle"})
YAML_LOADER_ARGS: FrozenSet[str] = frozenset({"Loader", "SafeLoader"})
DEBUG_MODE_VARS: FrozenSet[str] = frozenset({"DEBUG", "DEBUG_MODE"})
LOAD_FUNCS: FrozenSet[str] = frozenset({"load", "loads"})
VALIDATION_FUNCS: FrozenSet[str] = frozenset({"validate", "Validator", "Schema"})
VALIDATION_ATTRS: FrozenSet[str] = frozenset(
    {"validate", "parse_obj", "model_validate"}
)


class SecuritySeverity(Enum):
    """Severity levels for security findings (aligned with CVSS)."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VulnerabilityType(Enum):
    """Types of security vulnerabilities detected."""

    # Injection vulnerabilities (OWASP A03:2021)
    SQL_INJECTION = "sql_injection"
    NOSQL_INJECTION = "nosql_injection"
    COMMAND_INJECTION = "command_injection"
    LDAP_INJECTION = "ldap_injection"
    XPATH_INJECTION = "xpath_injection"
    TEMPLATE_INJECTION = "template_injection"

    # Sensitive Data Exposure (OWASP A02:2021)
    HARDCODED_SECRET = "hardcoded_secret"
    HARDCODED_PASSWORD = "hardcoded_password"
    HARDCODED_API_KEY = "hardcoded_api_key"
    HARDCODED_TOKEN = "hardcoded_token"
    SENSITIVE_DATA_LOGGING = "sensitive_data_logging"
    UNENCRYPTED_STORAGE = "unencrypted_storage"

    # Cryptographic Failures (OWASP A02:2021)
    WEAK_HASH_ALGORITHM = "weak_hash_algorithm"
    WEAK_ENCRYPTION = "weak_encryption"
    INSECURE_RANDOM = "insecure_random"
    MISSING_SALT = "missing_salt"
    WEAK_KEY_SIZE = "weak_key_size"

    # Broken Access Control (OWASP A01:2021)
    MISSING_AUTH_CHECK = "missing_auth_check"
    INSECURE_DIRECT_OBJECT_REF = "insecure_direct_object_ref"
    PATH_TRAVERSAL = "path_traversal"
    PRIVILEGE_ESCALATION_RISK = "privilege_escalation_risk"

    # Security Misconfiguration (OWASP A05:2021)
    DEBUG_MODE_ENABLED = "debug_mode_enabled"
    INSECURE_CORS = "insecure_cors"
    MISSING_SECURITY_HEADERS = "missing_security_headers"
    DEFAULT_CREDENTIALS = "default_credentials"

    # XSS and CSRF (OWASP A03:2021)
    XSS_VULNERABILITY = "xss_vulnerability"
    MISSING_CSRF_PROTECTION = "missing_csrf_protection"
    UNSAFE_REDIRECT = "unsafe_redirect"

    # Insecure Deserialization (OWASP A08:2021)
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    PICKLE_USAGE = "pickle_usage"
    YAML_LOAD_UNSAFE = "yaml_load_unsafe"

    # Input Validation
    MISSING_INPUT_VALIDATION = "missing_input_validation"
    REGEX_DOS = "regex_dos"
    INTEGER_OVERFLOW_RISK = "integer_overflow_risk"

    # Authentication Issues
    WEAK_PASSWORD_POLICY = "weak_password_policy"
    MISSING_RATE_LIMITING = "missing_rate_limiting"
    SESSION_FIXATION_RISK = "session_fixation_risk"
    JWT_WEAK_SECRET = "jwt_weak_secret"
    JWT_NO_EXPIRY = "jwt_no_expiry"


# OWASP Top 10 2021 Mapping
OWASP_MAPPING = {
    VulnerabilityType.SQL_INJECTION: "A03:2021-Injection",
    VulnerabilityType.NOSQL_INJECTION: "A03:2021-Injection",
    VulnerabilityType.COMMAND_INJECTION: "A03:2021-Injection",
    VulnerabilityType.LDAP_INJECTION: "A03:2021-Injection",
    VulnerabilityType.XPATH_INJECTION: "A03:2021-Injection",
    VulnerabilityType.TEMPLATE_INJECTION: "A03:2021-Injection",
    VulnerabilityType.XSS_VULNERABILITY: "A03:2021-Injection",
    VulnerabilityType.HARDCODED_SECRET: "A02:2021-Cryptographic Failures",
    VulnerabilityType.HARDCODED_PASSWORD: "A02:2021-Cryptographic Failures",
    VulnerabilityType.HARDCODED_API_KEY: "A02:2021-Cryptographic Failures",
    VulnerabilityType.HARDCODED_TOKEN: "A02:2021-Cryptographic Failures",
    VulnerabilityType.SENSITIVE_DATA_LOGGING: "A02:2021-Cryptographic Failures",
    VulnerabilityType.UNENCRYPTED_STORAGE: "A02:2021-Cryptographic Failures",
    VulnerabilityType.WEAK_HASH_ALGORITHM: "A02:2021-Cryptographic Failures",
    VulnerabilityType.WEAK_ENCRYPTION: "A02:2021-Cryptographic Failures",
    VulnerabilityType.INSECURE_RANDOM: "A02:2021-Cryptographic Failures",
    VulnerabilityType.MISSING_SALT: "A02:2021-Cryptographic Failures",
    VulnerabilityType.WEAK_KEY_SIZE: "A02:2021-Cryptographic Failures",
    VulnerabilityType.MISSING_AUTH_CHECK: "A01:2021-Broken Access Control",
    VulnerabilityType.INSECURE_DIRECT_OBJECT_REF: "A01:2021-Broken Access Control",
    VulnerabilityType.PATH_TRAVERSAL: "A01:2021-Broken Access Control",
    VulnerabilityType.PRIVILEGE_ESCALATION_RISK: "A01:2021-Broken Access Control",
    VulnerabilityType.DEBUG_MODE_ENABLED: "A05:2021-Security Misconfiguration",
    VulnerabilityType.INSECURE_CORS: "A05:2021-Security Misconfiguration",
    VulnerabilityType.MISSING_SECURITY_HEADERS: "A05:2021-Security Misconfiguration",
    VulnerabilityType.DEFAULT_CREDENTIALS: "A05:2021-Security Misconfiguration",
    VulnerabilityType.MISSING_CSRF_PROTECTION: "A05:2021-Security Misconfiguration",
    VulnerabilityType.UNSAFE_REDIRECT: "A05:2021-Security Misconfiguration",
    VulnerabilityType.INSECURE_DESERIALIZATION: "A08:2021-Software and Data Integrity",
    VulnerabilityType.PICKLE_USAGE: "A08:2021-Software and Data Integrity",
    VulnerabilityType.YAML_LOAD_UNSAFE: "A08:2021-Software and Data Integrity",
    VulnerabilityType.MISSING_INPUT_VALIDATION: "A03:2021-Injection",
    VulnerabilityType.REGEX_DOS: "A03:2021-Injection",
    VulnerabilityType.INTEGER_OVERFLOW_RISK: "A03:2021-Injection",
    VulnerabilityType.WEAK_PASSWORD_POLICY: "A07:2021-Identification and Authentication",
    VulnerabilityType.MISSING_RATE_LIMITING: "A07:2021-Identification and Authentication",
    VulnerabilityType.SESSION_FIXATION_RISK: "A07:2021-Identification and Authentication",
    VulnerabilityType.JWT_WEAK_SECRET: "A07:2021-Identification and Authentication",
    VulnerabilityType.JWT_NO_EXPIRY: "A07:2021-Identification and Authentication",
}

# Weak hash algorithms
WEAK_HASH_ALGORITHMS = {
    "md5": ("MD5 is cryptographically broken", "CWE-328"),
    "sha1": ("SHA1 is deprecated for security purposes", "CWE-328"),
    "sha": ("Plain SHA is deprecated", "CWE-328"),
}

# Weak encryption algorithms
WEAK_ENCRYPTION = {
    "des": ("DES is insecure, use AES", "CWE-327"),
    "3des": ("3DES is deprecated, use AES", "CWE-327"),
    "rc4": ("RC4 is broken, use AES-GCM", "CWE-327"),
    "blowfish": ("Blowfish has known weaknesses, use AES", "CWE-327"),
}
