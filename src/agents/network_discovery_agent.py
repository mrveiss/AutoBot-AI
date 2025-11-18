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
from typing import Any, Dict, List, Optional

from src.constants.network_constants import NetworkConstants
from src.utils.command_utils import execute_shell_command

logger = logging.getLogger(__name__)


class NetworkDiscoveryAgent:
    """Agent for network discovery and asset mapping"""

    def __init__(self):
        self.name = "network_discovery"
        self.description = "Discovers network assets and creates network maps"
        self.supported_tasks = [
            "network_scan",
            "host_discovery",
            "arp_scan",
            "traceroute",
            "network_map",
            "asset_inventory",
        ]

        # Get default network from configuration or environment
        import os

        self.default_network = os.getenv(
            "AUTOBOT_DEFAULT_SCAN_NETWORK", "192.168.1.0/24"
        )

    async def execute(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a network discovery task"""
        try:
            task_type = context.get("task_type", "network_scan")

            if task_type == "network_scan":
                return await self._network_scan(context)
            elif task_type == "host_discovery":
                return await self._host_discovery(context)
            elif task_type == "arp_scan":
                return await self._arp_scan(context)
            elif task_type == "traceroute":
                return await self._traceroute(context)
            elif task_type == "network_map":
                return await self._create_network_map(context)
            elif task_type == "asset_inventory":
                return await self._asset_inventory(context)
            else:
                return {
                    "status": "error",
                    "message": f"Unsupported task type: {task_type}",
                }

        except Exception as e:
            logger.error(f"Network discovery failed: {e}")
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

            result = await self._run_command(cmd)

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
            logger.error(f"Network scan failed: {e}")
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
            logger.error(f"Host discovery failed: {e}")
            return {"status": "error", "message": f"Host discovery failed: {str(e)}"}

    async def _arp_scan(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform ARP scan on local network"""
        try:
            network = context.get("network", self.default_network)

            # Use arp-scan if available, fallback to nmap
            cmd = ["arp-scan", "--local", network]

            # Check if arp-scan is available
            check_cmd = await self._run_command(["which", "arp-scan"])
            if check_cmd["status"] != "success":
                # Fallback to nmap ARP scan
                cmd = ["nmap", "-sn", "-PR", network]

            result = await self._run_command(cmd)

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
            logger.error(f"ARP scan failed: {e}")
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

            result = await self._run_command(cmd, timeout=60)

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
            logger.error(f"Traceroute failed: {e}")
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
            logger.error(f"Network mapping failed: {e}")
            return {"status": "error", "message": f"Network mapping failed: {str(e)}"}

    async def _asset_inventory(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create asset inventory"""
        try:
            network = context.get("network", self.default_network)

            # Discover hosts
            discovery_result = await self._host_discovery(
                {"network": network, "methods": ["ping", "arp"]}
            )

            if discovery_result["status"] != "success":
                return discovery_result

            assets = []

            # For each discovered host, gather more info
            for host in discovery_result["hosts"]:
                asset = {
                    "ip": host["ip"],
                    "mac": host.get("mac", "unknown"),
                    "vendor": host.get("vendor", "unknown"),
                    "hostname": None,
                    "open_ports": [],
                    "services": [],
                    "os_guess": None,
                }

                # Try to get hostname
                try:
                    import socket

                    hostname = socket.gethostbyaddr(host["ip"])[0]
                    asset["hostname"] = hostname
                except Exception:
                    pass

                # Quick port scan for common ports
                common_ports = "22,80,443,445,3389"
                port_cmd = ["nmap", "-p", common_ports, host["ip"], "-oX", "-"]
                port_result = await self._run_command(port_cmd, timeout=30)

                if port_result["status"] == "success":
                    open_ports = self._parse_nmap_output(port_result["output"])
                    asset["open_ports"] = [p["port"] for p in open_ports]
                    asset["services"] = [p["service"] for p in open_ports]

                assets.append(asset)

            # Categorize assets
            categories = {
                "servers": [],
                "workstations": [],
                "network_devices": [],
                "iot_devices": [],
                "unknown": [],
            }

            for asset in assets:
                if any(port in asset["open_ports"] for port in ["22", "80", "443"]):
                    categories["servers"].append(asset)
                elif "3389" in asset["open_ports"] or "445" in asset["open_ports"]:
                    categories["workstations"].append(asset)
                elif asset["ip"].endswith(".1"):
                    categories["network_devices"].append(asset)
                else:
                    categories["unknown"].append(asset)

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
            logger.error(f"Asset inventory failed: {e}")
            return {"status": "error", "message": f"Asset inventory failed: {str(e)}"}

    async def _ping_sweep(self, network: str) -> Dict[str, Any]:
        """Perform ping sweep"""
        cmd = ["nmap", "-sn", "-PE", network]
        result = await self._run_command(cmd)

        if result["status"] == "success":
            hosts = self._parse_host_discovery(result["output"])
            return {"status": "success", "hosts": hosts}
        return {"status": "error", "hosts": []}

    async def _tcp_discovery(self, network: str) -> Dict[str, Any]:
        """TCP SYN discovery"""
        cmd = ["nmap", "-sn", "-PS80,443,22", network]
        result = await self._run_command(cmd)

        if result["status"] == "success":
            hosts = self._parse_host_discovery(result["output"])
            return {"status": "success", "hosts": hosts}
        return {"status": "error", "hosts": []}

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

    def _parse_host_discovery(self, output: str) -> List[Dict[str, Any]]:
        """Parse host discovery output"""
        hosts = []
        lines = output.split("\n")

        current_host = None
        for line in lines:
            if "Nmap scan report for" in line:
                if current_host:
                    hosts.append(current_host)

                # Extract IP
                parts = line.split()
                ip = parts[-1].strip("()")
                hostname = parts[4] if len(parts) > 5 else None

                current_host = {"ip": ip, "hostname": hostname, "status": "up"}
            elif "MAC Address:" in line and current_host:
                parts = line.split()
                if len(parts) >= 3:
                    current_host["mac"] = parts[2]
                    if len(parts) > 3:
                        current_host["vendor"] = " ".join(parts[3:]).strip("()")

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
