# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Assessment Memory Integration

Integrates security assessment findings with Memory MCP for:
- Entity creation from scan results (hosts, services, vulnerabilities)
- Relationship tracking (host → service → vulnerability)
- Semantic search over security findings
- Graph-RAG queries for security context

Issue: #260
"""

import logging
from dataclasses import dataclass
from typing import Any, FrozenSet, Optional

from src.autobot_memory_graph import AutoBotMemoryGraph

# Issue #380: Module-level frozenset for security-related tags
_SECURITY_TAGS: FrozenSet[str] = frozenset(
    {"security", "vulnerability", "host", "service"}
)


@dataclass
class VulnerabilityRequest:
    """
    Request parameters for creating a vulnerability entity.

    Issue #319: Reduces long parameter list in create_vulnerability_entity().
    Groups vulnerability data into a single request object.
    """

    assessment_id: str
    host_ip: str
    cve_id: Optional[str] = None
    title: str = ""
    severity: str = "unknown"
    description: str = ""
    affected_port: Optional[int] = None
    affected_service: Optional[str] = None
    references: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ServiceRequest:
    """
    Request parameters for creating a service entity.

    Issue #319: Reduces long parameter list in create_service_entity().
    Groups service data into a single request object.
    """

    assessment_id: str
    host_ip: str
    port: int
    protocol: str = "tcp"
    service_name: Optional[str] = None
    version: Optional[str] = None
    product: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for security relation types (Issue #326)
DETAIL_RELATION_TYPES = {"contains", "runs", "has_vulnerability", "exploited_by"}
SEVERITY_RELATION_TYPES = {"affects"}


# Security-specific entity types (extend base ENTITY_TYPES)
SECURITY_ENTITY_TYPES = {
    "security_assessment": "Root assessment entity",
    "target_network": "Network/CIDR being assessed",
    "target_host": "Individual host IP",
    "service": "Service running on a port",
    "vulnerability": "Identified vulnerability/CVE",
    "exploit_attempt": "Exploitation attempt (training mode)",
    "finding": "General security finding",
}

# Security-specific relation types (extend base RELATION_TYPES)
SECURITY_RELATION_TYPES = {
    "contains": "Parent contains child (assessment → network → host)",
    "runs": "Host runs service",
    "has_vulnerability": "Service has vulnerability",
    "exploited_by": "Vulnerability exploited by attempt",
    "related_to": "General cross-reference",
    "depends_on": "Dependency relationship",
    "affects": "Vulnerability affects service/host",
}


class SecurityMemoryIntegration:
    """
    Integrates security assessment data with Memory MCP.

    Creates structured entities and relationships from security findings
    to enable Graph-RAG queries and persistent knowledge storage.

    Usage:
        integration = SecurityMemoryIntegration()
        await integration.initialize()

        # Store assessment as entity
        await integration.create_assessment_entity(assessment)

        # Store host with relationships
        await integration.create_host_entity(assessment_id, host_data)

        # Query findings
        results = await integration.search_security_findings("SSH vulnerability")
    """

    def __init__(self, memory_graph: Optional[AutoBotMemoryGraph] = None):
        """
        Initialize security memory integration.

        Args:
            memory_graph: Optional existing memory graph instance
        """
        self._memory_graph = memory_graph
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the memory graph connection."""
        if self._initialized:
            return

        if self._memory_graph is None:
            self._memory_graph = AutoBotMemoryGraph()

        await self._memory_graph.initialize()
        self._initialized = True
        logger.info("SecurityMemoryIntegration initialized")

    async def ensure_initialized(self) -> None:
        """Ensure the integration is initialized."""
        if not self._initialized:
            await self.initialize()

    def _build_assessment_observations(
        self,
        name: str,
        target: str,
        scope: list[str],
        training_mode: bool,
        metadata: Optional[dict[str, Any]],
    ) -> list[str]:
        """
        Build observations list for a security assessment entity.

        Issue #620.
        """
        observations = [
            f"Security assessment: {name}",
            f"Primary target: {target}",
            f"Scope: {', '.join(scope)}",
            f"Training mode: {'enabled' if training_mode else 'disabled'}",
        ]
        if metadata:
            for key, value in metadata.items():
                observations.append(f"{key}: {value}")
        return observations

    async def _store_assessment_in_memory(
        self,
        assessment_id: str,
        name: str,
        target: str,
        scope: list[str],
        training_mode: bool,
        observations: list[str],
        metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Store assessment entity in memory graph.

        Issue #620.
        """
        return await self._memory_graph.create_entity(
            entity_type="task",
            name=f"Security Assessment: {name}",
            observations=observations,
            metadata={
                "assessment_id": assessment_id,
                "type": "security_assessment",
                "target": target,
                "scope": scope,
                "training_mode": training_mode,
                **(metadata or {}),
            },
            tags=["security", "assessment", "pentest"],
        )

    async def create_assessment_entity(
        self,
        assessment_id: str,
        name: str,
        target: str,
        scope: list[str],
        training_mode: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create a memory entity for a security assessment.

        Args:
            assessment_id: Unique assessment identifier
            name: Assessment name
            target: Primary target
            scope: In-scope targets
            training_mode: Whether exploitation is enabled
            metadata: Additional metadata

        Returns:
            Created entity data
        """
        await self.ensure_initialized()
        observations = self._build_assessment_observations(
            name, target, scope, training_mode, metadata
        )
        entity = await self._store_assessment_in_memory(
            assessment_id, name, target, scope, training_mode, observations, metadata
        )
        logger.info("Created assessment entity: %s", assessment_id)
        return entity

    def _build_host_observations(
        self,
        ip: str,
        status: str,
        hostname: Optional[str],
        os_guess: Optional[str],
        metadata: Optional[dict[str, Any]],
    ) -> list[str]:
        """
        Build observations list for a host entity.

        Issue #620.
        """
        observations = [f"Target host: {ip}", f"Status: {status}"]
        if hostname:
            observations.append(f"Hostname: {hostname}")
        if os_guess:
            observations.append(f"OS: {os_guess}")
        if metadata:
            if metadata.get("mac_address"):
                observations.append(f"MAC: {metadata['mac_address']}")
            if metadata.get("vendor"):
                observations.append(f"Vendor: {metadata['vendor']}")
        return observations

    async def _store_host_in_memory(
        self,
        ip: str,
        observations: list[str],
        assessment_id: str,
        hostname: Optional[str],
        status: str,
        os_guess: Optional[str],
        metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Store host entity in memory graph.

        Issue #620.
        """
        return await self._memory_graph.create_entity(
            entity_type="context",
            name=f"Host: {ip}",
            observations=observations,
            metadata={
                "assessment_id": assessment_id,
                "type": "target_host",
                "ip": ip,
                "hostname": hostname,
                "status": status,
                "os_guess": os_guess,
                **(metadata or {}),
            },
            tags=["security", "host", "target"],
        )

    async def create_host_entity(
        self,
        assessment_id: str,
        ip: str,
        hostname: Optional[str] = None,
        status: str = "up",
        os_guess: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create a memory entity for a discovered host.

        Args:
            assessment_id: Parent assessment ID
            ip: Host IP address
            hostname: Optional hostname
            status: Host status (up/down)
            os_guess: OS detection result
            metadata: Additional metadata

        Returns:
            Created entity data
        """
        await self.ensure_initialized()
        observations = self._build_host_observations(
            ip, status, hostname, os_guess, metadata
        )
        entity = await self._store_host_in_memory(
            ip, observations, assessment_id, hostname, status, os_guess, metadata
        )
        await self._create_security_relation(
            from_entity=f"Security Assessment: {assessment_id}",
            to_entity=f"Host: {ip}",
            relation_type="contains",
        )
        logger.info("Created host entity: %s for assessment %s", ip, assessment_id)
        return entity

    def _build_service_observations(
        self,
        host_ip: str,
        port: int,
        protocol: str,
        service_name: Optional[str],
        version: Optional[str],
        product: Optional[str],
    ) -> list[str]:
        """
        Build observations list for a service entity.

        Issue #620.
        """
        observations = [
            f"Service on {host_ip}:{port}/{protocol}",
            f"Service: {service_name or 'unknown'}",
        ]
        if version:
            observations.append(f"Version: {version}")
        if product:
            observations.append(f"Product: {product}")
        return observations

    async def _store_service_in_memory(
        self,
        entity_name: str,
        observations: list[str],
        assessment_id: str,
        host_ip: str,
        port: int,
        protocol: str,
        service_name: Optional[str],
        version: Optional[str],
        product: Optional[str],
        metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Store service entity in memory graph.

        Issue #620.
        """
        return await self._memory_graph.create_entity(
            entity_type="context",
            name=entity_name,
            observations=observations,
            metadata={
                "assessment_id": assessment_id,
                "type": "service",
                "host_ip": host_ip,
                "port": port,
                "protocol": protocol,
                "service_name": service_name,
                "version": version,
                "product": product,
                **(metadata or {}),
            },
            tags=["security", "service", service_name or "unknown"],
        )

    async def create_service_entity(
        self,
        assessment_id: str,
        host_ip: str,
        port: int,
        protocol: str = "tcp",
        service_name: Optional[str] = None,
        version: Optional[str] = None,
        product: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create a memory entity for a discovered service.

        Args:
            assessment_id: Parent assessment ID
            host_ip: Host IP address
            port: Port number
            protocol: Protocol (tcp/udp)
            service_name: Service name
            version: Service version
            product: Product name
            metadata: Additional metadata

        Returns:
            Created entity data
        """
        await self.ensure_initialized()
        service_desc = service_name or "unknown"
        entity_name = f"Service: {host_ip}:{port}/{protocol} ({service_desc})"
        observations = self._build_service_observations(
            host_ip, port, protocol, service_name, version, product
        )
        entity = await self._store_service_in_memory(
            entity_name,
            observations,
            assessment_id,
            host_ip,
            port,
            protocol,
            service_name,
            version,
            product,
            metadata,
        )
        await self._create_security_relation(
            from_entity=f"Host: {host_ip}",
            to_entity=entity_name,
            relation_type="runs",
        )
        logger.info("Created service entity: %s", entity_name)
        return entity

    def _build_vuln_observations(
        self,
        vuln_name: str,
        severity: str,
        host_ip: str,
        description: str,
        affected_port: Optional[int],
        affected_service: Optional[str],
        references: Optional[list[str]],
    ) -> list[str]:
        """Build observations list for vulnerability (Issue #281 - extracted helper)."""
        observations = [
            f"Vulnerability: {vuln_name}",
            f"Severity: {severity.upper()}",
            f"Affected host: {host_ip}",
        ]
        if description:
            observations.append(f"Description: {description}")
        if affected_port:
            observations.append(f"Affected port: {affected_port}")
        if affected_service:
            observations.append(f"Affected service: {affected_service}")
        if references:
            observations.append(f"References: {', '.join(references[:3])}")
        return observations

    async def _create_vuln_relations(
        self,
        host_ip: str,
        entity_name: str,
        affected_port: Optional[int],
        affected_service: Optional[str],
    ) -> None:
        """Create relations for vulnerability entity (Issue #281 - extracted helper)."""
        await self._create_security_relation(
            from_entity=f"Host: {host_ip}",
            to_entity=entity_name,
            relation_type="relates_to",
        )
        if affected_port and affected_service:
            service_entity = (
                f"Service: {host_ip}:{affected_port}/tcp ({affected_service})"
            )
            await self._create_security_relation(
                from_entity=service_entity,
                to_entity=entity_name,
                relation_type="relates_to",
            )

    async def _store_vulnerability_in_memory(
        self,
        entity_name: str,
        observations: list[str],
        assessment_id: str,
        host_ip: str,
        cve_id: Optional[str],
        title: str,
        severity: str,
        affected_port: Optional[int],
        affected_service: Optional[str],
        metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Store vulnerability entity in memory graph.

        Issue #665: Extracted from create_vulnerability_entity to reduce function length.
        Handles the actual memory graph entity creation with all metadata.

        Args:
            entity_name: Name for the vulnerability entity.
            observations: List of observation strings for the entity.
            assessment_id: Parent assessment ID.
            host_ip: Affected host IP address.
            cve_id: CVE identifier if available.
            title: Vulnerability title.
            severity: Severity level (critical/high/medium/low/info).
            affected_port: Affected port number if applicable.
            affected_service: Affected service name if applicable.
            metadata: Additional metadata dictionary.

        Returns:
            dict[str, Any]: Created entity data from memory graph.
        """
        return await self._memory_graph.create_entity(
            entity_type="bug_fix",
            name=entity_name,
            observations=observations,
            metadata={
                "assessment_id": assessment_id,
                "type": "vulnerability",
                "host_ip": host_ip,
                "cve_id": cve_id,
                "title": title,
                "severity": severity,
                "affected_port": affected_port,
                "affected_service": affected_service,
                **(metadata or {}),
            },
            tags=["security", "vulnerability", severity, cve_id or "no-cve"],
        )

    def _normalize_to_request(
        self,
        request: Optional[VulnerabilityRequest],
        assessment_id: Optional[str],
        host_ip: Optional[str],
        cve_id: Optional[str],
        title: str,
        severity: str,
        description: str,
        affected_port: Optional[int],
        affected_service: Optional[str],
        references: Optional[list[str]],
        metadata: Optional[dict[str, Any]],
    ) -> VulnerabilityRequest:
        """
        Normalize parameters into a VulnerabilityRequest object. Issue #620.
        """
        if request is not None:
            return request
        if assessment_id is None or host_ip is None:
            raise ValueError(
                "Either 'request' object or 'assessment_id' and 'host_ip' required"
            )
        return VulnerabilityRequest(
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

    async def _build_and_store_vulnerability(
        self, req: VulnerabilityRequest
    ) -> dict[str, Any]:
        """
        Build observations, store entity, and create relations. Issue #620.
        """
        vuln_name = req.cve_id or req.title or "Unknown Vulnerability"
        entity_name = f"Vuln: {vuln_name} on {req.host_ip}"
        observations = self._build_vuln_observations(
            vuln_name,
            req.severity,
            req.host_ip,
            req.description,
            req.affected_port,
            req.affected_service,
            req.references,
        )
        entity = await self._store_vulnerability_in_memory(
            entity_name,
            observations,
            req.assessment_id,
            req.host_ip,
            req.cve_id,
            req.title,
            req.severity,
            req.affected_port,
            req.affected_service,
            req.metadata,
        )
        await self._create_vuln_relations(
            req.host_ip, entity_name, req.affected_port, req.affected_service
        )
        logger.info("Created vulnerability entity: %s", entity_name)
        return entity

    async def create_vulnerability_entity(
        self,
        request: Optional[VulnerabilityRequest] = None,
        *,
        assessment_id: Optional[str] = None,
        host_ip: Optional[str] = None,
        cve_id: Optional[str] = None,
        title: str = "",
        severity: str = "unknown",
        description: str = "",
        affected_port: Optional[int] = None,
        affected_service: Optional[str] = None,
        references: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create a memory entity for a discovered vulnerability.

        Args:
            request: VulnerabilityRequest object (preferred).
            assessment_id: Parent assessment ID. host_ip: Affected host IP.
            cve_id: CVE ID. title: Title. severity: Level. description: Details.
            affected_port: Port. affected_service: Service. references: URLs.
            metadata: Additional metadata dict.

        Returns:
            dict[str, Any]: Created entity data.
        """
        req = self._normalize_to_request(
            request,
            assessment_id,
            host_ip,
            cve_id,
            title,
            severity,
            description,
            affected_port,
            affected_service,
            references,
            metadata,
        )
        await self.ensure_initialized()
        return await self._build_and_store_vulnerability(req)

    async def _create_security_relation(
        self,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        strength: float = 1.0,
    ) -> bool:
        """
        Create a relationship between security entities.

        Args:
            from_entity: Source entity name
            to_entity: Target entity name
            relation_type: Type of relationship
            strength: Relationship strength (0.0-1.0)

        Returns:
            True if created successfully
        """
        try:
            # Map security relation types to base types
            base_relation = relation_type
            if relation_type in DETAIL_RELATION_TYPES:
                base_relation = "contains"
            elif relation_type in SEVERITY_RELATION_TYPES:
                base_relation = "relates_to"

            await self._memory_graph.create_relation(
                from_entity=from_entity,
                to_entity=to_entity,
                relation_type=base_relation,
                strength=strength,
            )
            return True
        except Exception as e:
            logger.warning(
                "Failed to create relation %s -> %s: %s", from_entity, to_entity, e
            )
            return False

    async def search_security_findings(
        self,
        query: str,
        entity_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search for security findings in memory.

        Args:
            query: Search query
            entity_type: Filter by type (vulnerability, service, host)
            severity: Filter by severity
            limit: Maximum results

        Returns:
            List of matching entities
        """
        await self.ensure_initialized()

        # Build search query with filters
        search_query = query
        if severity:
            search_query += f" severity:{severity}"

        results = await self._memory_graph.search_entities(
            query=search_query,
            entity_type=entity_type,
            limit=limit,
        )

        # Filter for security-related entities
        security_results = [
            r
            for r in results
            if r.get("metadata", {}).get("type") in SECURITY_ENTITY_TYPES
            or any(tag in r.get("tags", []) for tag in _SECURITY_TAGS)
        ]

        return security_results

    async def get_host_context(
        self,
        host_ip: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        Get full context for a host including services and vulnerabilities.

        Args:
            host_ip: Host IP address
            depth: Relationship traversal depth

        Returns:
            Host context with related entities
        """
        await self.ensure_initialized()

        # Search for the host entity
        host_results = await self._memory_graph.search_entities(
            query=f"Host: {host_ip}",
            limit=1,
        )

        if not host_results:
            return {"host": host_ip, "found": False}

        host_entity = host_results[0]

        # Get related entities (services, vulnerabilities)
        related = await self._memory_graph.traverse_relations(
            entity_name=host_entity.get("name", f"Host: {host_ip}"),
            depth=depth,
        )

        return {
            "host": host_ip,
            "found": True,
            "entity": host_entity,
            "related": related,
        }

    def _categorize_assessment_entities(
        self, entities: list[dict[str, Any]]
    ) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
        """
        Categorize assessment entities by type.

        Issue #620.
        """
        hosts, services, vulnerabilities, other = [], [], [], []
        for entity in entities:
            entity_type = entity.get("metadata", {}).get("type", "")
            if entity_type == "target_host":
                hosts.append(entity)
            elif entity_type == "service":
                services.append(entity)
            elif entity_type == "vulnerability":
                vulnerabilities.append(entity)
            else:
                other.append(entity)
        return hosts, services, vulnerabilities, other

    def _compute_severity_distribution(
        self, vulnerabilities: list[dict[str, Any]]
    ) -> dict[str, int]:
        """
        Compute severity distribution from vulnerability entities.

        Issue #620.
        """
        severity_counts: dict[str, int] = {}
        for vuln in vulnerabilities:
            sev = vuln.get("metadata", {}).get("severity", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        return severity_counts

    async def get_assessment_summary(self, assessment_id: str) -> dict[str, Any]:
        """
        Get a summary of all entities for an assessment.

        Args:
            assessment_id: Assessment UUID

        Returns:
            Summary with counts and key findings
        """
        await self.ensure_initialized()
        all_results = await self._memory_graph.search_entities(
            query=f"assessment_id:{assessment_id}", limit=500
        )
        hosts, services, vulnerabilities, _ = self._categorize_assessment_entities(
            all_results
        )
        severity_counts = self._compute_severity_distribution(vulnerabilities)
        critical_vulns = [
            v
            for v in vulnerabilities
            if v.get("metadata", {}).get("severity") == "critical"
        ][:5]
        return {
            "assessment_id": assessment_id,
            "total_entities": len(all_results),
            "hosts": len(hosts),
            "services": len(services),
            "vulnerabilities": len(vulnerabilities),
            "severity_distribution": severity_counts,
            "critical_vulns": critical_vulns,
        }


# Singleton instance (thread-safe)
import asyncio as _asyncio_lock

_security_memory: Optional[SecurityMemoryIntegration] = None
_security_memory_lock = _asyncio_lock.Lock()


async def get_security_memory_integration() -> SecurityMemoryIntegration:
    """Get or create the security memory integration singleton (thread-safe)."""
    global _security_memory
    if _security_memory is None:
        async with _security_memory_lock:
            # Double-check after acquiring lock
            if _security_memory is None:
                _security_memory = SecurityMemoryIntegration()
                await _security_memory.initialize()
    return _security_memory
