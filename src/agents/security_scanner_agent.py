# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Scanner Agent for AutoBot
Provides defensive security scanning and analysis capabilities
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.constants.network_constants import NetworkConstants
from src.utils.command_utils import execute_shell_command

logger = logging.getLogger(__name__)


class SecurityScannerAgent:
    """Agent for performing defensive security scans and vulnerability assessments"""

    def __init__(self):
        self.name = "security_scanner"
        self.description = (
            "Performs defensive security scans and vulnerability assessments"
        )
        self.supported_scan_types = [
            "port_scan",
            "service_detection",
            "vulnerability_scan",
            "ssl_scan",
            "dns_enum",
            "web_scan",
        ]

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

            # Validate target is appropriate (localhost, private network, or authorized)
            if not self._validate_target(target):
                return {
                    "status": "error",
                    "message": (
                        "Target validation failed. Only authorized targets allowed."
                    ),
                }

            # Execute appropriate scan based on type
            if scan_type == "port_scan":
                return await self._port_scan(target, context)
            elif scan_type == "service_detection":
                return await self._service_detection(target, context)
            elif scan_type == "vulnerability_scan":
                return await self._vulnerability_scan(target, context)
            elif scan_type == "ssl_scan":
                return await self._ssl_scan(target, context)
            elif scan_type == "dns_enum":
                return await self._dns_enumeration(target, context)
            elif scan_type == "web_scan":
                return await self._web_scan(target, context)
            else:
                return {
                    "status": "error",
                    "message": f"Unsupported scan type: {scan_type}",
                }

        except Exception as e:
            logger.error(f"Security scan failed: {e}")
            return {"status": "error", "message": f"Security scan failed: {str(e)}"}

    def _validate_target(self, target: str) -> bool:
        """Validate target is appropriate for scanning"""
        # Only allow scanning of:
        # 1. Localhost/loopback
        # 2. Private IP ranges (RFC1918)
        # 3. Explicitly authorized domains (would need config)

        allowed_targets = [
            NetworkConstants.LOCALHOST_NAME,
            NetworkConstants.LOCALHOST_IP,
            NetworkConstants.LOCALHOST_IPV6,
        ]

        # Check if target is in allowed list
        if target in allowed_targets:
            return True

        # Check if target is in private IP range
        import ipaddress

        try:
            ip = ipaddress.ip_address(target)
            if ip.is_private:
                return True
        except ValueError:
            # Not an IP address, could be hostname
            pass

        # For production, you'd check against authorized domains here
        logger.warning(f"Target {target} not in authorized list")
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
            result = await self._run_command(cmd)

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
            logger.error(f"Port scan failed: {e}")
            return {"status": "error", "message": f"Port scan failed: {str(e)}"}

    async def _service_detection(
        self, target: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Detect services running on open ports"""
        try:
            ports = context.get("ports", "1-1000")

            # Use nmap service detection
            cmd = ["nmap", "-sV", "-p", ports, target, "-oX", "-"]

            result = await self._run_command(cmd)

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
            logger.error(f"Service detection failed: {e}")
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

            result = await self._run_command(cmd, timeout=300)  # 5 minute timeout

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
            logger.error(f"Vulnerability scan failed: {e}")
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

            result = await self._run_command(cmd)

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
            logger.error(f"SSL scan failed: {e}")
            return {"status": "error", "message": f"SSL scan failed: {str(e)}"}

    async def _dns_enumeration(
        self, target: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform DNS enumeration"""
        try:
            # Use multiple tools for comprehensive enumeration
            results = {"domain": target, "dns_records": {}, "subdomains": []}

            # Get DNS records
            record_types = ["A", "AAAA", "MX", "TXT", "NS", "SOA"]
            for record_type in record_types:
                cmd = ["dig", "+short", record_type, target]
                result = await self._run_command(cmd)
                if result["status"] == "success" and result["output"].strip():
                    results["dns_records"][record_type] = (
                        result["output"].strip().split("\n")
                    )

            # Basic subdomain enumeration (would use wordlist in production)
            common_subdomains = ["www", "mail", "ftp", "admin", "api", "dev", "test"]
            for subdomain in common_subdomains:
                full_domain = f"{subdomain}.{target}"
                cmd = ["dig", "+short", "A", full_domain]
                result = await self._run_command(cmd)
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
            logger.error(f"DNS enumeration failed: {e}")
            return {"status": "error", "message": f"DNS enumeration failed: {str(e)}"}

    async def _web_scan(self, target: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform basic web application scanning"""
        try:
            # In production, might use:
            # - Nikto
            # - OWASP ZAP API
            # - Nuclei
            # - Custom web checks

            # Basic example checking common paths
            results = {"url": target, "findings": []}

            # Check robots.txt
            import aiohttp

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(f"{target}/robots.txt") as response:
                        if response.status == 200:
                            results["findings"].append(
                                {
                                    "type": "info",
                                    "path": "/robots.txt",
                                    "message": "Robots.txt file found",
                                }
                            )
                except Exception:
                    pass

                # Check common admin paths
                admin_paths = ["/admin", "/login", "/wp-admin", "/.git", "/.env"]
                for path in admin_paths:
                    try:
                        async with session.get(f"{target}{path}") as response:
                            if response.status in [200, 301, 302]:
                                results["findings"].append(
                                    {
                                        "type": "warning",
                                        "path": path,
                                        "status": response.status,
                                        "message": (
                                            "Potentially sensitive path accessible"
                                        ),
                                    }
                                )
                    except Exception:
                        pass

            return {
                "status": "success",
                "scan_type": "web_scan",
                "results": results,
                "scan_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Web scan failed: {e}")
            return {"status": "error", "message": f"Web scan failed: {str(e)}"}

    async def _run_command(self, cmd: List[str], timeout: int = 60) -> Dict[str, Any]:
        """Run a command with timeout - wrapper around common utility"""
        result = await execute_shell_command(cmd, timeout=timeout)

        # Convert to expected format for this agent
        if result["status"] == "success":
            return {"status": "success", "output": result["stdout"]}
        else:
            # Combine stderr and error info for backward compatibility
            error_msg = (
                result["stderr"]
                or f"Command failed with return code {result['return_code']}"
            )
            if result["status"] == "timeout":
                error_msg = f"Command timed out after {timeout} seconds"

            return {
                "status": "error",
                "message": error_msg,
            }

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
            result = await self._run_command(["which", tool_name], timeout=5)
            return result["status"] == "success"
        except Exception:
            return False

    async def _research_scanning_tools(self, scan_type: str) -> Dict[str, Any]:
        """Use research agent to find appropriate scanning tools"""
        try:
            # Import research agent
            from src.agents.research_agent import ResearchAgent, ResearchRequest

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
            logger.error(f"Tool research failed: {e}")
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
            from src.agents.research_agent import ResearchAgent, ResearchRequest

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
            logger.error(f"Installation guide research failed: {e}")
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

        if "apt install" in guide_lower or "apt-get install" in guide_lower:
            return "apt"
        elif "yum install" in guide_lower:
            return "yum"
        elif "dnf install" in guide_lower:
            return "dn"
        elif "pacman -S" in guide_lower:
            return "pacman"
        elif "brew install" in guide_lower:
            return "brew"
        else:
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
