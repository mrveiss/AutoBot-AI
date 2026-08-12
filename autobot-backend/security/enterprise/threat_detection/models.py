# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Threat Detection Data Models

Dataclasses for security events, threats, and user profiles.

Part of Issue #381 - God Class Refactoring
"""

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso, utc_timestamp

from .types import FILE_OPERATION_ACTIONS, ThreatCategory, ThreatLevel

logger = get_logger(__name__)


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
        timestamp_str = self.raw_event.get("timestamp", utc_timestamp())
        return parse_utc_iso(timestamp_str)

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
        return self.action in FILE_OPERATION_ACTIONS

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

    def get_threat_base_fields(self, **overrides) -> Dict:
        """Get base fields for ThreatEvent creation (Issue #372 - reduces feature envy).

        Returns dict with common fields needed when creating a ThreatEvent from this event.

        Args:
            **overrides: Field values that replace the event-derived defaults.
                Analyzers that need a fixed ``action``/``resource`` must pass it
                here rather than as a second keyword to ``ThreatEvent(...)``:
                splatting this dict AND repeating the key raised
                ``TypeError: got multiple values for keyword argument`` at the
                exact moment a threat was detected (#13551).
        """
        fields = {
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "source_ip": self.source_ip,
            "action": self.action,
            "resource": self.resource,
            "raw_event": self.raw_event,
        }
        fields.update(overrides)
        return fields

    def generate_threat_id(self, prefix: str) -> str:
        """Generate a unique threat ID based on this event (Issue #372 - reduces feature envy)."""
        event_hash = hash(f"{self.user_id}_{self.resource}") % 10000
        return f"{prefix}_{int(time.time())}_{event_hash}"


@dataclass
class EventHistory:
    """Encapsulates event history and provides query methods to reduce Feature Envy"""

    events: deque

    def count_recent_failures(self, user_id: str, source_ip: str, window_minutes: int) -> int:
        """Count recent authentication failures"""
        cutoff_time = now_utc() - timedelta(minutes=window_minutes)
        count = 0

        for event in reversed(self.events):
            event_time = parse_utc_iso(event.get("timestamp", utc_timestamp()))
            if event_time < cutoff_time:
                break
            if (
                event.get("action") == "authentication"
                and event.get("outcome") == "failure"
                and (event.get("user_id") == user_id or event.get("source_ip") == source_ip)
            ):
                count += 1

        return count

    def count_recent_api_requests(self, user_id: str, source_ip: str, window_minutes: int) -> int:
        """Count recent API requests"""
        cutoff_time = now_utc() - timedelta(minutes=window_minutes)
        count = 0

        for event in reversed(self.events):
            event_time = parse_utc_iso(event.get("timestamp", utc_timestamp()))
            if event_time < cutoff_time:
                break
            if event.get("action") == "api_request" and (
                event.get("user_id") == user_id or event.get("source_ip") == source_ip
            ):
                count += 1

        return count

    def get_recent_action_frequency(self, user_id: str, action: str, hours: int = 1) -> int:
        """Count recent action frequency for a user"""
        cutoff_time = now_utc() - timedelta(hours=hours)
        count = 0

        for event in reversed(self.events):
            event_time = parse_utc_iso(event.get("timestamp", utc_timestamp()))
            if event_time < cutoff_time:
                break
            if event.get("user_id") == user_id and event.get("action") == action:
                count += 1

        return count

    def get_recent_endpoint_usage(self, user_id: str, endpoint: str, hours: int = 24) -> int:
        """Get recent endpoint usage count"""
        cutoff_time = now_utc() - timedelta(hours=hours)
        count = 0

        for event in reversed(self.events):
            event_time = parse_utc_iso(event.get("timestamp", utc_timestamp()))
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
            1 for event in self.events if event.get("user_id") == user_id and event.get("action") in high_risk_actions
        )

    def count_off_hours_activity(self, user_id: str) -> int:
        """Count off-hours activity (before 6 AM) for a user"""
        return sum(
            1
            for event in self.events
            if event.get("user_id") == user_id and parse_utc_iso(event.get("timestamp", utc_timestamp())).hour < 6
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
    last_updated: datetime = field(default_factory=now_utc)

    def is_anomalous_time(self, hour: int) -> bool:
        """Check if access hour is anomalous for this user"""
        return hour not in self.typical_hours

    def is_anomalous_ip(self, ip: str) -> bool:
        """Check if IP is anomalous for this user"""
        return ip not in self.typical_ips

    def is_anomalous_action_frequency(self, action: str, current_frequency: int, deviation_threshold: float) -> bool:
        """Check if action frequency is anomalous"""
        normal_frequency = self.baseline_actions.get(action, 0)
        return current_frequency > normal_frequency * deviation_threshold

    def is_anomalous_file_access(self, resource: str) -> bool:
        """Check if file access is anomalous (never accessed before)"""
        return self.file_access_patterns.get(resource, 0) == 0

    def is_high_risk(self) -> bool:
        """Check if user is considered high risk"""
        return self.risk_score > 0.7

    # === Issue #14159: JSON (de)serialization, replacing pickle ===

    def to_dict(self) -> Dict:
        """Serialize to a JSON-safe dict.

        ``typical_ips`` is a ``set`` (JSON has no set type) so it is
        serialized as a sorted list; ``from_dict`` restores it to a set.
        ``last_updated`` is serialized as an ISO-8601 string.
        """
        return {
            "user_id": self.user_id,
            "baseline_actions": dict(self.baseline_actions),
            "typical_hours": list(self.typical_hours),
            "typical_ips": sorted(self.typical_ips),
            "command_patterns": list(self.command_patterns),
            "file_access_patterns": dict(self.file_access_patterns),
            "api_usage_patterns": dict(self.api_usage_patterns),
            "risk_score": self.risk_score,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "UserProfile | None":
        """Build a ``UserProfile`` from a parsed-JSON dict, validating every field.

        Returns ``None`` (and logs a warning) instead of raising when the
        entry does not validate, so one corrupt or hand-edited profile
        degrades to "that profile is dropped" -- never to "the process
        dies" and never to "unvalidated data is trusted" (#14159).
        """
        if not isinstance(data, dict):
            logger.warning(
                "Skipping user profile entry: expected a JSON object, got %s",
                type(data).__name__,
            )
            return None

        user_id = data.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            logger.warning("Skipping user profile entry: missing or invalid user_id")
            return None

        baseline_actions = data.get("baseline_actions", {})
        if not isinstance(baseline_actions, dict) or not all(
            isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
            for k, v in baseline_actions.items()
        ):
            logger.warning("Skipping user profile %s: invalid baseline_actions", user_id)
            return None

        typical_hours = data.get("typical_hours", [])
        if not isinstance(typical_hours, list) or not all(
            isinstance(h, int) and not isinstance(h, bool) for h in typical_hours
        ):
            logger.warning("Skipping user profile %s: invalid typical_hours", user_id)
            return None

        typical_ips = data.get("typical_ips", [])
        if not isinstance(typical_ips, list) or not all(isinstance(ip, str) for ip in typical_ips):
            logger.warning("Skipping user profile %s: invalid typical_ips", user_id)
            return None

        command_patterns = data.get("command_patterns", [])
        if not isinstance(command_patterns, list) or not all(isinstance(c, str) for c in command_patterns):
            logger.warning("Skipping user profile %s: invalid command_patterns", user_id)
            return None

        file_access_patterns = data.get("file_access_patterns", {})
        if not isinstance(file_access_patterns, dict) or not all(
            isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
            for k, v in file_access_patterns.items()
        ):
            logger.warning("Skipping user profile %s: invalid file_access_patterns", user_id)
            return None

        api_usage_patterns = data.get("api_usage_patterns", {})
        if not isinstance(api_usage_patterns, dict) or not all(
            isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
            for k, v in api_usage_patterns.items()
        ):
            logger.warning("Skipping user profile %s: invalid api_usage_patterns", user_id)
            return None

        risk_score = data.get("risk_score", 0.5)
        if not isinstance(risk_score, (int, float)) or isinstance(risk_score, bool):
            logger.warning("Skipping user profile %s: invalid risk_score", user_id)
            return None

        last_updated_raw = data.get("last_updated")
        try:
            last_updated = parse_utc_iso(last_updated_raw) if last_updated_raw is not None else now_utc()
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping user profile %s: invalid last_updated (%s)", user_id, exc)
            return None

        return cls(
            user_id=user_id,
            baseline_actions=dict(baseline_actions),
            typical_hours=list(typical_hours),
            typical_ips=set(typical_ips),
            command_patterns=list(command_patterns),
            file_access_patterns=dict(file_access_patterns),
            api_usage_patterns=dict(api_usage_patterns),
            risk_score=float(risk_score),
            last_updated=last_updated,
        )

    # === Issue #372: Feature Envy Reduction Methods ===

    def get_baseline_comparison(self, action: str, current_frequency: int) -> Dict:
        """Get baseline comparison dict for threat details (Issue #372 - reduces feature envy)."""
        return {
            "normal_action_frequency": self.baseline_actions.get(action, 0),
            "current_frequency": current_frequency,
            "typical_hours": list(self.typical_hours),
            "typical_ip_count": len(self.typical_ips),
        }

    def update_with_event(self, event: "SecurityEvent"):
        """Update profile with new event data"""
        # Update action frequency
        if event.action:
            self.baseline_actions[event.action] = self.baseline_actions.get(event.action, 0) + 1

        # Update typical hours
        event_hour = event.get_timestamp_hour()
        if event_hour not in self.typical_hours and len(self.typical_hours) < 12:
            self.typical_hours.append(event_hour)

        # Update typical IPs
        if event.source_ip and len(self.typical_ips) < 10:
            self.typical_ips.add(event.source_ip)

        # Update file access patterns
        if event.is_file_operation() and event.resource:
            self.file_access_patterns[event.resource] = self.file_access_patterns.get(event.resource, 0) + 1

        # Update API usage patterns
        if event.is_api_request() and event.resource:
            self.api_usage_patterns[event.resource] = self.api_usage_patterns.get(event.resource, 0) + 1

        self.last_updated = now_utc()

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
            "risk_level": ("high" if self.risk_score > 0.7 else "medium" if self.risk_score > 0.4 else "low"),
            "profile_age_days": (now_utc() - self.last_updated).days,
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

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        """Get user profile if exists"""
        return self.user_profiles.get(user_id)

    def get_recent_action_frequency(self, user_id: str, action: str, hours: int = 1) -> int:
        """Count recent action frequency for a user"""
        return self.event_history.get_recent_action_frequency(user_id, action, hours)

    def count_recent_failures(self, user_id: str, source_ip: str, window_minutes: int) -> int:
        """Count recent authentication failures"""
        return self.event_history.count_recent_failures(user_id, source_ip, window_minutes)

    def count_recent_api_requests(self, user_id: str, source_ip: str, window_minutes: int) -> int:
        """Count recent API requests"""
        return self.event_history.count_recent_api_requests(user_id, source_ip, window_minutes)

    def get_recent_endpoint_usage(self, user_id: str, endpoint: str, hours: int = 24) -> int:
        """Get recent endpoint usage count"""
        return self.event_history.get_recent_endpoint_usage(user_id, endpoint, hours)
