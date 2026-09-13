# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pattern-detection rules for the IDE integration engine (Issue #240).

Moved unchanged out of ``api/ide_integration.py`` (#16375), which sat at its
recorded size ceiling and needed room for its auth gate. ``IDEIntegrationEngine``
copies this list on construction; ``api.ide_integration`` re-imports it, so the
name is still reachable there.
"""

from api.schemas_code import DiagnosticSeverity, IDEPatternCategory

# Pattern detection rules
PATTERN_RULES = [
    {
        "id": "sql_injection",
        "name": "Potential SQL Injection",
        "pattern": r'execute\s*\(\s*["\'].*\s*\+\s*\w+',
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "Potential SQL injection vulnerability. Use parameterized queries.",
        "fix_template": "Use parameterized query: execute(query, (params,))",
    },
    {
        "id": "hardcoded_secret",
        "name": "Hardcoded Secret",
        "pattern": r'(password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "Hardcoded secret detected. Use environment variables.",
        "fix_template": "Use os.environ.get('SECRET_NAME')",
    },
    {
        "id": "bare_except",
        "name": "Bare Except Clause",
        "pattern": r"except\s*:",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Bare except clause catches all exceptions including KeyboardInterrupt.",
        "fix_template": "except Exception:",
    },
    {
        "id": "mutable_default",
        "name": "Mutable Default Argument",
        "pattern": r"def\s+\w+\([^)]*=\s*(\[\]|\{\}|\set\(\))",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Mutable default argument. Use None and initialize inside function.",
        "fix_template": "def func(arg=None):\n    if arg is None:\n        arg = []",
    },
    {
        "id": "print_statement",
        "name": "Debug Print Statement",
        "pattern": r"^\s*print\s*\(",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Debug print statement found. Consider using logging.",
        "fix_template": "logging.debug(...)",
    },
    {
        "id": "todo_comment",
        "name": "TODO Comment",
        # Require colon to avoid false positives (Issue #617)
        "pattern": r"#\s*TODO:\s*",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "TODO comment found. Consider tracking in issue tracker.",
        "fix_template": None,
    },
    {
        "id": "fixme_comment",
        "name": "FIXME Comment",
        # Require colon to avoid false positives (Issue #617)
        "pattern": r"#\s*FIXME:\s*",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.WARNING,
        "message": "FIXME comment indicates code that needs attention.",
        "fix_template": None,
    },
    {
        "id": "eval_usage",
        "name": "Eval Usage",
        "pattern": r"\beval\s*\(",
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "eval() is dangerous. Use ast.literal_eval() for safe parsing.",
        "fix_template": "ast.literal_eval(...)",
    },
    {
        "id": "exec_usage",
        "name": "Exec Usage",
        "pattern": r"\bexec\s*\(",
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.ERROR,
        "message": "exec() is dangerous. Consider alternatives.",
        "fix_template": None,
    },
    {
        "id": "assert_in_production",
        "name": "Assert Statement",
        "pattern": r"^\s*assert\s+",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.HINT,
        "message": "Assert statements are removed with -O flag. Use explicit checks.",
        "fix_template": "if not condition:\n    raise AssertionError(...)",
    },
    {
        "id": "subprocess_shell",
        "name": "Subprocess with Shell",
        "pattern": r"subprocess\.\w+\([^)]*shell\s*=\s*True",
        "category": IDEPatternCategory.SECURITY,
        "severity": DiagnosticSeverity.WARNING,
        "message": "shell=True can be a security risk. Use shell=False with list args.",
        "fix_template": "subprocess.run(['cmd', 'arg'], shell=False)",
    },
    {
        "id": "wildcard_import",
        "name": "Wildcard Import",
        "pattern": r"from\s+\w+\s+import\s+\*",
        "category": IDEPatternCategory.STYLE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Wildcard imports pollute namespace. Import specific names.",
        "fix_template": "from module import name1, name2",
    },
    {
        "id": "global_statement",
        "name": "Global Statement",
        "pattern": r"^\s*global\s+\w+",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Global statements can make code harder to understand.",
        "fix_template": None,
    },
    {
        "id": "magic_number",
        "name": "Magic Number",
        "pattern": r"(?<![0-9a-zA-Z_])[2-9]\d{2,}(?![0-9a-zA-Z_])",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "Magic number detected. Consider using a named constant.",
        "fix_template": "CONSTANT_NAME = value",
    },
    {
        "id": "long_line",
        "name": "Line Too Long",
        "pattern": r"^.{121,}$",
        "category": IDEPatternCategory.STYLE,
        "severity": DiagnosticSeverity.HINT,
        "message": "Line exceeds 120 characters. Consider breaking it up.",
        "fix_template": None,
    },
    {
        "id": "unused_variable",
        "name": "Potentially Unused Variable",
        "pattern": r"^\s*(\w+)\s*=\s*[^=].*(?!.*\1)",
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.HINT,
        "message": "Variable may be unused. Prefix with _ if intentional.",
        "fix_template": "_unused = value",
    },
    {
        "id": "empty_except",
        "name": "Empty Except Block",
        "pattern": r"except[^:]*:\s*\n\s*(pass|\.\.\.)\s*$",
        "category": IDEPatternCategory.ERROR_PRONE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Empty except block silently swallows errors.",
        "fix_template": "except Exception as e:\n    logging.exception('Error occurred')",
    },
    {
        "id": "deprecated_method",
        "name": "Deprecated Method",
        "pattern": r"\.(has_key|iteritems|itervalues|iterkeys)\s*\(",
        "category": IDEPatternCategory.DEPRECATED,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Using deprecated Python 2 method.",
        "fix_template": "Use Python 3 equivalents: 'in', .items(), .values(), .keys()",
    },
    {
        "id": "sync_in_async",
        "name": "Sync Call in Async Function",
        "pattern": r"async\s+def[^:]+:[^}]*(?:time\.sleep|requests\.\w+|open\()",
        "category": IDEPatternCategory.PERFORMANCE,
        "severity": DiagnosticSeverity.WARNING,
        "message": "Blocking call in async function. Use async alternatives.",
        "fix_template": "Use asyncio.sleep(), aiohttp, aiofiles",
    },
    {
        "id": "hardcoded_ip",
        "name": "Hardcoded IP Address",
        "pattern": r'["\'](?:\d{1,3}\.){3}\d{1,3}["\']',
        "category": IDEPatternCategory.CODE_QUALITY,
        "severity": DiagnosticSeverity.INFORMATION,
        "message": "Hardcoded IP address. Consider using configuration.",
        "fix_template": "Use config.get('HOST') or environment variable",
    },
]
