#!/usr/bin/env python3
"""
VM Connectivity Test Suite for AutoBot Distributed Infrastructure
Tests network connectivity and basic communication between all 5 VMs
"""

import socket
import subprocess
import time
import concurrent.futures
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VMConnectivityTest:
    """Test connectivity between all AutoBot VMs"""

    def __init__(self):
        self.vms = {
            'main_machine': '172.16.168.20',
            'vm1_frontend': '172.16.168.21',
            'vm2_npu': '172.16.168.22',
            'vm3_redis': '172.16.168.23',
            'vm4_ai': '172.16.168.24',
            'vm5_browser': '172.16.168.25'
        }

        self.ports = {
            'main_machine': [8001, 6080],  # Backend API, VNC
            'vm1_frontend': [5173],        # Vue.js Frontend
            'vm2_npu': [8081],            # NPU Worker
            'vm3_redis': [6379],          # Redis Database
            'vm4_ai': [8080],             # AI Stack
            'vm5_browser': [3000]         # Playwright Browser
        }

    def test_ping_connectivity(self) -> Dict[str, bool]:
        """Test basic ping connectivity to all VMs"""
        logger.info("Testing ping connectivity to all VMs...")
        results = {}

        def ping_vm(vm_name: str, ip: str) -> Tuple[str, bool]:
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '3', ip],
                    capture_output=True,
                    timeout=5
                )
                return vm_name, result.returncode == 0
            except Exception as e:
                logger.error(f"Ping test failed for {vm_name} ({ip}): {e}")
                return vm_name, False

        # Test all VMs concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(ping_vm, vm_name, ip) for vm_name, ip in self.vms.items()]

            for future in concurrent.futures.as_completed(futures):
                vm_name, success = future.result()
                results[vm_name] = success
                status = "✓" if success else "✗"
                logger.info(f"  {vm_name} ({self.vms[vm_name]}): {status}")

        return results

    def test_port_connectivity(self) -> Dict[str, Dict[int, bool]]:
        """Test port connectivity for all VM services"""
        logger.info("Testing port connectivity for all VM services...")
        results = {}

        def test_port(vm_name: str, ip: str, port: int) -> Tuple[str, int, bool]:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((ip, port))
                sock.close()
                return vm_name, port, result == 0
            except Exception as e:
                logger.error(f"Port test failed for {vm_name}:{port}: {e}")
                return vm_name, port, False

        # Test all ports concurrently
        all_tests = []
        for vm_name, ip in self.vms.items():
            for port in self.ports[vm_name]:
                all_tests.append((vm_name, ip, port))

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(test_port, vm_name, ip, port) for vm_name, ip, port in all_tests]

            for future in concurrent.futures.as_completed(futures):
                vm_name, port, success = future.result()
                if vm_name not in results:
                    results[vm_name] = {}
                results[vm_name][port] = success

                status = "✓" if success else "✗"
                logger.info(f"  {vm_name}:{port}: {status}")

        return results

    def test_network_latency(self) -> Dict[str, float]:
        """Test network latency between main machine and all VMs"""
        logger.info("Testing network latency...")
        latency_results = {}

        for vm_name, ip in self.vms.items():
            if vm_name == 'main_machine':
                continue  # Skip self

            try:
                # Run multiple ping tests for average
                latencies = []
                for _ in range(5):
                    result = subprocess.run(
                        ['ping', '-c', '1', '-W', '3', ip],
                        capture_output=True,
                        timeout=5
                    )

                    if result.returncode == 0:
                        # Extract latency from ping output
                        output = result.stdout.decode()
                        if 'time=' in output:
                            latency_str = output.split('time=')[1].split(' ')[0]
                            latencies.append(float(latency_str))

                if latencies:
                    avg_latency = sum(latencies) / len(latencies)
                    latency_results[vm_name] = avg_latency
                    logger.info(f"  {vm_name}: {avg_latency:.2f}ms")
                else:
                    latency_results[vm_name] = float('inf')
                    logger.warning(f"  {vm_name}: No successful pings")

            except Exception as e:
                logger.error(f"Latency test failed for {vm_name}: {e}")
                latency_results[vm_name] = float('inf')

        return latency_results

    def test_ssh_connectivity(self) -> Dict[str, bool]:
        """Test SSH connectivity to all VMs using AutoBot SSH key"""
        logger.info("Testing SSH connectivity...")
        ssh_results = {}

        import paramiko

        def test_ssh(vm_name: str, ip: str) -> Tuple[str, bool]:
            if vm_name == 'main_machine':
                return vm_name, True  # Skip SSH to self

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                # Use AutoBot SSH key
                client.connect(
                    hostname=ip,
                    username='autobot',
                    key_filename='/home/kali/.ssh/autobot_key',
                    timeout=10
                )

                # Test simple command
                stdin, stdout, stderr = client.exec_command('echo "SSH test successful"')
                output = stdout.read().decode().strip()
                success = output == "SSH test successful"

                client.close()
                return vm_name, success

            except Exception as e:
                logger.error(f"SSH test failed for {vm_name}: {e}")
                return vm_name, False

        # Test SSH to all VMs (except main machine)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(test_ssh, vm_name, ip)
                      for vm_name, ip in self.vms.items() if vm_name != 'main_machine']

            for future in concurrent.futures.as_completed(futures):
                vm_name, success = future.result()
                ssh_results[vm_name] = success
                status = "✓" if success else "✗"
                logger.info(f"  SSH to {vm_name}: {status}")

        return ssh_results

    def generate_connectivity_report(self) -> Dict[str, any]:
        """Generate comprehensive connectivity test report"""
        logger.info("Running comprehensive VM connectivity tests...")

        # Run all connectivity tests
        ping_results = self.test_ping_connectivity()
        port_results = self.test_port_connectivity()
        latency_results = self.test_network_latency()
        ssh_results = self.test_ssh_connectivity()

        # Calculate overall connectivity status
        overall_status = {}
        for vm_name in self.vms.keys():
            ping_ok = ping_results.get(vm_name, False)
            ports_ok = any(port_results.get(vm_name, {}).values()) if vm_name in port_results else False
            ssh_ok = ssh_results.get(vm_name, True)  # Main machine defaults to True

            overall_status[vm_name] = ping_ok and ports_ok and ssh_ok

        # Generate summary
        total_vms = len(self.vms)
        working_vms = sum(overall_status.values())
        connectivity_health = (working_vms / total_vms) * 100

        report = {
            'connectivity_summary': {
                'total_vms': total_vms,
                'working_vms': working_vms,
                'connectivity_health_percentage': connectivity_health,
                'status': 'HEALTHY' if connectivity_health >= 80 else 'DEGRADED'
            },
            'ping_results': ping_results,
            'port_results': port_results,
            'latency_results': latency_results,
            'ssh_results': ssh_results,
            'overall_vm_status': overall_status,
            'critical_issues': []
        }

        # Identify critical connectivity issues
        for vm_name, is_working in overall_status.items():
            if not is_working:
                report['critical_issues'].append({
                    'vm': vm_name,
                    'ip': self.vms[vm_name],
                    'issue': 'VM connectivity failure',
                    'ping': ping_results.get(vm_name, False),
                    'ports': port_results.get(vm_name, {}),
                    'ssh': ssh_results.get(vm_name, False)
                })

        return report

def main():
    """Main connectivity test execution"""
    connectivity_test = VMConnectivityTest()
    report = connectivity_test.generate_connectivity_report()

    # Print summary
    print("\n" + "="*50)
    print("VM CONNECTIVITY TEST SUMMARY")
    print("="*50)

    summary = report['connectivity_summary']
    print(f"Total VMs: {summary['total_vms']}")
    print(f"Working VMs: {summary['working_vms']}")
    print(f"Connectivity Health: {summary['connectivity_health_percentage']:.1f}%")
    print(f"Overall Status: {summary['status']}")

    if report['critical_issues']:
        print(f"\nCritical Issues ({len(report['critical_issues'])}):")
        for issue in report['critical_issues']:
            print(f"  - {issue['vm']} ({issue['ip']}): {issue['issue']}")

    print("\nDetailed connectivity results available in test logs.")
    print("="*50)

    return report

if __name__ == "__main__":
    main()