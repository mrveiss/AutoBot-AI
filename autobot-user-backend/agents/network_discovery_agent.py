# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Network Discovery Agent for AutoBot
Provides network mapping and asset discovery capabilities
"""

import ipaddress
import logging
from datetime import datetime
from typing import Any, Dict, FrozenSet, List

from constants.network_constants import NetworkConstants
from constants.threshold_constants import TimingConstants
from utils.agent_command_helpers import run_agent_command

logger = logging.getLogger(__name__)

# Issue #380: Module-level constants for agent configuration
_SERVER_PORTS: FrozenSet[str] = frozenset({"22", "80", "443"})
_SUPPORTED_DISCOVERY_TASKS = (
    "network_scan",
    "host_discovery",
    "arp_scan",
    "traceroute",
    "network_map",
    "asset_inventory",
)


class NetworkDiscoveryAgent:
    """Agent for network discovery and asset mapping"""

    def __init__(self):
        """Initialize network discovery agent (Issue #380: use module-level constant)."""
        self.name = "network_discovery"
        self.description = "Discovers network assets and creates network maps"
        self.supported_tasks = _SUPPORTED_DISCOVERY_TASKS

        # Get default network from configuration or environment
        import os

        self.default_network = os.getenv(
            "AUTOBOT_DEFAULT_SCAN_NETWORK", NetworkConstants.DEFAULT_SCAN_NETWORK
        )

    def _get_task_handlers(self) -> Dict[str, Any]:
        """Get task type to handler mapping (Issue #334 - extracted helper)."""
        return {
            "network_scan": self._network_scan,
            "host_discovery": self._host_discovery,
            "arp_scan": self._arp_scan,
            "traceroute": self._traceroute,
            "network_map": self._create_network_map,
            "asset_inventory": self._asset_inventory,
        }

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a network discovery task"""
        try:
            task_type = context.get("task_type", "network_scan")
            handlers = self._get_task_handlers()
            handler = handlers.get(task_type)

            if handler is None:
                return {"status": "error", "message": f"Unsupported task type: {task_type}"}

            return await handler(context)

        except Exception as e:
            logger.error("Network discovery failed: %s", e)
            return {"status": "error", "message": f"Network discovery failed: {str(e)}"}

    async def _network_scan(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Scan network for active hosts"""
        try:
            network = context.get("network", self.default_network)

            # Validate network
            try:
                ipaddress.ip_network(network)
            except ValueError:
                return {
                    "status": "error",
                    "message": f"Invalid network format: {network}",
                }

            # Use nmap for network discovery
            cmd = ["nmap", "-sn", network, "-oX", "-"]

            result = await run_agent_command(cmd)

            if result["status"] == "success":
                hosts = self._parse_host_discovery(result["output"])

                return {
                    "status": "success",
                    "task": "network_scan",
                    "network": network,
                    "hosts_found": len(hosts),
                    "hosts": hosts,
                    "scan_time": datetime.now().isoformat(),
                }
            else:
                return result

        except Exception as e:
            logger.error("Network scan failed: %s", e)
            return {"status": "error", "message": f"Network scan failed: {str(e)}"}

    async def _host_discovery(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Discover hosts using multiple methods"""
        try:
            network = context.get("network", self.default_network)
            methods = context.get("methods", ["ping", "arp"])

            discovered_hosts = {}

            # Ping sweep
            if "ping" in methods:
                ping_result = await self._ping_sweep(network)
                for host in ping_result.get("hosts", []):
                    discovered_hosts[host["ip"]] = host

            # ARP scan (local network only)
            if "arp" in methods:
                arp_result = await self._arp_scan({"network": network})
                for host in arp_result.get("hosts", []):
                    ip = host["ip"]
                    if ip in discovered_hosts:
                        discovered_hosts[ip].update(host)
                    else:
                        discovered_hosts[ip] = host

            # TCP SYN discovery
            if "tcp" in methods:
                tcp_result = await self._tcp_discovery(network)
                for host in tcp_result.get("hosts", []):
                    ip = host["ip"]
                    if ip in discovered_hosts:
                        discovered_hosts[ip]["tcp_responsive"] = True
                    else:
                        discovered_hosts[ip] = host

            return {
                "status": "success",
                "task": "host_discovery",
                "network": network,
                "methods_used": methods,
                "hosts_found": len(discovered_hosts),
                "hosts": list(discovered_hosts.values()),
                "scan_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Host discovery failed: %s", e)
            return {"status": "error", "message": f"Host discovery failed: {str(e)}"}

    async def _arp_scan(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform ARP scan on local network"""
        try:
            network = context.get("network", self.default_network)

            # Use arp-scan if available, fallback to nmap
            cmd = ["arp-scan", "--local", network]

            # Check if arp-scan is available
            check_cmd = await run_agent_command(["which", "arp-scan"])
            if check_cmd["status"] != "success":
                # Fallback to nmap ARP scan
                cmd = ["nmap", "-sn", "-PR", network]

            result = await run_agent_command(cmd)

            if result["status"] == "success":
                hosts = self._parse_arp_scan(result["output"])

                return {
                    "status": "success",
                    "task": "arp_scan",
                    "network": network,
                    "hosts_found": len(hosts),
                    "hosts": hosts,
                    "scan_time": datetime.now().isoformat(),
                }
            else:
                return result

        except Exception as e:
            logger.error("ARP scan failed: %s", e)
            return {"status": "error", "message": f"ARP scan failed: {str(e)}"}

    async def _traceroute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform traceroute to target"""
        try:
            target = context.get("target", "")
            max_hops = context.get("max_hops", 30)

            if not target:
                return {
                    "status": "error",
                    "message": "No target specified for traceroute",
                }

            # Use traceroute command
            cmd = ["traceroute", "-m", str(max_hops), target]

            result = await run_agent_command(cmd, timeout=TimingConstants.STANDARD_TIMEOUT)

            if result["status"] == "success":
                hops = self._parse_traceroute(result["output"])

                return {
                    "status": "success",
                    "task": "traceroute",
                    "target": target,
                    "hops": hops,
                    "total_hops": len(hops),
                    "scan_time": datetime.now().isoformat(),
                }
            else:
                return result

        except Exception as e:
            logger.error("Traceroute failed: %s", e)
            return {"status": "error", "message": f"Traceroute failed: {str(e)}"}

    async def _create_network_map(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a network map"""
        try:
            network = context.get("network", self.default_network)

            # First discover hosts
            discovery_result = await self._host_discovery(
                {"network": network, "methods": ["ping", "arp", "tcp"]}
            )

            if discovery_result["status"] != "success":
                return discovery_result

            hosts = discovery_result["hosts"]

            # Create network map structure
            network_map = {
                "network": network,
                "gateway": None,
                "hosts": [],
                "segments": {},
            }

            # Identify gateway (usually .1)
            for host in hosts:
                ip = ipaddress.ip_address(host["ip"])
                if str(ip).endswith(".1"):
                    network_map["gateway"] = host
                    host["role"] = "gateway"

            # Group hosts by subnet
            for host in hosts:
                ip = ipaddress.ip_address(host["ip"])
                subnet = str(ip).rsplit(".", 1)[0]

                if subnet not in network_map["segments"]:
                    network_map["segments"][subnet] = []

                network_map["segments"][subnet].append(host)
                network_map["hosts"].append(host)

            return {
                "status": "success",
                "task": "network_map",
                "network_map": network_map,
                "total_hosts": len(hosts),
                "segments": len(network_map["segments"]),
                "scan_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Network mapping failed: %s", e)
            return {"status": "error", "message": f"Network mapping failed: {str(e)}"}

    def _resolve_hostname(self, ip: str) -> str | None:
        """Resolve IP to hostname (Issue #334 - extracted helper)."""
        import socket

        try:
            return socket.gethostbyaddr(ip)[0]
        except Exception:
            return None

    async def _gather_host_info(self, host: Dict[str, Any]) -> Dict[str, Any]:
        """Gather detailed info for a single host (Issue #334 - extracted helper)."""
        asset = {
            "ip": host["ip"],
            "mac": host.get("mac", "unknown"),
            "vendor": host.get("vendor", "unknown"),
            "hostname": self._resolve_hostname(host["ip"]),
            "open_ports": [],
            "services": [],
            "os_guess": None,
        }

        # Quick port scan for common ports
        common_ports = "22,80,443,445,3389"
        port_cmd = ["nmap", "-p", common_ports, host["ip"], "-oX", "-"]
        port_result = await run_agent_command(port_cmd, timeout=TimingConstants.SHORT_TIMEOUT)

        if port_result["status"] == "success":
            open_ports = self._parse_nmap_output(port_result["output"])
            asset["open_ports"] = [p["port"] for p in open_ports]
            asset["services"] = [p["service"] for p in open_ports]

        return asset

    def _categorize_asset(self, asset: Dict[str, Any]) -> str:
        """Determine asset category (Issue #334 - extracted helper)."""
        if any(port in asset["open_ports"] for port in _SERVER_PORTS):
            return "servers"
        if "3389" in asset["open_ports"] or "445" in asset["open_ports"]:
            return "workstations"
        if asset["ip"].endswith(".1"):
            return "network_devices"
        return "unknown"

    async def _asset_inventory(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create asset inventory"""
        try:
            network = context.get("network", self.default_network)

            discovery_result = await self._host_discovery(
                {"network": network, "methods": ["ping", "arp"]}
            )
            if discovery_result["status"] != "success":
                return discovery_result

            # Gather detailed info for each host
            assets = [
                await self._gather_host_info(host)
                for host in discovery_result["hosts"]
            ]

            # Categorize assets
            categories = {
                "servers": [],
                "workstations": [],
                "network_devices": [],
                "iot_devices": [],
                "unknown": [],
            }
            for asset in assets:
                category = self._categorize_asset(asset)
                categories[category].append(asset)

            return {
                "status": "success",
                "task": "asset_inventory",
                "network": network,
                "total_assets": len(assets),
                "assets": assets,
                "categories": categories,
                "scan_time": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("Asset inventory failed: %s", e)
            return {"status": "error", "message": f"Asset inventory failed: {str(e)}"}

    async def _ping_sweep(self, network: str) -> Dict[str, Any]:
        """Perform ping sweep"""
        cmd = ["nmap", "-sn", "-PE", network]
        result = await run_agent_command(cmd)

        if result["status"] == "success":
            hosts = self._parse_host_discovery(result["output"])
            return {"status": "success", "hosts": hosts}
        return {"status": "error", "hosts": []}

    async def _tcp_discovery(self, network: str) -> Dict[str, Any]:
        """TCP SYN discovery"""
        cmd = ["nmap", "-sn", "-PS80,443,22", network]
        result = await run_agent_command(cmd)

        if result["status"] == "success":
            hosts = self._parse_host_discovery(result["output"])
            return {"status": "success", "hosts": hosts}
        return {"status": "error", "hosts": []}

    # _run_command moved to src/utils/agent_command_helpers.py (Issue #292)
    # Use run_agent_command() directly

    def _parse_scan_report_line(self, line: str) -> Dict[str, Any]:
        """Parse Nmap scan report line (Issue #334 - extracted helper)."""
        parts = line.split()
        ip = parts[-1].strip("()")
        hostname = parts[4] if len(parts) > 5 else None
        return {"ip": ip, "hostname": hostname, "status": "up"}

    def _parse_mac_line(self, line: str, current_host: Dict[str, Any]) -> None:
        """Parse MAC Address line (Issue #334 - extracted helper)."""
        parts = line.split()
        if len(parts) < 3:
            return
        current_host["mac"] = parts[2]
        if len(parts) > 3:
            current_host["vendor"] = " ".join(parts[3:]).strip("()")

    def _parse_host_discovery(self, output: str) -> List[Dict[str, Any]]:
        """Parse host discovery output"""
        hosts = []
        current_host = None

        for line in output.split("\n"):
            if "Nmap scan report for" in line:
                if current_host:
                    hosts.append(current_host)
                current_host = self._parse_scan_report_line(line)
            elif "MAC Address:" in line and current_host:
                self._parse_mac_line(line, current_host)

        if current_host:
            hosts.append(current_host)

        return hosts

    def _parse_arp_scan(self, output: str) -> List[Dict[str, Any]]:
        """Parse ARP scan output"""
        hosts = []
        lines = output.split("\n")

        for line in lines:
            parts = line.split()
            if len(parts) >= 3 and "." in parts[0]:
                try:
                    # Validate IP
                    ipaddress.ip_address(parts[0])
                    host = {
                        "ip": parts[0],
                        "mac": parts[1],
                        "vendor": " ".join(parts[2:]) if len(parts) > 2 else "unknown",
                    }
                    hosts.append(host)
                except Exception:
                    continue

        return hosts

    def _parse_traceroute(self, output: str) -> List[Dict[str, Any]]:
        """Parse traceroute output"""
        hops = []
        lines = output.split("\n")

        for line in lines:
            parts = line.strip().split()
            if len(parts) > 1 and parts[0].isdigit():
                hop_num = int(parts[0])

                # Extract IPs and hostnames
                hop_info = {"hop": hop_num, "hosts": []}

                for i in range(1, len(parts)):
                    if "(" in parts[i] and ")" in parts[i]:
                        # IP in parentheses
                        ip = parts[i].strip("()")
                        hostname = parts[i - 1] if i > 1 else None
                        hop_info["hosts"].append({"hostname": hostname, "ip": ip})

                if hop_info["hosts"]:
                    hops.append(hop_info)

        return hops

    def _parse_nmap_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse nmap output for open ports"""
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


# Create singleton instance
network_discovery_agent = NetworkDiscoveryAgent()
