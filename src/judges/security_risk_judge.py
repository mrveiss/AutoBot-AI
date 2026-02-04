# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Risk Judge

Implements LLM-as-Judge for security risk assessment, command safety evaluation,
and compliance checking throughout the AutoBot system.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.constants import SecurityThresholds
from src.constants.network_constants import NetworkConstants

from . import BaseLLMJudge, JudgmentDimension, JudgmentResult

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for security checks (Issue #326)
FILE_DELETE_OPS = {"delete", "remove", "rm"}
FILE_WRITE_OPS = {"write", "modify", "edit"}
FILE_READ_OPS = {"read", "view", "cat"}
CRITICAL_PATHS = {"/etc/", "/boot/", "/sys/"}
CRITICAL_WRITE_PATHS = {"/etc/", "/boot/"}
SENSITIVE_FILE_PATTERNS = {"passwd", "shadow", "key"}
FILE_TRANSFER_OPS = {"upload", "download", "transfer"}
FILE_TRANSFER_OPS_SIMPLE = {"upload", "download"}

# Issue #380: Module-level frozensets to avoid repeated list creation
_SENSITIVE_FILE_KEYWORDS = frozenset(
    {"password", "secret", "key", "token", "credential"}
)
_SYSTEM_DIRECTORIES = frozenset({"/etc/", "/usr/", "/var/"})
_SENSITIVE_PORTS = frozenset({22, 23, 3389, 5900, 135, 139, 445})
_REMOTE_ACCESS_PORTS = frozenset({22, 3389})  # SSH and RDP ports for auth requirements


class SecurityRiskJudge(BaseLLMJudge):
    """Judge for evaluating security risks, command safety, and compliance"""

    def _get_dangerous_patterns(self) -> Dict[str, List[str]]:
        """
        Return dangerous command patterns organized by risk category.

        Returns:
            Dict mapping category names to lists of regex patterns.

        Issue #620.
        """
        return {
            "destructive": [
                r"\brm\s+(-rf?|\-\-recursive)\s+/",
                r"\bformat\s+[a-zA-Z]:",
                r"\bdd\s+.*of=/dev/",
                r"\bmkfs\.",
                r"\bshred\b",
                r"\bwipe\b",
                r">\s*/dev/(sd[a-z]|nvme)",
                r"\bfdisk\s.*\-\-delete",
            ],
            "privilege_escalation": [
                r"\bsudo\s+su\s*\-",
                r"\bchmod\s+[47]77",
                r"\bchown\s+root",
                r"\bsetuid\b",
                r"\bsetgid\b",
                r"/etc/sudoers",
                r"/etc/passwd",
                r"/etc/shadow",
            ],
            "network_security": [
                r"\bnc\s+.*\-l.*\-p",
                r"\bnetcat\s+.*\-l",
                r"\biptables\s+.*DROP",
                r"\bufw\s+.*deny",
                r"\bfirewall\-cmd.*\-\-remove",
                r"\bssh\s+.*\-o\s+StrictHostKeyChecking=no",
            ],
            "data_exposure": [
                r"\bcat\s+.*/(etc/)?(passwd|shadow|hosts)",
                r"\bgrep\s+.*password.*/",
                r"\bfind\s+.*\-name.*\*\.key",
                r"\bls\s+.*\.pem$",
                r"\bps\s+.*aux.*grep.*password",
            ],
            "system_modification": [
                r"\bcrontab\s+\-e",
                r"/etc/hosts\s*$",
                r"/boot/",
                r"\bsystemctl\s+disable",
                r"\bchkconfig\s+.*off",
                r"\bupdate\-rc\.d.*remove",
            ],
        }

    def _get_safe_patterns(self) -> List[str]:
        """
        Return safe command whitelist patterns.

        Returns:
            List of regex patterns for commands considered safe.

        Issue #620.
        """
        return [
            r"^ls\s+",
            r"^pwd\s*$",
            r"^whoami\s*$",
            r"^date\s*$",
            r"^echo\s+",
            r"^cat\s+[^/]",  # Only local files, not system files
            r"^grep\s+.*[^/]",  # Only local searches
            r"^find\s+\.\s+",  # Only current directory searches
            r"^git\s+",
            r"^npm\s+",
            r"^pip\s+",
            r"^python\s+",
            r"^node\s+",
        ]

    def __init__(self, llm_interface=None):
        """Initialize security judge with risk thresholds. Issue #620."""
        super().__init__("security_risk", llm_interface)
        # Issue #318: Use centralized constants instead of magic numbers
        self.high_risk_threshold = SecurityThresholds.HIGH_RISK_THRESHOLD
        self.block_threshold = SecurityThresholds.BLOCK_THRESHOLD

        # Issue #620: Use extracted helper methods for pattern definitions
        self.dangerous_patterns = self._get_dangerous_patterns()
        self.safe_patterns = self._get_safe_patterns()

    async def evaluate_command_security(
        self,
        command: str,
        context: Dict[str, Any],
        user_permissions: List[str] = None,
        environment: str = "production",
    ) -> JudgmentResult:
        """
        Evaluate security risk of a command before execution

        Args:
            command: Command to evaluate
            context: Execution context
            user_permissions: User's permission levels
            environment: Environment type (development/staging/production)

        Returns:
            JudgmentResult with security assessment
        """
        # Define security evaluation criteria
        criteria = [
            JudgmentDimension.SAFETY,
            JudgmentDimension.SECURITY,
            JudgmentDimension.COMPLIANCE,
            JudgmentDimension.FEASIBILITY,
        ]

        # Prepare security context
        security_context = {
            "command": command,
            "execution_context": context,
            "user_permissions": user_permissions or [],
            "environment": environment,
            "risk_patterns": self._analyze_command_patterns(command),
            "high_risk_threshold": self.high_risk_threshold,
            "block_threshold": self.block_threshold,
        }

        return await self.make_judgment(
            subject={"command": command, "context": context},
            criteria=criteria,
            context=security_context,
        )

    def _extract_dimension_score(
        self, judgment: JudgmentResult, dimension: JudgmentDimension
    ) -> float:
        """
        Extract a specific dimension score from judgment result.

        (Issue #398: extracted helper to reduce duplication)

        Args:
            judgment: The judgment result containing criterion scores
            dimension: The dimension to extract score for

        Returns:
            Score for the dimension, or 0.0 if not found
        """
        return next(
            (s.score for s in judgment.criterion_scores if s.dimension == dimension),
            0.0,
        )

    def _build_file_access_result(
        self,
        judgment: JudgmentResult,
        safety_score: float,
        security_score: float,
        path_risks: List[str],
        operation_risk: str,
    ) -> Dict[str, Any]:
        """
        Build the file access risk assessment result.

        (Issue #398: extracted helper)

        Args:
            judgment: The judgment result
            safety_score: Extracted safety score
            security_score: Extracted security score
            path_risks: List of path-related risks
            operation_risk: Operation risk level

        Returns:
            Dict with complete risk assessment
        """
        return {
            "risk_level": self._calculate_risk_level(safety_score, security_score),
            "should_allow": safety_score > 0.7 and security_score > 0.7,
            "requires_confirmation": safety_score < 0.9 or security_score < 0.9,
            "risk_factors": (
                path_risks + [operation_risk] if operation_risk else path_risks
            ),
            "detailed_assessment": judgment,
            "mitigation_suggestions": judgment.improvement_suggestions,
        }

    async def assess_file_access_risk(
        self,
        file_path: str,
        operation: str,
        context: Dict[str, Any],
        user_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Assess security risk of file access operations.

        (Issue #398: refactored to use extracted helpers)

        Returns:
            Dict with risk assessment and recommendations
        """
        try:
            path_risks = self._analyze_file_path_risks(file_path)
            operation_risk = self._evaluate_operation_risk(operation, file_path)

            criteria = [
                JudgmentDimension.SAFETY,
                JudgmentDimension.SECURITY,
                JudgmentDimension.COMPLIANCE,
            ]

            access_context = {
                "file_path": file_path,
                "operation": operation,
                "path_risks": path_risks,
                "operation_risk": operation_risk,
                "context": context,
                "user_context": user_context,
            }

            judgment = await self.make_judgment(
                subject={"file_path": file_path, "operation": operation},
                criteria=criteria,
                context=access_context,
            )

            # Extract security-specific metrics (Issue #398: uses helper)
            safety_score = self._extract_dimension_score(
                judgment, JudgmentDimension.SAFETY
            )
            security_score = self._extract_dimension_score(
                judgment, JudgmentDimension.SECURITY
            )

            return self._build_file_access_result(
                judgment, safety_score, security_score, path_risks, operation_risk
            )

        except Exception as e:
            logger.error("Error assessing file access risk: %s", e)
            return {
                "risk_level": "unknown",
                "should_allow": False,
                "error": str(e),
                "requires_confirmation": True,
            }

    async def evaluate_network_operation_security(
        self, operation_data: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate security risks of network operations

        Returns:
            Dict with network security assessment
        """
        try:
            operation_type = operation_data.get("type", "unknown")
            target_host = operation_data.get("host", "unknown")
            port = operation_data.get("port", "unknown")
            protocol = operation_data.get("protocol", "unknown")

            # Analyze network operation risks
            network_risks = self._analyze_network_risks(operation_data)

            criteria = [
                JudgmentDimension.SAFETY,
                JudgmentDimension.SECURITY,
                JudgmentDimension.COMPLIANCE,
            ]

            network_context = {
                "operation_data": operation_data,
                "network_risks": network_risks,
                "context": context,
                "operation_type": operation_type,
                "target_host": target_host,
                "port": port,
                "protocol": protocol,
            }

            judgment = await self.make_judgment(
                subject=operation_data, criteria=criteria, context=network_context
            )

            return {
                "security_assessment": judgment,
                "network_risks": network_risks,
                "recommendation": judgment.recommendation,
                "confidence": judgment.confidence.value,
                "security_requirements": self._get_network_security_requirements(
                    operation_data
                ),
            }

        except Exception as e:
            logger.error("Error evaluating network operation security: %s", e)
            return {
                "error": str(e),
                "recommendation": "REJECT",
                "network_risks": ["Evaluation error - assume high risk"],
            }

    async def _prepare_judgment_prompt(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: Optional[List[Any]] = None,
        **kwargs,
    ) -> str:
        """Prepare the prompt for security risk evaluation"""

        subject_data = subject
        command = context.get("command")
        execution_context = context.get("execution_context", {})
        user_permissions = context.get("user_permissions", [])
        environment = context.get("environment", "production")
        risk_patterns = context.get("risk_patterns", {})

        if command:
            return self._prepare_command_security_prompt(
                command,
                execution_context,
                user_permissions,
                environment,
                risk_patterns,
                context,
            )
        elif "file_path" in subject_data:
            return self._prepare_file_access_prompt(subject_data, context)
        elif "operation_data" in context:
            return self._prepare_network_operation_prompt(subject_data, context)
        else:
            return self._prepare_general_security_prompt(subject_data, context)

    def _get_security_evaluation_criteria(self) -> str:
        """Return security evaluation criteria template.

        Issue #665: Extracted from _prepare_command_security_prompt to reduce function length.
        """
        return """
SECURITY EVALUATION CRITERIA:
Please evaluate this command on the following dimensions (score 0.0 to 1.0):

1. SAFETY: Risk of system damage or data loss
   - Could this command cause irreversible damage?
   - Does it modify critical system files or configurations?
   - Is there risk of data destruction or corruption?
   - Could it compromise system stability?

2. SECURITY: Information security and access control risks
   - Does it expose sensitive information?
   - Could it escalate privileges inappropriately?
   - Does it open security vulnerabilities?
   - Is there risk of unauthorized access?

3. COMPLIANCE: Adherence to security policies and best practices
   - Does it follow organizational security policies?
   - Is it compliant with security frameworks (SOC2, ISO27001)?
   - Does it meet audit requirements?
   - Are proper access controls maintained?

4. FEASIBILITY: Technical appropriateness and context
   - Is this command appropriate for the current environment?
   - Does the user have necessary permissions?
   - Is this the safest way to achieve the goal?
   - Are there safer alternatives available?"""

    def _get_security_decision_criteria(self) -> str:
        """Return security decision criteria template.

        Issue #665: Extracted from _prepare_command_security_prompt to reduce function length.
        """
        return """
ENVIRONMENT CONSIDERATIONS:
- Production: Highest security standards, minimal risk tolerance
- Staging: Moderate security, some risk acceptable for testing
- Development: Lower security requirements, higher risk tolerance

DECISION CRITERIA:
- Safety score < 0.3: REJECT (too dangerous)
- Security score < 0.3: REJECT (security risk too high)
- Environment = production AND (Safety < 0.7 OR Security < 0.7): CONDITIONAL approval
- All scores > 0.7: APPROVE
- Otherwise: CONDITIONAL approval with safeguards

Please provide your evaluation in the required JSON format with:
- Detailed risk assessment for each criterion
- Specific security concerns identified
- Recommended safeguards or alternatives
- Clear approval/rejection recommendation
- Mitigation strategies if applicable

Focus on protecting system integrity, user data, and organizational security while enabling legitimate operations."""

    def _prepare_command_security_prompt(
        self,
        command: str,
        execution_context: Dict[str, Any],
        user_permissions: List[str],
        environment: str,
        risk_patterns: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """Prepare prompt for command security evaluation. Issue #665: Refactored."""
        prompt = f"""
Please evaluate the security risk of the following command before execution:

COMMAND TO EVALUATE:
{command}

EXECUTION CONTEXT:
Environment: {environment}
User Permissions: {user_permissions}
Working Directory: {execution_context.get('working_directory', 'unknown')}
User: {execution_context.get('user', 'unknown')}
Session Type: {execution_context.get('session_type', 'unknown')}

RISK ANALYSIS:
Dangerous Patterns Detected: {risk_patterns.get('dangerous_patterns', [])}
Risk Categories: {risk_patterns.get('risk_categories', [])}
Safety Level: {risk_patterns.get('safety_level', 'unknown')}
{self._get_security_evaluation_criteria()}

RISK THRESHOLDS:
- High Risk Threshold: {context.get('high_risk_threshold', 0.3)} (commands above this need extra scrutiny)
- Block Threshold: {context.get('block_threshold', 0.7)} (commands above this should be blocked)
{self._get_security_decision_criteria()}
"""
        return prompt.strip()

    def _prepare_file_access_prompt(
        self, subject_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """Prepare prompt for file access security evaluation"""

        file_path = subject_data.get("file_path", "unknown")
        operation = subject_data.get("operation", "unknown")
        path_risks = context.get("path_risks", [])
        operation_risk = context.get("operation_risk", "none")

        prompt = f"""
Please evaluate the security risk of the following file access operation:

FILE ACCESS OPERATION:
File Path: {file_path}
Operation: {operation}

RISK ANALYSIS:
Path Risk Factors: {path_risks}
Operation Risk Level: {operation_risk}

SECURITY EVALUATION:
Please assess this file access on the following security dimensions:

1. SAFETY: Risk of data loss or system damage
   - Is this a critical system file?
   - Could the operation cause data loss?
   - Is there risk of system instability?

2. SECURITY: Information security risks
   - Does the file contain sensitive information?
   - Could access expose secrets or credentials?
   - Is proper access control maintained?

3. COMPLIANCE: Policy and regulatory compliance
   - Does this meet data protection requirements?
   - Is access properly authorized?
   - Are audit trails maintained?

CRITICAL SYSTEM PATHS:
- /etc/, /boot/, /sys/, /proc/: Critical system configuration
- /var/log/: System logs (read-only usually safe)
- /home/: User data (context-dependent)
- /tmp/: Temporary files (generally safer)

Please provide detailed security assessment in the required JSON format.
"""

        return prompt.strip()

    def _prepare_network_operation_prompt(
        self, subject_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """Prepare prompt for network operation security evaluation"""

        operation_data = context.get("operation_data", {})
        network_risks = context.get("network_risks", [])

        prompt = f"""
Please evaluate the security risk of the following network operation:

NETWORK OPERATION:
{json.dumps(operation_data, indent=2)}

IDENTIFIED RISKS:
{network_risks}

SECURITY EVALUATION:
Assess this network operation for:

1. SAFETY: Risk to network and system security
2. SECURITY: Data exposure and access control risks
3. COMPLIANCE: Network security policy adherence

Please provide comprehensive security assessment in the required JSON format.
"""

        return prompt.strip()

    def _prepare_general_security_prompt(
        self, subject_data: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """Prepare prompt for general security evaluation"""

        prompt = f"""
Please evaluate the security implications of the following operation:

OPERATION TO EVALUATE:
{json.dumps(subject_data, indent=2)}

CONTEXT:
{json.dumps(context, indent=2)}

Please provide thorough security assessment focusing on safety, security, and compliance requirements.
"""

        return prompt.strip()

    def _analyze_command_patterns(self, command: str) -> Dict[str, Any]:
        """Analyze command for dangerous patterns"""
        detected_patterns = []
        risk_categories = []

        for category, patterns in self.dangerous_patterns.items():
            for pattern in patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    detected_patterns.append(pattern)
                    if category not in risk_categories:
                        risk_categories.append(category)

        # Check if command matches safe patterns
        is_safe = any(
            re.match(pattern, command, re.IGNORECASE) for pattern in self.safe_patterns
        )

        if detected_patterns:
            safety_level = "high_risk"
        elif is_safe:
            safety_level = "safe"
        else:
            safety_level = "unknown"

        return {
            "dangerous_patterns": detected_patterns,
            "risk_categories": risk_categories,
            "safety_level": safety_level,
            "is_whitelisted": is_safe,
        }

    def _analyze_file_path_risks(self, file_path: str) -> List[str]:
        """Analyze file path for security risks"""
        risks = []

        # Critical system paths
        critical_paths = [
            "/etc/",
            "/boot/",
            "/sys/",
            "/proc/",
            "/dev/",
            "/var/log/auth.log",
            "/var/log/secure",
            "/etc/passwd",
            "/etc/shadow",
            "/etc/sudoers",
            "/root/",
        ]

        for critical_path in critical_paths:
            if file_path.startswith(critical_path):
                risks.append(f"Access to critical system path: {critical_path}")

        # Sensitive file patterns - Issue #380: Use module-level frozenset
        file_path_lower = file_path.lower()
        if any(pattern in file_path_lower for pattern in _SENSITIVE_FILE_KEYWORDS):
            risks.append("File name suggests sensitive content")

        # Hidden files in system directories - Issue #380: Use module-level frozenset
        if "/." in file_path and any(
            sys_dir in file_path for sys_dir in _SYSTEM_DIRECTORIES
        ):
            risks.append("Access to hidden system file")

        return risks

    def _evaluate_operation_risk(self, operation: str, file_path: str) -> str:
        """Evaluate risk level of file operation"""
        operation_lower = operation.lower()

        if operation_lower in FILE_DELETE_OPS:  # Issue #326
            if any(critical in file_path for critical in CRITICAL_PATHS):
                return "critical"
            return "high"
        elif operation_lower in FILE_WRITE_OPS:  # Issue #326
            if any(critical in file_path for critical in CRITICAL_WRITE_PATHS):
                return "high"
            return "medium"
        elif operation_lower in FILE_READ_OPS:  # Issue #326
            if any(sensitive in file_path for sensitive in SENSITIVE_FILE_PATTERNS):
                return "medium"
            return "low"
        else:
            return "unknown"

    def _analyze_network_risks(self, operation_data: Dict[str, Any]) -> List[str]:
        """Analyze network operation for security risks"""
        risks = []

        host = operation_data.get("host", "").lower()
        port = operation_data.get("port", 0)
        operation_type = operation_data.get("type", "").lower()

        # Check for suspicious hosts
        suspicious_hosts = [
            NetworkConstants.LOCALHOST_NAME,
            NetworkConstants.LOCALHOST_IP,
            NetworkConstants.BIND_ALL_INTERFACES,
        ]
        if any(suspicious in host for suspicious in suspicious_hosts):
            risks.append("Local network access - potential tunnel or backdoor")

        # Check for sensitive ports - Issue #380: Use module-level frozenset
        if port in _SENSITIVE_PORTS:
            risks.append(f"Access to sensitive port {port}")

        # Check for risky operations (Issue #326)
        if operation_type in FILE_TRANSFER_OPS:
            risks.append("Data transfer operation - potential data exfiltration")

        return risks

    def _calculate_risk_level(self, safety_score: float, security_score: float) -> str:
        """Calculate overall risk level"""
        min_score = min(safety_score, security_score)

        if min_score > 0.8:
            return "low"
        elif min_score > 0.6:
            return "medium"
        elif min_score > 0.3:
            return "high"
        else:
            return "critical"

    def _get_network_security_requirements(
        self, operation_data: Dict[str, Any]
    ) -> List[str]:
        """Get security requirements for network operations"""
        requirements = []

        operation_type = operation_data.get("type", "").lower()

        if operation_type in FILE_TRANSFER_OPS_SIMPLE:  # Issue #326
            requirements.extend(
                [
                    "Verify file content before transfer",
                    "Use encrypted connection (HTTPS/SFTP)",
                    "Validate target host certificate",
                    "Log all file transfers",
                ]
            )

        if operation_data.get("port") in _REMOTE_ACCESS_PORTS:
            requirements.extend(
                [
                    "Use key-based authentication",
                    "Verify host fingerprint",
                    "Enable connection logging",
                ]
            )

        return requirements

    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for security risk evaluation"""
        return """You are an expert cybersecurity specialist and risk assessor. Your role is to evaluate security risks, assess command safety, and ensure compliance with security policies and best practices.

Your expertise includes:
- Cybersecurity threat assessment and risk analysis
- System administration security and access controls
- Compliance frameworks (SOC2, ISO27001, NIST, PCI-DSS)
- Network security and data protection
- Incident response and vulnerability management
- Security policy development and enforcement

Security Evaluation Guidelines:
1. SECURITY FIRST: Always prioritize security and data protection
2. ZERO TRUST: Assume potential threats and verify everything
3. PRINCIPLE OF LEAST PRIVILEGE: Minimize access and permissions
4. DEFENSE IN DEPTH: Consider multiple security layers
5. RISK-BASED DECISIONS: Balance security with operational needs
6. COMPLIANCE AWARENESS: Ensure regulatory and policy adherence

Critical Security Considerations:
- System integrity and availability protection
- Data confidentiality and privacy preservation
- Access control and privilege management
- Network security and communication protection
- Audit trails and monitoring requirements
- Incident prevention and response capabilities

Risk Assessment Framework:
- CRITICAL (0.0-0.2): Immediate security threat, must be blocked
- HIGH (0.3-0.4): Significant risk, requires special approval
- MEDIUM (0.5-0.6): Moderate risk, additional safeguards needed
- LOW (0.7-0.8): Minimal risk, standard controls sufficient
- MINIMAL (0.9-1.0): Very low risk, routine operation

Command Safety Categories:
- DESTRUCTIVE: Operations that can cause irreversible damage
- PRIVILEGE_ESCALATION: Operations that increase user privileges
- NETWORK_SECURITY: Operations affecting network configurations
- DATA_EXPOSURE: Operations that may expose sensitive information
- SYSTEM_MODIFICATION: Operations that change system configuration

Response Format Requirements:
Always respond with valid JSON containing all required fields:
- overall_score: float between 0.0 and 1.0 (higher = safer)
- recommendation: exactly one of "APPROVE", "REJECT", "CONDITIONAL", "REVISE"
- confidence: exactly one of "very_low", "low", "medium", "high", "very_high"
- reasoning: detailed security analysis with specific risks identified
- criterion_scores: array with all requested security criteria
- improvement_suggestions: specific security recommendations and safeguards
- alternatives_analysis: safer alternatives if available

Be thorough, conservative with security decisions, and provide clear justification for all risk assessments. When in doubt, err on the side of caution and require additional safeguards."""
