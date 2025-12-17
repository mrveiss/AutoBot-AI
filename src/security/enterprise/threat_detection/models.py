# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from typing import Dict, List, Optional

from .types import FILE_OPERATION_ACTIONS, ThreatCategory, ThreatLevel


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

    def update_with_event(self, event: "SecurityEvent"):
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
