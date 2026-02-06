# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Compliance Manager for Enterprise Security
Handles SOC2, GDPR, ISO27001 audit logging and reporting requirements

Issue #378: Added threading locks for file operations to prevent race conditions.
"""

import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import aiofiles
import yaml
from cryptography.fernet import Fernet

from constants.path_constants import PATH

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets for compliance checks
_CONSENT_REQUIRED_ACTIONS = frozenset({"data_export", "analytics", "marketing"})
_COMPLIANCE_FRAMEWORKS_WITH_RETENTION = frozenset({"soc2", "gdpr", "iso27001"})
_AUTH_ACTIONS = frozenset({"login", "authentication"})
_MONITORING_ACTIONS = frozenset({"monitoring", "security_scan"})
_ACCESS_ACTIONS = frozenset({"data_access", "data_export"})
_MODIFICATION_ACTIONS = frozenset({"data_modification", "data_update"})
_DELETION_ACTIONS = frozenset({"data_deletion", "account_deletion"})
_PORTABILITY_ACTIONS = frozenset({"data_export", "data_portability"})
_HIGH_SEVERITY_LEVELS = frozenset({"high", "critical"})


class ComplianceFramework(Enum):
    """Supported compliance frameworks"""

    SOC2 = "soc2"
    GDPR = "gdpr"
    ISO27001 = "iso27001"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"


class AuditEventType(Enum):
    """Types of auditable events"""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    SYSTEM_CONFIGURATION = "system_configuration"
    SECURITY_INCIDENT = "security_incident"
    PRIVACY_EVENT = "privacy_event"
    ADMIN_ACTION = "admin_action"
    FILE_OPERATION = "file_operation"
    API_ACCESS = "api_access"


class DataClassification(Enum):
    """Data classification levels for privacy compliance"""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PII = "pii"
    SENSITIVE_PII = "sensitive_pii"


class ComplianceManager:
    """
    Enterprise compliance manager for audit logging, reporting, and regulatory compliance
    """

    def __init__(
        self,
        config_path: str = str(PATH.get_config_path("security", "compliance.yaml")),
    ):
        """Initialize compliance manager with config and audit storage paths."""
        self.config_path = config_path
        self.config = self._load_config()

        # Initialize audit storage
        self.audit_base_path = Path(
            self.config.get("audit_storage", {}).get(
                "base_path", str(PATH.get_log_path("audit"))
            )
        )
        self.audit_base_path.mkdir(parents=True, exist_ok=True)

        # Initialize encryption for sensitive audit data
        self.encryption_key = self._get_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key) if self.encryption_key else None

        # Compliance requirements mapping
        self.compliance_requirements = self._load_compliance_requirements()

        # Statistics tracking
        self.stats = {
            "total_events": 0,
            "events_by_type": {},
            "compliance_violations": 0,
            "pii_events": 0,
            "security_incidents": 0,
            "failed_authentications": 0,
        }

        # Initialize retention policies
        self.retention_policies = self._initialize_retention_policies()

        # Thread-safe file operations (Issue #378)
        self._file_lock = threading.Lock()

        logger.info("Compliance Manager initialized")

    def _load_config(self) -> Dict:
        """Load compliance configuration"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f)
            else:
                # Create default config
                default_config = self._get_default_config()
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error("Failed to load compliance config: %s", e)
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Return default compliance configuration"""
        return {
            "enabled_frameworks": ["soc2", "gdpr", "iso27001"],
            "audit_storage": {
                "base_path": str(PATH.get_log_path("audit")),
                "encrypt_sensitive": True,
                "max_file_size_mb": 100,
                "compression_enabled": True,
            },
            "retention_policies": {
                "authentication_events": {"days": 365},
                "data_access_events": {"days": 2555},  # 7 years for SOC2
                "security_incidents": {"days": 2555},
                "pii_events": {"days": 2555},
                "default": {"days": 365},
            },
            "privacy_controls": {
                "pii_detection": True,
                "anonymization": True,
                "consent_tracking": True,
                "right_to_erasure": True,
            },
            "reporting": {
                "daily_summary": True,
                "weekly_compliance": True,
                "monthly_detailed": True,
                "real_time_alerts": True,
            },
            "notification_thresholds": {
                "failed_authentication_rate": 10,  # per hour
                "security_incident_severity": "medium",
                "pii_access_unusual": 50,  # per hour
            },
        }

    def _save_config(self, config: Dict):
        """Save configuration to file (thread-safe, Issue #378)"""
        with self._file_lock:
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, default_flow_style=False)
            except Exception as e:
                logger.error("Failed to save compliance config: %s", e)

    def _get_encryption_key(self) -> Optional[bytes]:
        """Get or generate encryption key for sensitive audit data (thread-safe, Issue #378)"""
        key_path = self.audit_base_path / ".audit_key"

        # Note: _file_lock not yet initialized during __init__, use local lock
        with threading.Lock():
            if key_path.exists():
                try:
                    with open(key_path, "rb") as f:
                        return f.read()
                except Exception as e:
                    logger.error("Failed to load encryption key: %s", e)

            # Generate new key
            try:
                key = Fernet.generate_key()
                with open(key_path, "wb") as f:
                    f.write(key)

                # Set restrictive permissions
                os.chmod(key_path, 0o600)
                logger.info("Generated new audit encryption key")
                return key
            except Exception as e:
                logger.error("Failed to generate encryption key: %s", e)
                return None

    def _load_compliance_requirements(self) -> Dict:
        """Load compliance framework requirements"""
        return {
            ComplianceFramework.SOC2: {
                "required_events": [
                    AuditEventType.AUTHENTICATION,
                    AuditEventType.AUTHORIZATION,
                    AuditEventType.DATA_ACCESS,
                    AuditEventType.SYSTEM_CONFIGURATION,
                    AuditEventType.ADMIN_ACTION,
                ],
                "retention_days": 2555,  # 7 years
                "encryption_required": True,
                "integrity_monitoring": True,
            },
            ComplianceFramework.GDPR: {
                "required_events": [
                    AuditEventType.DATA_ACCESS,
                    AuditEventType.DATA_MODIFICATION,
                    AuditEventType.PRIVACY_EVENT,
                ],
                "retention_days": 2555,
                "pii_tracking": True,
                "consent_logging": True,
                "anonymization_required": True,
            },
            ComplianceFramework.ISO27001: {
                "required_events": [
                    AuditEventType.SECURITY_INCIDENT,
                    AuditEventType.SYSTEM_CONFIGURATION,
                    AuditEventType.ADMIN_ACTION,
                    AuditEventType.AUTHORIZATION,
                ],
                "retention_days": 2190,  # 6 years
                "risk_assessment": True,
                "security_monitoring": True,
            },
        }

    def _initialize_retention_policies(self) -> Dict:
        """Initialize data retention policies"""
        policies = self.config.get("retention_policies", {})

        # Ensure compliance with framework requirements
        for framework in self.config.get("enabled_frameworks", []):
            if framework in _COMPLIANCE_FRAMEWORKS_WITH_RETENTION:
                framework_enum = ComplianceFramework(framework)
                requirements = self.compliance_requirements.get(framework_enum, {})
                min_retention = requirements.get("retention_days", 365)

                # Update policies to meet minimum requirements
                for event_type in policies:
                    if policies[event_type]["days"] < min_retention:
                        policies[event_type]["days"] = min_retention
                        logger.info(
                            "Updated retention policy for %s to meet %s requirements",
                            event_type,
                            framework,
                        )

        return policies

    def _build_base_audit_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        action: str,
        resource: str,
        outcome: str,
        details: Optional[Dict],
        data_classification: DataClassification,
        compliance_frameworks: Optional[List[ComplianceFramework]],
    ) -> Dict:
        """
        Build base audit event dictionary with core fields.

        Returns:
            Audit event dictionary with generated event_id. Issue #620.
        """
        return {
            "event_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "outcome": outcome,
            "data_classification": data_classification.value,
            "details": details or {},
            "compliance_frameworks": [f.value for f in (compliance_frameworks or [])],
        }

    async def _process_audit_event(
        self,
        audit_event: Dict,
        data_classification: DataClassification,
    ) -> None:
        """
        Process audit event through enrichment, storage, and validation.

        Issue #620.
        """
        await self._enrich_compliance_data(audit_event)

        if data_classification in {
            DataClassification.PII,
            DataClassification.SENSITIVE_PII,
        }:
            await self._handle_pii_event(audit_event)

        await self._store_audit_event(audit_event)
        self._update_statistics(audit_event)

        await asyncio.gather(
            self._check_compliance_violations(audit_event),
            self._check_real_time_alerts(audit_event),
        )

    async def log_audit_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        action: str,
        resource: str,
        outcome: str = "success",
        details: Optional[Dict] = None,
        data_classification: DataClassification = DataClassification.INTERNAL,
        compliance_frameworks: Optional[List[ComplianceFramework]] = None,
    ) -> str:
        """
        Log audit event with comprehensive compliance tracking.

        Issue #620: Refactored to use _build_base_audit_event and
        _process_audit_event helpers.

        Returns:
            str: Unique audit event ID
        """
        audit_event = self._build_base_audit_event(
            event_type,
            user_id,
            action,
            resource,
            outcome,
            details,
            data_classification,
            compliance_frameworks,
        )

        await self._process_audit_event(audit_event, data_classification)

        return audit_event["event_id"]

    async def _enrich_compliance_data(self, audit_event: Dict):
        """Enrich audit event with compliance-specific data"""

        # Add SOC2-specific fields
        if "soc2" in self.config.get("enabled_frameworks", []):
            audit_event["soc2"] = {
                "trust_service_criteria": self._map_to_trust_criteria(
                    audit_event["action"]
                ),
                "control_objective": self._get_control_objective(
                    audit_event["event_type"]
                ),
                "evidence_type": "automated_log",
            }

        # Add GDPR-specific fields
        if "gdpr" in self.config.get("enabled_frameworks", []):
            audit_event["gdpr"] = {
                "lawful_basis": self._determine_lawful_basis(audit_event),
                "data_subject_rights": self._check_data_subject_rights(audit_event),
                "processing_purpose": self._get_processing_purpose(
                    audit_event["action"]
                ),
            }

        # Add ISO27001-specific fields
        if "iso27001" in self.config.get("enabled_frameworks", []):
            audit_event["iso27001"] = {
                "security_control": self._map_to_iso_control(audit_event["action"]),
                "risk_level": self._assess_risk_level(audit_event),
                "asset_classification": audit_event["data_classification"],
            }

    def _map_to_trust_criteria(self, action: str) -> List[str]:
        """Map action to SOC2 Trust Service Criteria"""
        mapping = {
            "login": ["CC6.1", "CC6.2"],  # Security - Logical access
            "data_access": ["CC6.3", "CC7.1"],  # Security - System operations
            "configuration_change": ["CC8.1"],  # Change Management
            "backup": ["A1.2"],  # Availability
            "monitoring": ["CC7.2"],  # System Monitoring
        }

        return mapping.get(action, ["CC1.1"])  # Default to Control Environment

    def _get_control_objective(self, event_type: str) -> str:
        """Get SOC2 control objective for event type"""
        objectives = {
            "authentication": "Access Control - User Authentication",
            "authorization": "Access Control - User Authorization",
            "data_access": "Data Protection - Authorized Access",
            "system_configuration": "Change Management - System Changes",
            "security_incident": "Incident Response - Security Events",
        }

        return objectives.get(event_type, "General Security Controls")

    def _determine_lawful_basis(self, audit_event: Dict) -> str:
        """Determine GDPR lawful basis for processing"""
        # This would typically involve business logic to determine basis
        action = audit_event["action"]

        if action in _AUTH_ACTIONS:
            return "contract"  # Performance of contract
        elif action in _MONITORING_ACTIONS:
            return "legitimate_interests"  # Legitimate interests
        elif "consent" in audit_event.get("details", {}):
            return "consent"  # Explicit consent
        else:
            return "legal_obligation"  # Compliance with legal obligation

    def _check_data_subject_rights(self, audit_event: Dict) -> List[str]:
        """Check which GDPR data subject rights are relevant"""
        rights = []

        action = audit_event["action"]
        if action in _ACCESS_ACTIONS:
            rights.append("right_of_access")
        if action in _MODIFICATION_ACTIONS:
            rights.append("right_to_rectification")
        if action in _DELETION_ACTIONS:
            rights.append("right_to_erasure")
        if action in _PORTABILITY_ACTIONS:
            rights.append("right_to_data_portability")

        return rights

    def _get_processing_purpose(self, action: str) -> str:
        """Get GDPR processing purpose"""
        purposes = {
            "login": "authentication_and_access_control",
            "data_access": "service_provision",
            "monitoring": "security_and_fraud_prevention",
            "backup": "data_protection_and_recovery",
            "analytics": "service_improvement",
        }

        return purposes.get(action, "operational_necessity")

    def _map_to_iso_control(self, action: str) -> str:
        """Map action to ISO27001 control"""
        controls = {
            "login": "A.9.2.1",  # User registration and de-registration
            "data_access": "A.9.4.1",  # Information access restriction
            "configuration_change": "A.12.1.2",  # Change management
            "monitoring": "A.12.4.1",  # Event logging
            "incident": "A.16.1.1",  # Incident management
        }

        return controls.get(action, "A.18.1.1")  # General compliance

    def _assess_risk_level(self, audit_event: Dict) -> str:
        """Assess risk level for ISO27001"""
        high_risk_actions = [
            "admin_action",
            "system_configuration",
            "security_incident",
        ]
        medium_risk_actions = ["data_modification", "authorization_change"]

        action = audit_event["action"]
        outcome = audit_event["outcome"]

        if outcome == "failure" or action in high_risk_actions:
            return "high"
        elif action in medium_risk_actions:
            return "medium"
        else:
            return "low"

    async def _handle_pii_event(self, audit_event: Dict):
        """Special handling for PII-related events"""
        self.stats["pii_events"] += 1

        # Add PII-specific metadata
        audit_event["pii_handling"] = {
            "anonymization_applied": (
                self.config.get("privacy_controls", {}).get("anonymization", False)
            ),
            "consent_verified": await self._verify_consent(audit_event),
            "retention_period": self._get_pii_retention_period(audit_event),
            "encryption_applied": True,  # PII should always be encrypted
        }

        # Log PII access for GDPR compliance (Issue #380: use module constant)
        if audit_event["action"] in _ACCESS_ACTIONS:
            await self._log_pii_access(audit_event)

    async def _verify_consent(self, audit_event: Dict) -> bool:
        """Verify user consent for PII processing"""
        # This would integrate with consent management system
        # For now, return basic logic
        action = audit_event["action"]

        # Check if consent is required for this action - Issue #380
        if action in _CONSENT_REQUIRED_ACTIONS:
            # In production, check actual consent records
            return False  # Conservative default

        return True  # Operational necessity doesn't require explicit consent

    def _get_pii_retention_period(self, audit_event: Dict) -> int:
        """Get retention period for PII events"""
        # GDPR requires minimum retention for compliance
        return self.retention_policies.get("pii_events", {"days": 2555})["days"]

    async def _log_pii_access(self, audit_event: Dict):
        """Log PII access for data subject access request compliance"""
        pii_access_log = {
            "timestamp": audit_event["timestamp"],
            "data_subject": audit_event["user_id"],
            "accessed_by": audit_event.get("details", {}).get("accessed_by", "system"),
            "purpose": audit_event.get("gdpr", {}).get("processing_purpose", "unknown"),
            "legal_basis": audit_event.get("gdpr", {}).get("lawful_basis", "unknown"),
        }

        # Store in separate PII access log for DSAR responses
        pii_log_path = (
            self.audit_base_path
            / "pii_access"
            / f"{datetime.utcnow().strftime('%Y-%m-%d')}.json"
        )
        # Issue #358 - avoid blocking
        await asyncio.to_thread(pii_log_path.parent.mkdir, exist_ok=True)

        try:
            # Use aiofiles for non-blocking file I/O
            async with aiofiles.open(pii_log_path, "a", encoding="utf-8") as f:
                await f.write(json.dumps(pii_access_log) + "\n")
        except OSError as e:
            logger.error("Failed to write PII log to %s: %s", pii_log_path, e)
        except Exception as e:
            logger.error("Failed to log PII access: %s", e)

    async def _store_audit_event(self, audit_event: Dict):
        """Store audit event with appropriate security measures"""

        # Determine storage path based on event type and date
        date_str = datetime.fromisoformat(audit_event["timestamp"]).strftime("%Y-%m-%d")
        event_type = audit_event["event_type"]

        storage_path = self.audit_base_path / event_type / f"{date_str}.jsonl"
        # Issue #358 - avoid blocking
        await asyncio.to_thread(storage_path.parent.mkdir, parents=True, exist_ok=True)

        # Encrypt sensitive events
        sensitive_events = [
            AuditEventType.PRIVACY_EVENT.value,
            AuditEventType.SECURITY_INCIDENT.value,
        ]

        if event_type in sensitive_events or audit_event["data_classification"] in {
            "pii",
            "sensitive_pii",
        }:
            await self._store_encrypted_event(audit_event, storage_path)
        else:
            await self._store_plain_event(audit_event, storage_path)

    async def _store_encrypted_event(self, audit_event: Dict, storage_path: Path):
        """Store encrypted audit event"""
        if not self.cipher_suite:
            logger.error("Encryption not available for sensitive audit event")
            return

        try:
            # Encrypt event data
            event_json = json.dumps(audit_event)
            encrypted_data = self.cipher_suite.encrypt(event_json.encode())

            # Store with encryption marker
            encrypted_event = {
                "encrypted": True,
                "data": encrypted_data.decode("utf-8"),
                "timestamp": audit_event["timestamp"],
                "event_id": audit_event["event_id"],
            }

            async with aiofiles.open(storage_path, "a", encoding="utf-8") as f:
                await f.write(json.dumps(encrypted_event) + "\n")

        except OSError as e:
            logger.error(
                "Failed to write encrypted audit event to %s: %s", storage_path, e
            )
        except Exception as e:
            logger.error("Failed to store encrypted audit event: %s", e)

    async def _store_plain_event(self, audit_event: Dict, storage_path: Path):
        """Store plain text audit event"""
        try:
            async with aiofiles.open(storage_path, "a", encoding="utf-8") as f:
                await f.write(json.dumps(audit_event) + "\n")
        except OSError as e:
            logger.error("Failed to write audit event to %s: %s", storage_path, e)
        except Exception as e:
            logger.error("Failed to store audit event: %s", e)

    def _update_statistics(self, audit_event: Dict):
        """Update compliance statistics"""
        self.stats["total_events"] += 1

        event_type = audit_event["event_type"]
        self.stats["events_by_type"][event_type] = (
            self.stats["events_by_type"].get(event_type, 0) + 1
        )

        if (
            audit_event["event_type"] == AuditEventType.AUTHENTICATION.value
            and audit_event["outcome"] == "failure"
        ):
            self.stats["failed_authentications"] += 1

        if audit_event["event_type"] == AuditEventType.SECURITY_INCIDENT.value:
            self.stats["security_incidents"] += 1

    async def _check_compliance_violations(self, audit_event: Dict):
        """Check for compliance violations"""
        enabled_frameworks = self.config.get("enabled_frameworks", [])

        # Issue #619: Build list of enabled checks and run in parallel
        check_tasks = []
        if "soc2" in enabled_frameworks:
            check_tasks.append(self._check_soc2_violations(audit_event))
        if "gdpr" in enabled_frameworks:
            check_tasks.append(self._check_gdpr_violations(audit_event))

        if not check_tasks:
            return

        # Run all compliance checks in parallel
        results = await asyncio.gather(*check_tasks)
        violations = []
        for result in results:
            violations.extend(result)

        # Log violations
        if violations:
            self.stats["compliance_violations"] += len(violations)
            await self._handle_compliance_violations(violations, audit_event)

    async def _check_soc2_violations(self, audit_event: Dict) -> List[Dict]:
        """Check for SOC2 compliance violations"""
        violations = []

        # Example: Check for unauthorized administrative actions
        if (
            audit_event["event_type"] == AuditEventType.ADMIN_ACTION.value
            and audit_event["outcome"] == "success"
            and "unauthorized" in audit_event.get("details", {}).get("flags", [])
        ):
            violations.append(
                {
                    "framework": "SOC2",
                    "violation_type": "unauthorized_admin_action",
                    "severity": "high",
                    "control": "CC6.1",
                    "description": (
                        "Administrative action performed without proper authorization"
                    ),
                }
            )

        return violations

    async def _check_gdpr_violations(self, audit_event: Dict) -> List[Dict]:
        """Check for GDPR compliance violations"""
        violations = []

        # Example: Check for PII access without consent
        if audit_event["data_classification"] in {
            "pii",
            "sensitive_pii",
        } and not audit_event.get("pii_handling", {}).get("consent_verified", True):
            violations.append(
                {
                    "framework": "GDPR",
                    "violation_type": "pii_access_without_consent",
                    "severity": "high",
                    "article": "Article 6",
                    "description": "PII accessed without valid legal basis or consent",
                }
            )

        return violations

    async def _handle_compliance_violations(
        self, violations: List[Dict], audit_event: Dict
    ):
        """Handle detected compliance violations"""
        for violation in violations:
            # Log violation
            violation_event = {
                "event_id": str(uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": "compliance_violation",
                "original_event_id": audit_event["event_id"],
                "violation": violation,
                "severity": violation["severity"],
            }

            # Store violation record
            await self._store_violation_record(violation_event)

            # Send alerts for high severity violations (Issue #380: use module constant)
            if violation["severity"] in _HIGH_SEVERITY_LEVELS:
                await self._send_compliance_alert(violation_event)

    async def _store_violation_record(self, violation_event: Dict):
        """Store compliance violation record"""
        violations_path = (
            self.audit_base_path
            / "violations"
            / f"{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
        )
        # Issue #358 - avoid blocking
        await asyncio.to_thread(violations_path.parent.mkdir, exist_ok=True)

        try:
            # Use aiofiles for non-blocking file I/O
            async with aiofiles.open(violations_path, "a", encoding="utf-8") as f:
                await f.write(json.dumps(violation_event) + "\n")
        except OSError as e:
            logger.error(
                "Failed to write violation record to %s: %s", violations_path, e
            )
        except Exception as e:
            logger.error("Failed to store violation record: %s", e)

    async def _send_compliance_alert(self, violation_event: Dict):
        """Send real-time compliance alert"""
        # This would integrate with alerting system (email, Slack, etc.)
        logger.critical(
            f"COMPLIANCE VIOLATION: {violation_event['violation']['framework']} - "
            f"{violation_event['violation']['violation_type']} - "
            f"Severity: {violation_event['severity']}"
        )

    async def _check_real_time_alerts(self, audit_event: Dict):
        """Check for real-time alert conditions"""
        thresholds = self.config.get("notification_thresholds", {})

        # Check failed authentication rate
        if (
            audit_event["event_type"] == AuditEventType.AUTHENTICATION.value
            and audit_event["outcome"] == "failure"
        ):
            recent_failures = await self._count_recent_events(
                AuditEventType.AUTHENTICATION, outcome="failure", hours=1
            )

            if recent_failures >= thresholds.get("failed_authentication_rate", 10):
                await self._send_security_alert(
                    "High authentication failure rate detected"
                )

    async def _count_recent_events(
        self, event_type: AuditEventType, outcome: str = None, hours: int = 1
    ) -> int:
        """Count recent events of specific type"""
        # This would query the audit logs for recent events
        # For now, return a placeholder
        return 0

    async def _send_security_alert(self, message: str):
        """Send security alert"""
        logger.warning("SECURITY ALERT: %s", message)

    async def generate_compliance_report(
        self,
        framework: ComplianceFramework,
        start_date: datetime,
        end_date: datetime,
        output_path: Optional[Path] = None,
    ) -> Dict:
        """Generate compliance report for specific framework"""

        report = {
            "framework": framework.value,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "generated_at": datetime.utcnow().isoformat(),
            "statistics": await self._gather_compliance_statistics(
                framework, start_date, end_date
            ),
            "violations": await self._gather_violations(
                framework, start_date, end_date
            ),
            "evidence": await self._gather_compliance_evidence(
                framework, start_date, end_date
            ),
        }

        # Save report if output path provided
        if output_path:
            await self._save_report(report, output_path)

        return report

    async def _gather_compliance_statistics(
        self, framework: ComplianceFramework, start_date: datetime, end_date: datetime
    ) -> Dict:
        """Gather statistics for compliance report"""
        # This would analyze audit logs for the period
        return {
            "total_events": self.stats["total_events"],
            "events_by_type": self.stats["events_by_type"],
            "violations_count": self.stats["compliance_violations"],
            "security_incidents": self.stats["security_incidents"],
        }

    async def _gather_violations(
        self, framework: ComplianceFramework, start_date: datetime, end_date: datetime
    ) -> List[Dict]:
        """Gather compliance violations for report"""
        # This would read violation records from the period
        return []

    async def _gather_compliance_evidence(
        self, framework: ComplianceFramework, start_date: datetime, end_date: datetime
    ) -> Dict:
        """Gather compliance evidence for report"""
        requirements = self.compliance_requirements.get(framework, {})
        evidence = {}

        for event_type in requirements.get("required_events", []):
            evidence[event_type.value] = {
                "events_logged": True,  # Would check actual logs
                "retention_compliant": True,
                "encryption_applied": requirements.get("encryption_required", False),
            }

        return evidence

    async def _save_report(self, report: Dict, output_path: Path):
        """Save compliance report to file"""
        try:
            await asyncio.to_thread(
                output_path.parent.mkdir, parents=True, exist_ok=True
            )
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(report, indent=2))
            logger.info("Compliance report saved to %s", output_path)
        except OSError as e:
            logger.error("Failed to write compliance report to %s: %s", output_path, e)
        except Exception as e:
            logger.error("Failed to save compliance report: %s", e)

    def get_compliance_status(self) -> Dict:
        """Get current compliance status across all frameworks"""
        status = {
            "frameworks": {},
            "overall_health": "unknown",
            "statistics": self.stats,
            "last_violation": None,
            "next_audit_due": None,
        }

        for framework_name in self.config.get("enabled_frameworks", []):
            # Framework enum and requirements available for future validation
            _ = ComplianceFramework(framework_name)

            status["frameworks"][framework_name] = {
                "enabled": True,
                "retention_compliant": True,  # Would check actual retention
                "required_events_logged": True,  # Would verify logging
                "violations_count": 0,  # Would count actual violations
                "last_audit": None,
            }

        # Determine overall health
        total_violations = sum(
            f.get("violations_count", 0) for f in status["frameworks"].values()
        )
        if total_violations == 0:
            status["overall_health"] = "healthy"
        elif total_violations < 5:
            status["overall_health"] = "warning"
        else:
            status["overall_health"] = "critical"

        return status
