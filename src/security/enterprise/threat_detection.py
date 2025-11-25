# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Threat Detection Engine for Enterprise Security
Provides behavioral anomaly detection, ML-based threat detection, and enhanced security monitoring
"""

import asyncio
import json
import logging
import math
import pickle
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.constants.network_constants import NetworkConstants
from src.constants.path_constants import PATH

logger = logging.getLogger(__name__)


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
    baseline_actions: Dict[str, float]
    typical_hours: List[int]
    typical_ips: set
    command_patterns: List[str]
    file_access_patterns: Dict[str, int]
    api_usage_patterns: Dict[str, float]
    risk_score: float
    last_updated: datetime


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

        # Load existing profiles
        self._load_user_profiles()

        # Initialize background tasks
        self._start_background_tasks()

        logger.info("Threat Detection Engine initialized")

    def _load_config(self) -> Dict:
        """Load threat detection configuration"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, "r") as f:
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
        """Save configuration to file"""
        try:
            Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
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
        # Schedule periodic tasks
        asyncio.create_task(self._periodic_model_training())
        asyncio.create_task(self._periodic_profile_updates())
        asyncio.create_task(self._periodic_cleanup())

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
                await asyncio.sleep(3600)  # Cleanup every hour
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

        # Extract user_id for behavior tracking
        user_id = event.get("user_id", "unknown")

        # Run all detection methods
        detected_threats = []

        # 1. Command injection detection
        if self.config.get("detection_modes", {}).get(
            "command_injection_detection", True
        ):
            cmd_threat = await self._detect_command_injection(event)
            if cmd_threat:
                detected_threats.append(cmd_threat)

        # 2. Behavioral anomaly detection
        if self.config.get("detection_modes", {}).get("behavioral_analysis", True):
            behavioral_threat = await self._detect_behavioral_anomaly(event)
            if behavioral_threat:
                detected_threats.append(behavioral_threat)

        # 3. Brute force detection
        if self.config.get("detection_modes", {}).get("brute_force_detection", True):
            brute_force_threat = await self._detect_brute_force(event)
            if brute_force_threat:
                detected_threats.append(brute_force_threat)

        # 4. File upload scanning
        if self.config.get("detection_modes", {}).get("file_upload_scanning", True):
            file_threat = await self._detect_malicious_file(event)
            if file_threat:
                detected_threats.append(file_threat)

        # 5. API abuse detection
        if self.config.get("detection_modes", {}).get("api_abuse_detection", True):
            api_threat = await self._detect_api_abuse(event)
            if api_threat:
                detected_threats.append(api_threat)

        # 6. Insider threat detection
        if self.config.get("detection_modes", {}).get("insider_threat_detection", True):
            insider_threat = await self._detect_insider_threat(event)
            if insider_threat:
                detected_threats.append(insider_threat)

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
        await self._update_user_behavior(user_id, event)

        return None

    async def _detect_command_injection(self, event: Dict) -> Optional[ThreatEvent]:
        """Detect command injection attempts"""
        action = event.get("action", "")
        details = event.get("details", {})

        # Check command content for injection patterns
        command_content = details.get("command", "") + " " + details.get("args", "")

        detected_patterns = []
        max_severity = "low"

        for pattern_info in self.command_injection_patterns:
            import re

            if re.search(pattern_info["pattern"], command_content, re.IGNORECASE):
                detected_patterns.append(pattern_info)
                if pattern_info["severity"] == "critical":
                    max_severity = "critical"
                elif pattern_info["severity"] == "high" and max_severity != "critical":
                    max_severity = "high"
                elif pattern_info["severity"] == "medium" and max_severity not in [
                    "critical",
                    "high",
                ]:
                    max_severity = "medium"

        if detected_patterns:
            confidence = min(1.0, len(detected_patterns) * 0.3 + 0.4)

            return ThreatEvent(
                event_id=f"cmd_inj_{int(time.time())}_{hash(command_content) % 10000}",
                timestamp=datetime.fromisoformat(
                    event.get("timestamp", datetime.utcnow().isoformat())
                ),
                threat_category=ThreatCategory.COMMAND_INJECTION,
                threat_level=ThreatLevel(max_severity),
                confidence_score=confidence,
                user_id=event.get("user_id", "unknown"),
                source_ip=event.get("source_ip", "unknown"),
                action=action,
                resource=event.get("resource", ""),
                details={
                    "detected_patterns": [p["description"] for p in detected_patterns],
                    "command_content": command_content[:200],  # Truncated for logging
                    "pattern_categories": [p["category"] for p in detected_patterns],
                },
                raw_event=event,
                mitigation_actions=[
                    "block_command",
                    "quarantine_session",
                    "alert_security_team",
                ],
            )

        return None

    async def _detect_behavioral_anomaly(self, event: Dict) -> Optional[ThreatEvent]:
        """Detect behavioral anomalies using user profiles"""
        user_id = event.get("user_id", "unknown")

        if user_id == "unknown" or user_id not in self.user_profiles:
            return None

        profile = self.user_profiles[user_id]
        anomalies = []

        # Check time-based anomalies
        current_hour = datetime.fromisoformat(
            event.get("timestamp", datetime.utcnow().isoformat())
        ).hour
        if current_hour not in profile.typical_hours:
            anomalies.append("unusual_access_time")

        # Check IP-based anomalies
        source_ip = event.get("source_ip", "")
        if source_ip and source_ip not in profile.typical_ips:
            anomalies.append("unusual_source_ip")

        # Check action frequency anomalies
        action = event.get("action", "")
        normal_frequency = profile.baseline_actions.get(action, 0)
        recent_frequency = self._get_recent_action_frequency(user_id, action)

        deviation_threshold = self.config.get("behavioral_analysis", {}).get(
            "deviation_threshold", 2.0
        )
        if recent_frequency > normal_frequency * deviation_threshold:
            anomalies.append("unusual_action_frequency")

        # Check file access patterns
        resource = event.get("resource", "")
        if resource and action in ["file_read", "file_write", "file_delete"]:
            normal_access = profile.file_access_patterns.get(resource, 0)
            if normal_access == 0:  # Never accessed this file before
                anomalies.append("unusual_file_access")

        if anomalies:
            # Calculate confidence based on number and severity of anomalies
            confidence = min(1.0, len(anomalies) * 0.25 + 0.3)
            threat_level = (
                ThreatLevel.HIGH if len(anomalies) >= 3 else ThreatLevel.MEDIUM
            )

            return ThreatEvent(
                event_id=f"behavioral_{int(time.time())}_{hash(user_id) % 10000}",
                timestamp=datetime.fromisoformat(
                    event.get("timestamp", datetime.utcnow().isoformat())
                ),
                threat_category=ThreatCategory.BEHAVIORAL_ANOMALY,
                threat_level=threat_level,
                confidence_score=confidence,
                user_id=user_id,
                source_ip=source_ip,
                action=action,
                resource=resource,
                details={
                    "anomalies_detected": anomalies,
                    "user_risk_score": profile.risk_score,
                    "baseline_comparison": {
                        "normal_action_frequency": normal_frequency,
                        "current_frequency": recent_frequency,
                        "typical_hours": list(profile.typical_hours),
                        "typical_ip_count": len(profile.typical_ips),
                    },
                },
                raw_event=event,
                mitigation_actions=[
                    "monitor_user",
                    "require_additional_auth",
                    "alert_security_team",
                ],
            )

        return None

    async def _detect_brute_force(self, event: Dict) -> Optional[ThreatEvent]:
        """Detect brute force attacks"""
        if event.get("action") != "authentication" or event.get("outcome") != "failure":
            return None

        user_id = event.get("user_id", "unknown")
        source_ip = event.get("source_ip", "unknown")

        # Count recent failed attempts
        window_minutes = self.config.get("thresholds", {}).get(
            "brute_force_window_minutes", 15
        ),
        threshold = self.config.get("thresholds", {}).get("brute_force_attempts", 5)

        recent_failures = self._count_recent_failures(
            user_id, source_ip, window_minutes
        )

        if recent_failures >= threshold:
            confidence = min(1.0, recent_failures / threshold)

            return ThreatEvent(
                event_id=f"brute_force_{int(time.time())}_{hash(f'{user_id}_{source_ip}') % 10000}",
                timestamp=datetime.fromisoformat(
                    event.get("timestamp", datetime.utcnow().isoformat())
                ),
                threat_category=ThreatCategory.BRUTE_FORCE,
                threat_level=ThreatLevel.HIGH,
                confidence_score=confidence,
                user_id=user_id,
                source_ip=source_ip,
                action="authentication",
                resource="login",
                details={
                    "failed_attempts": recent_failures,
                    "time_window_minutes": window_minutes,
                    "attack_pattern": (
                        "credential_stuffing"
                        if user_id != "unknown"
                        else "dictionary_attack"
                    ),
                },
                raw_event=event,
                mitigation_actions=["block_ip", "lock_account", "alert_security_team"],
            )

        return None

    async def _detect_malicious_file(self, event: Dict) -> Optional[ThreatEvent]:
        """Detect malicious file uploads"""
        if event.get("action") not in ["file_upload", "file_write"]:
            return None

        details = event.get("details", {})
        filename = details.get("filename", "")
        file_content = details.get("content_preview", "")
        file_size = details.get("file_size", 0)

        threats = []

        # Check file signatures
        for signature in self.malicious_file_signatures:
            # Check extensions
            if "extension" in signature:
                for ext in signature["extension"]:
                    if filename.lower().endswith(ext.lower()):
                        threats.append(f"suspicious_extension_{ext}")

            # Check content patterns
            if "content_patterns" in signature and file_content:
                for pattern in signature["content_patterns"]:
                    if pattern in file_content:
                        threats.append(f"malicious_content_{pattern}")

            # Check suspicious names
            if "suspicious_names" in signature:
                for name in signature["suspicious_names"]:
                    if name.lower() in filename.lower():
                        threats.append(f"suspicious_name_{name}")

        # Check file size anomalies
        size_threshold = (
            self.config.get("thresholds", {}).get("file_size_suspicious_mb", 100)
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
                timestamp=datetime.fromisoformat(
                    event.get("timestamp", datetime.utcnow().isoformat())
                ),
                threat_category=ThreatCategory.MALICIOUS_UPLOAD,
                threat_level=threat_level,
                confidence_score=confidence,
                user_id=event.get("user_id", "unknown"),
                source_ip=event.get("source_ip", "unknown"),
                action=event.get("action"),
                resource=filename,
                details={
                    "detected_threats": threats,
                    "filename": filename,
                    "file_size": file_size,
                    "content_preview": file_content[:100] if file_content else "",
                },
                raw_event=event,
                mitigation_actions=[
                    "quarantine_file",
                    "scan_with_antivirus",
                    "alert_security_team",
                ],
            )

        return None

    async def _detect_api_abuse(self, event: Dict) -> Optional[ThreatEvent]:
        """Detect API abuse patterns"""
        if event.get("action") != "api_request":
            return None

        user_id = event.get("user_id", "unknown")
        source_ip = event.get("source_ip", "unknown")
        endpoint = event.get("resource", "")

        # Check rate limiting
        rate_limit = self.config.get("thresholds", {}).get(
            "api_rate_limit_per_minute", 100
        ),
        recent_requests = self._count_recent_api_requests(
            user_id, source_ip, 1
        )  # 1 minute window

        threats = []

        if recent_requests > rate_limit:
            threats.append("rate_limit_exceeded")

        # Check for unusual endpoint access
        user_profile = self.user_profiles.get(user_id)
        if user_profile and endpoint:
            normal_usage = user_profile.api_usage_patterns.get(endpoint, 0)
            current_usage = self._get_recent_endpoint_usage(user_id, endpoint)

            if normal_usage == 0 and current_usage > 0:
                threats.append("unusual_endpoint_access")
            elif current_usage > normal_usage * 5:  # 5x normal usage
                threats.append("excessive_endpoint_usage")

        # Check for bulk data operations
        details = event.get("details", {})
        response_size = details.get("response_size", 0)
        bulk_threshold = (
            self.config.get("thresholds", {}).get("bulk_data_threshold_mb", 100)
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

            return ThreatEvent(
                event_id=f"api_abuse_{int(time.time())}_{hash(f'{user_id}_{endpoint}') % 10000}",
                timestamp=datetime.fromisoformat(
                    event.get("timestamp", datetime.utcnow().isoformat())
                ),
                threat_category=ThreatCategory.API_ABUSE,
                threat_level=threat_level,
                confidence_score=confidence,
                user_id=user_id,
                source_ip=source_ip,
                action="api_request",
                resource=endpoint,
                details={
                    "abuse_patterns": threats,
                    "request_rate": recent_requests,
                    "rate_limit": rate_limit,
                    "response_size": response_size,
                    "endpoint": endpoint,
                },
                raw_event=event,
                mitigation_actions=[
                    "rate_limit_user",
                    "monitor_api_usage",
                    "alert_security_team",
                ],
            )

        return None

    async def _detect_insider_threat(self, event: Dict) -> Optional[ThreatEvent]:
        """Detect insider threat indicators"""
        user_id = event.get("user_id", "unknown")
        action = event.get("action", "")

        if user_id == "unknown":
            return None

        # High-risk insider threat indicators
        high_risk_actions = [
            "bulk_data_export",
            "privilege_escalation",
            "unauthorized_access",
            "credential_theft",
            "system_configuration_change",
        ]

        # Check for high-risk actions
        risk_indicators = []

        if action in high_risk_actions:
            risk_indicators.append(f"high_risk_action_{action}")

        # Check for off-hours access
        timestamp = datetime.fromisoformat(
            event.get("timestamp", datetime.utcnow().isoformat())
        )
        if timestamp.hour < 6 or timestamp.hour > 22:  # Outside normal business hours
            risk_indicators.append("off_hours_access")

        # Check for unusual resource access
        resource = event.get("resource", "")
        if resource and any(
            sensitive in resource.lower()
            for sensitive in ["admin", "config", "secret", "key", "password"]
        ):
            risk_indicators.append("sensitive_resource_access")

        # Check user risk profile
        user_profile = self.user_profiles.get(user_id)
        if user_profile and user_profile.risk_score > 0.7:
            risk_indicators.append("high_risk_user")

        # Check for data exfiltration patterns
        details = event.get("details", {})
        if details.get("data_volume", 0) > 1000000:  # > 1MB
            risk_indicators.append("large_data_access")

        if len(risk_indicators) >= 2:  # Multiple indicators suggest insider threat
            confidence = min(1.0, len(risk_indicators) * 0.3 + 0.4)
            threat_level = (
                ThreatLevel.CRITICAL if len(risk_indicators) >= 4 else ThreatLevel.HIGH
            )

            return ThreatEvent(
                event_id=f"insider_{int(time.time())}_{hash(user_id) % 10000}",
                timestamp=timestamp,
                threat_category=ThreatCategory.INSIDER_THREAT,
                threat_level=threat_level,
                confidence_score=confidence,
                user_id=user_id,
                source_ip=event.get("source_ip", "unknown"),
                action=action,
                resource=resource,
                details={
                    "risk_indicators": risk_indicators,
                    "user_risk_score": user_profile.risk_score if user_profile else 0.0,
                    "access_time": timestamp.isoformat(),
                    "data_sensitivity": (
                        "high"
                        if any(
                            "sensitive" in indicator for indicator in risk_indicators
                        )
                        else "medium"
                    ),
                },
                raw_event=event,
                mitigation_actions=[
                    "enhanced_monitoring",
                    "require_manager_approval",
                    "alert_security_team",
                    "document_incident",
                ],
            )

        return None

    def _get_recent_action_frequency(
        self, user_id: str, action: str, hours: int = 1
    ) -> int:
        """Count recent action frequency for a user"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        count = 0

        for event in reversed(self.recent_events):
            event_time = datetime.fromisoformat(
                event.get("timestamp", datetime.utcnow().isoformat())
            )
            if event_time < cutoff_time:
                break
            if event.get("user_id") == user_id and event.get("action") == action:
                count += 1

        return count

    def _count_recent_failures(
        self, user_id: str, source_ip: str, window_minutes: int
    ) -> int:
        """Count recent authentication failures"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)
        count = 0

        for event in reversed(self.recent_events):
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

    def _count_recent_api_requests(
        self, user_id: str, source_ip: str, window_minutes: int
    ) -> int:
        """Count recent API requests"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)
        count = 0

        for event in reversed(self.recent_events):
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

    def _get_recent_endpoint_usage(
        self, user_id: str, endpoint: str, hours: int = 24
    ) -> int:
        """Get recent endpoint usage count"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        count = 0

        for event in reversed(self.recent_events):
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

    async def _update_user_behavior(self, user_id: str, event: Dict):
        """Update user behavioral profile with new event"""
        if user_id == "unknown":
            return

        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = UserProfile(
                user_id=user_id,
                baseline_actions={},
                typical_hours=[],
                typical_ips=set(),
                command_patterns=[],
                file_access_patterns={},
                api_usage_patterns={},
                risk_score=0.5,
                last_updated=datetime.utcnow(),
            )
            self.stats["users_monitored"] += 1

        profile = self.user_profiles[user_id]

        # Update action frequency
        action = event.get("action", "")
        if action:
            profile.baseline_actions[action] = (
                profile.baseline_actions.get(action, 0) + 1
            )

        # Update typical hours
        event_hour = datetime.fromisoformat(
            event.get("timestamp", datetime.utcnow().isoformat())
        ).hour
        if event_hour not in profile.typical_hours and len(profile.typical_hours) < 12:
            profile.typical_hours.append(event_hour)

        # Update typical IPs
        source_ip = event.get("source_ip", "")
        if source_ip and len(profile.typical_ips) < 10:
            profile.typical_ips.add(source_ip)

        # Update file access patterns
        if action in ["file_read", "file_write", "file_delete"]:
            resource = event.get("resource", "")
            if resource:
                profile.file_access_patterns[resource] = (
                    profile.file_access_patterns.get(resource, 0) + 1
                )

        # Update API usage patterns
        if action == "api_request":
            endpoint = event.get("resource", "")
            if endpoint:
                profile.api_usage_patterns[endpoint] = (
                    profile.api_usage_patterns.get(endpoint, 0) + 1
                )

        profile.last_updated = datetime.utcnow()

    async def _execute_response_actions(self, threat: ThreatEvent):
        """Execute automated response actions based on threat"""
        response_config = self.config.get("response_actions", {})

        for action in threat.mitigation_actions:
            if action == "block_ip" and response_config.get(
                "auto_block_critical", False
            ):
                await self._block_ip_address(threat.source_ip)

            elif action == "quarantine_file" and response_config.get(
                "auto_quarantine_files", True
            ):
                await self._quarantine_file(threat.resource)

            elif action == "rate_limit_user" and response_config.get(
                "rate_limit_suspicious_ips", True
            ):
                await self._apply_rate_limiting(threat.user_id, threat.source_ip)

            elif action == "alert_security_team" and response_config.get(
                "alert_security_team", True
            ):
                await self._send_security_alert(threat)

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
        """Update all user profiles"""
        try:
            for user_id, profile in self.user_profiles.items():
                # Calculate risk score based on recent activity
                profile.risk_score = self._calculate_user_risk_score(user_id)

            self._save_user_profiles()
            logger.info("User profiles updated successfully")
        except Exception as e:
            logger.error(f"Failed to update user profiles: {e}")

    def _calculate_user_risk_score(self, user_id: str) -> float:
        """Calculate risk score for a user based on recent behavior"""
        risk_factors = []

        # Count recent high-risk actions
        high_risk_actions = [
            "admin_action",
            "system_configuration",
            "privilege_escalation",
        ]
        recent_high_risk = sum(
            1
            for event in self.recent_events
            if event.get("user_id") == user_id
            and event.get("action") in high_risk_actions
        )

        if recent_high_risk > 5:
            risk_factors.append(0.3)
        elif recent_high_risk > 2:
            risk_factors.append(0.2)

        # Check for off-hours activity
        off_hours_activity = sum(
            1
            for event in self.recent_events
            if event.get("user_id") == user_id
            and datetime.fromisoformat(
                event.get("timestamp", datetime.utcnow().isoformat())
            ).hour
            < 6
        )

        if off_hours_activity > 10:
            risk_factors.append(0.2)
        elif off_hours_activity > 5:
            risk_factors.append(0.1)

        # Base risk score
        base_risk = 0.3

        return min(1.0, base_risk + sum(risk_factors))

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

        # Analyze recent activity
        recent_events = [e for e in self.recent_events if e.get("user_id") == user_id]

        return {
            "user_id": user_id,
            "risk_score": profile.risk_score,
            "risk_level": (
                "high"
                if profile.risk_score > 0.7
                else "medium" if profile.risk_score > 0.4 else "low"
            ),
            "profile_age_days": (datetime.utcnow() - profile.last_updated).days,
            "total_actions": sum(profile.baseline_actions.values()),
            "unique_actions": len(profile.baseline_actions),
            "typical_access_hours": sorted(profile.typical_hours),
            "known_ip_addresses": len(profile.typical_ips),
            "recent_activity_count": len(recent_events),
            "file_access_diversity": len(profile.file_access_patterns),
            "api_usage_diversity": len(profile.api_usage_patterns),
            "last_updated": profile.last_updated.isoformat(),
        }
