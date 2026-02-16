# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Scanner Agent for AutoBot
Provides defensive security scanning and analysis capabilities
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from autobot_shared.http_client import get_http_client
from backend.constants.network_constants import NetworkConstants
from backend.constants.threshold_constants import TimingConstants
from backend.utils.agent_command_helpers import run_agent_command

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuples for constant scan types and targets
_SUPPORTED_SCAN_TYPES = (
    "port_scan",
    "service_detection",
    "vulnerability_scan",
    "ssl_scan",
    "dns_enum",
    "web_scan",
)
_ALLOWED_SCAN_TARGETS = (
    NetworkConstants.LOCALHOST_NAME,
    NetworkConstants.LOCALHOST_IP,
    NetworkConstants.LOCALHOST_IPV6,
)

# Issue #380: Module-level tuple for common subdomains in DNS enumeration
_COMMON_SUBDOMAINS = ("www", "mail", "ftp", "admin", "api", "dev", "test")

# Issue #380: Module-level tuple for DNS record types in enumeration
_DNS_RECORD_TYPES = ("A", "AAAA", "MX", "TXT", "NS", "SOA")


class SecurityScannerAgent:
    """Agent for performing defensive security scans and vulnerability assessments"""

    def __init__(self):
        """Initialize security scanner agent (Issue #380: use module-level constants)."""
        self.name = "security_scanner"
        self.description = (
            "Performs defensive security scans and vulnerability assessments"
        )
        self.supported_scan_types = _SUPPORTED_SCAN_TYPES

    def _get_scan_handlers(self) -> Dict[str, Any]:
        """Get scan type to handler mapping (Issue #334 - extracted helper)."""
        return {
            "port_scan": self._port_scan,
            "service_detection": self._service_detection,
            "vulnerability_scan": self._vulnerability_scan,
            "ssl_scan": self._ssl_scan,
            "dns_enum": self._dns_enumeration,
            "web_scan": self._web_scan,
        }

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a security scanning task"""
        try:
            scan_type = context.get("scan_type", "port_scan")
            target = context.get("target", "")

            if not target:
                return {
                    "status": "error",
                    "message": "No target specified for security scan",
                }

            if not self._validate_target(target):
                return {
                    "status": "error",
                    "message": "Target validation failed. Only authorized targets allowed.",
                }

            handlers = self._get_scan_handlers()
            handler = handlers.get(scan_type)

            if handler is None:
                return {
                    "status": "error",
                    "message": f"Unsupported scan type: {scan_type}",
                }

            return await handler(target, context)

        except Exception as e:
            logger.error("Security scan failed: %s", e)
            return {"status": "error", "message": f"Security scan failed: {str(e)}"}

    def _validate_target(self, target: str) -> bool:
        """Validate target is appropriate for scanning"""
        # Only allow scanning of:
        # 1. Localhost/loopback
        # 2. Private IP ranges (RFC1918)
        # 3. Explicitly authorized domains (would need config)
        # Issue #380: Use module-level constant for allowed targets

        # Check if target is in allowed list
        if target in _ALLOWED_SCAN_TARGETS:
            return True

        # Check if target is in private IP range
        import ipaddress

        try:
            ip = ipaddress.ip_address(target)
            if ip.is_private:
                return True
        except ValueError as e:
            # Not an IP address, could be hostname
            logger.debug("Not a valid IP address, treating as hostname: %s", e)

        # For production, you'd check against authorized domains here
        logger.warning("Target %s not in authorized list", target)
        return False

    async def _port_scan(self, target: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a port scan using available tools"""
        try:
            ports = context.get("ports", "1-1000")

            # Check if nmap is available, if not suggest alternatives
            nmap_available = await self._check_tool_availability("nmap")

            if not nmap_available:
                # Use research agent to find port scanning tools
                tool_research = await self._research_scanning_tools("port scanning")

                return {
                    "status": "tool_required",
                    "message": "Port scanning requires specialized tools",
                    "required_tools": tool_research.get("recommended_tools", ["nmap"]),
                    "research_results": tool_research,
                    "next_steps": [
                        "Install recommended scanning tools",
                        "Verify tool installation",
                        "Re-run port scan",
                    ],
                }

            # If nmap is available, proceed with scan
            scan_type = context.get("nmap_scan_type", "-sS")  # SYN scan by default
            cmd = ["nmap", scan_type, "-p", ports, target, "-oX", "-"]

            # Execute scan
            result = await run_agent_command(cmd)

            if result["status"] == "success":
                # Parse nmap output
                open_ports = self._parse_nmap_output(result["output"])

                return {
                    "status": "success",
                    "scan_type": "port_scan",
                    "target": target,
                    "open_ports": open_ports,
                    "scan_time": datetime.now().isoformat(),
                    "raw_output": result["output"],
                }
            else:
                return result

        except Exception as e:
            logger.error("Port scan failed: %s", e)
            return {"status": "error", "message": f"Port scan failed: {str(e)}"}

    async def _service_detection(
        self, target: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detect services running on open ports"""
        try:
            ports = context.get("ports", "1-1000")

            # Use nmap service detection
            cmd = ["nmap", "-sV", "-p", ports, target, "-oX", "-"]

            result = await run_agent_command(cmd)

            if result["status"] == "success":
                services = self._parse_nmap_services(result["output"])

                return {
                    "status": "success",
                    "scan_type": "service_detection",
                    "target": target,
                    "services": services,
                    "scan_time": datetime.now().isoformat(),
                }
            else:
                return result

        except Exception as e:
            logger.error("Service detection failed: %s", e)
            return {"status": "error", "message": f"Service detection failed: {str(e)}"}

    async def _vulnerability_scan(
        self, target: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform basic vulnerability scanning"""
        try:
            # For a real implementation, you might use:
            # - Nmap scripts (--script vuln)
            # - OpenVAS API
            # - Nuclei templates
            # - Custom vulnerability checks

            # Basic example using nmap vulnerability scripts
            cmd = ["nmap", "--script", "vuln", "-p-", target]

            result = await run_agent_command(
                cmd, timeout=TimingConstants.VERY_LONG_TIMEOUT
            )  # 5 minute timeout

            if result["status"] == "success":
                vulnerabilities = self._parse_vulnerabilities(result["output"])

                return {
                    "status": "success",
                    "scan_type": "vulnerability_scan",
                    "target": target,
                    "vulnerabilities": vulnerabilities,
                    "scan_time": datetime.now().isoformat(),
                }
            else:
                return result

        except Exception as e:
            logger.error("Vulnerability scan failed: %s", e)
            return {
                "status": "error",
                "message": f"Vulnerability scan failed: {str(e)}",
            }

    async def _ssl_scan(self, target: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Scan SSL/TLS configuration"""
        try:
            port = context.get("port", "443")

            # Use testssl.sh or sslscan if available
            # Fallback to nmap ssl scripts
            cmd = ["nmap", "--script", "ssl-*", "-p", str(port), target]

            result = await run_agent_command(cmd)

            if result["status"] == "success":
                ssl_info = self._parse_ssl_info(result["output"])

                return {
                    "status": "success",
                    "scan_type": "ssl_scan",
                    "target": target,
                    "port": port,
                    "ssl_info": ssl_info,
                    "scan_time": datetime.now().isoformat(),
                }
            else:
                return result

        except Exception as e:
            logger.error("SSL scan failed: %s", e)
            return {"status": "error", "message": f"SSL scan failed: {str(e)}"}

    async def _dns_enumeration(
        self, target: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform DNS enumeration"""
        try:
            # Use multiple tools for comprehensive enumeration
            results = {"domain": target, "dns_records": {}, "subdomains": []}

            # Get DNS records - Issue #380: use module constant
            for record_type in _DNS_RECORD_TYPES:
                cmd = ["dig", "+short", record_type, target]
                result = await run_agent_command(cmd)
                if result["status"] == "success" and result["output"].strip():
                    results["dns_records"][record_type] = (
                        result["output"].strip().split("\n")
                    )

            # Basic subdomain enumeration (Issue #380: use module constant)
            for subdomain in _COMMON_SUBDOMAINS:
                full_domain = f"{subdomain}.{target}"
                cmd = ["dig", "+short", "A", full_domain]
                result = await run_agent_command(cmd)
                if result["status"] == "success" and result["output"].strip():
                    results["subdomains"].append(
                        {"subdomain": full_domain, "ip": result["output"].strip()}
                    )

            return {
                "status": "success",
                "scan_type": "dns_enumeration",
                "results": results,
                "scan_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("DNS enumeration failed: %s", e)
            return {"status": "error", "message": f"DNS enumeration failed: {str(e)}"}

    async def _check_robots_txt(
        self, http_client, target: str, findings: List[Dict]
    ) -> None:
        """Check for robots.txt (Issue #334 - extracted helper)."""
        try:
            async with await http_client.get(f"{target}/robots.txt") as response:
                if response.status == 200:
                    findings.append(
                        {
                            "type": "info",
                            "path": "/robots.txt",
                            "message": "Robots.txt file found",
                        }
                    )
        except Exception as e:
            logger.debug("robots.txt not accessible: %s", e)

    async def _check_admin_path(
        self, http_client, target: str, path: str, findings: List[Dict]
    ) -> None:
        """Check single admin path (Issue #334 - extracted helper)."""
        try:
            async with await http_client.get(f"{target}{path}") as response:
                if response.status in (200, 301, 302):
                    findings.append(
                        {
                            "type": "warning",
                            "path": path,
                            "status": response.status,
                            "message": "Potentially sensitive path accessible",
                        }
                    )
        except Exception as e:
            logger.debug("Path check failed for %s: %s", path, e)

    async def _web_scan(self, target: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform basic web application scanning"""
        try:
            results = {"url": target, "findings": []}
            http_client = get_http_client()

            await self._check_robots_txt(http_client, target, results["findings"])

            admin_paths = ["/admin", "/login", "/wp-admin", "/.git", "/.env"]
            for path in admin_paths:
                await self._check_admin_path(
                    http_client, target, path, results["findings"]
                )

            return {
                "status": "success",
                "scan_type": "web_scan",
                "results": results,
                "scan_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Web scan failed: %s", e)
            return {"status": "error", "message": f"Web scan failed: {str(e)}"}

    # _run_command moved to src/utils/agent_command_helpers.py (Issue #292)
    # Use run_agent_command() directly

    def _parse_nmap_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse nmap XML output for open ports"""
        # For simplicity, doing basic text parsing
        # In production, use python-nmap or parse XML properly
        open_ports = []
        lines = output.split("\n")
        for line in lines:
            if "open" in line and "/tcp" in line:
                parts = line.split()
                if len(parts) >= 3:
                    port_info = {
                        "port": parts[0].split("/")[0],
                        "state": "open",
                        "service": parts[2] if len(parts) > 2 else "unknown",
                    }
                    open_ports.append(port_info)
        return open_ports

    def _parse_nmap_services(self, output: str) -> List[Dict[str, Any]]:
        """Parse nmap service detection output"""
        services = []
        lines = output.split("\n")
        for line in lines:
            if "open" in line and "/tcp" in line:
                parts = line.split()
                if len(parts) >= 3:
                    service_info = {
                        "port": parts[0].split("/")[0],
                        "service": parts[2],
                        "version": " ".join(parts[3:]) if len(parts) > 3 else "",
                    }
                    services.append(service_info)
        return services

    def _parse_vulnerabilities(self, output: str) -> List[Dict[str, Any]]:
        """Parse vulnerability scan output"""
        vulnerabilities = []
        # Basic parsing - in production, parse properly based on tool output
        if "VULNERABLE:" in output:
            vuln_sections = output.split("VULNERABLE:")
            for section in vuln_sections[1:]:
                lines = section.strip().split("\n")
                if lines:
                    vulnerabilities.append(
                        {
                            "vulnerability": lines[0].strip(),
                            "severity": "unknown",
                            "description": (
                                "\n".join(lines[1:3]) if len(lines) > 1 else ""
                            ),
                        }
                    )
        return vulnerabilities

    def _parse_ssl_info(self, output: str) -> Dict[str, Any]:
        """Parse SSL scan output"""
        ssl_info = {"protocols": [], "ciphers": [], "certificate": {}}

        # Basic parsing - in production, use proper SSL testing tools
        lines = output.split("\n")
        for line in lines:
            if "TLSv" in line or "SSLv" in line:
                ssl_info["protocols"].append(line.strip())
            elif "cipher" in line.lower():
                ssl_info["ciphers"].append(line.strip())

        return ssl_info

    async def _check_tool_availability(self, tool_name: str) -> bool:
        """Check if a security tool is available on the system"""
        try:
            result = await run_agent_command(["which", tool_name], timeout=5)
            return result["status"] == "success"
        except Exception as e:
            logger.debug("Tool availability check failed for %s: %s", tool_name, e)
            return False

    async def _research_scanning_tools(self, scan_type: str) -> Dict[str, Any]:
        """Use research agent to find appropriate scanning tools"""
        try:
            # Import research agent
            from agents.research_agent import ResearchAgent, ResearchRequest

            research_agent = ResearchAgent()
            query = f"{scan_type} tools for security assessment Kali Linux 2024"

            request = ResearchRequest(query=query, focus="tools")

            # Perform research
            research_result = await research_agent.research_specific_tools(request)

            # Extract tool recommendations
            tools_info = {
                "scan_type": scan_type,
                "recommended_tools": self._extract_tool_names(research_result.summary),
                "installation_info": research_result.summary,
                "research_summary": research_result.summary,
                "confidence": getattr(research_result, "confidence", 0.8),
                "sources": getattr(research_result, "sources", [])[:3],
            }

            return tools_info

        except Exception as e:
            logger.error("Tool research failed: %s", e)
            # Fallback with known tools
            return {
                "scan_type": scan_type,
                "recommended_tools": self._get_fallback_tools(scan_type),
                "installation_info": f"Please install {scan_type} tools manually",
                "research_summary": "Research failed, using fallback recommendations",
                "confidence": 0.5,
                "sources": [],
            }

    def _extract_tool_names(self, research_summary: str) -> List[str]:
        """Extract tool names from research summary"""
        # Common security tools for different scan types
        tool_patterns = {
            "nmap": ["nmap", "network mapper"],
            "masscan": ["masscan", "fast port scanner"],
            "zmap": ["zmap", "internet scanner"],
            "nikto": ["nikto", "web scanner"],
            "openvas": ["openvas", "vulnerability scanner"],
            "nessus": ["nessus", "vulnerability assessment"],
            "sqlmap": ["sqlmap", "sql injection"],
            "dirb": ["dirb", "directory buster"],
            "gobuster": ["gobuster", "directory brute force"],
            "hydra": ["hydra", "login cracker"],
            "john": ["john", "password cracker"],
            "hashcat": ["hashcat", "hash cracking"],
            "metasploit": ["metasploit", "exploitation framework"],
        }

        found_tools = []
        summary_lower = research_summary.lower()

        for tool, patterns in tool_patterns.items():
            if any(pattern in summary_lower for pattern in patterns):
                found_tools.append(tool)

        # Return top 5 most relevant tools
        return found_tools[:5] if found_tools else ["nmap", "masscan"]

    def _get_fallback_tools(self, scan_type: str) -> List[str]:
        """Get fallback tool recommendations when research fails"""
        fallback_map = {
            "port scanning": ["nmap", "masscan", "zmap"],
            "vulnerability scan": ["openvas", "nessus", "nikto"],
            "web scanning": ["nikto", "dirb", "gobuster"],
            "service detection": ["nmap", "banner"],
            "ssl scan": ["sslscan", "testssl", "nmap"],
        }

        return fallback_map.get(scan_type, ["nmap"])

    async def get_tool_installation_guide(self, tool_name: str) -> Dict[str, Any]:
        """Get installation guide for a specific tool using research agent"""
        try:
            from agents.research_agent import ResearchAgent, ResearchRequest

            research_agent = ResearchAgent()
            query = f"how to install {tool_name} on Kali Linux Ubuntu apt package manager 2024"

            request = ResearchRequest(query=query, focus="installation")

            research_result = await research_agent.research_installation_guide(request)

            return {
                "tool": tool_name,
                "installation_guide": research_result.summary,
                "package_manager": self._detect_package_manager(
                    research_result.summary
                ),
                "install_commands": self._extract_install_commands(
                    research_result.summary
                ),
                "confidence": getattr(research_result, "confidence", 0.8),
                "sources": getattr(research_result, "sources", [])[:2],
            }

        except Exception as e:
            logger.error("Installation guide research failed: %s", e)
            return {
                "tool": tool_name,
                "installation_guide": f"Try: sudo apt install {tool_name}",
                "package_manager": "apt",
                "install_commands": [
                    "sudo apt update",
                    f"sudo apt install {tool_name}",
                ],
                "confidence": 0.3,
                "sources": [],
            }

    def _detect_package_manager(self, guide_text: str) -> str:
        """Detect package manager from installation guide"""
        guide_lower = guide_text.lower()

        # Package manager detection patterns
        patterns = [
            (["apt install", "apt-get install"], "apt"),
            (["yum install"], "yum"),
            (["dnf install"], "dn"),
            (["pacman -S"], "pacman"),
            (["brew install"], "brew"),
        ]

        for keywords, pkg_manager in patterns:
            if any(kw in guide_lower for kw in keywords):
                return pkg_manager

        return "apt"  # Default for Kali/Ubuntu

    def _extract_install_commands(self, guide_text: str) -> List[str]:
        """Extract installation commands from guide text"""
        commands = []
        lines = guide_text.split("\n")

        for line in lines:
            line = line.strip()
            if (
                line.startswith("sudo apt")
                or line.startswith("apt install")
                or line.startswith("sudo yum")
                or line.startswith("sudo dn")
                or line.startswith("sudo pacman")
            ):
                commands.append(line)

        # If no commands found, provide basic apt command
        if not commands:
            tool_name = "nmap"  # default
            commands = ["sudo apt update", f"sudo apt install -y {tool_name}"]

        return commands


# Create singleton instance
security_scanner_agent = SecurityScannerAgent()
