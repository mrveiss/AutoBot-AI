#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Host-to-Container DNS Service
Provides automatic DNS resolution from host to Docker containers
"""

import json
import logging
import subprocess
import time
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - HostDNS - %(message)s')
logger = logging.getLogger(__name__)


class HostContainerDNS:
    def __init__(self):
        self.hosts_file = "/etc/hosts"
        self.marker_start = "# AutoBot Container DNS - Start"
        self.marker_end = "# AutoBot Container DNS - End"
        self.network_name = "autobot-network"

    def get_container_mappings(self) -> Dict[str, str]:
        """Get container name to IP mappings from Docker network"""
        try:
            # Get network info
            result = subprocess.run([
                'docker', 'network', 'inspect', self.network_name
            ], capture_output=True, text=True, check=True)

            network_data = json.loads(result.stdout)[0]
            containers = network_data.get('Containers', {})

            mappings = {}
            for container_id, info in containers.items():
                name = info.get('Name', '')
                ip = info.get('IPv4Address', '').split('/')[0]

                if name and ip:
                    mappings[name] = ip
                    # Add .autobot domain
                    mappings[f"{name}.autobot"] = ip

                    # Add short aliases
                    if name.startswith('autobot-'):
                        short_name = name.replace('autobot-', '')
                        mappings[f"{short_name}.autobot"] = ip

            logger.info("Found %s container mappings", len(mappings))
            return mappings

        except subprocess.CalledProcessError as e:
            logger.error("Failed to get container mappings: %s", e)
            return {}
        except Exception as e:
            logger.error("Error getting container mappings: %s", e)
            return {}

    def generate_hosts_entries(self, mappings: Dict[str, str]) -> List[str]:
        """Generate /etc/hosts entries"""
        entries = [self.marker_start]

        # Add timestamp
        entries.append(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        entries.append("")

        # Sort by IP for cleaner output
        by_ip = {}
        for name, ip in mappings.items():
            if ip not in by_ip:
                by_ip[ip] = []
            by_ip[ip].append(name)

        for ip, names in sorted(by_ip.items()):
            # Primary name (shortest) first
            names.sort(key=len)
            entries.append(f"{ip}\t" + "\t".join(names))

        entries.append("")
        entries.append(self.marker_end)
        return entries

    def update_hosts_file(self, new_entries: List[str]) -> bool:
        """Update /etc/hosts with new entries"""
        try:
            # Read current hosts file
            with open(self.hosts_file, 'r') as f:
                lines = f.readlines()

            # Remove old AutoBot entries
            filtered_lines = []
            skip = False

            for line in lines:
                line = line.rstrip()
                if line == self.marker_start:
                    skip = True
                elif line == self.marker_end:
                    skip = False
                    continue
                elif not skip:
                    filtered_lines.append(line)

            # Add new entries
            all_lines = filtered_lines + [''] + new_entries + ['']

            # Write back to hosts file
            content = '\n'.join(all_lines)

            # Use sudo to write
            process = subprocess.run([
                'sudo', 'tee', self.hosts_file
            ], input=content, text=True, capture_output=True)

            if process.returncode == 0:
                logger.info("✅ Updated /etc/hosts successfully")
                return True
            else:
                logger.error("Failed to update /etc/hosts: %s", process.stderr)
                return False

        except Exception as e:
            logger.error("Error updating hosts file: %s", e)
            return False

    def test_resolution(self, mappings: Dict[str, str]) -> Dict[str, bool]:
        """Test DNS resolution"""
        results = {}

        for name, expected_ip in mappings.items():
            try:
                import socket
                resolved_ip = socket.gethostbyname(name)
                results[name] = (resolved_ip == expected_ip)

                if resolved_ip == expected_ip:
                    logger.info("✅ %s → %s", name, resolved_ip)
                else:
                    logger.warning("❌ %s → %s (expected %s)", name, resolved_ip, expected_ip)

            except socket.gaierror:
                results[name] = False
                logger.warning("❌ %s → DNS resolution failed", name)

        return results

    def test_connectivity(self, mappings: Dict[str, str]) -> Dict[str, Dict[str, bool]]:
        """Test container connectivity on common ports"""
        connectivity = {}

        port_map = {
            'autobot-redis': [6379],
            'autobot-frontend': [5173],
            'autobot-ai-stack': [8080],
            'autobot-npu-worker': [8081],
            'autobot-browser': [3000],
            'autobot-seq': [80]
        }

        for container_name, ip in mappings.items():
            if container_name in port_map:
                connectivity[container_name] = {}

                for port in port_map[container_name]:
                    try:
                        import socket
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(2)
                        result = sock.connect_ex((ip, port))
                        sock.close()

                        connectivity[container_name][port] = (result == 0)

                        if result == 0:
                            logger.info("✅ %s:%s - reachable", container_name, port)
                        else:
                            logger.warning("❌ %s:%s - not reachable", container_name, port)

                    except Exception as e:
                        connectivity[container_name][port] = False
                        logger.warning("❌ %s:%s - error: %s", container_name, port, e)

        return connectivity

    def run_once(self) -> bool:
        """Run DNS update once"""
        logger.info("🔄 Updating host-to-container DNS mappings...")

        mappings = self.get_container_mappings()
        if not mappings:
            logger.warning("No container mappings found")
            return False

        entries = self.generate_hosts_entries(mappings)
        success = self.update_hosts_file(entries)

        if success:
            logger.info("✅ Updated %s container DNS mappings", len(mappings))
            return True
        else:
            logger.error("❌ Failed to update DNS mappings")
            return False

    def run_daemon(self, interval: int = 60):
        """Run as daemon with periodic updates"""
        logger.info("🚀 Starting host-container DNS daemon (refresh every %ss)", interval)

        while True:
            try:
                self.run_once()
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("🛑 DNS daemon stopped")
                break
            except Exception as e:
                logger.error("❌ Daemon error: %s", e)
                time.sleep(10)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Host-to-Container DNS Service')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--interval', type=int, default=60, help='Update interval for daemon (seconds)')
    parser.add_argument('--test', action='store_true', help='Test DNS resolution')
    parser.add_argument('--connectivity', action='store_true', help='Test container connectivity')
    parser.add_argument('--show', action='store_true', help='Show current mappings')

    args = parser.parse_args()

    dns_service = HostContainerDNS()

    if args.show:
        mappings = dns_service.get_container_mappings()
        print("🔍 Container Mappings:")
        for name, ip in sorted(mappings.items()):
            print(f"  {name} → {ip}")
        return

    if args.test:
        mappings = dns_service.get_container_mappings()
        print("🧪 Testing DNS Resolution:")
        dns_service.test_resolution(mappings)
        return

    if args.connectivity:
        mappings = dns_service.get_container_mappings()
        print("🌐 Testing Container Connectivity:")
        dns_service.test_connectivity(mappings)
        return

    if args.daemon:
        dns_service.run_daemon(args.interval)
    else:
        dns_service.run_once()


if __name__ == "__main__":
    main()
