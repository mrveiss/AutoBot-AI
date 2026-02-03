# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AST visitor for security pattern analysis.

Issue #712: Extracted from security_analyzer.py for modularity.
"""

import ast
from typing import Dict, List, Optional, Set

from .constants import (
    DEBUG_MODE_VARS,
    HTTP_METHODS,
    INSECURE_RANDOM_FUNCS,
    LOAD_FUNCS,
    OWASP_MAPPING,
    PICKLE_MODULES,
    VALIDATION_ATTRS,
    VALIDATION_FUNCS,
    WEAK_HASH_ALGORITHMS,
    YAML_LOADER_ARGS,
    SecuritySeverity,
    VulnerabilityType,
)
from .finding import SecurityFinding


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
        if self._is_web_handler(node):
            self._check_input_validation(node)

    def _is_web_handler(self, node) -> bool:
        """Check if function is a web request handler."""
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func = decorator.func
                if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
                    return True
            elif isinstance(decorator, ast.Attribute) and decorator.attr in HTTP_METHODS:
                return True
        return False

    def _has_validation_call(self, node) -> bool:
        """Check if node has validation call patterns."""
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if isinstance(func, ast.Name) and func.id in VALIDATION_FUNCS:
                return True
            if isinstance(func, ast.Attribute) and func.attr in VALIDATION_ATTRS:
                return True
        return False

    def _has_type_annotations(self, node) -> bool:
        """Check if function has type annotations."""
        return any(arg.annotation for arg in node.args.args)

    def _check_input_validation(self, node) -> None:
        """Check if web handler validates input."""
        has_validation = self._has_validation_call(node) or self._has_type_annotations(node)

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
                    owasp_category=OWASP_MAPPING[VulnerabilityType.MISSING_INPUT_VALIDATION],
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
                self._add_injection_finding(
                    node, "compile()", VulnerabilityType.COMMAND_INJECTION, "CWE-95",
                    severity=SecuritySeverity.MEDIUM, confidence=0.6,
                )

        elif isinstance(func, ast.Attribute):
            if func.attr == "system" and self._get_module_name(func) == "os":
                self._check_command_injection(node, "os.system()")
            elif func.attr == "popen" and self._get_module_name(func) == "os":
                self._check_command_injection(node, "os.popen()")

    def _check_crypto_usage(self, node: ast.Call) -> None:
        """Check for weak cryptographic usage."""
        func = node.func

        if isinstance(func, ast.Attribute):
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
                        owasp_category=OWASP_MAPPING[VulnerabilityType.WEAK_HASH_ALGORITHM],
                        cwe_id=cwe,
                        current_code=code,
                        secure_alternative="hashlib.sha256() or bcrypt.hashpw()",
                        confidence=0.9,
                    )
                )

            if func.attr in INSECURE_RANDOM_FUNCS:
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
                            owasp_category=OWASP_MAPPING[VulnerabilityType.INSECURE_RANDOM],
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
            if func.attr in LOAD_FUNCS and self._get_module_name(func) in PICKLE_MODULES:
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

            if func.attr == "load" and self._get_module_name(func) == "yaml":
                has_loader = any(kw.arg in YAML_LOADER_ARGS for kw in node.keywords)
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
                            owasp_category=OWASP_MAPPING[VulnerabilityType.YAML_LOAD_UNSAFE],
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
                                owasp_category=OWASP_MAPPING[VulnerabilityType.COMMAND_INJECTION],
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
                if target.id.upper() in DEBUG_MODE_VARS:
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
                                owasp_category=OWASP_MAPPING[VulnerabilityType.DEBUG_MODE_ENABLED],
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
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.JoinedStr):
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
                        owasp_category=OWASP_MAPPING[VulnerabilityType.COMMAND_INJECTION],
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
        elif isinstance(node, ast.NameConstant):
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
            pass
        return ""
