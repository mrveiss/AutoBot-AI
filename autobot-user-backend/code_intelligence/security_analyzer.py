# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Pattern Analyzer

Detects security vulnerabilities through pattern analysis including:
- SQL injection patterns
- Hardcoded secrets and credentials
- Weak cryptography usage
- Input validation gaps
- Authentication/authorization issues
- OWASP Top 10 vulnerability mapping

Part of Issue #219 - Security Pattern Analyzer
Issue #554 - Added Vector/Redis/LLM infrastructure for semantic analysis
Parent Epic: #217 - Advanced Code Intelligence
"""

import ast
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set

# Issue #554: Import analytics infrastructure for semantic analysis
try:
    from src.code_intelligence.analytics_infrastructure import (
        SIMILARITY_MEDIUM,
        SemanticAnalysisMixin,
    )

    HAS_ANALYTICS_INFRASTRUCTURE = True
except ImportError:
    HAS_ANALYTICS_INFRASTRUCTURE = False
    SemanticAnalysisMixin = object  # Fallback to object if not available

# Issue #607: Import shared caches for performance optimization
try:
    from src.code_intelligence.shared.ast_cache import get_ast_with_content

    HAS_SHARED_CACHE = True
except ImportError:
    HAS_SHARED_CACHE = False

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for placeholder patterns (Issue #326)
PLACEHOLDER_PATTERNS = {"example", "placeholder", "your_", "xxx", "changeme", "todo"}

# Issue #380: Module-level frozensets for security pattern checking
_HTTP_METHODS: FrozenSet[str] = frozenset(
    {"get", "post", "put", "delete", "patch", "route"}
)
_INSECURE_RANDOM_FUNCS: FrozenSet[str] = frozenset(
    {"random", "randint", "choice", "shuffle"}
)
_PICKLE_MODULES: FrozenSet[str] = frozenset({"pickle", "cPickle"})
_YAML_LOADER_ARGS: FrozenSet[str] = frozenset({"Loader", "SafeLoader"})
_DEBUG_MODE_VARS: FrozenSet[str] = frozenset({"DEBUG", "DEBUG_MODE"})
_LOAD_FUNCS: FrozenSet[str] = frozenset({"load", "loads"})  # Issue #380
_VALIDATION_FUNCS: FrozenSet[str] = frozenset({"validate", "Validator", "Schema"})
_VALIDATION_ATTRS: FrozenSet[str] = frozenset(
    {"validate", "parse_obj", "model_validate"}
)


class SecuritySeverity(Enum):
    """Severity levels for security findings (aligned with CVSS)."""

    INFO = "info"  # Informational, no immediate risk
    LOW = "low"  # Minor security concern
    MEDIUM = "medium"  # Moderate security risk
    HIGH = "high"  # Serious security vulnerability
    CRITICAL = "critical"  # Severe, requires immediate action


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
    # nosec B105 - These are vulnerability TYPE NAMES, not actual secrets
    HARDCODED_SECRET = "hardcoded_secret"  # nosec B105
    HARDCODED_PASSWORD = "hardcoded_password"  # nosec B105
    HARDCODED_API_KEY = "hardcoded_api_key"  # nosec B105
    HARDCODED_TOKEN = "hardcoded_token"  # nosec B105
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
    # nosec B105 - These are vulnerability TYPE NAMES, not actual secrets
    WEAK_PASSWORD_POLICY = "weak_password_policy"  # nosec B105
    MISSING_RATE_LIMITING = "missing_rate_limiting"
    SESSION_FIXATION_RISK = "session_fixation_risk"
    JWT_WEAK_SECRET = "jwt_weak_secret"  # nosec B105
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


@dataclass
class SecurityFinding:
    """Result of security analysis for a single finding."""

    vulnerability_type: VulnerabilityType
    severity: SecuritySeverity
    file_path: str
    line_start: int
    line_end: int
    description: str
    recommendation: str
    owasp_category: str
    cwe_id: Optional[str] = None
    current_code: str = ""
    secure_alternative: str = ""
    confidence: float = 1.0  # 0.0-1.0, how confident we are in this finding
    false_positive_risk: str = "low"  # low, medium, high
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to dictionary for API responses."""
        return {
            "vulnerability_type": self.vulnerability_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "description": self.description,
            "recommendation": self.recommendation,
            "owasp_category": self.owasp_category,
            "cwe_id": self.cwe_id,
            "current_code": self.current_code,
            "secure_alternative": self.secure_alternative,
            "confidence": self.confidence,
            "false_positive_risk": self.false_positive_risk,
            "references": self.references,
        }


# Patterns for detecting hardcoded secrets
SECRET_PATTERNS = [
    # API Keys
    (
        r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{16,}["\']',
        VulnerabilityType.HARDCODED_API_KEY,
        "CWE-798",
    ),
    # AWS Keys
    (
        r'(?i)(aws[_-]?access[_-]?key[_-]?id)\s*[=:]\s*["\']AKIA[A-Z0-9]{16}["\']',
        VulnerabilityType.HARDCODED_API_KEY,
        "CWE-798",
    ),
    (
        r'(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[=:]\s*["\'][a-zA-Z0-9/+=]{40}["\']',
        VulnerabilityType.HARDCODED_SECRET,
        "CWE-798",
    ),
    # Generic secrets
    (
        r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{16,}["\']',
        VulnerabilityType.HARDCODED_SECRET,
        "CWE-798",
    ),
    # Passwords
    (
        r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{4,}["\']',
        VulnerabilityType.HARDCODED_PASSWORD,
        "CWE-259",
    ),
    # Tokens
    (
        r'(?i)(token|auth[_-]?token|access[_-]?token|bearer)\s*[=:]\s*["\'][a-zA-Z0-9_\-\.]{20,}["\']',
        VulnerabilityType.HARDCODED_TOKEN,
        "CWE-798",
    ),
    # Private keys
    (
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        VulnerabilityType.HARDCODED_SECRET,
        "CWE-321",
    ),
    # Database connection strings with credentials
    (
        r"(?i)(mongodb|postgresql|mysql|redis)://[^:]+:[^@]+@",
        VulnerabilityType.HARDCODED_PASSWORD,
        "CWE-259",
    ),
    # JWT secrets
    (
        r'(?i)(jwt[_-]?secret|signing[_-]?key)\s*[=:]\s*["\'][^"\']{8,}["\']',
        VulnerabilityType.JWT_WEAK_SECRET,
        "CWE-347",
    ),
]

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

# SQL injection patterns
SQL_INJECTION_PATTERNS = [
    # String formatting in SQL
    (r'execute\s*\(\s*["\'].*%s.*["\']', "String formatting in SQL query"),
    (r'execute\s*\(\s*f["\']', "f-string in SQL query"),
    (r'execute\s*\(\s*["\'].*\+.*["\']', "String concatenation in SQL query"),
    # cursor.execute with format
    (r'cursor\.execute\s*\(\s*["\'].*\.format\s*\(', "format() in SQL query"),
    # Raw queries with user input
    (r'raw\s*\(\s*f["\']', "f-string in raw SQL"),
    (r"rawquery.*%", "String interpolation in raw query"),
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    (r"os\.system\s*\(\s*f[\"']", "f-string in os.system()"),
    (r"os\.system\s*\(\s*[^)]*\+", "String concatenation in os.system()"),
    (r"subprocess\.\w+\s*\(\s*f[\"']", "f-string in subprocess call"),
    (r"subprocess\.\w+\s*\([^)]*shell\s*=\s*True", "shell=True in subprocess"),
    (r"os\.popen\s*\(\s*f[\"']", "f-string in os.popen()"),
    (r'eval\s*\(\s*[^)"\']+\)', "eval() with variable input"),
    (r"exec\s*\(\s*[^)\"']+\)", "exec() with variable input"),
]


class SecurityASTVisitor(ast.NodeVisitor):
    """AST visitor for security pattern analysis."""

    def __init__(self, file_path: str, source_lines: List[str]):
        """Initialize AST visitor with file context and tracking state."""
        self.file_path = file_path
        self.source_lines = source_lines
        self.findings: List[SecurityFinding] = []
        self.imports: Set[str] = set()
        self.function_context: Optional[str] = None
        self.class_context: Optional[str] = None
        self.has_input_validation: Dict[str, bool] = {}

    def visit_Import(self, node: ast.Import) -> None:
        """Track imports for context."""
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track from imports."""
        if node.module:
            self.imports.add(node.module.split(".")[0])
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Analyze function definitions."""
        old_context = self.function_context
        self.function_context = node.name
        self._check_function_security(node)
        self.generic_visit(node)
        self.function_context = old_context

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Analyze async function definitions."""
        old_context = self.function_context
        self.function_context = node.name
        self._check_function_security(node)
        self.generic_visit(node)
        self.function_context = old_context

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class context."""
        old_context = self.class_context
        self.class_context = node.name
        self.generic_visit(node)
        self.class_context = old_context

    def visit_Call(self, node: ast.Call) -> None:
        """Analyze function calls for security issues."""
        self._check_dangerous_calls(node)
        self._check_crypto_usage(node)
        self._check_deserialization(node)
        self._check_subprocess_usage(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Check assignments for security issues."""
        self._check_debug_settings(node)
        self.generic_visit(node)

    def _check_function_security(self, node) -> None:
        """Check function for security patterns."""
        # Check for missing input validation in web handlers
        if self._is_web_handler(node):
            self._check_input_validation(node)

    def _is_web_handler(self, node) -> bool:
        """Check if function is a web request handler."""
        # Check for FastAPI/Flask decorators
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Attribute):
                    if func.attr in _HTTP_METHODS:
                        return True
            elif isinstance(decorator, ast.Attribute):
                if decorator.attr in _HTTP_METHODS:
                    return True
        return False

    def _has_validation_call(self, node) -> bool:
        """Check if node has validation call patterns (Issue #335 - extracted helper)."""
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name) and func.id in _VALIDATION_FUNCS:
                return True  # Issue #380: use module constant
            if isinstance(func, ast.Attribute) and func.attr in _VALIDATION_ATTRS:
                return True  # Issue #380: use module constant
        return False

    def _has_type_annotations(self, node) -> bool:
        """Check if function has type annotations (Issue #335 - extracted helper)."""
        return any(arg.annotation for arg in node.args.args)

    def _check_input_validation(self, node) -> None:
        """Check if web handler validates input."""
        has_validation = self._has_validation_call(node) or self._has_type_annotations(
            node
        )

        if not has_validation:
            code = self._get_source_segment(node.lineno, node.end_lineno or node.lineno)
            self.findings.append(
                SecurityFinding(
                    vulnerability_type=VulnerabilityType.MISSING_INPUT_VALIDATION,
                    severity=SecuritySeverity.MEDIUM,
                    file_path=self.file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    description=f"Web handler '{node.name}' may lack input validation",
                    recommendation="Use Pydantic models or validation decorators",
                    owasp_category=OWASP_MAPPING[
                        VulnerabilityType.MISSING_INPUT_VALIDATION
                    ],
                    cwe_id="CWE-20",
                    current_code=code,
                    secure_alternative="Use Pydantic BaseModel for request validation",
                    confidence=0.7,
                    false_positive_risk="medium",
                )
            )

    def _check_dangerous_calls(self, node: ast.Call) -> None:
        """Check for dangerous function calls."""
        func = node.func

        # Check eval/exec
        if isinstance(func, ast.Name):
            if func.id == "eval":
                self._add_injection_finding(
                    node, "eval()", VulnerabilityType.COMMAND_INJECTION, "CWE-95"
                )
            elif func.id == "exec":
                self._add_injection_finding(
                    node, "exec()", VulnerabilityType.COMMAND_INJECTION, "CWE-95"
                )
            elif func.id == "compile":
                # compile() can be dangerous with user input
                self._add_injection_finding(
                    node,
                    "compile()",
                    VulnerabilityType.COMMAND_INJECTION,
                    "CWE-95",
                    severity=SecuritySeverity.MEDIUM,
                    confidence=0.6,
                )

        # Check os.system, os.popen
        elif isinstance(func, ast.Attribute):
            if func.attr == "system" and self._get_module_name(func) == "os":
                self._check_command_injection(node, "os.system()")
            elif func.attr == "popen" and self._get_module_name(func) == "os":
                self._check_command_injection(node, "os.popen()")

    def _check_crypto_usage(self, node: ast.Call) -> None:
        """Check for weak cryptographic usage."""
        func = node.func

        if isinstance(func, ast.Attribute):
            # Check hashlib usage
            if func.attr in WEAK_HASH_ALGORITHMS:
                msg, cwe = WEAK_HASH_ALGORITHMS[func.attr]
                code = self._get_source_segment(node.lineno, node.lineno)
                self.findings.append(
                    SecurityFinding(
                        vulnerability_type=VulnerabilityType.WEAK_HASH_ALGORITHM,
                        severity=SecuritySeverity.MEDIUM,
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.lineno,
                        description=f"Weak hash algorithm: {func.attr}. {msg}",
                        recommendation="Use SHA-256 or SHA-3 for hashing, bcrypt/argon2 for passwords",
                        owasp_category=OWASP_MAPPING[
                            VulnerabilityType.WEAK_HASH_ALGORITHM
                        ],
                        cwe_id=cwe,
                        current_code=code,
                        secure_alternative="hashlib.sha256() or bcrypt.hashpw()",
                        confidence=0.9,
                    )
                )

            # Check for random module (not cryptographically secure)
            if func.attr in _INSECURE_RANDOM_FUNCS:
                module = self._get_module_name(func)
                if module == "random":
                    code = self._get_source_segment(node.lineno, node.lineno)
                    self.findings.append(
                        SecurityFinding(
                            vulnerability_type=VulnerabilityType.INSECURE_RANDOM,
                            severity=SecuritySeverity.LOW,
                            file_path=self.file_path,
                            line_start=node.lineno,
                            line_end=node.lineno,
                            description="random module is not cryptographically secure",
                            recommendation="Use secrets module for security-sensitive randomness",
                            owasp_category=OWASP_MAPPING[
                                VulnerabilityType.INSECURE_RANDOM
                            ],
                            cwe_id="CWE-330",
                            current_code=code,
                            secure_alternative="secrets.token_hex() or secrets.randbelow()",
                            confidence=0.7,
                            false_positive_risk="medium",
                        )
                    )

    def _check_deserialization(self, node: ast.Call) -> None:
        """Check for insecure deserialization."""
        func = node.func

        if isinstance(func, ast.Attribute):
            # Pickle is dangerous
            if (
                func.attr in _LOAD_FUNCS
                and self._get_module_name(func) in _PICKLE_MODULES
            ):
                code = self._get_source_segment(node.lineno, node.lineno)
                self.findings.append(
                    SecurityFinding(
                        vulnerability_type=VulnerabilityType.PICKLE_USAGE,
                        severity=SecuritySeverity.HIGH,
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.lineno,
                        description="pickle.load()/loads() can execute arbitrary code",
                        recommendation="Use JSON or other safe serialization formats",
                        owasp_category=OWASP_MAPPING[VulnerabilityType.PICKLE_USAGE],
                        cwe_id="CWE-502",
                        current_code=code,
                        secure_alternative="json.loads() for data, or use hmac to verify pickle integrity",
                        confidence=0.95,
                    )
                )

            # yaml.load without Loader
            if func.attr == "load" and self._get_module_name(func) == "yaml":
                # Check if safe_load or Loader is specified
                has_loader = any(kw.arg in _YAML_LOADER_ARGS for kw in node.keywords)
                if not has_loader:
                    code = self._get_source_segment(node.lineno, node.lineno)
                    self.findings.append(
                        SecurityFinding(
                            vulnerability_type=VulnerabilityType.YAML_LOAD_UNSAFE,
                            severity=SecuritySeverity.HIGH,
                            file_path=self.file_path,
                            line_start=node.lineno,
                            line_end=node.lineno,
                            description="yaml.load() without SafeLoader can execute arbitrary code",
                            recommendation="Use yaml.safe_load() or specify Loader=yaml.SafeLoader",
                            owasp_category=OWASP_MAPPING[
                                VulnerabilityType.YAML_LOAD_UNSAFE
                            ],
                            cwe_id="CWE-502",
                            current_code=code,
                            secure_alternative="yaml.safe_load(data) or yaml.load(data, Loader=yaml.SafeLoader)",
                            confidence=0.9,
                        )
                    )

    def _check_subprocess_usage(self, node: ast.Call) -> None:
        """Check subprocess calls for command injection."""
        func = node.func

        if isinstance(func, ast.Attribute):
            module = self._get_module_name(func)
            if module == "subprocess":
                # Check for shell=True
                for kw in node.keywords:
                    if kw.arg == "shell" and self._is_truthy(kw.value):
                        code = self._get_source_segment(node.lineno, node.lineno)
                        self.findings.append(
                            SecurityFinding(
                                vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
                                severity=SecuritySeverity.HIGH,
                                file_path=self.file_path,
                                line_start=node.lineno,
                                line_end=node.lineno,
                                description="subprocess with shell=True is vulnerable to injection",
                                recommendation="Use shell=False and pass command as list",
                                owasp_category=OWASP_MAPPING[
                                    VulnerabilityType.COMMAND_INJECTION
                                ],
                                cwe_id="CWE-78",
                                current_code=code,
                                secure_alternative="subprocess.run(['cmd', 'arg1', 'arg2'], shell=False)",
                                confidence=0.85,
                            )
                        )
                        break

    def _check_debug_settings(self, node: ast.Assign) -> None:
        """Check for debug mode enabled."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                if target.id.upper() in _DEBUG_MODE_VARS:
                    if self._is_truthy(node.value):
                        code = self._get_source_segment(node.lineno, node.lineno)
                        self.findings.append(
                            SecurityFinding(
                                vulnerability_type=VulnerabilityType.DEBUG_MODE_ENABLED,
                                severity=SecuritySeverity.MEDIUM,
                                file_path=self.file_path,
                                line_start=node.lineno,
                                line_end=node.lineno,
                                description="Debug mode appears to be enabled",
                                recommendation="Disable debug mode in production",
                                owasp_category=OWASP_MAPPING[
                                    VulnerabilityType.DEBUG_MODE_ENABLED
                                ],
                                cwe_id="CWE-489",
                                current_code=code,
                                secure_alternative="DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'",
                                confidence=0.7,
                                false_positive_risk="medium",
                            )
                        )

    def _add_injection_finding(
        self,
        node: ast.Call,
        function_name: str,
        vuln_type: VulnerabilityType,
        cwe_id: str,
        severity: SecuritySeverity = SecuritySeverity.CRITICAL,
        confidence: float = 0.9,
    ) -> None:
        """Add an injection vulnerability finding."""
        code = self._get_source_segment(node.lineno, node.lineno)
        self.findings.append(
            SecurityFinding(
                vulnerability_type=vuln_type,
                severity=severity,
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=node.lineno,
                description=f"Dangerous function {function_name} detected",
                recommendation=f"Avoid using {function_name} with user input",
                owasp_category=OWASP_MAPPING[vuln_type],
                cwe_id=cwe_id,
                current_code=code,
                confidence=confidence,
            )
        )

    def _check_command_injection(self, node: ast.Call, function_name: str) -> None:
        """Check if command execution is vulnerable to injection."""
        # Check if first argument contains f-string or format
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.JoinedStr):  # f-string
                code = self._get_source_segment(node.lineno, node.lineno)
                self.findings.append(
                    SecurityFinding(
                        vulnerability_type=VulnerabilityType.COMMAND_INJECTION,
                        severity=SecuritySeverity.CRITICAL,
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.lineno,
                        description=f"f-string in {function_name} is vulnerable to command injection",
                        recommendation="Use subprocess.run() with list arguments",
                        owasp_category=OWASP_MAPPING[
                            VulnerabilityType.COMMAND_INJECTION
                        ],
                        cwe_id="CWE-78",
                        current_code=code,
                        secure_alternative="subprocess.run(['cmd', arg], shell=False)",
                        confidence=0.95,
                    )
                )

    def _get_module_name(self, node: ast.Attribute) -> Optional[str]:
        """Get module name from attribute access."""
        if isinstance(node.value, ast.Name):
            return node.value.id
        elif isinstance(node.value, ast.Attribute):
            return self._get_module_name(node.value)
        return None

    def _is_truthy(self, node: ast.expr) -> bool:
        """Check if AST node represents a truthy value."""
        if isinstance(node, ast.Constant):
            return bool(node.value)
        elif isinstance(node, ast.NameConstant):  # Python 3.7
            return bool(node.value)
        elif isinstance(node, ast.Name):
            return node.id.lower() == "true"
        return False

    def _get_source_segment(self, start: int, end: int) -> str:
        """Get source code for line range."""
        try:
            if start > 0 and start <= len(self.source_lines):
                lines = self.source_lines[start - 1 : end]
                return "\n".join(lines)
        except Exception:
            pass  # nosec B110 - Intentionally return empty for invalid ranges
        return ""


class SecurityAnalyzer(SemanticAnalysisMixin):
    """
    Main security pattern analyzer.

    Issue #554: Now includes optional semantic analysis via ChromaDB/Redis/LLM
    infrastructure for detecting semantically similar security vulnerabilities.
    """

    def __init__(
        self,
        project_root: Optional[str] = None,
        exclude_patterns: Optional[List[str]] = None,
        use_semantic_analysis: bool = False,
        use_cache: bool = True,
        use_shared_cache: bool = True,
    ):
        """
        Initialize security analyzer with project root and exclusion patterns.

        Args:
            project_root: Root directory for analysis
            exclude_patterns: Patterns to exclude from analysis
            use_semantic_analysis: Whether to use LLM-based semantic analysis (Issue #554)
            use_cache: Whether to use Redis caching for results (Issue #554)
            use_shared_cache: Whether to use shared FileListCache/ASTCache (Issue #607)
        """
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.exclude_patterns = exclude_patterns or [
            "venv",
            "node_modules",
            ".git",
            "__pycache__",
            "*.pyc",
            "test_*",
            "*_test.py",
            "archives",
            "migrations",
        ]
        self.results: List[SecurityFinding] = []
        self.total_files_scanned: int = 0  # Issue #686: Track total files analyzed
        self.use_semantic_analysis = (
            use_semantic_analysis and HAS_ANALYTICS_INFRASTRUCTURE
        )
        self.use_shared_cache = use_shared_cache and HAS_SHARED_CACHE

        # Issue #554: Initialize analytics infrastructure if semantic analysis enabled
        if self.use_semantic_analysis:
            self._init_infrastructure(
                collection_name="security_analysis_vectors",
                use_llm=True,
                use_cache=use_cache,
                redis_database="analytics",
            )

    def analyze_file(self, file_path: str) -> List[SecurityFinding]:
        """
        Analyze a single file for security vulnerabilities.

        Issue #607: Uses shared ASTCache when available for performance.
        """
        findings: List[SecurityFinding] = []
        path = Path(file_path)

        if not path.exists() or not path.suffix == ".py":
            return findings

        try:
            # Issue #607: Use shared AST cache if available
            if self.use_shared_cache:
                tree, content = get_ast_with_content(file_path)
                lines = content.split("\n") if content else []
            else:
                content = path.read_text(encoding="utf-8")
                lines = content.split("\n")
                try:
                    tree = ast.parse(content)
                except SyntaxError:
                    tree = None

            # AST-based analysis
            if tree is not None:
                visitor = SecurityASTVisitor(str(path), lines)
                visitor.visit(tree)
                findings.extend(visitor.findings)
            else:
                logger.warning("Syntax error in %s, skipping AST analysis", file_path)

            # Regex-based analysis for patterns AST can't catch
            if content:
                findings.extend(self._regex_analysis(str(path), content, lines))

        except Exception as e:
            logger.error("Error analyzing %s: %s", file_path, e)

        return findings

    def _check_hardcoded_secrets(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Check for hardcoded secrets (Issue #665: extracted helper)."""
        findings: List[SecurityFinding] = []

        for pattern, vuln_type, cwe_id in SECRET_PATTERNS:
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                code = lines[line_num - 1] if line_num <= len(lines) else ""

                # Skip environment variable lookups
                if "os.getenv" in code or "os.environ" in code:
                    continue
                # Skip placeholders/examples (O(1) lookup - Issue #326)
                if any(p in match.group().lower() for p in PLACEHOLDER_PATTERNS):
                    continue

                findings.append(
                    SecurityFinding(
                        vulnerability_type=vuln_type,
                        severity=SecuritySeverity.HIGH,
                        file_path=file_path,
                        line_start=line_num,
                        line_end=line_num,
                        description="Potential hardcoded credential detected",
                        recommendation="Use environment variables or secrets manager",
                        owasp_category=OWASP_MAPPING[vuln_type],
                        cwe_id=cwe_id,
                        current_code=code.strip(),
                        secure_alternative="os.getenv('SECRET_NAME') or use secrets manager",
                        confidence=0.8,
                        false_positive_risk="medium",
                    )
                )

        return findings

    def _check_sql_injection(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Check for SQL injection patterns (Issue #665: extracted helper)."""
        findings: List[SecurityFinding] = []

        for pattern, description in SQL_INJECTION_PATTERNS:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[: match.start()].count("\n") + 1
                code = lines[line_num - 1] if line_num <= len(lines) else ""

                findings.append(
                    SecurityFinding(
                        vulnerability_type=VulnerabilityType.SQL_INJECTION,
                        severity=SecuritySeverity.CRITICAL,
                        file_path=file_path,
                        line_start=line_num,
                        line_end=line_num,
                        description=f"Potential SQL injection: {description}",
                        recommendation="Use parameterized queries",
                        owasp_category=OWASP_MAPPING[VulnerabilityType.SQL_INJECTION],
                        cwe_id="CWE-89",
                        current_code=code.strip(),
                        secure_alternative='cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
                        confidence=0.85,
                    )
                )

        return findings

    def _check_path_traversal(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """Check for path traversal vulnerabilities (Issue #665: extracted helper)."""
        findings: List[SecurityFinding] = []
        path_traversal_pattern = r'open\s*\(\s*[^)]*\+[^)]*\)|open\s*\(\s*f["\']'

        for match in re.finditer(path_traversal_pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            code = lines[line_num - 1] if line_num <= len(lines) else ""

            # Skip if path validation nearby
            context_start = max(0, line_num - 3)
            context_end = min(len(lines), line_num + 1)
            context = "\n".join(lines[context_start:context_end])
            if "os.path.abspath" in context or "secure" in context.lower():
                continue

            findings.append(
                SecurityFinding(
                    vulnerability_type=VulnerabilityType.PATH_TRAVERSAL,
                    severity=SecuritySeverity.HIGH,
                    file_path=file_path,
                    line_start=line_num,
                    line_end=line_num,
                    description="Potential path traversal vulnerability",
                    recommendation="Validate and sanitize file paths",
                    owasp_category=OWASP_MAPPING[VulnerabilityType.PATH_TRAVERSAL],
                    cwe_id="CWE-22",
                    current_code=code.strip(),
                    secure_alternative="os.path.abspath() and check against allowed directory",
                    confidence=0.7,
                    false_positive_risk="medium",
                )
            )

        return findings

    def _regex_analysis(
        self, file_path: str, content: str, lines: List[str]
    ) -> List[SecurityFinding]:
        """
        Perform regex-based security analysis.

        Issue #665: Refactored to use extracted helper methods for each pattern type.
        """
        findings: List[SecurityFinding] = []

        # Check for hardcoded secrets (Issue #665: uses helper)
        findings.extend(self._check_hardcoded_secrets(file_path, content, lines))

        # Check for SQL injection patterns (Issue #665: uses helper)
        findings.extend(self._check_sql_injection(file_path, content, lines))

        # Check for path traversal (Issue #665: uses helper)
        findings.extend(self._check_path_traversal(file_path, content, lines))

        return findings

    def analyze_directory(
        self, directory: Optional[str] = None
    ) -> List[SecurityFinding]:
        """Analyze all Python files in a directory."""
        target = Path(directory) if directory else self.project_root
        self.results = []
        self.total_files_scanned = 0  # Issue #686: Reset counter

        for py_file in target.rglob("*.py"):
            # Check exclusions
            if self._should_exclude(py_file):
                continue

            self.total_files_scanned += 1  # Issue #686: Count all files scanned
            findings = self.analyze_file(str(py_file))
            self.results.extend(findings)

        return self.results

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        path_str = str(path)
        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path_str:
                return True
        return False

    def _aggregate_findings_by_category(
        self,
    ) -> tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
        """Aggregate findings by severity, type, and OWASP category. Issue #620."""
        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_owasp: Dict[str, int] = {}

        for finding in self.results:
            sev = finding.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            vtype = finding.vulnerability_type.value
            by_type[vtype] = by_type.get(vtype, 0) + 1

            owasp = finding.owasp_category
            by_owasp[owasp] = by_owasp.get(owasp, 0) + 1

        return by_severity, by_type, by_owasp

    def _build_summary_dict(
        self,
        by_severity: Dict[str, int],
        by_type: Dict[str, int],
        by_owasp: Dict[str, int],
        security_score: int,
        risk_level: str,
    ) -> Dict[str, Any]:
        """Build the final summary dictionary with all metrics. Issue #620."""
        files_analyzed = (
            self.total_files_scanned
            if self.total_files_scanned > 0
            else len(set(f.file_path for f in self.results))
        )

        return {
            "total_findings": len(self.results),
            "by_severity": by_severity,
            "by_type": by_type,
            "by_owasp_category": by_owasp,
            "security_score": security_score,
            "risk_level": risk_level,
            "critical_issues": by_severity.get("critical", 0),
            "high_issues": by_severity.get("high", 0),
            "files_analyzed": files_analyzed,
            "files_with_issues": len(set(f.file_path for f in self.results)),
        }

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of security findings.

        Issue #686: Uses exponential decay scoring to prevent score overflow.
        Scores now degrade gracefully instead of immediately hitting 0.
        """
        from src.code_intelligence.shared.scoring import (
            calculate_score_from_severity_counts,
            get_risk_level_from_score,
        )

        by_severity, by_type, by_owasp = self._aggregate_findings_by_category()
        security_score = calculate_score_from_severity_counts(by_severity)
        risk_level = get_risk_level_from_score(security_score)

        return self._build_summary_dict(
            by_severity, by_type, by_owasp, security_score, risk_level
        )

    def _get_risk_level(self, score: int) -> str:
        """
        Get risk level based on security score.

        DEPRECATED: Use get_risk_level_from_score from shared.scoring instead.
        Kept for backward compatibility.
        """
        if score >= 90:
            return "low"
        elif score >= 70:
            return "medium"
        elif score >= 50:
            return "high"
        else:
            return "critical"

    def generate_report(self, format: str = "json") -> str:
        """Generate security report."""
        import json

        report = {
            "summary": self.get_summary(),
            "findings": [f.to_dict() for f in self.results],
            "recommendations": self._get_top_recommendations(),
        }

        if format == "json":
            return json.dumps(report, indent=2)
        elif format == "markdown":
            return self._generate_markdown_report(report)
        else:
            return json.dumps(report, indent=2)

    def _get_top_recommendations(self) -> List[str]:
        """Get top security recommendations based on findings."""
        recommendations = []

        severity_priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_findings = sorted(
            self.results, key=lambda f: severity_priority.get(f.severity.value, 4)
        )

        seen_types = set()
        for finding in sorted_findings[:10]:
            if finding.vulnerability_type not in seen_types:
                recommendations.append(
                    f"[{finding.severity.value.upper()}] {finding.recommendation}"
                )
                seen_types.add(finding.vulnerability_type)

        return recommendations

    def _generate_markdown_report(self, report: Dict) -> str:
        """Generate markdown-formatted report."""
        md = ["# Security Analysis Report\n"]

        summary = report["summary"]
        md.append("## Summary\n")
        md.append(f"- **Security Score**: {summary['security_score']}/100\n")
        md.append(f"- **Risk Level**: {summary['risk_level'].upper()}\n")
        md.append(f"- **Total Findings**: {summary['total_findings']}\n")
        md.append(f"- **Critical Issues**: {summary['critical_issues']}\n")
        md.append(f"- **High Issues**: {summary['high_issues']}\n\n")

        if report["recommendations"]:
            md.append("## Top Recommendations\n")
            for rec in report["recommendations"]:
                md.append(f"- {rec}\n")
            md.append("\n")

        if report["findings"]:
            md.append("## Findings\n")
            for finding in report["findings"][:20]:  # Limit to top 20
                md.append(f"### {finding['vulnerability_type']}\n")
                md.append(f"- **Severity**: {finding['severity']}\n")
                md.append(
                    f"- **File**: {finding['file_path']}:{finding['line_start']}\n"
                )
                md.append(f"- **Description**: {finding['description']}\n")
                md.append(f"- **OWASP**: {finding['owasp_category']}\n")
                if finding.get("cwe_id"):
                    md.append(f"- **CWE**: {finding['cwe_id']}\n")
                md.append(f"- **Fix**: {finding['recommendation']}\n\n")

        return "".join(md)

    # Issue #554: Async semantic analysis methods

    async def analyze_directory_async(
        self,
        directory: Optional[str] = None,
        find_semantic_duplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyze a directory with optional semantic analysis.

        Issue #554: Async version that supports ChromaDB/Redis/LLM infrastructure.

        Args:
            directory: Path to directory to analyze
            find_semantic_duplicates: Whether to find semantically similar vulnerabilities

        Returns:
            Dictionary with analysis results including semantic matches
        """
        start_time = time.time()

        # Run standard analysis first
        results = self.analyze_directory(directory)

        result = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
            "semantic_duplicates": [],
            "infrastructure_metrics": {},
        }

        # Run semantic analysis if enabled
        if self.use_semantic_analysis and find_semantic_duplicates:
            semantic_dups = await self._find_semantic_security_duplicates(results)
            result["semantic_duplicates"] = semantic_dups

            # Add infrastructure metrics
            result["infrastructure_metrics"] = self._get_infrastructure_metrics()

        result["analysis_time_ms"] = (time.time() - start_time) * 1000
        return result

    async def _find_semantic_security_duplicates(
        self,
        findings: List[SecurityFinding],
    ) -> List[Dict[str, Any]]:
        """
        Find semantically similar security vulnerabilities using LLM embeddings.

        Issue #554: Uses the generic _find_semantic_duplicates_with_extraction
        helper from SemanticAnalysisMixin to reduce code duplication.

        Args:
            findings: List of detected security findings

        Returns:
            List of duplicate pairs with similarity scores
        """
        try:
            return await self._find_semantic_duplicates_with_extraction(
                items=findings,
                code_extractors=["current_code"],
                metadata_keys={
                    "vulnerability_type": "vulnerability_type",
                    "file_path": "file_path",
                    "line_start": "line_start",
                    "description": "description",
                    "owasp_category": "owasp_category",
                },
                min_similarity=SIMILARITY_MEDIUM
                if HAS_ANALYTICS_INFRASTRUCTURE
                else 0.7,
            )
        except Exception as e:
            logger.warning("Semantic duplicate detection failed: %s", e)
            return []

    async def cache_analysis_results(
        self,
        directory: str,
        results: List[SecurityFinding],
    ) -> bool:
        """
        Cache analysis results in Redis for faster retrieval.

        Issue #554: Uses Redis caching from analytics infrastructure.

        Args:
            directory: Analyzed directory path
            results: Analysis results to cache

        Returns:
            True if cached successfully
        """
        if not self.use_semantic_analysis:
            return False

        cache_key = self._generate_content_hash(directory)
        results_dict = {
            "results": [r.to_dict() for r in results],
            "summary": self.get_summary(),
        }

        return await self._cache_result(
            key=cache_key,
            result=results_dict,
            prefix="security_analysis",
        )

    async def get_cached_analysis(
        self,
        directory: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached analysis results from Redis.

        Issue #554: Retrieves cached results for faster repeat analysis.

        Args:
            directory: Directory path to look up

        Returns:
            Cached analysis results or None if not found
        """
        if not self.use_semantic_analysis:
            return None

        cache_key = self._generate_content_hash(directory)
        return await self._get_cached_result(
            key=cache_key,
            prefix="security_analysis",
        )


def analyze_security(
    directory: Optional[str] = None, exclude_patterns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to analyze security of a directory.

    Args:
        directory: Directory to analyze (defaults to current directory)
        exclude_patterns: Patterns to exclude from analysis

    Returns:
        Dictionary with results and summary
    """
    analyzer = SecurityAnalyzer(
        project_root=directory, exclude_patterns=exclude_patterns
    )
    results = analyzer.analyze_directory()

    return {
        "results": [r.to_dict() for r in results],
        "summary": analyzer.get_summary(),
        "report": analyzer.generate_report(format="markdown"),
    }


def get_vulnerability_types() -> List[Dict[str, str]]:
    """Get all supported vulnerability types with descriptions."""
    return [
        {
            "type": vt.value,
            "owasp": OWASP_MAPPING.get(vt, "Unknown"),
            "category": vt.name.replace("_", " ").title(),
        }
        for vt in VulnerabilityType
    ]


async def analyze_security_async(
    directory: Optional[str] = None,
    exclude_patterns: Optional[List[str]] = None,
    use_semantic_analysis: bool = True,
    find_semantic_duplicates: bool = True,
) -> Dict[str, Any]:
    """
    Async convenience function to analyze security with semantic analysis.

    Issue #554: Async version with ChromaDB/Redis/LLM infrastructure support.

    Args:
        directory: Directory to analyze (defaults to current directory)
        exclude_patterns: Patterns to exclude from analysis
        use_semantic_analysis: Whether to use LLM-based semantic analysis
        find_semantic_duplicates: Whether to find semantically similar vulnerabilities

    Returns:
        Dictionary with results and summary including semantic matches
    """
    analyzer = SecurityAnalyzer(
        project_root=directory,
        exclude_patterns=exclude_patterns,
        use_semantic_analysis=use_semantic_analysis,
    )
    return await analyzer.analyze_directory_async(
        find_semantic_duplicates=find_semantic_duplicates,
    )
