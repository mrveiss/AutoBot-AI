# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Threat Detection Engine

Main engine for advanced threat detection with ML-based anomaly detection.

Part of Issue #381 - God Class Refactoring
Issue #378: Added threading locks for file operations to prevent race conditions.
"""

import asyncio
import logging
import pickle  # nosec B403 - internal profile storage only
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import yaml
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.constants.path_constants import PATH
from src.constants.threshold_constants import TimingConstants

from .analyzers import (
    APIAbuseAnalyzer,
    BehavioralAnomalyAnalyzer,
    BruteForceAnalyzer,
    CommandInjectionAnalyzer,
    InsiderThreatAnalyzer,
    MaliciousFileAnalyzer,
    ThreatAnalyzer,
)
from .models import (
    AnalysisContext,
    EventHistory,
    SecurityEvent,
    ThreatEvent,
    UserProfile,
)

logger = logging.getLogger(__name__)


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

        self._initialize_ml_models()
        self._initialize_profile_storage()
        self._initialize_threat_patterns()
        self._initialize_monitoring_structures()
        self._initialize_stats()
        self._initialize_analyzers()

        self._load_user_profiles()
        self._start_background_tasks()

        logger.info("Threat Detection Engine initialized")

    def _initialize_ml_models(self) -> None:
        """Initialize ML detection models. Issue #620."""
        self.anomaly_detector = IsolationForest(contamination=0.1, random_state=42)
        self.scaler = StandardScaler()
        self.clustering_model = DBSCAN(eps=0.5, min_samples=5)

    def _initialize_profile_storage(self) -> None:
        """Initialize user profile storage paths. Issue #620."""
        self.user_profiles: Dict[str, UserProfile] = {}
        self.profile_storage_path = PATH.get_data_path("security", "user_profiles.pkl")
        self.profile_storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _initialize_threat_patterns(self) -> None:
        """Load threat intelligence and detection patterns. Issue #620."""
        self.command_injection_patterns = self._load_injection_patterns()
        self.malicious_file_signatures = self._load_file_signatures()
        self.suspicious_api_patterns = self._load_api_patterns()

    def _initialize_monitoring_structures(self) -> None:
        """Initialize real-time monitoring data structures. Issue #620."""
        self.recent_events = deque(maxlen=10000)  # Last 10k events for analysis
        self.event_history = EventHistory(events=self.recent_events)
        self.user_sessions = defaultdict(dict)  # Active user session tracking
        self.ip_reputation = defaultdict(float)  # IP reputation scores

    def _initialize_stats(self) -> None:
        """Initialize statistics and metrics tracking. Issue #620."""
        self.stats = {
            "total_events_processed": 0,
            "threats_detected": 0,
            "false_positives": 0,
            "threats_by_category": defaultdict(int),
            "threats_by_level": defaultdict(int),
            "users_monitored": 0,
            "models_trained": 0,
        }

    def _initialize_analyzers(self) -> None:
        """Initialize threat analyzer instances. Issue #620."""
        self.analyzers: List[ThreatAnalyzer] = [
            CommandInjectionAnalyzer(),
            BehavioralAnomalyAnalyzer(),
            BruteForceAnalyzer(),
            MaliciousFileAnalyzer(),
            APIAbuseAnalyzer(),
            InsiderThreatAnalyzer(),
        ]

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
            logger.error("Failed to load threat detection config: %s", e)
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
                logger.error("Failed to save threat detection config: %s", e)

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
                    self.user_profiles = pickle.load(f)  # nosec B301
                self.stats["users_monitored"] = len(self.user_profiles)
                logger.info("Loaded %s user profiles", len(self.user_profiles))
        except Exception as e:
            logger.error("Failed to load user profiles: %s", e)
            self.user_profiles = {}

    def _save_user_profiles(self):
        """Save user behavioral profiles"""
        try:
            with open(self.profile_storage_path, "wb") as f:
                pickle.dump(self.user_profiles, f)
        except Exception as e:
            logger.error("Failed to save user profiles: %s", e)

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
                logger.error("Error in periodic model training: %s", e)

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
                logger.error("Error in periodic profile updates: %s", e)

    async def _periodic_cleanup(self):
        """Periodic cleanup of old data and statistics"""
        while True:
            try:
                await asyncio.sleep(
                    TimingConstants.HOURLY_INTERVAL
                )  # Cleanup every hour
                await self._cleanup_old_data()
            except Exception as e:
                logger.error("Error in periodic cleanup: %s", e)

    def _get_analyzer_mode_map(self) -> Dict:
        """Get mapping of analyzer types to their config mode keys. Issue #620."""
        return {
            CommandInjectionAnalyzer: "command_injection_detection",
            BehavioralAnomalyAnalyzer: "behavioral_analysis",
            BruteForceAnalyzer: "brute_force_detection",
            MaliciousFileAnalyzer: "file_upload_scanning",
            APIAbuseAnalyzer: "api_abuse_detection",
            InsiderThreatAnalyzer: "insider_threat_detection",
        }

    async def _run_analyzers(
        self, security_event: SecurityEvent, context: AnalysisContext
    ) -> List[ThreatEvent]:
        """Run all enabled analyzers on the security event. Issue #620."""
        detected_threats = []
        detection_modes = self.config.get("detection_modes", {})
        analyzer_mode_map = self._get_analyzer_mode_map()

        for analyzer in self.analyzers:
            mode_key = analyzer_mode_map.get(type(analyzer))
            if mode_key and not detection_modes.get(mode_key, True):
                continue

            threat = await analyzer.analyze(security_event, context)
            if threat:
                detected_threats.append(threat)

        return detected_threats

    async def _process_detected_threat(
        self, detected_threats: List[ThreatEvent]
    ) -> ThreatEvent:
        """Process detected threats and update statistics. Issue #620."""
        primary_threat = max(
            detected_threats,
            key=lambda t: (t.threat_level.value, t.confidence_score),
        )

        self.stats["threats_detected"] += 1
        self.stats["threats_by_category"][primary_threat.threat_category.value] += 1
        self.stats["threats_by_level"][primary_threat.threat_level.value] += 1

        await self._execute_response_actions(primary_threat)

        return primary_threat

    async def analyze_event(self, event: Dict) -> Optional[ThreatEvent]:
        """
        Analyze a security event for potential threats.

        Args:
            event: Security event to analyze

        Returns:
            ThreatEvent if threat detected, None otherwise
        """
        self.stats["total_events_processed"] += 1
        self.recent_events.append(event)

        security_event = SecurityEvent(raw_event=event)

        context = AnalysisContext(
            config=self.config,
            user_profiles=self.user_profiles,
            event_history=self.event_history,
            injection_patterns=self.command_injection_patterns,
            file_signatures=self.malicious_file_signatures,
            api_patterns=self.suspicious_api_patterns,
        )

        detected_threats = await self._run_analyzers(security_event, context)

        if detected_threats:
            return await self._process_detected_threat(detected_threats)

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
            "block_ip": (
                self._block_ip_address,
                "auto_block_critical",
                threat.source_ip,
            ),
            "quarantine_file": (
                self._quarantine_file,
                "auto_quarantine_files",
                threat.resource,
            ),
            "rate_limit_user": (
                self._apply_rate_limiting,
                "rate_limit_suspicious_ips",
                (threat.user_id, threat.source_ip),
            ),
            "alert_security_team": (
                self._send_security_alert,
                "alert_security_team",
                threat,
            ),
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
        logger.warning("SECURITY ACTION: Blocking IP address %s", ip_address)
        # Implementation would integrate with firewall/WAF

    async def _quarantine_file(self, filename: str):
        """Quarantine suspicious file"""
        logger.warning("SECURITY ACTION: Quarantining file %s", filename)
        # Implementation would move file to quarantine directory

    async def _apply_rate_limiting(self, user_id: str, ip_address: str):
        """Apply rate limiting to user/IP"""
        logger.warning(
            "SECURITY ACTION: Rate limiting user %s from IP %s", user_id, ip_address
        )
        # Implementation would update rate limiting rules

    async def _send_security_alert(self, threat: ThreatEvent):
        """Send security alert to security team"""
        logger.critical(
            "SECURITY THREAT DETECTED: %s | Level: %s | User: %s | Confidence: %.2f | IP: %s",
            threat.threat_category.value,
            threat.threat_level.value,
            threat.user_id,
            threat.confidence_score,
            threat.source_ip,
        )

    async def _retrain_models(self):
        """Retrain ML models with new data"""
        min_samples = self.config.get("ml_models", {}).get("min_training_samples", 1000)

        if len(self.recent_events) < min_samples:
            logger.info(
                "Insufficient data for model training: %s < %s",
                len(self.recent_events),
                min_samples,
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
            logger.error("Failed to retrain models: %s", e)

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
            logger.error("Failed to update user profiles: %s", e)

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
                "Cleanup completed: removed %s expired sessions", len(expired_sessions)
            )

        except Exception as e:
            logger.error("Error during cleanup: %s", e)

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
