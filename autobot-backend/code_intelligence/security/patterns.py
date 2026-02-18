# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Regex patterns for security vulnerability detection.

Issue #712: Extracted from security_analyzer.py for modularity.
"""

from .constants import VulnerabilityType

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

# SQL injection patterns
SQL_INJECTION_PATTERNS = [
    (r'execute\s*\(\s*["\'].*%s.*["\']', "String formatting in SQL query"),
    (r'execute\s*\(\s*f["\']', "f-string in SQL query"),
    (r'execute\s*\(\s*["\'].*\+.*["\']', "String concatenation in SQL query"),
    (r'cursor\.execute\s*\(\s*["\'].*\.format\s*\(', "format() in SQL query"),
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
