# Security Assessment Workflow Manager - Architecture Design

**Author**: mrveiss
**Copyright**: (c) 2025 mrveiss
**Issue**: #260
**Status**: Design Document
**Version**: 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [Workflow State Machine](#workflow-state-machine)
3. [Redis Storage Schema](#redis-storage-schema)
4. [Entity Schema for Memory MCP](#entity-schema-for-memory-mcp)
5. [Tool Output Parser Interface](#tool-output-parser-interface)
6. [API Endpoint Design](#api-endpoint-design)
7. [Chat Integration Points](#chat-integration-points)
8. [Implementation Roadmap](#implementation-roadmap)

---

## Overview

### Purpose

The Security Assessment Workflow Manager provides structured, resumable security assessments integrated with AutoBot's chat system and Memory MCP. It enables:

- **Structured Assessment Flow**: Guided phases from reconnaissance to reporting
- **Persistent State**: Redis-backed workflow state survives restarts
- **Memory Integration**: All findings stored as searchable entities in Memory MCP
- **Tool Output Parsing**: Automatic parsing of security tool outputs (nmap, etc.)
- **Resume Capability**: Pick up assessments where you left off

### Architecture Overview

```
+------------------+     +----------------------+     +------------------+
|   Chat Agent     |<--->| SecurityWorkflow     |<--->| Redis DB 7       |
|   (LLM + User)   |     | Manager              |     | (Workflow State) |
+------------------+     +----------------------+     +------------------+
                               |
                               v
                    +----------------------+
                    | Tool Output Parsers  |
                    | (Nmap, Nuclei, etc.) |
                    +----------------------+
                               |
                               v
                    +----------------------+     +------------------+
                    | SecurityMemory       |<--->| Redis DB 9       |
                    | Graph                |     | (Memory Entities)|
                    +----------------------+     +------------------+
```

### Key Design Principles

1. **No Hardcoded Values**: All IPs, ports, timeouts via NetworkConstants or config
2. **Canonical Redis Pattern**: Use `get_redis_client(database="workflows")`
3. **UTF-8 Encoding**: All file I/O and JSON with explicit encoding
4. **Separation of Concerns**: Parser, Workflow, Memory as distinct layers
5. **Training Mode Safety**: Exploitation only in controlled training environments

---

## Workflow State Machine

### Phase Definitions

```
+--------+     +--------+     +-----------+     +-------------+
|  INIT  |---->| RECON  |---->| PORT_SCAN |---->| ENUMERATION |
+--------+     +--------+     +-----------+     +-------------+
                                                       |
+----------+     +--------------+     +-------------+  |
| COMPLETE |<----| REPORTING    |<----| VULN_ANALYSIS|<+
+----------+     +--------------+     +-------------+
                                            |
                                            v
                                    +---------------+
                                    | EXPLOITATION  |
                                    | (Training     |
                                    |  Mode Only)   |
                                    +---------------+
```

### State Definitions

| Phase | Description | Entry Conditions | Exit Conditions |
|-------|-------------|------------------|-----------------|
| `INIT` | Assessment created, target defined | New assessment | Target validated, scope confirmed |
| `RECON` | Passive reconnaissance | INIT complete | DNS/WHOIS/OSINT gathered |
| `PORT_SCAN` | Active port scanning | RECON complete | Open ports identified |
| `ENUMERATION` | Service enumeration | PORT_SCAN complete | Services + versions identified |
| `VULN_ANALYSIS` | Vulnerability identification | ENUMERATION complete | CVEs/vulns catalogued |
| `EXPLOITATION` | Exploit testing (training only) | VULN_ANALYSIS + training_mode=true | Exploit attempts logged |
| `REPORTING` | Generate findings report | VULN_ANALYSIS or EXPLOITATION complete | Report generated |
| `COMPLETE` | Assessment finished | REPORTING complete | N/A (terminal state) |

### State Transition Diagram (ASCII)

```
                            +---------+
                            |  ERROR  |
                            +---------+
                                 ^
                                 | (any phase can error)
                                 |
+------+   validate   +-------+   scan    +-----------+   enumerate   +-------------+
| INIT |------------->| RECON |---------->| PORT_SCAN |-------------->| ENUMERATION |
+------+              +-------+           +-----------+               +-------------+
   ^                                                                         |
   | resume                                                                  | analyze
   |                                                                         v
+----------+   finalize   +-----------+   report   +---------------+
| COMPLETE |<-------------| REPORTING |<-----------| VULN_ANALYSIS |
+----------+              +-----------+            +---------------+
                                ^                         |
                                |                         | exploit (training_mode=true)
                                |                         v
                                |                  +---------------+
                                +------------------| EXPLOITATION  |
                                                   +---------------+
```

### State Transition Rules

```python
VALID_TRANSITIONS = {
    "INIT": ["RECON", "ERROR"],
    "RECON": ["PORT_SCAN", "ERROR", "INIT"],  # Can go back to INIT
    "PORT_SCAN": ["ENUMERATION", "ERROR", "RECON"],
    "ENUMERATION": ["VULN_ANALYSIS", "ERROR", "PORT_SCAN"],
    "VULN_ANALYSIS": ["EXPLOITATION", "REPORTING", "ERROR", "ENUMERATION"],
    "EXPLOITATION": ["REPORTING", "ERROR", "VULN_ANALYSIS"],
    "REPORTING": ["COMPLETE", "ERROR"],
    "COMPLETE": [],  # Terminal state
    "ERROR": ["INIT", "RECON", "PORT_SCAN", "ENUMERATION",
              "VULN_ANALYSIS", "EXPLOITATION", "REPORTING"],  # Can recover
}
```

### Phase Actions

Each phase has defined actions and outputs:

```python
PHASE_ACTIONS = {
    "INIT": {
        "actions": ["define_target", "set_scope", "confirm_authorization"],
        "outputs": ["assessment_id", "target_network", "scope_definition"],
        "required_inputs": ["target_cidr_or_ip", "assessment_name"],
    },
    "RECON": {
        "actions": ["dns_lookup", "whois_query", "subdomain_enum", "osint_gather"],
        "outputs": ["dns_records", "domain_info", "subdomains", "osint_findings"],
        "required_inputs": ["target_domain"],
    },
    "PORT_SCAN": {
        "actions": ["tcp_scan", "udp_scan", "top_ports_scan", "full_scan"],
        "outputs": ["open_ports", "filtered_ports", "host_discovery"],
        "required_inputs": ["target_hosts"],
    },
    "ENUMERATION": {
        "actions": ["service_detection", "version_scan", "os_detection", "script_scan"],
        "outputs": ["services", "versions", "os_info", "banners"],
        "required_inputs": ["open_ports", "target_hosts"],
    },
    "VULN_ANALYSIS": {
        "actions": ["vuln_scan", "cve_lookup", "exploit_db_check", "nuclei_scan"],
        "outputs": ["vulnerabilities", "cve_list", "severity_ratings"],
        "required_inputs": ["services", "versions"],
    },
    "EXPLOITATION": {
        "actions": ["exploit_test", "payload_delivery", "privilege_escalation"],
        "outputs": ["exploit_attempts", "successful_exploits", "access_levels"],
        "required_inputs": ["vulnerabilities", "training_mode=true"],
        "safety_requirements": ["training_mode_enabled", "isolated_network"],
    },
    "REPORTING": {
        "actions": ["generate_report", "export_findings", "create_summary"],
        "outputs": ["report_path", "executive_summary", "technical_details"],
        "required_inputs": ["all_findings"],
    },
}
```

---

## Redis Storage Schema

### Database Allocation

- **DB 7 (workflows)**: Assessment workflow state, phase history, pending actions
- **DB 9 (memory)**: Security entities (hosts, services, vulnerabilities)

### Key Structure

```
# Assessment workflow state
workflow:assessment:{assessment_id}              # Main assessment document
workflow:assessment:{assessment_id}:phases       # Phase history list
workflow:assessment:{assessment_id}:actions      # Pending/completed actions
workflow:assessment:{assessment_id}:findings     # Quick findings index

# Assessment indexes
workflow:assessments:active                      # Set of active assessment IDs
workflow:assessments:by_target:{target_hash}     # Assessments for target
workflow:assessments:by_user:{user_id}           # User's assessments
```

### Assessment Document Schema (RedisJSON)

```json
{
  "id": "uuid-v4",
  "name": "Target Corp Security Assessment",
  "target": {
    "type": "network|host|domain",
    "value": "192.168.1.0/24",
    "scope": ["192.168.1.0/24"],
    "exclusions": ["192.168.1.1"]
  },
  "state": {
    "current_phase": "ENUMERATION",
    "previous_phase": "PORT_SCAN",
    "phase_started_at": 1735500000000,
    "error": null,
    "error_count": 0
  },
  "config": {
    "training_mode": false,
    "aggressive_scanning": false,
    "scan_timing": "T3",
    "max_concurrent_hosts": 10
  },
  "metadata": {
    "created_at": 1735400000000,
    "updated_at": 1735500000000,
    "created_by": "user_session_id",
    "chat_session_id": "chat_session_uuid",
    "version": 1
  },
  "statistics": {
    "hosts_discovered": 15,
    "open_ports": 47,
    "services_identified": 32,
    "vulnerabilities_found": 8,
    "critical_vulns": 2,
    "high_vulns": 3
  },
  "memory_entities": {
    "assessment_entity_id": "memory-entity-uuid",
    "network_entity_ids": ["uuid1", "uuid2"],
    "host_entity_ids": ["uuid3", "uuid4"]
  }
}
```

### Phase History Schema

```json
{
  "phase": "PORT_SCAN",
  "started_at": 1735450000000,
  "completed_at": 1735451000000,
  "duration_ms": 1000000,
  "status": "completed",
  "actions_completed": ["tcp_scan", "top_ports_scan"],
  "actions_skipped": ["udp_scan"],
  "findings_count": 47,
  "error": null,
  "tool_outputs": [
    {
      "tool": "nmap",
      "command": "nmap -sS -p- 192.168.1.0/24",
      "output_key": "workflow:output:{assessment_id}:{output_id}",
      "parsed": true
    }
  ]
}
```

### Tool Output Storage

Large tool outputs stored separately with TTL:

```
workflow:output:{assessment_id}:{output_id}     # Raw output (TTL: 7 days)
workflow:parsed:{assessment_id}:{output_id}     # Parsed structured data
```

---

## Entity Schema for Memory MCP

### Entity Type Hierarchy

```
security_assessment (root)
    |
    +-- target_network (CIDR range)
    |       |
    |       +-- target_host (IP address)
    |               |
    |               +-- service (port + service)
    |                       |
    |                       +-- vulnerability (CVE, severity)
    |                               |
    |                               +-- exploit_attempt (training mode)
    |
    +-- finding (general observation)
```

### Entity Type Definitions

#### security_assessment

```python
SECURITY_ASSESSMENT_ENTITY = {
    "entityType": "security_assessment",
    "name": "Assessment: {assessment_name}",
    "observations": [
        "Assessment ID: {assessment_id}",
        "Target: {target_value}",
        "Started: {start_date}",
        "Current Phase: {current_phase}",
        "Status: {status}",
    ],
    "metadata": {
        "assessment_id": "uuid",
        "target_type": "network|host|domain",
        "target_value": "192.168.1.0/24",
        "training_mode": False,
        "tags": ["security", "assessment", "pentest"],
        "priority": "high",
        "status": "active|completed|error",
    },
}
```

#### target_network

```python
TARGET_NETWORK_ENTITY = {
    "entityType": "target_network",
    "name": "Network: {cidr}",
    "observations": [
        "CIDR: {cidr}",
        "Netmask: {netmask}",
        "Host Range: {first_ip} - {last_ip}",
        "Usable Hosts: {host_count}",
        "Discovered Hosts: {discovered_count}",
    ],
    "metadata": {
        "cidr": "192.168.1.0/24",
        "network_address": "192.168.1.0",
        "broadcast_address": "192.168.1.255",
        "host_count": 254,
        "assessment_id": "parent-assessment-uuid",
        "tags": ["network", "internal"],
    },
}
```

#### target_host

```python
TARGET_HOST_ENTITY = {
    "entityType": "target_host",
    "name": "Host: {ip_address}",
    "observations": [
        "IP Address: {ip_address}",
        "Hostname: {hostname}",
        "OS: {os_detection}",
        "Open Ports: {open_port_count}",
        "Services: {service_list}",
        "Risk Level: {risk_level}",
    ],
    "metadata": {
        "ip_address": "192.168.1.100",
        "hostname": "webserver.internal",
        "mac_address": "00:11:22:33:44:55",
        "os_family": "Linux",
        "os_version": "Ubuntu 22.04",
        "open_ports": [22, 80, 443, 3306],
        "risk_level": "high|medium|low",
        "assessment_id": "parent-assessment-uuid",
        "network_id": "parent-network-uuid",
        "tags": ["host", "linux", "webserver"],
    },
}
```

#### service

```python
SERVICE_ENTITY = {
    "entityType": "service",
    "name": "Service: {service_name} on {ip}:{port}",
    "observations": [
        "Port: {port}/{protocol}",
        "Service: {service_name}",
        "Version: {version}",
        "Product: {product}",
        "Banner: {banner}",
        "State: {state}",
    ],
    "metadata": {
        "port": 443,
        "protocol": "tcp",
        "service_name": "https",
        "product": "nginx",
        "version": "1.24.0",
        "extrainfo": "Ubuntu",
        "banner": "nginx/1.24.0",
        "state": "open",
        "host_id": "parent-host-uuid",
        "assessment_id": "root-assessment-uuid",
        "tags": ["service", "web", "https"],
    },
}
```

#### vulnerability

```python
VULNERABILITY_ENTITY = {
    "entityType": "vulnerability",
    "name": "Vuln: {cve_id} - {title}",
    "observations": [
        "CVE: {cve_id}",
        "Title: {title}",
        "Severity: {severity} (CVSS: {cvss_score})",
        "Affected: {affected_component}",
        "Description: {description}",
        "Remediation: {remediation}",
        "References: {references}",
    ],
    "metadata": {
        "cve_id": "CVE-2024-12345",
        "title": "Remote Code Execution in nginx",
        "severity": "critical|high|medium|low|info",
        "cvss_score": 9.8,
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cwe_id": "CWE-78",
        "affected_versions": ["1.24.0", "1.24.1"],
        "exploit_available": True,
        "exploitability": "easy|moderate|difficult",
        "service_id": "parent-service-uuid",
        "host_id": "grandparent-host-uuid",
        "assessment_id": "root-assessment-uuid",
        "tags": ["vulnerability", "critical", "rce"],
    },
}
```

#### exploit_attempt

```python
EXPLOIT_ATTEMPT_ENTITY = {
    "entityType": "exploit_attempt",
    "name": "Exploit: {exploit_name} against {target}",
    "observations": [
        "Exploit: {exploit_name}",
        "Target: {target_service}",
        "Result: {result}",
        "Access Gained: {access_level}",
        "Timestamp: {timestamp}",
        "Notes: {notes}",
    ],
    "metadata": {
        "exploit_module": "exploit/unix/webapp/nginx_rce",
        "target_vulnerability": "CVE-2024-12345",
        "result": "success|failed|error",
        "access_level": "none|user|root|system",
        "payload": "reverse_shell",
        "training_mode": True,  # MUST be True
        "vulnerability_id": "parent-vuln-uuid",
        "assessment_id": "root-assessment-uuid",
        "tags": ["exploit", "training", "success"],
    },
}
```

#### finding

```python
FINDING_ENTITY = {
    "entityType": "finding",
    "name": "Finding: {title}",
    "observations": [
        "Category: {category}",
        "Description: {description}",
        "Impact: {impact}",
        "Recommendation: {recommendation}",
        "Evidence: {evidence}",
    ],
    "metadata": {
        "category": "misconfiguration|information_disclosure|weak_auth",
        "severity": "high|medium|low|info",
        "affected_components": ["192.168.1.100:443"],
        "assessment_id": "root-assessment-uuid",
        "phase": "ENUMERATION",
        "tags": ["finding", "misconfiguration"],
    },
}
```

### Relationship Types

```python
RELATIONSHIP_TYPES = {
    # Hierarchical containment
    "contains": {
        "description": "Parent contains child",
        "valid_pairs": [
            ("security_assessment", "target_network"),
            ("security_assessment", "finding"),
            ("target_network", "target_host"),
            ("target_host", "service"),
            ("service", "vulnerability"),
        ],
    },

    # Service relationships
    "runs": {
        "description": "Host runs service",
        "valid_pairs": [("target_host", "service")],
    },

    # Vulnerability relationships
    "has_vulnerability": {
        "description": "Service has vulnerability",
        "valid_pairs": [("service", "vulnerability")],
    },

    # Exploitation relationships
    "exploited_by": {
        "description": "Vulnerability exploited by attempt",
        "valid_pairs": [("vulnerability", "exploit_attempt")],
    },
    "targets": {
        "description": "Exploit attempt targets service",
        "valid_pairs": [("exploit_attempt", "service")],
    },

    # Cross-references
    "related_to": {
        "description": "General relationship between any entities",
        "valid_pairs": "any",
    },
    "depends_on": {
        "description": "Entity depends on another",
        "valid_pairs": [
            ("vulnerability", "service"),  # Vuln depends on service version
            ("exploit_attempt", "vulnerability"),  # Exploit depends on vuln
        ],
    },
}
```

### Memory Graph Integration

```python
class SecurityMemoryGraph:
    """
    Extends AutoBotMemoryGraph with security-specific entity types
    and relationship validations.
    """

    # Additional entity types for security
    SECURITY_ENTITY_TYPES = {
        "security_assessment",
        "target_network",
        "target_host",
        "service",
        "vulnerability",
        "exploit_attempt",
        "finding",
    }

    # Combine with base entity types
    ENTITY_TYPES = AutoBotMemoryGraph.ENTITY_TYPES | SECURITY_ENTITY_TYPES

    # Additional relation types
    SECURITY_RELATION_TYPES = {
        "contains",
        "runs",
        "has_vulnerability",
        "exploited_by",
        "targets",
    }

    RELATION_TYPES = AutoBotMemoryGraph.RELATION_TYPES | SECURITY_RELATION_TYPES
```

---

## Tool Output Parser Interface

### Base Parser Architecture

```
+-------------------+
|  BaseToolParser   |  (Abstract Base Class)
+-------------------+
         |
         +------------------+------------------+------------------+
         |                  |                  |                  |
+----------------+  +----------------+  +----------------+  +----------------+
| NmapParser     |  | NucleiParser   |  | MasscanParser  |  | NiktoParser    |
+----------------+  +----------------+  +----------------+  +----------------+
         |                  |                  |                  |
         +------------------+------------------+------------------+
                            |
                   +-------------------+
                   | ParsedToolOutput  |  (Unified Output Format)
                   +-------------------+
```

### Base Parser Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class OutputFormat(Enum):
    """Supported tool output formats"""
    XML = "xml"
    JSON = "json"
    GREPABLE = "grepable"
    TEXT = "text"
    CSV = "csv"


@dataclass
class ParsedHost:
    """Unified host representation from tool output"""
    ip_address: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    os_family: Optional[str] = None
    os_version: Optional[str] = None
    status: str = "up"
    ports: List["ParsedPort"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedPort:
    """Unified port/service representation"""
    port: int
    protocol: str = "tcp"
    state: str = "open"
    service: Optional[str] = None
    product: Optional[str] = None
    version: Optional[str] = None
    extrainfo: Optional[str] = None
    cpe: Optional[str] = None
    scripts: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedVulnerability:
    """Unified vulnerability representation"""
    vuln_id: str  # CVE or tool-specific ID
    title: str
    severity: str
    cvss_score: Optional[float] = None
    description: Optional[str] = None
    affected_component: Optional[str] = None
    references: List[str] = field(default_factory=list)
    remediation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedToolOutput:
    """Unified output from any security tool"""
    tool_name: str
    tool_version: Optional[str]
    scan_time: int  # Unix timestamp ms
    scan_duration_ms: Optional[int]
    command: Optional[str]
    hosts: List[ParsedHost] = field(default_factory=list)
    vulnerabilities: List[ParsedVulnerability] = field(default_factory=list)
    raw_output: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseToolParser(ABC):
    """Abstract base class for security tool output parsers"""

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Tool name this parser handles"""
        pass

    @property
    @abstractmethod
    def supported_formats(self) -> List[OutputFormat]:
        """List of supported output formats"""
        pass

    @abstractmethod
    def parse(
        self,
        output: str,
        format: OutputFormat = OutputFormat.XML
    ) -> ParsedToolOutput:
        """
        Parse tool output into unified format.

        Args:
            output: Raw tool output string
            format: Output format to parse

        Returns:
            ParsedToolOutput with structured data

        Raises:
            ParseError: If output cannot be parsed
        """
        pass

    @abstractmethod
    def validate_output(self, output: str, format: OutputFormat) -> bool:
        """
        Validate that output is parseable.

        Args:
            output: Raw output to validate
            format: Expected format

        Returns:
            True if valid, False otherwise
        """
        pass

    def detect_format(self, output: str) -> Optional[OutputFormat]:
        """
        Auto-detect output format from content.

        Args:
            output: Raw output string

        Returns:
            Detected OutputFormat or None
        """
        output_start = output.strip()[:100].lower()

        if output_start.startswith("<?xml") or "<nmaprun" in output_start:
            return OutputFormat.XML
        if output_start.startswith("{") or output_start.startswith("["):
            return OutputFormat.JSON
        if output_start.startswith("host:") or "# nmap" in output_start:
            return OutputFormat.GREPABLE

        return OutputFormat.TEXT
```

### Nmap Parser Implementation

```python
import xml.etree.ElementTree as ET
from datetime import datetime
import re


class NmapParser(BaseToolParser):
    """Parser for nmap output in XML, grepable, and text formats"""

    @property
    def tool_name(self) -> str:
        return "nmap"

    @property
    def supported_formats(self) -> List[OutputFormat]:
        return [OutputFormat.XML, OutputFormat.GREPABLE, OutputFormat.TEXT]

    def parse(
        self,
        output: str,
        format: OutputFormat = OutputFormat.XML
    ) -> ParsedToolOutput:
        """Parse nmap output based on format"""
        if format == OutputFormat.XML:
            return self._parse_xml(output)
        elif format == OutputFormat.GREPABLE:
            return self._parse_grepable(output)
        elif format == OutputFormat.TEXT:
            return self._parse_text(output)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _parse_xml(self, xml_output: str) -> ParsedToolOutput:
        """Parse nmap XML output (-oX)"""
        root = ET.fromstring(xml_output)

        # Extract scan metadata
        scan_info = root.find("scaninfo")
        run_stats = root.find("runstats")

        result = ParsedToolOutput(
            tool_name="nmap",
            tool_version=root.get("version"),
            scan_time=int(root.get("start", "0")) * 1000,
            command=root.get("args"),
            hosts=[],
            metadata={
                "scan_type": scan_info.get("type") if scan_info is not None else None,
                "protocol": scan_info.get("protocol") if scan_info is not None else None,
            }
        )

        # Parse timing stats
        if run_stats is not None:
            finished = run_stats.find("finished")
            if finished is not None:
                elapsed = finished.get("elapsed")
                if elapsed:
                    result.scan_duration_ms = int(float(elapsed) * 1000)

        # Parse hosts
        for host_elem in root.findall("host"):
            host = self._parse_host_element(host_elem)
            if host:
                result.hosts.append(host)

        return result

    def _parse_host_element(self, host_elem: ET.Element) -> Optional[ParsedHost]:
        """Parse a single host element from nmap XML"""
        # Get status
        status = host_elem.find("status")
        if status is not None and status.get("state") != "up":
            return None

        # Get address
        addr_elem = host_elem.find("address[@addrtype='ipv4']")
        if addr_elem is None:
            addr_elem = host_elem.find("address[@addrtype='ipv6']")

        if addr_elem is None:
            return None

        host = ParsedHost(
            ip_address=addr_elem.get("addr"),
            status="up"
        )

        # Get MAC address
        mac_elem = host_elem.find("address[@addrtype='mac']")
        if mac_elem is not None:
            host.mac_address = mac_elem.get("addr")

        # Get hostname
        hostnames = host_elem.find("hostnames")
        if hostnames is not None:
            hostname_elem = hostnames.find("hostname")
            if hostname_elem is not None:
                host.hostname = hostname_elem.get("name")

        # Get OS detection
        os_elem = host_elem.find("os")
        if os_elem is not None:
            osmatch = os_elem.find("osmatch")
            if osmatch is not None:
                host.os_family = osmatch.get("name")
                osclass = osmatch.find("osclass")
                if osclass is not None:
                    host.os_version = osclass.get("osgen")

        # Parse ports
        ports_elem = host_elem.find("ports")
        if ports_elem is not None:
            for port_elem in ports_elem.findall("port"):
                port = self._parse_port_element(port_elem)
                if port:
                    host.ports.append(port)

        return host

    def _parse_port_element(self, port_elem: ET.Element) -> Optional[ParsedPort]:
        """Parse a single port element from nmap XML"""
        state_elem = port_elem.find("state")
        if state_elem is None or state_elem.get("state") != "open":
            return None

        port = ParsedPort(
            port=int(port_elem.get("portid")),
            protocol=port_elem.get("protocol", "tcp"),
            state="open"
        )

        # Get service info
        service_elem = port_elem.find("service")
        if service_elem is not None:
            port.service = service_elem.get("name")
            port.product = service_elem.get("product")
            port.version = service_elem.get("version")
            port.extrainfo = service_elem.get("extrainfo")

            # Get CPE
            cpe_elem = service_elem.find("cpe")
            if cpe_elem is not None and cpe_elem.text:
                port.cpe = cpe_elem.text

        # Parse script output
        for script_elem in port_elem.findall("script"):
            port.scripts.append({
                "id": script_elem.get("id"),
                "output": script_elem.get("output")
            })

        return port

    def _parse_grepable(self, greppable_output: str) -> ParsedToolOutput:
        """Parse nmap grepable output (-oG)"""
        result = ParsedToolOutput(
            tool_name="nmap",
            tool_version=None,
            scan_time=int(datetime.now().timestamp() * 1000),
            hosts=[]
        )

        for line in greppable_output.split("\n"):
            if not line.startswith("Host:"):
                continue

            # Parse: Host: 192.168.1.1 ()	Status: Up
            # Parse: Host: 192.168.1.1 ()	Ports: 22/open/tcp//ssh///, 80/open/tcp//http///
            parts = line.split("\t")

            # Extract IP
            host_match = re.match(r"Host:\s+(\S+)", parts[0])
            if not host_match:
                continue

            ip = host_match.group(1)
            host = ParsedHost(ip_address=ip)

            # Parse ports if present
            for part in parts[1:]:
                if part.startswith("Ports:"):
                    port_str = part[6:].strip()
                    for port_info in port_str.split(","):
                        port_info = port_info.strip()
                        if not port_info:
                            continue

                        # Format: port/state/protocol/owner/service/rpc_info/version
                        fields = port_info.split("/")
                        if len(fields) >= 3 and fields[1] == "open":
                            port = ParsedPort(
                                port=int(fields[0]),
                                state="open",
                                protocol=fields[2] if len(fields) > 2 else "tcp",
                                service=fields[4] if len(fields) > 4 else None,
                            )
                            host.ports.append(port)

            result.hosts.append(host)

        return result

    def _parse_text(self, text_output: str) -> ParsedToolOutput:
        """Parse nmap normal text output"""
        result = ParsedToolOutput(
            tool_name="nmap",
            tool_version=None,
            scan_time=int(datetime.now().timestamp() * 1000),
            hosts=[],
            raw_output=text_output
        )

        current_host = None

        for line in text_output.split("\n"):
            line = line.strip()

            # Detect host
            if line.startswith("Nmap scan report for"):
                if current_host:
                    result.hosts.append(current_host)

                # Extract IP from "Nmap scan report for hostname (192.168.1.1)"
                # or "Nmap scan report for 192.168.1.1"
                ip_match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line)
                if ip_match:
                    ip = ip_match.group(1)
                else:
                    ip_match = re.search(r"for\s+(\d+\.\d+\.\d+\.\d+)", line)
                    ip = ip_match.group(1) if ip_match else None

                if ip:
                    current_host = ParsedHost(ip_address=ip)

            # Detect open port
            elif current_host and "/tcp" in line or "/udp" in line:
                port_match = re.match(
                    r"(\d+)/(tcp|udp)\s+(\w+)\s+(.+)?",
                    line
                )
                if port_match and port_match.group(3) == "open":
                    port = ParsedPort(
                        port=int(port_match.group(1)),
                        protocol=port_match.group(2),
                        state="open",
                        service=port_match.group(4).strip() if port_match.group(4) else None
                    )
                    current_host.ports.append(port)

        if current_host:
            result.hosts.append(current_host)

        return result

    def validate_output(self, output: str, format: OutputFormat) -> bool:
        """Validate nmap output format"""
        if format == OutputFormat.XML:
            try:
                root = ET.fromstring(output)
                return root.tag == "nmaprun"
            except ET.ParseError:
                return False
        elif format == OutputFormat.GREPABLE:
            return "Host:" in output
        elif format == OutputFormat.TEXT:
            return "Nmap scan report" in output or "Starting Nmap" in output

        return False
```

### Parser Registry

```python
class ParserRegistry:
    """Registry for tool output parsers"""

    _parsers: Dict[str, BaseToolParser] = {}

    @classmethod
    def register(cls, parser: BaseToolParser):
        """Register a parser for a tool"""
        cls._parsers[parser.tool_name.lower()] = parser

    @classmethod
    def get_parser(cls, tool_name: str) -> Optional[BaseToolParser]:
        """Get parser for a specific tool"""
        return cls._parsers.get(tool_name.lower())

    @classmethod
    def parse_output(
        cls,
        tool_name: str,
        output: str,
        format: Optional[OutputFormat] = None
    ) -> ParsedToolOutput:
        """
        Parse tool output using appropriate parser.

        Args:
            tool_name: Name of the tool (e.g., "nmap")
            output: Raw tool output
            format: Output format (auto-detected if None)

        Returns:
            ParsedToolOutput with structured data

        Raises:
            ValueError: If no parser available for tool
        """
        parser = cls.get_parser(tool_name)
        if not parser:
            raise ValueError(f"No parser registered for tool: {tool_name}")

        if format is None:
            format = parser.detect_format(output)
            if format is None:
                format = OutputFormat.TEXT

        return parser.parse(output, format)


# Register default parsers
ParserRegistry.register(NmapParser())
# ParserRegistry.register(NucleiParser())  # Future
# ParserRegistry.register(MasscanParser())  # Future
```

---

## API Endpoint Design

### Router Configuration

```python
# File: backend/api/security_assessment.py

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, WebSocket
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

router = APIRouter(prefix="/api/security", tags=["security-assessment"])
```

### Request/Response Models

```python
# ============== Request Models ==============

class AssessmentCreateRequest(BaseModel):
    """Create a new security assessment"""
    name: str = Field(..., min_length=1, max_length=200)
    target_type: str = Field(..., pattern="^(network|host|domain)$")
    target_value: str = Field(..., description="CIDR, IP, or domain")
    scope: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    training_mode: bool = Field(default=False)
    config: Optional[dict] = Field(default_factory=dict)


class PhaseTransitionRequest(BaseModel):
    """Request to transition assessment to a new phase"""
    target_phase: str = Field(..., description="Target phase to transition to")
    force: bool = Field(default=False, description="Force transition even if incomplete")


class ActionExecuteRequest(BaseModel):
    """Execute an action within the current phase"""
    action: str = Field(..., description="Action name to execute")
    parameters: Optional[dict] = Field(default_factory=dict)


class ToolOutputSubmitRequest(BaseModel):
    """Submit tool output for parsing and storage"""
    tool_name: str = Field(...)
    output: str = Field(...)
    format: Optional[str] = Field(default=None)
    command: Optional[str] = Field(default=None)


# ============== Response Models ==============

class AssessmentResponse(BaseModel):
    """Assessment details response"""
    id: str
    name: str
    target: dict
    state: dict
    config: dict
    metadata: dict
    statistics: dict


class PhaseHistoryResponse(BaseModel):
    """Phase history entry"""
    phase: str
    started_at: int
    completed_at: Optional[int]
    status: str
    actions_completed: List[str]
    findings_count: int


class FindingResponse(BaseModel):
    """Security finding"""
    id: str
    type: str  # host, service, vulnerability, finding
    title: str
    severity: str
    data: dict
```

### RESTful Endpoints

```python
# ============== Assessment CRUD ==============

@router.post("/assessments", status_code=201)
async def create_assessment(
    request: AssessmentCreateRequest,
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Create a new security assessment.

    Initializes assessment in INIT phase with target validation.
    Creates root entity in Memory MCP.
    """
    pass


@router.get("/assessments")
async def list_assessments(
    status: Optional[str] = Query(None, pattern="^(active|completed|error|all)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """List all assessments with optional filtering."""
    pass


@router.get("/assessments/{assessment_id}")
async def get_assessment(
    assessment_id: str = Path(...),
    include_findings: bool = Query(False),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Get assessment details by ID."""
    pass


@router.delete("/assessments/{assessment_id}")
async def delete_assessment(
    assessment_id: str = Path(...),
    cascade: bool = Query(True, description="Delete related Memory entities"),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Delete an assessment and optionally related entities."""
    pass


# ============== Phase Management ==============

@router.get("/assessments/{assessment_id}/phase")
async def get_current_phase(
    assessment_id: str = Path(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Get current phase details including available actions."""
    pass


@router.post("/assessments/{assessment_id}/phase/transition")
async def transition_phase(
    assessment_id: str = Path(...),
    request: PhaseTransitionRequest = Body(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Transition assessment to a new phase.

    Validates transition rules and phase completion requirements.
    """
    pass


@router.get("/assessments/{assessment_id}/phases/history")
async def get_phase_history(
    assessment_id: str = Path(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Get complete phase transition history."""
    pass


# ============== Action Execution ==============

@router.get("/assessments/{assessment_id}/actions")
async def get_available_actions(
    assessment_id: str = Path(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Get available actions for current phase."""
    pass


@router.post("/assessments/{assessment_id}/actions/execute")
async def execute_action(
    assessment_id: str = Path(...),
    request: ActionExecuteRequest = Body(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Execute an action within the current phase.

    Returns action result and any findings generated.
    """
    pass


# ============== Tool Output ==============

@router.post("/assessments/{assessment_id}/tools/output")
async def submit_tool_output(
    assessment_id: str = Path(...),
    request: ToolOutputSubmitRequest = Body(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Submit tool output for parsing.

    Parses output, creates Memory entities, updates statistics.
    """
    pass


@router.get("/assessments/{assessment_id}/tools/outputs")
async def list_tool_outputs(
    assessment_id: str = Path(...),
    tool: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """List all tool outputs for an assessment."""
    pass


# ============== Findings ==============

@router.get("/assessments/{assessment_id}/findings")
async def list_findings(
    assessment_id: str = Path(...),
    type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """List all findings with filtering."""
    pass


@router.get("/assessments/{assessment_id}/findings/{finding_id}")
async def get_finding(
    assessment_id: str = Path(...),
    finding_id: str = Path(...),
    include_relations: bool = Query(True),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Get finding details from Memory MCP."""
    pass


# ============== Reporting ==============

@router.post("/assessments/{assessment_id}/report/generate")
async def generate_report(
    assessment_id: str = Path(...),
    format: str = Query("markdown", pattern="^(markdown|html|json|pdf)$"),
    include_evidence: bool = Query(True),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Generate assessment report."""
    pass


@router.get("/assessments/{assessment_id}/report")
async def get_report(
    assessment_id: str = Path(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Get generated report if available."""
    pass


# ============== Resume/Recovery ==============

@router.post("/assessments/{assessment_id}/resume")
async def resume_assessment(
    assessment_id: str = Path(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """
    Resume a paused or errored assessment.

    Re-establishes chat session binding and returns current state.
    """
    pass


@router.post("/assessments/{assessment_id}/recover")
async def recover_from_error(
    assessment_id: str = Path(...),
    target_phase: Optional[str] = Query(None),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Recover from error state to specified phase."""
    pass
```

### WebSocket Endpoint for Real-time Updates

```python
@router.websocket("/assessments/{assessment_id}/ws")
async def assessment_websocket(
    websocket: WebSocket,
    assessment_id: str = Path(...),
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
):
    """
    WebSocket for real-time assessment updates.

    Sends:
    - Phase transitions
    - Action progress
    - Finding discoveries
    - Error notifications

    Message format:
    {
        "type": "phase_change|action_progress|finding|error|stats_update",
        "timestamp": 1735500000000,
        "data": {...}
    }
    """
    await websocket.accept()

    try:
        # Subscribe to assessment events
        async for event in manager.subscribe_events(assessment_id):
            await websocket.send_json(event)
    except Exception as e:
        await websocket.close(code=1011, reason=str(e))
```

### Health Check Endpoint

```python
@router.get("/health")
async def security_health_check(
    manager: SecurityWorkflowManager = Depends(get_workflow_manager),
) -> JSONResponse:
    """Health check for security assessment subsystem."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "workflow_manager": "healthy" if manager.initialized else "unavailable",
                "redis_workflows": "healthy",  # Check DB 7
                "redis_memory": "healthy",     # Check DB 9
                "parser_registry": f"{len(ParserRegistry._parsers)} parsers registered",
            },
            "active_assessments": await manager.get_active_count(),
        }
    )
```

---

## Chat Integration Points

### Agent Detection of Tool Output

The chat agent needs to detect when security tool output is present in messages:

```python
class SecurityToolOutputDetector:
    """
    Detects security tool output in chat messages.

    Integrates with ChatWorkflowManager to parse and store outputs.
    """

    # Tool output signatures
    TOOL_SIGNATURES = {
        "nmap": [
            r"Starting Nmap \d+\.\d+",
            r"Nmap scan report for",
            r"<\?xml.*nmaprun",
            r"^Host:\s+\d+\.\d+\.\d+\.\d+",
        ],
        "masscan": [
            r"Starting masscan \d+\.\d+",
            r"Discovered open port",
        ],
        "nuclei": [
            r"\[INF\].*nuclei",
            r"^\[.*\] \[.*\] \[.*\]",  # [severity] [template-id] [protocol]
        ],
        "nikto": [
            r"- Nikto v\d+\.\d+",
            r"\+ Target IP:",
        ],
    }

    def detect_tool_output(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if message contains security tool output.

        Returns:
            Dict with tool_name and confidence, or None if not detected
        """
        for tool_name, patterns in self.TOOL_SIGNATURES.items():
            for pattern in patterns:
                if re.search(pattern, message, re.MULTILINE | re.IGNORECASE):
                    return {
                        "tool_name": tool_name,
                        "confidence": 0.9,
                        "pattern_matched": pattern,
                    }
        return None

    def extract_tool_output(
        self,
        message: str,
        tool_name: str
    ) -> Optional[str]:
        """
        Extract the actual tool output from a message.

        Handles cases where output is embedded in markdown code blocks
        or mixed with other text.
        """
        # Try to extract from code block first
        code_block_pattern = r"```(?:bash|text|xml|json)?\n(.*?)```"
        matches = re.findall(code_block_pattern, message, re.DOTALL)

        for match in matches:
            if self.detect_tool_output(match):
                return match.strip()

        # If no code block, return the full message
        return message
```

### Chat Workflow Integration

```python
class SecurityAwareChatWorkflow:
    """
    Extends ChatWorkflowManager with security assessment awareness.

    Automatically:
    - Detects active assessments for chat session
    - Parses tool output from messages
    - Updates assessment state based on conversation
    - Provides assessment context to LLM
    """

    def __init__(self, base_workflow: ChatWorkflowManager):
        self.base_workflow = base_workflow
        self.detector = SecurityToolOutputDetector()
        self.assessment_manager = None  # Lazy init

    async def get_assessment_context(self, session_id: str) -> Optional[str]:
        """
        Get assessment context for LLM prompt enhancement.

        Returns context string if session has active assessment.
        """
        manager = await self._get_manager()
        assessment = await manager.get_assessment_for_session(session_id)

        if not assessment:
            return None

        return f"""
**Active Security Assessment:**
- Name: {assessment['name']}
- Target: {assessment['target']['value']}
- Current Phase: {assessment['state']['current_phase']}
- Findings: {assessment['statistics']['vulnerabilities_found']} vulnerabilities

Available actions for current phase:
{self._format_available_actions(assessment['state']['current_phase'])}

To execute an action, use: /security action <action_name>
To transition phases, use: /security phase <phase_name>
To view findings, use: /security findings
"""

    async def process_message_with_security(
        self,
        session_id: str,
        message: str,
        context: Optional[Dict] = None,
    ):
        """
        Process message with security assessment awareness.

        1. Check for tool output and parse if found
        2. Check for assessment commands
        3. Add assessment context to LLM prompt
        4. Delegate to base workflow
        """
        manager = await self._get_manager()

        # Check for tool output
        detection = self.detector.detect_tool_output(message)
        if detection:
            assessment = await manager.get_assessment_for_session(session_id)
            if assessment:
                # Parse and store tool output
                tool_output = self.detector.extract_tool_output(
                    message,
                    detection['tool_name']
                )

                parse_result = await manager.submit_tool_output(
                    assessment_id=assessment['id'],
                    tool_name=detection['tool_name'],
                    output=tool_output,
                )

                # Yield parsing result message
                yield WorkflowMessage(
                    type="security_tool_parsed",
                    content=f"Parsed {detection['tool_name']} output: "
                            f"{parse_result['hosts_found']} hosts, "
                            f"{parse_result['services_found']} services found",
                    metadata=parse_result,
                )

        # Enhance context with assessment info
        assessment_context = await self.get_assessment_context(session_id)
        if assessment_context:
            context = context or {}
            context['security_assessment_context'] = assessment_context

        # Delegate to base workflow
        async for msg in self.base_workflow.process_message_stream(
            session_id,
            message,
            context
        ):
            yield msg
```

### Slash Commands for Security

```python
# Extend SlashCommandHandler with security commands

SECURITY_COMMANDS = {
    "/security": {
        "description": "Security assessment commands",
        "subcommands": {
            "new": "Create new assessment: /security new <name> <target>",
            "status": "Show current assessment status",
            "phase": "Transition phase: /security phase <phase_name>",
            "action": "Execute action: /security action <action_name>",
            "findings": "List findings: /security findings [severity]",
            "resume": "Resume paused assessment",
            "report": "Generate report: /security report [format]",
        },
    },
    "/scan": {
        "description": "Quick scan shortcuts",
        "subcommands": {
            "ports": "Port scan: /scan ports <target>",
            "services": "Service detection: /scan services <target>",
            "vuln": "Vulnerability scan: /scan vuln <target>",
        },
    },
}


class SecuritySlashCommandHandler:
    """Handler for security-related slash commands"""

    async def handle_security_command(
        self,
        command: str,
        args: List[str],
        session_id: str,
    ) -> SlashCommandResult:
        """Handle /security commands"""
        if not args:
            return self._show_security_help()

        subcommand = args[0].lower()

        if subcommand == "new":
            return await self._create_assessment(args[1:], session_id)
        elif subcommand == "status":
            return await self._show_status(session_id)
        elif subcommand == "phase":
            return await self._transition_phase(args[1:], session_id)
        elif subcommand == "action":
            return await self._execute_action(args[1:], session_id)
        elif subcommand == "findings":
            return await self._list_findings(args[1:], session_id)
        elif subcommand == "resume":
            return await self._resume_assessment(session_id)
        elif subcommand == "report":
            return await self._generate_report(args[1:], session_id)
        else:
            return SlashCommandResult(
                success=False,
                content=f"Unknown subcommand: {subcommand}",
            )
```

### Resume Capability

```python
class AssessmentResumeHandler:
    """
    Handles resuming assessments across sessions.

    Features:
    - Auto-detect abandoned assessments
    - Offer resume on new session start
    - Rebuild context from Memory MCP
    """

    async def check_for_resumable(self, user_id: str) -> List[Dict]:
        """Check for assessments that can be resumed"""
        manager = await self._get_manager()

        # Find active/paused assessments for user
        assessments = await manager.list_assessments(
            status="active",
            created_by=user_id,
        )

        resumable = []
        for assessment in assessments:
            # Check if assessment is truly active (not stale)
            last_activity = assessment['metadata'].get('updated_at', 0)
            age_hours = (time.time() * 1000 - last_activity) / 3600000

            if age_hours < 168:  # Less than 1 week old
                resumable.append({
                    "id": assessment['id'],
                    "name": assessment['name'],
                    "phase": assessment['state']['current_phase'],
                    "target": assessment['target']['value'],
                    "last_activity": last_activity,
                    "age_hours": age_hours,
                })

        return resumable

    async def resume_assessment(
        self,
        assessment_id: str,
        session_id: str,
    ) -> Dict:
        """
        Resume an assessment in a new chat session.

        1. Load assessment state from Redis
        2. Rebuild context from Memory entities
        3. Bind to new chat session
        4. Return summary for user
        """
        manager = await self._get_manager()

        # Load assessment
        assessment = await manager.get_assessment(assessment_id)
        if not assessment:
            raise ValueError(f"Assessment not found: {assessment_id}")

        # Bind to new session
        await manager.bind_session(assessment_id, session_id)

        # Build resume summary
        summary = await self._build_resume_summary(assessment)

        return {
            "assessment": assessment,
            "summary": summary,
            "available_actions": PHASE_ACTIONS[assessment['state']['current_phase']]['actions'],
        }

    async def _build_resume_summary(self, assessment: Dict) -> str:
        """Build human-readable resume summary"""
        memory = await self._get_memory_graph()

        # Get key findings from Memory MCP
        findings = await memory.search_entities(
            query=f"assessment_id:{assessment['id']}",
            entity_type="vulnerability",
            limit=5,
        )

        summary = f"""
**Resuming Assessment: {assessment['name']}**

**Target:** {assessment['target']['value']}
**Current Phase:** {assessment['state']['current_phase']}
**Progress:**
- Hosts discovered: {assessment['statistics']['hosts_discovered']}
- Services found: {assessment['statistics']['services_identified']}
- Vulnerabilities: {assessment['statistics']['vulnerabilities_found']}
  - Critical: {assessment['statistics']['critical_vulns']}
  - High: {assessment['statistics']['high_vulns']}

**Recent Findings:**
"""
        for finding in findings[:3]:
            summary += f"- {finding['name']}\n"

        summary += f"""
**Next Steps:**
You can continue with the {assessment['state']['current_phase']} phase.
Available actions: {', '.join(PHASE_ACTIONS[assessment['state']['current_phase']]['actions'])}

Use `/security action <name>` to execute an action.
"""
        return summary
```

### LLM Context Enhancement

```python
# System prompt addition for security-aware conversations

SECURITY_ASSESSMENT_SYSTEM_PROMPT = """
## Security Assessment Mode

You are assisting with an active security assessment. Follow these guidelines:

### Current Assessment Context
{assessment_context}

### Guidelines
1. **Tool Output Detection**: When you see security tool output (nmap, nuclei, etc.),
   acknowledge it and note key findings.

2. **Phase Awareness**: Know what phase the assessment is in and suggest appropriate
   next steps.

3. **Finding Documentation**: When vulnerabilities are discovered, ensure they are
   properly documented with:
   - Severity rating
   - Affected component
   - Potential impact
   - Remediation suggestions

4. **Safety First**: For exploitation testing:
   - ONLY proceed if training_mode is enabled
   - Verify target is in authorized scope
   - Document all exploitation attempts

### Commands Available
- `/security status` - Show assessment status
- `/security action <name>` - Execute scanning action
- `/security findings` - List findings
- `/security phase <name>` - Move to next phase
- `/security report` - Generate report

### Phase Flow
INIT → RECON → PORT_SCAN → ENUMERATION → VULN_ANALYSIS → [EXPLOITATION] → REPORTING → COMPLETE
"""
```

---

## Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1-2)

**Files to Create:**
```
src/security/
├── __init__.py
├── workflow_manager.py          # SecurityWorkflowManager class
├── state_machine.py             # Phase definitions and transitions
├── memory_integration.py        # SecurityMemoryGraph extension
└── parsers/
    ├── __init__.py
    ├── base.py                  # BaseToolParser abstract class
    ├── nmap_parser.py           # NmapParser implementation
    └── registry.py              # ParserRegistry

backend/api/
└── security_assessment.py       # REST API endpoints
```

**Deliverables:**
- [ ] SecurityWorkflowManager with Redis storage
- [ ] State machine with validation
- [ ] NmapParser for XML/grepable/text formats
- [ ] Basic API endpoints (CRUD)
- [ ] Unit tests for parsers

### Phase 2: Memory Integration (Week 2-3)

**Files to Create/Modify:**
```
src/security/
├── entity_types.py              # Security entity type definitions
├── relationship_types.py        # Security relationship definitions
└── memory_integration.py        # Enhanced with entity creation

src/autobot_memory_graph.py      # Extend with security types (if needed)
```

**Deliverables:**
- [ ] Security entity types registered
- [ ] Automatic entity creation from parsed output
- [ ] Relationship management (contains, has_vulnerability, etc.)
- [ ] Search by assessment ID
- [ ] Integration tests

### Phase 3: Chat Integration (Week 3-4)

**Files to Create/Modify:**
```
src/security/
├── chat_integration.py          # SecurityAwareChatWorkflow
├── tool_detector.py             # SecurityToolOutputDetector
└── slash_commands.py            # Security slash command handlers

src/chat_workflow_manager.py     # Add security hooks
src/slash_command_handler.py     # Register security commands
```

**Deliverables:**
- [ ] Tool output detection in chat
- [ ] Automatic parsing and storage
- [ ] Slash commands (/security, /scan)
- [ ] LLM context enhancement
- [ ] Resume capability

### Phase 4: Reporting & Polish (Week 4-5)

**Files to Create:**
```
src/security/
├── report_generator.py          # Report generation (MD, HTML, JSON)
└── templates/
    ├── report_markdown.jinja2
    ├── report_html.jinja2
    └── executive_summary.jinja2

backend/api/
└── security_assessment.py       # Add WebSocket, reporting endpoints
```

**Deliverables:**
- [ ] Report generation (multiple formats)
- [ ] WebSocket real-time updates
- [ ] Error recovery mechanisms
- [ ] Documentation
- [ ] End-to-end integration tests

### Testing Strategy

```python
# Test categories

# Unit Tests
tests/unit/security/
├── test_state_machine.py        # Phase transition validation
├── test_nmap_parser.py          # Parser correctness
├── test_entity_creation.py      # Memory entity creation
└── test_tool_detection.py       # Tool output detection

# Integration Tests
tests/integration/security/
├── test_workflow_redis.py       # Redis storage operations
├── test_memory_integration.py   # Memory MCP integration
├── test_chat_integration.py     # Chat workflow integration
└── test_api_endpoints.py        # REST API functionality

# End-to-End Tests
tests/e2e/security/
├── test_full_assessment.py      # Complete assessment flow
└── test_resume_capability.py    # Resume across sessions
```

---

## Appendix

### A. Example Assessment Flow

```
User: /security new "Corp Network Audit" 192.168.1.0/24

AutoBot: Created assessment "Corp Network Audit" targeting 192.168.1.0/24
         Assessment ID: a1b2c3d4-...
         Current Phase: INIT

         To proceed, confirm the scope is authorized and run:
         /security phase recon

User: /security phase recon

AutoBot: Moving to RECON phase.
         Available actions:
         - dns_lookup: Query DNS records
         - whois_query: WHOIS lookup
         - subdomain_enum: Find subdomains

         Start with: /security action dns_lookup

User: nmap -sS -p- 192.168.1.0/24
[... nmap output ...]

AutoBot: [Parsed nmap output]
         - 15 hosts discovered
         - 47 open ports found
         - Key services: SSH(22), HTTP(80), HTTPS(443), MySQL(3306)

         Findings stored in assessment. View with /security findings

         Recommend: /security action service_detection for version info

User: /security findings

AutoBot: **Assessment Findings (15 hosts, 47 ports)**

         Critical Hosts:
         - 192.168.1.100: 12 open ports (HTTP, MySQL, SSH)
         - 192.168.1.105: 8 open ports (HTTPS, PostgreSQL)

         Interesting Services:
         - MySQL 5.7.42 on 192.168.1.100:3306
         - nginx 1.24.0 on 192.168.1.100:80
         ...
```

### B. Redis Key Examples

```bash
# List active assessments
redis-cli -n 7 SMEMBERS workflow:assessments:active

# Get assessment details
redis-cli -n 7 JSON.GET workflow:assessment:a1b2c3d4-...

# Get phase history
redis-cli -n 7 LRANGE workflow:assessment:a1b2c3d4-...:phases 0 -1

# Get Memory entities for assessment
redis-cli -n 9 FT.SEARCH memory_entity_idx "@assessment_id:{a1b2c3d4*}"
```

### C. Security Considerations

1. **Training Mode Enforcement**
   - Exploitation actions REQUIRE `training_mode=true`
   - Validated at state machine level, cannot be bypassed
   - All exploitation attempts logged with full audit trail

2. **Target Scope Validation**
   - Targets validated against authorized scope
   - Exclusions strictly enforced
   - External targets require explicit authorization

3. **Data Protection**
   - Sensitive findings encrypted at rest (if configured)
   - Tool outputs with credentials auto-redacted
   - Report access controlled by session ownership

4. **Audit Logging**
   - All phase transitions logged
   - All action executions logged
   - All findings modifications logged
   - Logs stored in Redis DB 10 (audit)

---

**Document Version History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-11-29 | mrveiss | Initial design document |
