# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Assessment Workflow Manager

Provides structured, resumable security assessments with:
- Phase-based workflow (RECON → PORT_SCAN → ENUMERATION → VULN_ANALYSIS → REPORTING)
- Redis-persisted state (survives restarts)
- Memory MCP integration for findings storage
- Tool output parsing (nmap, etc.)

Issue: #260
"""

import ast
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from redis.exceptions import RedisError

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Lazy import for memory integration to avoid circular imports (Issue #662: thread-safe)
_memory_integration = None
_memory_integration_lock = asyncio.Lock()


async def _get_memory_integration():
    """Lazy load memory integration (thread-safe)."""
    global _memory_integration
    if _memory_integration is None:
        async with _memory_integration_lock:
            # Double-check after acquiring lock
            if _memory_integration is None:
                try:
                    from src.services.security_memory_integration import (
                        get_security_memory_integration,
                    )

                    _memory_integration = await get_security_memory_integration()
                except Exception as e:
                    logger.warning("Memory integration not available: %s", e)
    return _memory_integration


class AssessmentPhase(str, Enum):
    """Security assessment workflow phases."""

    INIT = "INIT"
    RECON = "RECON"
    PORT_SCAN = "PORT_SCAN"
    ENUMERATION = "ENUMERATION"
    VULN_ANALYSIS = "VULN_ANALYSIS"
    EXPLOITATION = "EXPLOITATION"  # Training mode only
    REPORTING = "REPORTING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


# Valid phase transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    "INIT": ["RECON", "ERROR"],
    "RECON": ["PORT_SCAN", "ERROR", "INIT"],
    "PORT_SCAN": ["ENUMERATION", "ERROR", "RECON"],
    "ENUMERATION": ["VULN_ANALYSIS", "ERROR", "PORT_SCAN"],
    "VULN_ANALYSIS": ["EXPLOITATION", "REPORTING", "ERROR", "ENUMERATION"],
    "EXPLOITATION": ["REPORTING", "ERROR", "VULN_ANALYSIS"],
    "REPORTING": ["COMPLETE", "ERROR"],
    "COMPLETE": [],  # Terminal state
    "ERROR": [
        "INIT",
        "RECON",
        "PORT_SCAN",
        "ENUMERATION",
        "VULN_ANALYSIS",
        "EXPLOITATION",
        "REPORTING",
    ],
}

# Phase descriptions for context
PHASE_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "INIT": {
        "description": "Assessment initialization and target definition",
        "actions": ["define_target", "set_scope", "validate_authorization"],
        "required_data": ["target", "scope"],
    },
    "RECON": {
        "description": "Passive reconnaissance and information gathering",
        "actions": ["dns_lookup", "whois", "osint", "subdomain_enum"],
        "required_data": [],
    },
    "PORT_SCAN": {
        "description": "Active port scanning to identify open ports",
        "actions": ["tcp_scan", "udp_scan", "syn_scan"],
        "required_data": [],
    },
    "ENUMERATION": {
        "description": "Service and version enumeration on open ports",
        "actions": ["service_detection", "version_scan", "banner_grab"],
        "required_data": ["open_ports"],
    },
    "VULN_ANALYSIS": {
        "description": "Vulnerability identification and CVE mapping",
        "actions": ["vuln_scan", "cve_lookup", "exploit_search"],
        "required_data": ["services"],
    },
    "EXPLOITATION": {
        "description": "Controlled exploitation (training mode only)",
        "actions": ["exploit_test", "payload_delivery", "post_exploit"],
        "required_data": ["vulnerabilities"],
        "requires_training_mode": True,
    },
    "REPORTING": {
        "description": "Generate comprehensive assessment report",
        "actions": ["generate_report", "export_findings", "create_summary"],
        "required_data": [],
    },
    "COMPLETE": {
        "description": "Assessment completed",
        "actions": [],
        "required_data": [],
    },
    "ERROR": {
        "description": "Error state - requires recovery",
        "actions": ["diagnose", "recover", "retry"],
        "required_data": [],
    },
}


@dataclass
class PhaseTransition:
    """Record of a phase transition."""

    from_phase: str
    to_phase: str
    timestamp: str
    reason: str
    user: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetHost:
    """Represents a target host in the assessment."""

    ip: str
    hostname: Optional[str] = None
    status: str = "unknown"  # unknown, up, down
    ports: list[dict[str, Any]] = field(default_factory=list)
    services: list[dict[str, Any]] = field(default_factory=list)
    vulnerabilities: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ip": self.ip,
            "hostname": self.hostname,
            "status": self.status,
            "ports": self.ports,
            "services": self.services,
            "vulnerabilities": self.vulnerabilities,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TargetHost":
        """Create from dictionary."""
        return cls(
            ip=data.get("ip", ""),
            hostname=data.get("hostname"),
            status=data.get("status", "unknown"),
            ports=data.get("ports", []),
            services=data.get("services", []),
            vulnerabilities=data.get("vulnerabilities", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SecurityAssessment:
    """Represents a security assessment with full state."""

    id: str
    name: str
    target: str  # IP, CIDR, or hostname
    scope: list[str]  # List of in-scope targets
    phase: AssessmentPhase
    training_mode: bool = False
    created_at: str = ""
    updated_at: str = ""
    phase_history: list[dict[str, Any]] = field(default_factory=list)
    hosts: list[TargetHost] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set timestamps if not provided."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "target": self.target,
            "scope": self.scope,
            "phase": self.phase.value
            if isinstance(self.phase, AssessmentPhase)
            else self.phase,
            "training_mode": self.training_mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "phase_history": self.phase_history,
            "hosts": [
                h.to_dict() if isinstance(h, TargetHost) else h for h in self.hosts
            ],
            "findings": self.findings,
            "actions_taken": self.actions_taken,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SecurityAssessment":
        """Create from dictionary."""
        phase = data.get("phase", "INIT")
        if isinstance(phase, str):
            phase = AssessmentPhase(phase)

        hosts = [
            TargetHost.from_dict(h) if isinstance(h, dict) else h
            for h in data.get("hosts", [])
        ]

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            target=data.get("target", ""),
            scope=data.get("scope", []),
            phase=phase,
            training_mode=data.get("training_mode", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            phase_history=data.get("phase_history", []),
            hosts=hosts,
            findings=data.get("findings", []),
            actions_taken=data.get("actions_taken", []),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


class SecurityWorkflowManager:
    """
    Manages security assessment workflows with Redis persistence.

    Usage:
        from src.constants.network_constants import NetworkConstants

        manager = SecurityWorkflowManager()
        target_network = NetworkConstants.DEFAULT_SCAN_NETWORK

        # Create assessment
        assessment = await manager.create_assessment(
            name="Internal Network Scan",
            target=target_network,
            scope=[target_network],
            training_mode=False
        )

        # Advance phase
        await manager.advance_phase(assessment.id, "Completed reconnaissance")

        # Add findings (use discovered hosts from scan)
        await manager.add_finding(assessment.id, {
            "type": "open_port",
            "host": "<discovered_host>",  # Replace with actual scan result
            "port": 22,
            "service": "ssh"
        })

        # Resume later
        assessment = await manager.get_assessment(assessment.id)
    """

    REDIS_KEY_PREFIX = "workflow:assessment"
    REDIS_ACTIVE_INDEX = "workflow:assessments:active"
    REDIS_TTL_DAYS = 30  # Keep assessments for 30 days

    def __init__(self) -> None:
        """Initialize security workflow manager with Redis client placeholder."""
        self._redis_client: Any = None

    async def _get_redis(self) -> Any:
        """Get Redis client for workflow database."""
        if self._redis_client is None:
            self._redis_client = await get_redis_client(
                async_client=True, database="workflows"
            )
        return self._redis_client

    def _assessment_key(self, assessment_id: str) -> str:
        """Generate Redis key for an assessment."""
        return f"{self.REDIS_KEY_PREFIX}:{assessment_id}"

    async def create_assessment(
        self,
        name: str,
        target: str,
        scope: Optional[list[str]] = None,
        training_mode: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SecurityAssessment:
        """
        Create a new security assessment.

        Args:
            name: Human-readable assessment name
            target: Primary target (IP, CIDR, hostname)
            scope: List of in-scope targets (defaults to [target])
            training_mode: Enable exploitation phase
            metadata: Additional assessment metadata

        Returns:
            Created SecurityAssessment
        """
        assessment_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        assessment = SecurityAssessment(
            id=assessment_id,
            name=name,
            target=target,
            scope=scope or [target],
            phase=AssessmentPhase.INIT,
            training_mode=training_mode,
            created_at=now,
            updated_at=now,
            phase_history=[
                {
                    "phase": "INIT",
                    "timestamp": now,
                    "action": "Assessment created",
                }
            ],
            metadata=metadata or {},
        )

        # Persist to Redis
        await self._save_assessment(assessment)

        logger.info(
            "Created security assessment: id=%s, name=%s, target=%s, training_mode=%s",
            assessment_id,
            name,
            target,
            training_mode,
        )

        # Create Memory MCP entity for the assessment
        try:
            memory = await _get_memory_integration()
            if memory:
                await memory.create_assessment_entity(
                    assessment_id=assessment_id,
                    name=name,
                    target=target,
                    scope=scope or [target],
                    training_mode=training_mode,
                    metadata=metadata,
                )
        except Exception as e:
            logger.warning("Failed to create assessment entity in Memory MCP: %s", e)

        return assessment

    async def _save_assessment(self, assessment: SecurityAssessment) -> None:
        """Save assessment to Redis."""
        try:
            redis = await self._get_redis()
            key = self._assessment_key(assessment.id)

            # Update timestamp
            assessment.updated_at = datetime.now(timezone.utc).isoformat()

            # Save as JSON
            await redis.set(
                key,
                json.dumps(assessment.to_dict(), ensure_ascii=False),
                ex=self.REDIS_TTL_DAYS * 24 * 3600,
            )

            # Add to active index if not complete
            if assessment.phase != AssessmentPhase.COMPLETE:
                await redis.sadd(self.REDIS_ACTIVE_INDEX, assessment.id)
            else:
                await redis.srem(self.REDIS_ACTIVE_INDEX, assessment.id)
        except RedisError as e:
            logger.error("Failed to save assessment %s: %s", assessment.id, e)
            raise RuntimeError(f"Failed to save assessment: {e}")

    async def get_assessment(self, assessment_id: str) -> Optional[SecurityAssessment]:
        """
        Retrieve an assessment by ID.

        Args:
            assessment_id: Assessment UUID

        Returns:
            SecurityAssessment or None if not found
        """
        try:
            redis = await self._get_redis()
            key = self._assessment_key(assessment_id)

            data = await redis.get(key)
            if not data:
                return None

            return SecurityAssessment.from_dict(json.loads(data))
        except RedisError as e:
            logger.error("Failed to get assessment %s: %s", assessment_id, e)
            raise RuntimeError(f"Failed to get assessment: {e}")

    def _parse_assessment_data(
        self, aid: str, data: dict
    ) -> Optional[SecurityAssessment]:
        """Parse raw Redis data into SecurityAssessment (Issue #315: extracted helper).

        Args:
            aid: Assessment ID
            data: Raw Redis hash data

        Returns:
            SecurityAssessment or None on error
        """
        if not data:
            return None

        try:
            # Decode bytes if needed
            decoded = {}
            for k, v in data.items():
                key = k if isinstance(k, str) else k.decode("utf-8")
                val = v if isinstance(v, str) else v.decode("utf-8")
                decoded[key] = val

            return SecurityAssessment(
                assessment_id=decoded["assessment_id"],
                session_id=decoded["session_id"],
                phase=decoded["phase"],
                status=decoded["status"],
                created_at=decoded["created_at"],
                updated_at=decoded["updated_at"],
                findings=ast.literal_eval(decoded.get("findings", "[]")),
                metadata=ast.literal_eval(decoded.get("metadata", "{}")),
            )
        except Exception as e:
            logger.error("Error parsing assessment %s: %s", aid, e)
            return None

    async def list_active_assessments(self) -> list[SecurityAssessment]:
        """List all active (non-complete) assessments."""
        try:
            redis = await self._get_redis()
            assessment_ids = await redis.smembers(self.REDIS_ACTIVE_INDEX)

            if not assessment_ids:
                return []

            # Batch fetch assessments using pipeline
            pipe = redis.pipeline()
            for aid in assessment_ids:
                key = f"{self.REDIS_KEY_PREFIX}{aid}"
                pipe.hgetall(key)

            results = await pipe.execute()

            # Parse results using helper (Issue #315: reduced nesting)
            assessments = []
            for aid, data in zip(assessment_ids, results):
                assessment = self._parse_assessment_data(aid, data)
                if assessment:
                    assessments.append(assessment)

            return sorted(assessments, key=lambda a: a.updated_at, reverse=True)
        except RedisError as e:
            logger.error("Failed to list active assessments: %s", e)
            raise RuntimeError(f"Failed to list active assessments: {e}")

    async def advance_phase(
        self,
        assessment_id: str,
        reason: str = "",
        target_phase: Optional[str] = None,
    ) -> Optional[SecurityAssessment]:
        """
        Advance to the next workflow phase.

        Args:
            assessment_id: Assessment UUID
            reason: Reason for phase transition
            target_phase: Specific phase to transition to (optional)

        Returns:
            Updated SecurityAssessment or None if transition invalid
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            logger.error("Assessment not found: %s", assessment_id)
            return None

        current_phase = assessment.phase.value
        valid_next = VALID_TRANSITIONS.get(current_phase, [])

        if not valid_next:
            logger.warning("No valid transitions from %s", current_phase)
            return assessment

        # Determine target phase
        if target_phase:
            if target_phase not in valid_next:
                logger.error(
                    "Invalid transition: %s -> %s. Valid: %s",
                    current_phase,
                    target_phase,
                    valid_next,
                )
                return None
            next_phase = target_phase
        else:
            # Auto-advance to first valid (non-error) phase
            next_phase = next(
                (p for p in valid_next if p != "ERROR"),
                valid_next[0] if valid_next else None,
            )

        if not next_phase:
            return assessment

        # Check training mode requirement for exploitation
        if next_phase == "EXPLOITATION" and not assessment.training_mode:
            logger.warning(
                "Cannot enter EXPLOITATION phase: training_mode=False. "
                "Skipping to REPORTING."
            )
            next_phase = "REPORTING"

        # Record transition
        now = datetime.now(timezone.utc).isoformat()
        transition = {
            "from_phase": current_phase,
            "to_phase": next_phase,
            "timestamp": now,
            "reason": reason or f"Advancing from {current_phase}",
        }

        assessment.phase = AssessmentPhase(next_phase)
        assessment.phase_history.append(transition)

        await self._save_assessment(assessment)

        logger.info(
            "Assessment %s: %s -> %s ", assessment_id, current_phase, next_phase
        )

        return assessment

    async def add_host(
        self,
        assessment_id: str,
        ip: str,
        hostname: Optional[str] = None,
        status: str = "unknown",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[SecurityAssessment]:
        """
        Add a discovered host to the assessment.

        Args:
            assessment_id: Assessment UUID
            ip: Host IP address
            hostname: Optional hostname
            status: Host status (unknown, up, down)
            metadata: Additional host metadata

        Returns:
            Updated SecurityAssessment
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        is_new_host = False

        # Check if host already exists
        existing = next((h for h in assessment.hosts if h.ip == ip), None)
        if existing:
            # Update existing host
            existing.hostname = hostname or existing.hostname
            existing.status = status
            existing.metadata.update(metadata or {})
        else:
            # Add new host
            host = TargetHost(
                ip=ip,
                hostname=hostname,
                status=status,
                metadata=metadata or {},
            )
            assessment.hosts.append(host)
            is_new_host = True

        await self._save_assessment(assessment)
        logger.info("Added/updated host %s in assessment %s", ip, assessment_id)

        # Create Memory MCP entity for new hosts
        if is_new_host:
            try:
                memory = await _get_memory_integration()
                if memory:
                    await memory.create_host_entity(
                        assessment_id=assessment_id,
                        ip=ip,
                        hostname=hostname,
                        status=status,
                        os_guess=metadata.get("os_guess") if metadata else None,
                        metadata=metadata,
                    )
            except Exception as e:
                logger.warning("Failed to create host entity in Memory MCP: %s", e)

        return assessment

    async def add_port(
        self,
        assessment_id: str,
        host_ip: str,
        port: int,
        protocol: str = "tcp",
        state: str = "open",
        service: Optional[str] = None,
        version: Optional[str] = None,
        product: Optional[str] = None,
    ) -> Optional[SecurityAssessment]:
        """
        Add a discovered port to a host.

        Args:
            assessment_id: Assessment UUID
            host_ip: Host IP address
            port: Port number
            protocol: Protocol (tcp/udp)
            state: Port state (open/closed/filtered)
            service: Service name
            version: Service version
            product: Product name

        Returns:
            Updated SecurityAssessment
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        # Find or create host
        host = next((h for h in assessment.hosts if h.ip == host_ip), None)
        is_new_host = host is None
        if not host:
            host = TargetHost(ip=host_ip, status="up")
            assessment.hosts.append(host)

        # Add port
        port_info = {
            "port": port,
            "protocol": protocol,
            "state": state,
            "service": service,
            "version": version,
            "product": product,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        }
        host.ports.append(port_info)

        # Add to services if identified
        if service:
            service_info = {
                "port": port,
                "name": service,
                "version": version,
                "protocol": protocol,
                "product": product,
            }
            host.services.append(service_info)

        await self._save_assessment(assessment)
        logger.info("to %s in assessment %s", host_ip, assessment_id)

        # Issue #398: Create Memory MCP entities (uses extracted helper)
        await self._create_port_memory_entity(
            assessment_id,
            host_ip,
            is_new_host,
            port,
            protocol,
            state,
            service,
            version,
            product,
        )

        return assessment

    async def _create_port_memory_entity(
        self,
        assessment_id: str,
        host_ip: str,
        is_new_host: bool,
        port: int,
        protocol: str,
        state: str,
        service: Optional[str],
        version: Optional[str],
        product: Optional[str],
    ) -> None:
        """Create Memory MCP entities for port discovery (Issue #398: extracted)."""
        try:
            memory = await _get_memory_integration()
            if not memory:
                return

            # Create host entity if new
            if is_new_host:
                await memory.create_host_entity(
                    assessment_id=assessment_id,
                    ip=host_ip,
                    status="up",
                )

            # Create service entity for identified services
            if service and state == "open":
                await memory.create_service_entity(
                    assessment_id=assessment_id,
                    host_ip=host_ip,
                    port=port,
                    protocol=protocol,
                    service_name=service,
                    version=version,
                    product=product,
                )
        except Exception as e:
            logger.warning("Failed to create service entity in Memory MCP: %s", e)

    async def add_vulnerability(
        self,
        assessment_id: str,
        host_ip: str,
        cve_id: Optional[str] = None,
        title: str = "",
        severity: str = "unknown",
        description: str = "",
        affected_service: Optional[str] = None,
        affected_port: Optional[int] = None,
        references: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[SecurityAssessment]:
        """
        Add a discovered vulnerability.

        Args:
            assessment_id: Assessment UUID
            host_ip: Affected host IP
            cve_id: CVE identifier (e.g., CVE-2024-1234)
            title: Vulnerability title
            severity: Severity (critical/high/medium/low/info)
            description: Vulnerability description
            affected_service: Affected service name
            affected_port: Affected port number
            references: Reference URLs
            metadata: Additional vulnerability data

        Returns:
            Updated SecurityAssessment
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        # Find or create host
        host = next((h for h in assessment.hosts if h.ip == host_ip), None)
        is_new_host = host is None
        if not host:
            host = TargetHost(ip=host_ip, status="up")
            assessment.hosts.append(host)

        vuln = {
            "cve_id": cve_id,
            "title": title,
            "severity": severity,
            "description": description,
            "affected_service": affected_service,
            "affected_port": affected_port,
            "references": references or [],
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        host.vulnerabilities.append(vuln)

        # Also add to findings
        finding = {
            "type": "vulnerability",
            "host": host_ip,
            "data": vuln,
        }
        assessment.findings.append(finding)

        await self._save_assessment(assessment)
        logger.info(
            "Added vulnerability %s to %s in assessment %s",
            cve_id or title,
            host_ip,
            assessment_id,
        )

        # Issue #398: Create Memory MCP entities (uses extracted helper)
        await self._create_vulnerability_memory_entity(
            assessment_id,
            host_ip,
            is_new_host,
            cve_id,
            title,
            severity,
            description,
            affected_port,
            affected_service,
            references,
            metadata,
        )

        return assessment

    async def _create_vulnerability_memory_entity(
        self,
        assessment_id: str,
        host_ip: str,
        is_new_host: bool,
        cve_id: Optional[str],
        title: str,
        severity: str,
        description: str,
        affected_port: Optional[int],
        affected_service: Optional[str],
        references: Optional[list[str]],
        metadata: Optional[dict[str, Any]],
    ) -> None:
        """Create Memory MCP entities for vulnerability (Issue #398: extracted)."""
        try:
            memory = await _get_memory_integration()
            if not memory:
                return

            # Create host entity if new
            if is_new_host:
                await memory.create_host_entity(
                    assessment_id=assessment_id,
                    ip=host_ip,
                    status="up",
                )

            # Issue #319: Use request object to reduce parameter count
            from src.services.security_memory_integration import VulnerabilityRequest

            vuln_request = VulnerabilityRequest(
                assessment_id=assessment_id,
                host_ip=host_ip,
                cve_id=cve_id,
                title=title,
                severity=severity,
                description=description,
                affected_port=affected_port,
                affected_service=affected_service,
                references=references,
                metadata=metadata,
            )
            await memory.create_vulnerability_entity(request=vuln_request)
        except Exception as e:
            logger.warning("Failed to create vulnerability entity in Memory MCP: %s", e)

    async def add_finding(
        self,
        assessment_id: str,
        finding: dict[str, Any],
    ) -> Optional[SecurityAssessment]:
        """
        Add a general finding to the assessment.

        Args:
            assessment_id: Assessment UUID
            finding: Finding data (type, description, etc.)

        Returns:
            Updated SecurityAssessment
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        finding["timestamp"] = datetime.now(timezone.utc).isoformat()
        assessment.findings.append(finding)

        await self._save_assessment(assessment)
        logger.info(
            "Added finding to assessment %s: %s", assessment_id, finding.get("type")
        )

        return assessment

    async def record_action(
        self,
        assessment_id: str,
        action: str,
        tool: Optional[str] = None,
        command: Optional[str] = None,
        result: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[SecurityAssessment]:
        """
        Record an action taken during the assessment.

        Args:
            assessment_id: Assessment UUID
            action: Action description
            tool: Tool used (e.g., nmap, nikto)
            command: Command executed
            result: Action result summary
            metadata: Additional action data

        Returns:
            Updated SecurityAssessment
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        action_record = {
            "action": action,
            "phase": assessment.phase.value,
            "tool": tool,
            "command": command,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        assessment.actions_taken.append(action_record)

        await self._save_assessment(assessment)
        logger.debug("Recorded action in assessment %s: %s", assessment_id, action)

        return assessment

    async def set_error(
        self,
        assessment_id: str,
        error_message: str,
    ) -> Optional[SecurityAssessment]:
        """
        Set assessment to error state.

        Args:
            assessment_id: Assessment UUID
            error_message: Error description

        Returns:
            Updated SecurityAssessment
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        previous_phase = assessment.phase.value
        assessment.phase = AssessmentPhase.ERROR
        assessment.error_message = error_message

        now = datetime.now(timezone.utc).isoformat()
        assessment.phase_history.append(
            {
                "from_phase": previous_phase,
                "to_phase": "ERROR",
                "timestamp": now,
                "reason": error_message,
            }
        )

        await self._save_assessment(assessment)
        logger.error(
            "Assessment %s entered ERROR state: %s", assessment_id, error_message
        )

        return assessment

    async def recover_from_error(
        self,
        assessment_id: str,
        target_phase: str,
        reason: str = "Manual recovery",
    ) -> Optional[SecurityAssessment]:
        """
        Recover from error state to a specific phase.

        Args:
            assessment_id: Assessment UUID
            target_phase: Phase to recover to
            reason: Recovery reason

        Returns:
            Updated SecurityAssessment
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        if assessment.phase != AssessmentPhase.ERROR:
            logger.warning("Assessment %s is not in ERROR state", assessment_id)
            return assessment

        valid_recovery = VALID_TRANSITIONS.get("ERROR", [])
        if target_phase not in valid_recovery:
            logger.error("Cannot recover to phase %s", target_phase)
            return None

        assessment.phase = AssessmentPhase(target_phase)
        assessment.error_message = None

        now = datetime.now(timezone.utc).isoformat()
        assessment.phase_history.append(
            {
                "from_phase": "ERROR",
                "to_phase": target_phase,
                "timestamp": now,
                "reason": reason,
            }
        )

        await self._save_assessment(assessment)
        logger.info("Assessment %s recovered to %s", assessment_id, target_phase)

        return assessment

    async def delete_assessment(self, assessment_id: str) -> bool:
        """
        Delete an assessment.

        Args:
            assessment_id: Assessment UUID

        Returns:
            True if deleted, False if not found
        """
        try:
            redis = await self._get_redis()
            key = self._assessment_key(assessment_id)

            deleted = await redis.delete(key)
            await redis.srem(self.REDIS_ACTIVE_INDEX, assessment_id)

            if deleted:
                logger.info("Deleted assessment %s", assessment_id)
                return True

            return False
        except RedisError as e:
            logger.error("Failed to delete assessment %s: %s", assessment_id, e)
            raise RuntimeError(f"Failed to delete assessment: {e}")

    async def get_assessment_summary(
        self,
        assessment_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Get a summary of an assessment for context.

        Args:
            assessment_id: Assessment UUID

        Returns:
            Summary dictionary for LLM context
        """
        assessment = await self.get_assessment(assessment_id)
        if not assessment:
            return None

        # Count findings by type
        vuln_count = len(
            [f for f in assessment.findings if f.get("type") == "vulnerability"]
        )
        host_count = len(assessment.hosts)
        port_count = sum(len(h.ports) for h in assessment.hosts)
        service_count = sum(len(h.services) for h in assessment.hosts)

        # Get severity distribution
        severity_counts: dict[str, int] = {}
        for host in assessment.hosts:
            for vuln in host.vulnerabilities:
                sev = vuln.get("severity", "unknown")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "id": assessment.id,
            "name": assessment.name,
            "target": assessment.target,
            "phase": assessment.phase.value,
            "phase_description": PHASE_DESCRIPTIONS.get(assessment.phase.value, {}).get(
                "description", ""
            ),
            "training_mode": assessment.training_mode,
            "stats": {
                "hosts": host_count,
                "ports": port_count,
                "services": service_count,
                "vulnerabilities": vuln_count,
                "severity_distribution": severity_counts,
                "actions_taken": len(assessment.actions_taken),
            },
            "next_actions": PHASE_DESCRIPTIONS.get(assessment.phase.value, {}).get(
                "actions", []
            ),
            "created_at": assessment.created_at,
            "updated_at": assessment.updated_at,
        }


# Singleton instance (thread-safe)
import threading

_workflow_manager: Optional[SecurityWorkflowManager] = None
_workflow_manager_lock = threading.Lock()


def get_security_workflow_manager() -> SecurityWorkflowManager:
    """Get or create the security workflow manager singleton (thread-safe)."""
    global _workflow_manager
    if _workflow_manager is None:
        with _workflow_manager_lock:
            # Double-check after acquiring lock
            if _workflow_manager is None:
                _workflow_manager = SecurityWorkflowManager()
    return _workflow_manager
