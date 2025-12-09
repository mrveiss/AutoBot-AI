# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Threat Detection Engine for Enterprise Security
Provides behavioral anomaly detection, ML-based threat detection, and enhanced security monitoring

Issue #378: Added threading locks for file operations to prevent race conditions.
"""

import asyncio
import logging
import pickle
import re
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import yaml
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.constants.path_constants import PATH
from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozensets to avoid repeated list creation in detection methods
_SENSITIVE_RESOURCE_KEYWORDS = frozenset({"admin", "config", "secret", "key", "password"})
_FILE_OPERATION_ACTIONS = frozenset({"file_read", "file_write", "file_delete", "file_upload"})


class ThreatLevel(Enum):
    """Threat severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatCategory(Enum):
    """Categories of security threats"""

    COMMAND_INJECTION = "command_injection"
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"
    BRUTE_FORCE = "brute_force"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    MALICIOUS_UPLOAD = "malicious_upload"
    INSIDER_THREAT = "insider_threat"
    API_ABUSE = "api_abuse"
    RECONNAISSANCE = "reconnaissance"
    LATERAL_MOVEMENT = "lateral_movement"


@dataclass
class SecurityEvent:
    """Typed wrapper for raw security event dictionaries"""

    raw_event: Dict

    @property
    def user_id(self) -> str:
        """Get user ID from event, defaulting to 'unknown'."""
        return self.raw_event.get("user_id", "unknown")

    @property
    def source_ip(self) -> str:
        """Get source IP address from event, defaulting to 'unknown'."""
        return self.raw_event.get("source_ip", "unknown")

    @property
    def action(self) -> str:
        """Get action type from event."""
        return self.raw_event.get("action", "")

    @property
    def resource(self) -> str:
        """Get resource identifier from event."""
        return self.raw_event.get("resource", "")

    @property
    def timestamp(self) -> datetime:
        """Get event timestamp as datetime object."""
        timestamp_str = self.raw_event.get("timestamp", datetime.utcnow().isoformat())
        return datetime.fromisoformat(timestamp_str)

    @property
    def details(self) -> Dict:
        """Get event details dictionary."""
        return self.raw_event.get("details", {})

    @property
    def outcome(self) -> str:
        """Get event outcome string."""
        return self.raw_event.get("outcome", "")

    def is_authentication_event(self) -> bool:
        """Check if event is an authentication action."""
        return self.action == "authentication"

    def is_authentication_failure(self) -> bool:
        """Check if event is a failed authentication attempt."""
        return self.is_authentication_event() and self.outcome == "failure"

    def is_file_operation(self) -> bool:
        """Check if event is a file system operation."""
        return self.action in _FILE_OPERATION_ACTIONS

    def is_api_request(self) -> bool:
        """Check if event is an API request."""
        return self.action == "api_request"

    def get_timestamp_hour(self) -> int:
        """Get the hour component of the event timestamp."""
        return self.timestamp.hour

    def get_command_content(self) -> str:
        """Extract command content from details"""
        command = self.details.get("command", "")
        args = self.details.get("args", "")
        return f"{command} {args}"

    def get_filename(self) -> str:
        """Get filename from event details."""
        return self.details.get("filename", "")

    def get_file_content_preview(self) -> str:
        """Get file content preview from event details."""
        return self.details.get("content_preview", "")

    def get_file_size(self) -> int:
        """Get file size in bytes from event details."""
        return self.details.get("file_size", 0)

    def get_response_size(self) -> int:
        """Get response size in bytes from event details."""
        return self.details.get("response_size", 0)

    def get_data_volume(self) -> int:
        """Get data volume in bytes from event details."""
        return self.details.get("data_volume", 0)

    # === Issue #372: Feature Envy Reduction Methods ===

    def get_threat_base_fields(self) -> Dict:
        """Get base fields for ThreatEvent creation (Issue #372 - reduces feature envy).

        Returns dict with common fields needed when creating a ThreatEvent from this event.
        """
        return {
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "source_ip": self.source_ip,
            "action": self.action,
            "resource": self.resource,
            "raw_event": self.raw_event,
        }

    def generate_threat_id(self, prefix: str) -> str:
        """Generate a unique threat ID based on this event (Issue #372 - reduces feature envy)."""
        event_hash = hash(f"{self.user_id}_{self.resource}") % 10000
        return f"{prefix}_{int(time.time())}_{event_hash}"


@dataclass
class EventHistory:
    """Encapsulates event history and provides query methods to reduce Feature Envy"""

    events: deque

    def count_recent_failures(
        self, user_id: str, source_ip: str, window_minutes: int
    ) -> int:
        """Count recent authentication failures"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)
        count = 0

        for event in reversed(self.events):
            event_time = datetime.fromisoformat(
                event.get("timestamp", datetime.utcnow().isoformat())
            )
            if event_time < cutoff_time:
                break
            if (
                event.get("action") == "authentication"
                and event.get("outcome") == "failure"
                and (
                    event.get("user_id") == user_id
                    or event.get("source_ip") == source_ip
                )
            ):
                count += 1

        return count

    def count_recent_api_requests(
        self, user_id: str, source_ip: str, window_minutes: int
    ) -> int:
        """Count recent API requests"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)
        count = 0

        for event in reversed(self.events):
            event_time = datetime.fromisoformat(
                event.get("timestamp", datetime.utcnow().isoformat())
            )
            if event_time < cutoff_time:
                break
            if event.get("action") == "api_request" and (
                event.get("user_id") == user_id or event.get("source_ip") == source_ip
            ):
                count += 1

        return count

    def get_recent_action_frequency(
        self, user_id: str, action: str, hours: int = 1
    ) -> int:
        """Count recent action frequency for a user"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        count = 0

        for event in reversed(self.events):
            event_time = datetime.fromisoformat(
                event.get("timestamp", datetime.utcnow().isoformat())
            )
            if event_time < cutoff_time:
                break
            if event.get("user_id") == user_id and event.get("action") == action:
                count += 1

        return count

    def get_recent_endpoint_usage(
        self, user_id: str, endpoint: str, hours: int = 24
    ) -> int:
        """Get recent endpoint usage count"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        count = 0

        for event in reversed(self.events):
            event_time = datetime.fromisoformat(
                event.get("timestamp", datetime.utcnow().isoformat())
            )
            if event_time < cutoff_time:
                break
            if (
                event.get("user_id") == user_id
                and event.get("action") == "api_request"
                and event.get("resource") == endpoint
            ):
                count += 1

        return count

    def filter_by_user(self, user_id: str) -> List[Dict]:
        """Get all events for a specific user"""
        return [e for e in self.events if e.get("user_id") == user_id]

    def count_high_risk_actions(self, user_id: str) -> int:
        """Count recent high-risk actions for a user"""
        high_risk_actions = [
            "admin_action",
            "system_configuration",
            "privilege_escalation",
        ]
        return sum(
            1
            for event in self.events
            if event.get("user_id") == user_id
            and event.get("action") in high_risk_actions
        )

    def count_off_hours_activity(self, user_id: str) -> int:
        """Count off-hours activity (before 6 AM) for a user"""
        return sum(
            1
            for event in self.events
            if event.get("user_id") == user_id
            and datetime.fromisoformat(
                event.get("timestamp", datetime.utcnow().isoformat())
            ).hour
            < 6
        )


@dataclass
class ThreatEvent:
    """Represents a detected security threat"""

    event_id: str
    timestamp: datetime
    threat_category: ThreatCategory
    threat_level: ThreatLevel
    confidence_score: float
    user_id: str
    source_ip: str
    action: str
    resource: str
    details: Dict
    raw_event: Dict
    mitigation_actions: List[str]


@dataclass
class UserProfile:
    """User behavioral profile for anomaly detection"""

    user_id: str
    baseline_actions: Dict[str, float] = field(default_factory=dict)
    typical_hours: List[int] = field(default_factory=list)
    typical_ips: set = field(default_factory=set)
    command_patterns: List[str] = field(default_factory=list)
    file_access_patterns: Dict[str, int] = field(default_factory=dict)
    api_usage_patterns: Dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.5
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def is_anomalous_time(self, hour: int) -> bool:
        """Check if access hour is anomalous for this user"""
        return hour not in self.typical_hours

    def is_anomalous_ip(self, ip: str) -> bool:
        """Check if IP is anomalous for this user"""
        return ip not in self.typical_ips

    def is_anomalous_action_frequency(
        self, action: str, current_frequency: int, deviation_threshold: float
    ) -> bool:
        """Check if action frequency is anomalous"""
        normal_frequency = self.baseline_actions.get(action, 0)
        return current_frequency > normal_frequency * deviation_threshold

    def is_anomalous_file_access(self, resource: str) -> bool:
        """Check if file access is anomalous (never accessed before)"""
        return self.file_access_patterns.get(resource, 0) == 0

    def is_high_risk(self) -> bool:
        """Check if user is considered high risk"""
        return self.risk_score > 0.7

    # === Issue #372: Feature Envy Reduction Methods ===

    def get_baseline_comparison(self, action: str, current_frequency: int) -> Dict:
        """Get baseline comparison dict for threat details (Issue #372 - reduces feature envy)."""
        return {
            "normal_action_frequency": self.baseline_actions.get(action, 0),
            "current_frequency": current_frequency,
            "typical_hours": list(self.typical_hours),
            "typical_ip_count": len(self.typical_ips),
        }

    def update_with_event(self, event: SecurityEvent):
        """Update profile with new event data"""
        # Update action frequency
        if event.action:
            self.baseline_actions[event.action] = (
                self.baseline_actions.get(event.action, 0) + 1
            )

        # Update typical hours
        event_hour = event.get_timestamp_hour()
        if event_hour not in self.typical_hours and len(self.typical_hours) < 12:
            self.typical_hours.append(event_hour)

        # Update typical IPs
        if event.source_ip and len(self.typical_ips) < 10:
            self.typical_ips.add(event.source_ip)

        # Update file access patterns
        if event.is_file_operation() and event.resource:
            self.file_access_patterns[event.resource] = (
                self.file_access_patterns.get(event.resource, 0) + 1
            )

        # Update API usage patterns
        if event.is_api_request() and event.resource:
            self.api_usage_patterns[event.resource] = (
                self.api_usage_patterns.get(event.resource, 0) + 1
            )

        self.last_updated = datetime.utcnow()

    def calculate_risk_score(self, event_history: EventHistory) -> float:
        """Calculate risk score based on recent behavior from event history"""
        risk_factors = []

        # Count recent high-risk actions
        recent_high_risk = event_history.count_high_risk_actions(self.user_id)

        if recent_high_risk > 5:
            risk_factors.append(0.3)
        elif recent_high_risk > 2:
            risk_factors.append(0.2)

        # Check for off-hours activity
        off_hours_activity = event_history.count_off_hours_activity(self.user_id)

        if off_hours_activity > 10:
            risk_factors.append(0.2)
        elif off_hours_activity > 5:
            risk_factors.append(0.1)

        # Base risk score
        base_risk = 0.3
        return min(1.0, base_risk + sum(risk_factors))

    def get_risk_assessment(self, event_history: EventHistory) -> Dict:
        """Get comprehensive risk assessment for this user"""
        # Filter events for this user
        user_events = event_history.filter_by_user(self.user_id)

        return {
            "user_id": self.user_id,
            "risk_score": self.risk_score,
            "risk_level": (
                "high"
                if self.risk_score > 0.7
                else "medium" if self.risk_score > 0.4 else "low"
            ),
            "profile_age_days": (datetime.utcnow() - self.last_updated).days,
            "total_actions": sum(self.baseline_actions.values()),
            "unique_actions": len(self.baseline_actions),
            "typical_access_hours": sorted(self.typical_hours),
            "known_ip_addresses": len(self.typical_ips),
            "recent_activity_count": len(user_events),
            "file_access_diversity": len(self.file_access_patterns),
            "api_usage_diversity": len(self.api_usage_patterns),
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class AnalysisContext:
    """Context data for threat analysis"""

    config: Dict
    user_profiles: Dict[str, UserProfile]
    event_history: EventHistory
    injection_patterns: List[Dict]
    file_signatures: List[Dict]
    api_patterns: List[Dict]

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile if exists"""
        return self.user_profiles.get(user_id)

    def get_recent_action_frequency(
        self, user_id: str, action: str, hours: int = 1
    ) -> int:
        """Count recent action frequency for a user"""
        return self.event_history.get_recent_action_frequency(user_id, action, hours)

    def count_recent_failures(
        self, user_id: str, source_ip: str, window_minutes: int
    ) -> int:
        """Count recent authentication failures"""
        return self.event_history.count_recent_failures(
            user_id, source_ip, window_minutes
        )

    def count_recent_api_requests(
        self, user_id: str, source_ip: str, window_minutes: int
    ) -> int:
        """Count recent API requests"""
        return self.event_history.count_recent_api_requests(
            user_id, source_ip, window_minutes
        )

    def get_recent_endpoint_usage(
        self, user_id: str, endpoint: str, hours: int = 24
    ) -> int:
        """Get recent endpoint usage count"""
        return self.event_history.get_recent_endpoint_usage(user_id, endpoint, hours)


class ThreatAnalyzer(ABC):
    """Abstract base class for threat analyzers"""

    @abstractmethod
    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Analyze event for specific threat type"""
        pass


# Issue #315 - Severity priority ordering for comparison
_SEVERITY_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _get_max_severity(current: str, new: str) -> str:
    """Return the higher severity between two values (Issue #315 - extracted helper)."""
    if _SEVERITY_PRIORITY.get(new, 0) > _SEVERITY_PRIORITY.get(current, 0):
        return new
    return current


class CommandInjectionAnalyzer(ThreatAnalyzer):
    """Analyzes events for command injection threats"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect command injection attempts (Issue #315 - refactored)."""
        command_content = event.get_command_content()

        detected_patterns = []
        max_severity = "low"

        for pattern_info in context.injection_patterns:
            if re.search(pattern_info["pattern"], command_content, re.IGNORECASE):
                detected_patterns.append(pattern_info)
                max_severity = _get_max_severity(max_severity, pattern_info["severity"])

        if detected_patterns:
            confidence = min(1.0, len(detected_patterns) * 0.3 + 0.4)

            return ThreatEvent(
                event_id=f"cmd_inj_{int(time.time())}_{hash(command_content) % 10000}",
                timestamp=event.timestamp,
                threat_category=ThreatCategory.COMMAND_INJECTION,
                threat_level=ThreatLevel(max_severity),
                confidence_score=confidence,
                user_id=event.user_id,
                source_ip=event.source_ip,
                action=event.action,
                resource=event.resource,
                details={
                    "detected_patterns": [p["description"] for p in detected_patterns],
                    "command_content": command_content[:200],
                    "pattern_categories": [p["category"] for p in detected_patterns],
                },
                raw_event=event.raw_event,
                mitigation_actions=[
                    "block_command",
                    "quarantine_session",
                    "alert_security_team",
                ],
            )

        return None


class BehavioralAnomalyAnalyzer(ThreatAnalyzer):
    """Analyzes events for behavioral anomalies"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect behavioral anomalies using user profiles"""
        if event.user_id == "unknown":
            return None

        profile = context.get_user_profile(event.user_id)
        if not profile:
            return None

        anomalies = []

        # Check time-based anomalies
        if profile.is_anomalous_time(event.get_timestamp_hour()):
            anomalies.append("unusual_access_time")

        # Check IP-based anomalies
        if profile.is_anomalous_ip(event.source_ip):
            anomalies.append("unusual_source_ip")

        # Check action frequency anomalies
        recent_frequency = context.get_recent_action_frequency(
            event.user_id, event.action
        )
        deviation_threshold = context.config.get("behavioral_analysis", {}).get(
            "deviation_threshold", 2.0
        )
        if profile.is_anomalous_action_frequency(
            event.action, recent_frequency, deviation_threshold
        ):
            anomalies.append("unusual_action_frequency")

        # Check file access patterns
        if event.is_file_operation() and profile.is_anomalous_file_access(
            event.resource
        ):
            anomalies.append("unusual_file_access")

        if anomalies:
            confidence = min(1.0, len(anomalies) * 0.25 + 0.3)
            threat_level = (
                ThreatLevel.HIGH if len(anomalies) >= 3 else ThreatLevel.MEDIUM
            )

            # Issue #372: Use model methods to reduce feature envy
            base_fields = event.get_threat_base_fields()
            return ThreatEvent(
                event_id=event.generate_threat_id("behavioral"),
                threat_category=ThreatCategory.BEHAVIORAL_ANOMALY,
                threat_level=threat_level,
                confidence_score=confidence,
                details={
                    "anomalies_detected": anomalies,
                    "user_risk_score": profile.risk_score,
                    "baseline_comparison": profile.get_baseline_comparison(
                        event.action, recent_frequency
                    ),
                },
                mitigation_actions=[
                    "monitor_user",
                    "require_additional_auth",
                    "alert_security_team",
                ],
                **base_fields,
            )

        return None


class BruteForceAnalyzer(ThreatAnalyzer):
    """Analyzes events for brute force attacks"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect brute force attacks"""
        if not event.is_authentication_failure():
            return None

        window_minutes = context.config.get("thresholds", {}).get(
            "brute_force_window_minutes", 15
        )
        threshold = context.config.get("thresholds", {}).get("brute_force_attempts", 5)

        recent_failures = context.count_recent_failures(
            event.user_id, event.source_ip, window_minutes
        )

        if recent_failures >= threshold:
            confidence = min(1.0, recent_failures / threshold)
            event_hash = hash(f"{event.user_id}_{event.source_ip}") % 10000

            return ThreatEvent(
                event_id=f"brute_force_{int(time.time())}_{event_hash}",
                timestamp=event.timestamp,
                threat_category=ThreatCategory.BRUTE_FORCE,
                threat_level=ThreatLevel.HIGH,
                confidence_score=confidence,
                user_id=event.user_id,
                source_ip=event.source_ip,
                action="authentication",
                resource="login",
                details={
                    "failed_attempts": recent_failures,
                    "time_window_minutes": window_minutes,
                    "attack_pattern": (
                        "credential_stuffing"
                        if event.user_id != "unknown"
                        else "dictionary_attack"
                    ),
                },
                raw_event=event.raw_event,
                mitigation_actions=["block_ip", "lock_account", "alert_security_team"],
            )

        return None


class MaliciousFileAnalyzer(ThreatAnalyzer):
    """Analyzes events for malicious file uploads"""

    def _check_signature_patterns(
        self,
        signature: dict,
        key: str,
        target: str,
        threat_prefix: str,
        match_type: str = "contains",
    ) -> List[str]:
        """
        Check signature patterns against a target string.

        Issue #281: Extracted helper to reduce repetition in analyze.

        Args:
            signature: Signature dict containing pattern lists
            key: Key in signature dict to check (e.g., "extension", "suspicious_names")
            target: Target string to check against
            threat_prefix: Prefix for threat identifiers
            match_type: "contains", "endswith", or "exact"

        Returns:
            List of detected threat identifiers
        """
        threats = []
        if key not in signature:
            return threats

        target_lower = target.lower()
        for pattern in signature[key]:
            pattern_lower = pattern.lower()
            matched = False

            if match_type == "endswith":
                matched = target_lower.endswith(pattern_lower)
            elif match_type == "contains":
                matched = pattern_lower in target_lower
            elif match_type == "exact":
                matched = pattern in target

            if matched:
                threats.append(f"{threat_prefix}_{pattern}")

        return threats

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect malicious file uploads"""
        if not event.is_file_operation():
            return None

        filename = event.get_filename()
        file_content = event.get_file_content_preview()
        file_size = event.get_file_size()

        threats = []

        # Check file signatures (Issue #281: Using extracted helper)
        for signature in context.file_signatures:
            # Check extensions
            threats.extend(
                self._check_signature_patterns(
                    signature, "extension", filename,
                    "suspicious_extension", match_type="endswith"
                )
            )

            # Check content patterns
            if file_content:
                threats.extend(
                    self._check_signature_patterns(
                        signature, "content_patterns", file_content,
                        "malicious_content", match_type="exact"
                    )
                )

            # Check suspicious names
            threats.extend(
                self._check_signature_patterns(
                    signature, "suspicious_names", filename,
                    "suspicious_name", match_type="contains"
                )
            )

        # Check file size anomalies
        size_threshold = (
            context.config.get("thresholds", {}).get("file_size_suspicious_mb", 100)
            * 1024
            * 1024
        )
        if file_size > size_threshold:
            threats.append("unusually_large_file")

        if threats:
            confidence = min(1.0, len(threats) * 0.3 + 0.4)
            threat_level = (
                ThreatLevel.CRITICAL
                if any("malicious_content" in t for t in threats)
                else ThreatLevel.HIGH
            )

            return ThreatEvent(
                event_id=f"malicious_file_{int(time.time())}_{hash(filename) % 10000}",
                timestamp=event.timestamp,
                threat_category=ThreatCategory.MALICIOUS_UPLOAD,
                threat_level=threat_level,
                confidence_score=confidence,
                user_id=event.user_id,
                source_ip=event.source_ip,
                action=event.action,
                resource=filename,
                details={
                    "detected_threats": threats,
                    "filename": filename,
                    "file_size": file_size,
                    "content_preview": file_content[:100] if file_content else "",
                },
                raw_event=event.raw_event,
                mitigation_actions=[
                    "quarantine_file",
                    "scan_with_antivirus",
                    "alert_security_team",
                ],
            )

        return None


class APIAbuseAnalyzer(ThreatAnalyzer):
    """Analyzes events for API abuse patterns"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect API abuse patterns"""
        if not event.is_api_request():
            return None

        rate_limit = context.config.get("thresholds", {}).get(
            "api_rate_limit_per_minute", 100
        )
        recent_requests = context.count_recent_api_requests(
            event.user_id, event.source_ip, 1
        )

        threats = []

        if recent_requests > rate_limit:
            threats.append("rate_limit_exceeded")

        # Check for unusual endpoint access
        user_profile = context.get_user_profile(event.user_id)
        if user_profile and event.resource:
            normal_usage = user_profile.api_usage_patterns.get(event.resource, 0)
            current_usage = context.get_recent_endpoint_usage(
                event.user_id, event.resource
            )

            if normal_usage == 0 and current_usage > 0:
                threats.append("unusual_endpoint_access")
            elif current_usage > normal_usage * 5:
                threats.append("excessive_endpoint_usage")

        # Check for bulk data operations
        response_size = event.get_response_size()
        bulk_threshold = (
            context.config.get("thresholds", {}).get("bulk_data_threshold_mb", 100)
            * 1024
            * 1024
        )

        if response_size > bulk_threshold:
            threats.append("bulk_data_download")

        if threats:
            confidence = min(1.0, len(threats) * 0.4 + 0.3)
            threat_level = (
                ThreatLevel.HIGH
                if "bulk_data_download" in threats
                else ThreatLevel.MEDIUM
            )
            # Issue #372: Use SecurityEvent methods to reduce feature envy
            base_fields = event.get_threat_base_fields()

            return ThreatEvent(
                event_id=event.generate_threat_id("api_abuse"),
                **base_fields,
                threat_category=ThreatCategory.API_ABUSE,
                threat_level=threat_level,
                confidence_score=confidence,
                action="api_request",  # Override base action
                details={
                    "abuse_patterns": threats,
                    "request_rate": recent_requests,
                    "rate_limit": rate_limit,
                    "response_size": response_size,
                    "endpoint": event.resource,
                },
                mitigation_actions=[
                    "rate_limit_user",
                    "monitor_api_usage",
                    "alert_security_team",
                ],
            )

        return None


class InsiderThreatAnalyzer(ThreatAnalyzer):
    """Analyzes events for insider threat indicators"""

    async def analyze(
        self, event: SecurityEvent, context: AnalysisContext
    ) -> Optional[ThreatEvent]:
        """Detect insider threat indicators"""
        if event.user_id == "unknown":
            return None

        # High-risk insider threat indicators
        high_risk_actions = [
            "bulk_data_export",
            "privilege_escalation",
            "unauthorized_access",
            "credential_theft",
            "system_configuration_change",
        ]

        risk_indicators = []

        if event.action in high_risk_actions:
            risk_indicators.append(f"high_risk_action_{event.action}")

        # Check for off-hours access
        if event.get_timestamp_hour() < 6 or event.get_timestamp_hour() > 22:
            risk_indicators.append("off_hours_access")

        # Check for unusual resource access
        # Issue #380: Use module-level frozenset for O(1) lookup
        if event.resource and any(
            sensitive in event.resource.lower()
            for sensitive in _SENSITIVE_RESOURCE_KEYWORDS
        ):
            risk_indicators.append("sensitive_resource_access")

        # Check user risk profile
        user_profile = context.get_user_profile(event.user_id)
        if user_profile and user_profile.is_high_risk():
            risk_indicators.append("high_risk_user")

        # Check for data exfiltration patterns
        if event.get_data_volume() > 1000000:
            risk_indicators.append("large_data_access")

        if len(risk_indicators) >= 2:
            confidence = min(1.0, len(risk_indicators) * 0.3 + 0.4)
            threat_level = (
                ThreatLevel.CRITICAL if len(risk_indicators) >= 4 else ThreatLevel.HIGH
            )

            # Issue #372: Use SecurityEvent methods to reduce feature envy
            base_fields = event.get_threat_base_fields()

            return ThreatEvent(
                event_id=event.generate_threat_id("insider"),
                **base_fields,
                threat_category=ThreatCategory.INSIDER_THREAT,
                threat_level=threat_level,
                confidence_score=confidence,
                details={
                    "risk_indicators": risk_indicators,
                    "user_risk_score": user_profile.risk_score if user_profile else 0.0,
                    "access_time": event.timestamp.isoformat(),
                    "data_sensitivity": (
                        "high"
                        if any(
                            "sensitive" in indicator for indicator in risk_indicators
                        )
                        else "medium"
                    ),
                },
                mitigation_actions=[
                    "enhanced_monitoring",
                    "require_manager_approval",
                    "alert_security_team",
                    "document_incident",
                ],
            )

        return None


class ThreatDetectionEngine:
    """
    Advanced threat detection engine with ML-based anomaly detection
    """

    def __init__(
        self,
        config_path: str = str(
            PATH.get_config_path("security", "threat_detection.yaml")
        ),
    ):
        """Initialize threat detection engine with ML models and configuration."""
        # Thread-safe file operations - must be initialized first (Issue #378)
        self._file_lock = threading.Lock()

        self.config_path = config_path
        self.config = self._load_config()

        # Initialize detection models
        self.anomaly_detector = IsolationForest(contamination=0.1, random_state=42)
        self.scaler = StandardScaler()
        self.clustering_model = DBSCAN(eps=0.5, min_samples=5)

        # User behavioral profiles
        self.user_profiles: Dict[str, UserProfile] = {}
        self.profile_storage_path = PATH.get_data_path("security", "user_profiles.pkl")
        self.profile_storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Threat intelligence and patterns
        self.command_injection_patterns = self._load_injection_patterns()
        self.malicious_file_signatures = self._load_file_signatures()
        self.suspicious_api_patterns = self._load_api_patterns()

        # Real-time monitoring data structures
        self.recent_events = deque(maxlen=10000)  # Last 10k events for analysis
        self.event_history = EventHistory(events=self.recent_events)
        self.user_sessions = defaultdict(dict)  # Active user session tracking
        self.ip_reputation = defaultdict(float)  # IP reputation scores

        # Statistics and metrics
        self.stats = {
            "total_events_processed": 0,
            "threats_detected": 0,
            "false_positives": 0,
            "threats_by_category": defaultdict(int),
            "threats_by_level": defaultdict(int),
            "users_monitored": 0,
            "models_trained": 0,
        }

        # Initialize threat analyzers
        self.analyzers: List[ThreatAnalyzer] = [
            CommandInjectionAnalyzer(),
            BehavioralAnomalyAnalyzer(),
            BruteForceAnalyzer(),
            MaliciousFileAnalyzer(),
            APIAbuseAnalyzer(),
            InsiderThreatAnalyzer(),
        ]

        # Load existing profiles
        self._load_user_profiles()

        # Initialize background tasks
        self._start_background_tasks()

        logger.info("Threat Detection Engine initialized")

    def _load_config(self) -> Dict:
        """Load threat detection configuration"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
            else:
                default_config = self._get_default_config()
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error(f"Failed to load threat detection config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Return default threat detection configuration"""
        return {
            "detection_modes": {
                "behavioral_analysis": True,
                "command_injection_detection": True,
                "file_upload_scanning": True,
                "api_abuse_detection": True,
                "brute_force_detection": True,
                "insider_threat_detection": True,
            },
            "ml_models": {
                "anomaly_detection": True,
                "clustering_analysis": True,
                "pattern_recognition": True,
                "model_retrain_hours": 24,
                "min_training_samples": 1000,
            },
            "thresholds": {
                "anomaly_score": 0.7,
                "confidence_threshold": 0.8,
                "brute_force_attempts": 5,
                "brute_force_window_minutes": 15,
                "unusual_hour_threshold": 0.1,
                "file_size_suspicious_mb": 100,
                "api_rate_limit_per_minute": 100,
            },
            "behavioral_analysis": {
                "profile_update_hours": 6,
                "baseline_days": 30,
                "deviation_threshold": 2.0,
                "min_events_for_profile": 50,
            },
            "response_actions": {
                "auto_block_critical": False,
                "auto_quarantine_files": True,
                "rate_limit_suspicious_ips": True,
                "alert_security_team": True,
                "create_incident_tickets": False,
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
                logger.error(f"Failed to save threat detection config: {e}")

    def _load_injection_patterns(self) -> List[Dict]:
        """Load command injection detection patterns"""
        return [
            {
                "pattern": r"[;&|`$(){}[\]\\]",
                "description": "Shell metacharacters",
                "severity": "high",
                "category": "shell_injection",
            },
            {
                "pattern": r"(rm\s+-rf|del\s+/[sf]|format\s+c:)",
                "description": "Destructive file operations",
                "severity": "critical",
                "category": "destructive_commands",
            },
            {
                "pattern": r"(wget|curl|nc|netcat)\s+",
                "description": "Network tools for data exfiltration",
                "severity": "high",
                "category": "network_tools",
            },
            {
                "pattern": r"(base64|xxd|hexdump)\s+",
                "description": "Encoding tools for obfuscation",
                "severity": "medium",
                "category": "encoding_tools",
            },
            {
                "pattern": r"(sudo|su|chmod\s+777|chown)",
                "description": "Privilege escalation attempts",
                "severity": "high",
                "category": "privilege_escalation",
            },
            {
                "pattern": r"(/etc/passwd|/etc/shadow|/etc/hosts)",
                "description": "System file access",
                "severity": "high",
                "category": "system_file_access",
            },
            {
                "pattern": r"(python\s+-c|perl\s+-e|ruby\s+-e)",
                "description": "Inline script execution",
                "severity": "medium",
                "category": "script_injection",
            },
        ]

    def _load_file_signatures(self) -> List[Dict]:
        """Load malicious file signatures"""
        return [
            {
                "extension": [".exe", ".scr", ".bat", ".cmd"],
                "description": "Executable files",
                "risk_level": "high",
            },
            {
                "magic_bytes": ["4D5A", "7F454C46"],  # PE and ELF headers
                "description": "Binary executables",
                "risk_level": "high",
            },
            {
                "content_patterns": ["eval(", "exec(", "system(", "shell_exec("],
                "description": "Code execution patterns",
                "risk_level": "high",
            },
            {
                "suspicious_names": ["cmd.php", "shell.jsp", "backdoor", "webshell"],
                "description": "Common backdoor names",
                "risk_level": "critical",
            },
        ]

    def _load_api_patterns(self) -> List[Dict]:
        """Load suspicious API usage patterns"""
        return [
            {
                "pattern": "rapid_sequential_requests",
                "description": "Rapid API requests indicating automation",
                "threshold": 50,  # requests per minute
                "severity": "medium",
            },
            {
                "pattern": "unusual_endpoint_access",
                "description": "Access to rarely used endpoints",
                "threshold": 0.05,  # 5% of normal usage
                "severity": "medium",
            },
            {
                "pattern": "bulk_data_download",
                "description": "Large data download operations",
                "threshold": 1000,  # MB downloaded
                "severity": "high",
            },
            {
                "pattern": "privilege_boundary_crossing",
                "description": "Accessing resources beyond normal permissions",
                "severity": "high",
            },
        ]

    def _load_user_profiles(self):
        """Load existing user behavioral profiles"""
        try:
            if self.profile_storage_path.exists():
                with open(self.profile_storage_path, "rb") as f:
                    self.user_profiles = pickle.load(f)
                self.stats["users_monitored"] = len(self.user_profiles)
                logger.info(f"Loaded {len(self.user_profiles)} user profiles")
        except Exception as e:
            logger.error(f"Failed to load user profiles: {e}")
            self.user_profiles = {}

    def _save_user_profiles(self):
        """Save user behavioral profiles"""
        try:
            with open(self.profile_storage_path, "wb") as f:
                pickle.dump(self.user_profiles, f)
        except Exception as e:
            logger.error(f"Failed to save user profiles: {e}")

    def _start_background_tasks(self):
        """Start background monitoring and maintenance tasks"""
        # Schedule periodic tasks only if event loop is running
        try:
            asyncio.create_task(self._periodic_model_training())
            asyncio.create_task(self._periodic_profile_updates())
            asyncio.create_task(self._periodic_cleanup())
        except RuntimeError:
            # No event loop running - tasks will be started when loop becomes available
            logger.debug(
                "No event loop running, background tasks will be started later"
            )

    async def _periodic_model_training(self):
        """Periodically retrain ML models with new data"""
        retrain_interval = (
            self.config.get("ml_models", {}).get("model_retrain_hours", 24) * 3600
        )

        while True:
            try:
                await asyncio.sleep(retrain_interval)
                await self._retrain_models()
            except Exception as e:
                logger.error(f"Error in periodic model training: {e}")

    async def _periodic_profile_updates(self):
        """Periodically update user behavioral profiles"""
        update_interval = (
            self.config.get("behavioral_analysis", {}).get("profile_update_hours", 6)
            * 3600
        )

        while True:
            try:
                await asyncio.sleep(update_interval)
                await self._update_user_profiles()
            except Exception as e:
                logger.error(f"Error in periodic profile updates: {e}")

    async def _periodic_cleanup(self):
        """Periodic cleanup of old data and statistics"""
        while True:
            try:
                await asyncio.sleep(TimingConstants.HOURLY_INTERVAL)  # Cleanup every hour
                await self._cleanup_old_data()
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def analyze_event(self, event: Dict) -> Optional[ThreatEvent]:
        """
        Analyze a security event for potential threats

        Args:
            event: Security event to analyze

        Returns:
            ThreatEvent if threat detected, None otherwise
        """
        self.stats["total_events_processed"] += 1
        self.recent_events.append(event)

        # Wrap event in SecurityEvent for typed access
        security_event = SecurityEvent(raw_event=event)

        # Create analysis context
        context = AnalysisContext(
            config=self.config,
            user_profiles=self.user_profiles,
            event_history=self.event_history,
            injection_patterns=self.command_injection_patterns,
            file_signatures=self.malicious_file_signatures,
            api_patterns=self.suspicious_api_patterns,
        )

        # Run all analyzers
        detected_threats = []

        detection_modes = self.config.get("detection_modes", {})
        analyzer_mode_map = {
            CommandInjectionAnalyzer: "command_injection_detection",
            BehavioralAnomalyAnalyzer: "behavioral_analysis",
            BruteForceAnalyzer: "brute_force_detection",
            MaliciousFileAnalyzer: "file_upload_scanning",
            APIAbuseAnalyzer: "api_abuse_detection",
            InsiderThreatAnalyzer: "insider_threat_detection",
        }

        for analyzer in self.analyzers:
            # Check if this analyzer type is enabled
            mode_key = analyzer_mode_map.get(type(analyzer))
            if mode_key and not detection_modes.get(mode_key, True):
                continue

            threat = await analyzer.analyze(security_event, context)
            if threat:
                detected_threats.append(threat)

        # Select highest priority threat
        if detected_threats:
            primary_threat = max(
                detected_threats,
                key=lambda t: (t.threat_level.value, t.confidence_score),
            )

            self.stats["threats_detected"] += 1
            self.stats["threats_by_category"][primary_threat.threat_category.value] += 1
            self.stats["threats_by_level"][primary_threat.threat_level.value] += 1

            # Execute response actions
            await self._execute_response_actions(primary_threat)

            return primary_threat

        # Update user profile with benign behavior
        await self._update_user_behavior(security_event.user_id, security_event)

        return None

    async def _update_user_behavior(self, user_id: str, event: SecurityEvent):
        """Update user behavioral profile with new event"""
        if user_id == "unknown":
            return

        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = UserProfile(user_id=user_id)
            self.stats["users_monitored"] += 1

        profile = self.user_profiles[user_id]
        profile.update_with_event(event)

    def _get_response_action_handler(self, action: str, threat: ThreatEvent):
        """Get handler and config key for action type (Issue #315 - dispatch table)."""
        action_handlers = {
            "block_ip": (self._block_ip_address, "auto_block_critical", threat.source_ip),
            "quarantine_file": (self._quarantine_file, "auto_quarantine_files", threat.resource),
            "rate_limit_user": (self._apply_rate_limiting, "rate_limit_suspicious_ips", (threat.user_id, threat.source_ip)),
            "alert_security_team": (self._send_security_alert, "alert_security_team", threat),
        }
        return action_handlers.get(action)

    async def _execute_response_actions(self, threat: ThreatEvent):
        """Execute automated response actions based on threat (Issue #315 - refactored)."""
        response_config = self.config.get("response_actions", {})

        for action in threat.mitigation_actions:
            handler_info = self._get_response_action_handler(action, threat)
            if not handler_info:
                continue

            handler, config_key, args = handler_info
            if not response_config.get(config_key, config_key != "auto_block_critical"):
                continue

            # Execute with proper argument handling
            if isinstance(args, tuple):
                await handler(*args)
            else:
                await handler(args)

    async def _block_ip_address(self, ip_address: str):
        """Block suspicious IP address"""
        logger.warning(f"SECURITY ACTION: Blocking IP address {ip_address}")
        # Implementation would integrate with firewall/WAF

    async def _quarantine_file(self, filename: str):
        """Quarantine suspicious file"""
        logger.warning(f"SECURITY ACTION: Quarantining file {filename}")
        # Implementation would move file to quarantine directory

    async def _apply_rate_limiting(self, user_id: str, ip_address: str):
        """Apply rate limiting to user/IP"""
        logger.warning(
            f"SECURITY ACTION: Rate limiting user {user_id} from IP {ip_address}"
        )
        # Implementation would update rate limiting rules

    async def _send_security_alert(self, threat: ThreatEvent):
        """Send security alert to security team"""
        logger.critical(
            f"SECURITY THREAT DETECTED: {threat.threat_category.value} | "
            f"Level: {threat.threat_level.value} | "
            f"User: {threat.user_id} | "
            f"Confidence: {threat.confidence_score:.2f} | "
            f"IP: {threat.source_ip}"
        )

    async def _retrain_models(self):
        """Retrain ML models with new data"""
        min_samples = self.config.get("ml_models", {}).get("min_training_samples", 1000)

        if len(self.recent_events) < min_samples:
            logger.info(
                f"Insufficient data for model training: {len(self.recent_events)} < {min_samples}"
            )
            return

        try:
            # Prepare training data
            features = self._extract_features_from_events()

            if len(features) > 0:
                # Retrain anomaly detection model
                self.anomaly_detector.fit(features)
                self.stats["models_trained"] += 1
                logger.info("ML models retrained successfully")

        except Exception as e:
            logger.error(f"Failed to retrain models: {e}")

    def _extract_features_from_events(self) -> np.ndarray:
        """Extract numerical features from events for ML training"""
        features = []

        for event in self.recent_events[-1000:]:  # Use last 1000 events
            feature_vector = [
                len(event.get("action", "")),
                len(event.get("resource", "")),
                datetime.fromisoformat(
                    event.get("timestamp", datetime.utcnow().isoformat())
                ).hour,
                1 if event.get("outcome") == "success" else 0,
                len(event.get("details", {})),
                hash(event.get("user_id", "")) % 1000,  # User hash for anonymity
                hash(event.get("source_ip", "")) % 1000,  # IP hash for anonymity
            ]
            features.append(feature_vector)

        return np.array(features)

    async def _update_user_profiles(self):
        """Update all user profiles with risk scores from event history"""
        try:
            for user_id, profile in self.user_profiles.items():
                # Calculate risk score using profile's method with event history
                profile.risk_score = profile.calculate_risk_score(self.event_history)

            self._save_user_profiles()
            logger.info("User profiles updated successfully")
        except Exception as e:
            logger.error(f"Failed to update user profiles: {e}")

    async def _cleanup_old_data(self):
        """Clean up old data and maintain performance"""
        try:
            # Clean up old user sessions
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            expired_sessions = []

            for session_id, session_data in self.user_sessions.items():
                if session_data.get("last_activity", datetime.utcnow()) < cutoff_time:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                del self.user_sessions[session_id]

            # Reset daily statistics
            if datetime.utcnow().hour == 0:  # Midnight
                self.stats["threats_by_category"] = defaultdict(int)
                self.stats["threats_by_level"] = defaultdict(int)

            logger.debug(
                f"Cleanup completed: removed {len(expired_sessions)} expired sessions"
            )

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_threat_statistics(self) -> Dict:
        """Get threat detection statistics"""
        return {
            **self.stats,
            "recent_events_count": len(self.recent_events),
            "active_user_profiles": len(self.user_profiles),
            "active_sessions": len(self.user_sessions),
            "detection_rate": (
                self.stats["threats_detected"]
                / max(1, self.stats["total_events_processed"])
            ),
            "false_positive_rate": (
                self.stats["false_positives"] / max(1, self.stats["threats_detected"])
            ),
        }

    async def get_user_risk_assessment(self, user_id: str) -> Dict:
        """Get comprehensive risk assessment for a user"""
        if user_id not in self.user_profiles:
            return {"error": "User profile not found"}

        profile = self.user_profiles[user_id]

        # Use profile's method to generate assessment with event history
        return profile.get_risk_assessment(self.event_history)
