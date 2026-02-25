# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Policy Manager for Enterprise AutoBot
Provides centralized security policy management, enforcement, and compliance monitoring

Issue #378: Added threading locks for file operations to prevent race conditions.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import yaml
from constants.path_constants import PATH

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for policy versioning and data classification (Issue #326)
MAJOR_VERSION_UPDATE_KEYS = {"rules", "enforcement_mode"}
SENSITIVE_DATA_CLASSIFICATIONS = {"confidential", "restricted", "pii"}


class PolicyType(Enum):
    """Types of security policies"""

    ACCESS_CONTROL = "access_control"
    PASSWORD_POLICY = "password_policy"
    SESSION_MANAGEMENT = "session_management"
    DATA_PROTECTION = "data_protection"
    NETWORK_SECURITY = "network_security"
    AUDIT_LOGGING = "audit_logging"
    COMPLIANCE = "compliance"
    INCIDENT_RESPONSE = "incident_response"


class PolicyStatus(Enum):
    """Policy status values"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    DEPRECATED = "deprecated"


class EnforcementMode(Enum):
    """Policy enforcement modes"""

    ENFORCE = "enforce"  # Block non-compliant actions
    WARN = "warn"  # Log warnings but allow
    MONITOR = "monitor"  # Log for monitoring only
    DISABLED = "disabled"  # Policy disabled


@dataclass
class SecurityPolicy:
    """Represents a security policy"""

    policy_id: str
    name: str
    description: str
    policy_type: PolicyType
    status: PolicyStatus
    enforcement_mode: EnforcementMode
    rules: List[Dict]
    metadata: Dict
    created_at: datetime
    updated_at: datetime
    version: str
    author: str
    approval_required: bool
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None


@dataclass
class PolicyViolation:
    """Represents a policy violation"""

    violation_id: str
    policy_id: str
    user_id: str
    resource: str
    action: str
    violation_type: str
    severity: str
    timestamp: datetime
    details: Dict
    resolved: bool = False
    resolution_notes: Optional[str] = None


class SecurityPolicyManager:
    """
    Enterprise security policy management system
    """

    def __init__(
        self,
        config_path: str = str(
            PATH.get_config_path("security", "security_policies.yaml")
        ),
    ):
        """Initialize security policy manager with config and policy storage."""
        # Thread-safe file operations - must be initialized first (Issue #378)
        self._file_lock = threading.Lock()

        self.config_path = config_path
        self.config = self._load_config()

        # Policy storage
        self.policies_path = PATH.get_data_path("security", "policies")
        self.policies_path.mkdir(parents=True, exist_ok=True)

        # Load policies
        self.policies: Dict[str, SecurityPolicy] = {}
        self.policy_violations: List[PolicyViolation] = []
        self._load_policies()

        # Compliance frameworks mapping
        self.compliance_mappings = self._load_compliance_mappings()

        # Statistics
        self.stats = {
            "total_policies": 0,
            "active_policies": 0,
            "policy_violations": 0,
            "violations_by_type": {},
            "compliance_score": 0.0,
            "last_policy_update": None,
        }

        # Initialize default policies
        self._initialize_default_policies()

        logger.info("Security Policy Manager initialized")

    def _load_config(self) -> Dict:
        """Load security policy configuration"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            else:
                default_config = self._get_default_config()
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error("Failed to load policy config: %s", e)
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Return default security policy configuration"""
        return {
            "policy_management": {
                "require_approval": True,
                "version_control": True,
                "automatic_backup": True,
                "change_notification": True,
            },
            "enforcement": {
                "default_mode": "enforce",
                "grace_period_hours": 24,
                "violation_threshold": 3,
                "automatic_remediation": False,
            },
            "compliance": {
                "frameworks": ["soc2", "gdpr", "iso27001"],
                "audit_frequency_days": 30,
                "compliance_threshold": 0.95,
                "reporting_enabled": True,
            },
            "notifications": {
                "policy_violations": True,
                "policy_updates": True,
                "compliance_alerts": True,
                "violation_thresholds": {"high": 1, "medium": 5, "low": 10},
            },
        }

    def _save_config(self, config: Dict):
        """Save configuration to file (thread-safe, Issue #378)"""
        with self._file_lock:
            try:
                Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, default_flow_style=False)
            except Exception as e:
                logger.error("Failed to save policy config: %s", e)

    def _load_policies(self):
        """Load all security policies from storage"""
        try:
            policy_files = list(self.policies_path.glob("*.json"))

            for policy_file in policy_files:
                with open(policy_file, "r", encoding="utf-8") as f:
                    policy_data = json.load(f)

                # Convert datetime strings back to objects
                policy_data["created_at"] = datetime.fromisoformat(
                    policy_data["created_at"]
                )
                policy_data["updated_at"] = datetime.fromisoformat(
                    policy_data["updated_at"]
                )

                if policy_data.get("approved_at"):
                    policy_data["approved_at"] = datetime.fromisoformat(
                        policy_data["approved_at"]
                    )
                if policy_data.get("effective_date"):
                    policy_data["effective_date"] = datetime.fromisoformat(
                        policy_data["effective_date"]
                    )
                if policy_data.get("expiry_date"):
                    policy_data["expiry_date"] = datetime.fromisoformat(
                        policy_data["expiry_date"]
                    )

                # Convert enums
                policy_data["policy_type"] = PolicyType(policy_data["policy_type"])
                policy_data["status"] = PolicyStatus(policy_data["status"])
                policy_data["enforcement_mode"] = EnforcementMode(
                    policy_data["enforcement_mode"]
                )

                policy = SecurityPolicy(**policy_data)
                self.policies[policy.policy_id] = policy

            self._update_policy_statistics()
            logger.info("Loaded %s security policies", len(self.policies))

        except Exception as e:
            logger.error("Failed to load policies: %s", e)

    def _save_policy(self, policy: SecurityPolicy):
        """Save a single policy to storage (thread-safe, Issue #378)"""
        with self._file_lock:
            try:
                policy_file = self.policies_path / f"{policy.policy_id}.json"

                # Convert to dict and handle datetime serialization
                policy_dict = asdict(policy)
                policy_dict["created_at"] = policy.created_at.isoformat()
                policy_dict["updated_at"] = policy.updated_at.isoformat()

                if policy.approved_at:
                    policy_dict["approved_at"] = policy.approved_at.isoformat()
                if policy.effective_date:
                    policy_dict["effective_date"] = policy.effective_date.isoformat()
                if policy.expiry_date:
                    policy_dict["expiry_date"] = policy.expiry_date.isoformat()

                # Convert enums to values
                policy_dict["policy_type"] = policy.policy_type.value
                policy_dict["status"] = policy.status.value
                policy_dict["enforcement_mode"] = policy.enforcement_mode.value

                with open(policy_file, "w", encoding="utf-8") as f:
                    json.dump(policy_dict, f, indent=2, ensure_ascii=False)

            except Exception as e:
                logger.error("Failed to save policy %s: %s", policy.policy_id, e)

    def _load_compliance_mappings(self) -> Dict:
        """Load compliance framework mappings"""
        return {
            "soc2": {
                "access_control": ["CC6.1", "CC6.2", "CC6.3"],
                "password_policy": ["CC6.1"],
                "session_management": ["CC6.2"],
                "data_protection": ["CC6.7", "CC7.1"],
                "audit_logging": ["CC7.2"],
                "network_security": ["CC6.1"],
            },
            "gdpr": {
                "data_protection": ["Article 25", "Article 32"],
                "access_control": ["Article 32"],
                "audit_logging": ["Article 30"],
                "incident_response": ["Article 33", "Article 34"],
            },
            "iso27001": {
                "access_control": ["A.9.1.1", "A.9.2.1", "A.9.4.1"],
                "password_policy": ["A.9.2.1"],
                "session_management": ["A.9.2.5"],
                "data_protection": ["A.10.1.1", "A.18.1.3"],
                "network_security": ["A.13.1.1", "A.13.2.1"],
                "audit_logging": ["A.12.4.1"],
                "incident_response": ["A.16.1.1"],
            },
        }

    def _get_password_policy_definition(self) -> Dict:
        """Get password security policy definition."""
        return {
            "name": "Password Security Policy",
            "description": "Defines password strength and lifecycle requirements",
            "policy_type": PolicyType.PASSWORD_POLICY,
            "rules": [
                {
                    "name": "minimum_length",
                    "value": 12,
                    "description": "Passwords must be at least 12 characters long",
                },
                {
                    "name": "complexity_requirements",
                    "value": {
                        "uppercase": True,
                        "lowercase": True,
                        "numbers": True,
                        "special_chars": True,
                    },
                    "description": (
                        "Passwords must contain uppercase, lowercase, numbers, "
                        "and special characters"
                    ),
                },
                {
                    "name": "password_history",
                    "value": 12,
                    "description": "Cannot reuse last 12 passwords",
                },
                {
                    "name": "max_age_days",
                    "value": 90,
                    "description": "Passwords must be changed every 90 days",
                },
            ],
        }

    def _get_session_policy_definition(self) -> Dict:
        """Get session management policy definition."""
        return {
            "name": "Session Management Policy",
            "description": "Defines session timeout and security requirements",
            "policy_type": PolicyType.SESSION_MANAGEMENT,
            "rules": [
                {
                    "name": "idle_timeout_minutes",
                    "value": 30,
                    "description": "Sessions timeout after 30 minutes of inactivity",
                },
                {
                    "name": "absolute_timeout_hours",
                    "value": 8,
                    "description": "Sessions must be renewed every 8 hours",
                },
                {
                    "name": "concurrent_sessions",
                    "value": 3,
                    "description": "Maximum 3 concurrent sessions per user",
                },
                {
                    "name": "secure_cookies",
                    "value": True,
                    "description": "All session cookies must be secure",
                },
            ],
        }

    def _get_data_protection_policy_definition(self) -> Dict:
        """Get data protection policy definition."""
        return {
            "name": "Data Protection Policy",
            "description": "Defines data classification and protection requirements",
            "policy_type": PolicyType.DATA_PROTECTION,
            "rules": [
                {
                    "name": "encryption_at_rest",
                    "value": True,
                    "description": "All sensitive data must be encrypted at rest",
                },
                {
                    "name": "encryption_in_transit",
                    "value": True,
                    "description": "All data transmission must be encrypted",
                },
                {
                    "name": "data_retention_days",
                    "value": 2555,
                    "description": "Data retention period for compliance (7 years)",
                },
                {
                    "name": "pii_handling",
                    "value": {
                        "detection_required": True,
                        "anonymization_required": True,
                        "consent_tracking": True,
                    },
                    "description": (
                        "PII must be detected, anonymized, and consent tracked"
                    ),
                },
            ],
        }

    def _get_access_control_policy_definition(self) -> Dict:
        """Get access control policy definition."""
        return {
            "name": "Access Control Policy",
            "description": "Defines user access and authorization requirements",
            "policy_type": PolicyType.ACCESS_CONTROL,
            "rules": [
                {
                    "name": "principle_of_least_privilege",
                    "value": True,
                    "description": "Users granted minimum necessary access",
                },
                {
                    "name": "role_based_access",
                    "value": True,
                    "description": "Access controlled through role assignments",
                },
                {
                    "name": "access_review_frequency_days",
                    "value": 90,
                    "description": "Access permissions reviewed quarterly",
                },
                {
                    "name": "admin_access_approval",
                    "value": True,
                    "description": "Administrative access requires approval",
                },
            ],
        }

    def _get_audit_logging_policy_definition(self) -> Dict:
        """Get audit logging policy definition."""
        return {
            "name": "Audit Logging Policy",
            "description": "Defines audit logging and monitoring requirements",
            "policy_type": PolicyType.AUDIT_LOGGING,
            "rules": [
                {
                    "name": "log_authentication_events",
                    "value": True,
                    "description": "All authentication events must be logged",
                },
                {
                    "name": "log_authorization_events",
                    "value": True,
                    "description": "All authorization events must be logged",
                },
                {
                    "name": "log_data_access",
                    "value": True,
                    "description": "All data access events must be logged",
                },
                {
                    "name": "log_retention_days",
                    "value": 2555,
                    "description": "Audit logs retained for 7 years",
                },
                {
                    "name": "log_integrity_protection",
                    "value": True,
                    "description": "Audit logs must be protected from tampering",
                },
            ],
        }

    def _get_default_policy_definitions(self) -> List[Dict]:
        """Get all default policy definitions."""
        return [
            self._get_password_policy_definition(),
            self._get_session_policy_definition(),
            self._get_data_protection_policy_definition(),
            self._get_access_control_policy_definition(),
            self._get_audit_logging_policy_definition(),
        ]

    def _initialize_default_policies(self):
        """Initialize default security policies if none exist."""
        if len(self.policies) > 0:
            return

        default_policies = self._get_default_policy_definitions()

        for policy_data in default_policies:
            policy_id = self.create_policy(
                name=policy_data["name"],
                description=policy_data["description"],
                policy_type=policy_data["policy_type"],
                rules=policy_data["rules"],
                author="system",
            )
            self.approve_policy(policy_id, "system")

        logger.info("Initialized %s default security policies", len(default_policies))

    def create_policy(
        self,
        name: str,
        description: str,
        policy_type: PolicyType,
        rules: List[Dict],
        author: str,
        enforcement_mode: EnforcementMode = EnforcementMode.ENFORCE,
        effective_date: Optional[datetime] = None,
        expiry_date: Optional[datetime] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Create a new security policy"""

        policy_id = str(uuid4())

        policy = SecurityPolicy(
            policy_id=policy_id,
            name=name,
            description=description,
            policy_type=policy_type,
            status=PolicyStatus.DRAFT,
            enforcement_mode=enforcement_mode,
            rules=rules,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            version="1.0",
            author=author,
            approval_required=self.config.get("policy_management", {}).get(
                "require_approval", True
            ),
            effective_date=effective_date,
            expiry_date=expiry_date,
        )

        self.policies[policy_id] = policy
        self._save_policy(policy)
        self._update_policy_statistics()

        logger.info("Created new security policy: %s (%s)", name, policy_id)
        return policy_id

    def update_policy(self, policy_id: str, updates: Dict, author: str) -> bool:
        """Update an existing security policy"""

        if policy_id not in self.policies:
            logger.error("Policy not found: %s", policy_id)
            return False

        policy = self.policies[policy_id]

        # Create new version
        version_parts = policy.version.split(".")
        major, minor = int(version_parts[0]), int(version_parts[1])

        # Increment version
        if any(key in updates for key in MAJOR_VERSION_UPDATE_KEYS):
            major += 1
            minor = 0
        else:
            minor += 1

        new_version = f"{major}.{minor}"

        # Apply updates
        for key, value in updates.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

        policy.version = new_version
        policy.updated_at = datetime.utcnow()
        policy.author = author

        # Reset approval if significant changes
        if any(key in updates for key in MAJOR_VERSION_UPDATE_KEYS):
            policy.status = PolicyStatus.DRAFT
            policy.approved_by = None
            policy.approved_at = None

        self._save_policy(policy)
        self._update_policy_statistics()

        logger.info("Updated policy %s to version %s", policy_id, new_version)
        return True

    def approve_policy(self, policy_id: str, approver: str) -> bool:
        """Approve a security policy"""

        if policy_id not in self.policies:
            logger.error("Policy not found: %s", policy_id)
            return False

        policy = self.policies[policy_id]

        policy.status = PolicyStatus.ACTIVE
        policy.approved_by = approver
        policy.approved_at = datetime.utcnow()

        if not policy.effective_date:
            policy.effective_date = datetime.utcnow()

        self._save_policy(policy)
        self._update_policy_statistics()

        logger.info("Approved policy %s by %s", policy_id, approver)
        return True

    def deactivate_policy(self, policy_id: str) -> bool:
        """Deactivate a security policy"""

        if policy_id not in self.policies:
            logger.error("Policy not found: %s", policy_id)
            return False

        policy = self.policies[policy_id]
        policy.status = PolicyStatus.INACTIVE
        policy.updated_at = datetime.utcnow()

        self._save_policy(policy)
        self._update_policy_statistics()

        logger.info("Deactivated policy %s", policy_id)
        return True

    def _create_violation(
        self, policy: "SecurityPolicy", check_result: Dict, context: Dict
    ) -> "PolicyViolation":
        """Create a PolicyViolation from check result (Issue #315 - extracted helper)."""
        return PolicyViolation(
            violation_id=str(uuid4()),
            policy_id=policy.policy_id,
            user_id=context.get("user_id", "unknown"),
            resource=context.get("resource", ""),
            action=context.get("action", ""),
            violation_type=check_result["violation_type"],
            severity=check_result["severity"],
            timestamp=datetime.utcnow(),
            details=check_result["details"],
        )

    def _apply_enforcement_mode(
        self,
        enforcement_result: Dict,
        policy: "SecurityPolicy",
        violation: "PolicyViolation",
    ):
        """Apply enforcement mode to result (Issue #315 - extracted helper)."""
        mode_actions = {
            EnforcementMode.ENFORCE: lambda: (
                enforcement_result.update({"allowed": False}),
                enforcement_result["violations"].append(violation),
            ),
            EnforcementMode.WARN: lambda: enforcement_result["warnings"].append(
                violation
            ),
            EnforcementMode.MONITOR: lambda: None,  # Log only, no action
        }
        action = mode_actions.get(policy.enforcement_mode)
        if action:
            action()

    async def enforce_policy(self, policy_type: PolicyType, context: Dict) -> Dict:
        """Enforce policies of a specific type against a context (Issue #315 - refactored)."""
        enforcement_result = {
            "allowed": True,
            "violations": [],
            "warnings": [],
            "policy_checks": [],
        }

        active_policies = [
            p
            for p in self.policies.values()
            if p.policy_type == policy_type and p.status == PolicyStatus.ACTIVE
        ]

        for policy in active_policies:
            check_result = await self._check_policy_compliance(policy, context)
            enforcement_result["policy_checks"].append(check_result)

            if check_result["compliant"]:
                continue

            violation = self._create_violation(policy, check_result, context)
            self._apply_enforcement_mode(enforcement_result, policy, violation)
            self.policy_violations.append(violation)
            self._log_policy_violation(violation)

        return enforcement_result

    def _get_policy_checker(self, policy_type: PolicyType):
        """Get the appropriate policy checker for type (Issue #315 - dispatch table)."""
        policy_checkers = {
            PolicyType.PASSWORD_POLICY: self._check_password_policy,
            PolicyType.SESSION_MANAGEMENT: self._check_session_policy,
            PolicyType.ACCESS_CONTROL: self._check_access_policy,
            PolicyType.DATA_PROTECTION: self._check_data_protection_policy,
            PolicyType.AUDIT_LOGGING: self._check_audit_policy,
        }
        return policy_checkers.get(policy_type)

    async def _check_policy_compliance(
        self, policy: SecurityPolicy, context: Dict
    ) -> Dict:
        """Check if context complies with a specific policy (Issue #315 - refactored)."""
        result = {
            "policy_id": policy.policy_id,
            "policy_name": policy.name,
            "compliant": True,
            "violation_type": None,
            "severity": "low",
            "details": {},
        }

        # Use dispatch table for policy-specific checks
        checker = self._get_policy_checker(policy.policy_type)
        if checker:
            result = await checker(policy, context, result)

        return result

    def _check_password_complexity(
        self, password: str, requirements: Dict, result: Dict
    ) -> None:
        """Check password complexity requirements."""
        checks = [
            ("uppercase", lambda p: any(c.isupper() for c in p), "uppercase_letter"),
            ("lowercase", lambda p: any(c.islower() for c in p), "lowercase_letter"),
            ("numbers", lambda p: any(c.isdigit() for c in p), "number"),
            (
                "special_chars",
                lambda p: any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in p),
                "special_character",
            ),
        ]
        for req_key, check_fn, missing_type in checks:
            if requirements.get(req_key) and not check_fn(password):
                result["compliant"] = False
                result["violation_type"] = "password_complexity"
                result["severity"] = "medium"
                result["details"]["missing"] = missing_type

    async def _check_password_policy(
        self, policy: SecurityPolicy, context: Dict, result: Dict
    ) -> Dict:
        """Check password policy compliance."""
        password = context.get("password", "")
        if not password:
            return result

        for rule in policy.rules:
            if rule["name"] == "minimum_length" and len(password) < rule["value"]:
                result["compliant"] = False
                result["violation_type"] = "password_too_short"
                result["severity"] = "medium"
                result["details"]["minimum_length"] = rule["value"]
                result["details"]["actual_length"] = len(password)
            elif rule["name"] == "complexity_requirements":
                self._check_password_complexity(password, rule["value"], result)

        return result

    async def _check_session_policy(
        self, policy: SecurityPolicy, context: Dict, result: Dict
    ) -> Dict:
        """Check session management policy compliance"""
        session_data = context.get("session", {})

        for rule in policy.rules:
            if rule["name"] == "idle_timeout_minutes":
                last_activity = session_data.get("last_activity")
                if last_activity:
                    idle_time = (datetime.utcnow() - last_activity).total_seconds() / 60
                    if idle_time > rule["value"]:
                        result["compliant"] = False
                        result["violation_type"] = "session_idle_timeout"
                        result["severity"] = "low"
                        result["details"]["idle_minutes"] = idle_time
                        result["details"]["max_idle_minutes"] = rule["value"]

            elif rule["name"] == "concurrent_sessions":
                active_sessions = session_data.get("active_sessions", 0)
                if active_sessions > rule["value"]:
                    result["compliant"] = False
                    result["violation_type"] = "too_many_sessions"
                    result["severity"] = "medium"
                    result["details"]["active_sessions"] = active_sessions
                    result["details"]["max_sessions"] = rule["value"]

        return result

    async def _check_access_policy(
        self, policy: SecurityPolicy, context: Dict, result: Dict
    ) -> Dict:
        """Check access control policy compliance"""
        user_role = context.get("user_role", "")
        requested_action = context.get("action", "")
        resource = context.get("resource", "")

        for rule in policy.rules:
            if rule["name"] == "admin_access_approval":
                if (
                    rule["value"]
                    and user_role == "admin"
                    and not context.get("manager_approved", False)
                ):
                    result["compliant"] = False
                    result["violation_type"] = "admin_access_not_approved"
                    result["severity"] = "high"
                    result["details"]["action"] = requested_action
                    result["details"]["resource"] = resource

        return result

    async def _check_data_protection_policy(
        self, policy: SecurityPolicy, context: Dict, result: Dict
    ) -> Dict:
        """Check data protection policy compliance"""
        data_classification = context.get("data_classification", "")
        encryption_status = context.get("encryption_status", {})

        for rule in policy.rules:
            if rule["name"] == "encryption_at_rest":
                if (
                    rule["value"]
                    and data_classification in SENSITIVE_DATA_CLASSIFICATIONS
                    and not encryption_status.get("at_rest", False)
                ):
                    result["compliant"] = False
                    result["violation_type"] = "data_not_encrypted_at_rest"
                    result["severity"] = "high"
                    result["details"]["data_classification"] = data_classification

            elif rule["name"] == "encryption_in_transit":
                if rule["value"] and not encryption_status.get("in_transit", False):
                    result["compliant"] = False
                    result["violation_type"] = "data_not_encrypted_in_transit"
                    result["severity"] = "high"
                    result["details"]["protocol"] = context.get("protocol", "unknown")

        return result

    async def _check_audit_policy(
        self, policy: SecurityPolicy, context: Dict, result: Dict
    ) -> Dict:
        """Check audit logging policy compliance"""
        event_type = context.get("event_type", "")
        logging_enabled = context.get("logging_enabled", False)

        for rule in policy.rules:
            if rule["name"] == "log_authentication_events":
                if (
                    rule["value"]
                    and event_type == "authentication"
                    and not logging_enabled
                ):
                    result["compliant"] = False
                    result["violation_type"] = "authentication_not_logged"
                    result["severity"] = "medium"
                    result["details"]["event_type"] = event_type

        return result

    def _log_policy_violation(self, violation: PolicyViolation):
        """Log policy violation for monitoring and compliance"""
        self.stats["policy_violations"] += 1
        violation_type = violation.violation_type
        self.stats["violations_by_type"][violation_type] = (
            self.stats["violations_by_type"].get(violation_type, 0) + 1
        )

        logger.warning(
            "POLICY VIOLATION: %s | Policy: %s | User: %s | Severity: %s | Resource: %s",
            violation.violation_type,
            violation.policy_id,
            violation.user_id,
            violation.severity,
            violation.resource,
        )

    def get_policy(self, policy_id: str) -> Optional[SecurityPolicy]:
        """Get a specific policy by ID"""
        return self.policies.get(policy_id)

    def list_policies(
        self,
        policy_type: Optional[PolicyType] = None,
        status: Optional[PolicyStatus] = None,
    ) -> List[SecurityPolicy]:
        """List policies with optional filtering"""

        policies = list(self.policies.values())

        if policy_type:
            policies = [p for p in policies if p.policy_type == policy_type]

        if status:
            policies = [p for p in policies if p.status == status]

        return policies

    def get_compliance_mapping(
        self, policy_type: PolicyType, framework: str
    ) -> List[str]:
        """Get compliance framework mappings for a policy type"""
        return self.compliance_mappings.get(framework, {}).get(policy_type.value, [])

    def _calculate_policy_coverage(self, framework_mappings: Dict) -> Dict[str, Dict]:
        """Calculate policy coverage for each policy type."""
        coverage = {}
        for policy_type_str, controls in framework_mappings.items():
            policy_type = PolicyType(policy_type_str)
            active_policies = [
                p
                for p in self.policies.values()
                if p.policy_type == policy_type and p.status == PolicyStatus.ACTIVE
            ]
            coverage[policy_type_str] = {
                "required_controls": controls,
                "active_policies": len(active_policies),
                "policy_names": [p.name for p in active_policies],
                "coverage_percentage": len(active_policies) / len(controls) * 100
                if controls
                else 100,
            }
        return coverage

    def _calculate_violations_summary(self) -> Dict[str, int]:
        """Calculate violations summary by policy type."""
        summary = {}
        for violation in self.policy_violations[-100:]:
            policy = self.policies.get(violation.policy_id)
            if policy:
                policy_type_str = policy.policy_type.value
                summary[policy_type_str] = summary.get(policy_type_str, 0) + 1
        return summary

    def _calculate_compliance_score(self, policy_coverage: Dict) -> float:
        """Calculate overall compliance score."""
        if not policy_coverage:
            return 0.0
        total_coverage = sum(
            pc["coverage_percentage"] for pc in policy_coverage.values()
        )
        avg_coverage = total_coverage / len(policy_coverage)
        violation_penalty = min(20, len(self.policy_violations[-30:]))
        return max(0, (avg_coverage - violation_penalty) / 100)

    def generate_compliance_report(self, framework: str) -> Dict:
        """Generate compliance report for a specific framework."""
        framework_mappings = self.compliance_mappings.get(framework, {})
        policy_coverage = self._calculate_policy_coverage(framework_mappings)
        compliance_score = self._calculate_compliance_score(policy_coverage)

        recommendations = []
        if compliance_score < 0.95:
            for policy_type_str, coverage in policy_coverage.items():
                if coverage["coverage_percentage"] < 100:
                    recommendations.append(
                        f"Implement policies for {policy_type_str} to cover "
                        f"required controls: {coverage['required_controls']}"
                    )

        return {
            "framework": framework,
            "generated_at": datetime.utcnow().isoformat(),
            "policy_coverage": policy_coverage,
            "violations_summary": self._calculate_violations_summary(),
            "compliance_score": compliance_score,
            "recommendations": recommendations,
        }

    def _update_policy_statistics(self):
        """Update policy statistics"""
        self.stats["total_policies"] = len(self.policies)
        self.stats["active_policies"] = len(
            [p for p in self.policies.values() if p.status == PolicyStatus.ACTIVE]
        )
        self.stats["last_policy_update"] = datetime.utcnow().isoformat()

        # Calculate compliance score
        if self.stats["total_policies"] > 0:
            active_ratio = self.stats["active_policies"] / self.stats["total_policies"]
            violation_penalty = min(
                0.3, self.stats["policy_violations"] / 100
            )  # Max 30% penalty
            self.stats["compliance_score"] = max(0, active_ratio - violation_penalty)

    def get_statistics(self) -> Dict:
        """Get policy management statistics"""
        return {
            **self.stats,
            "policies_by_type": {
                policy_type.value: len(
                    [p for p in self.policies.values() if p.policy_type == policy_type]
                )
                for policy_type in PolicyType
            },
            "policies_by_status": {
                status.value: len(
                    [p for p in self.policies.values() if p.status == status]
                )
                for status in PolicyStatus
            },
            "recent_violations": len(
                [
                    v
                    for v in self.policy_violations
                    if (datetime.utcnow() - v.timestamp).days <= 30
                ]
            ),
        }

    async def check_policy_compliance_batch(self, contexts: List[Dict]) -> List[Dict]:
        """Check policy compliance for multiple contexts in batch"""
        results = []

        for context in contexts:
            policy_type = context.get("policy_type")
            if policy_type and isinstance(policy_type, str):
                policy_type = PolicyType(policy_type)

            if policy_type:
                result = await self.enforce_policy(policy_type, context)
                results.append(result)
            else:
                results.append({"error": "Invalid or missing policy_type"})

        return results
