#!/usr/bin/env python3
"""
Security Port Audit for AutoBot System
Checks for unexpected ports and validates only required services are exposed
"""

import subprocess
import json
import re
import sys
from typing import Dict, List, Set, Tuple

class AutoBotPortAuditor:
    def __init__(self):
        self.expected_ports = {
            # AutoBot Core Services
            5173: "Frontend (Vite Dev Server)",
            8001: "Backend API (FastAPI/Uvicorn)",
            
            # Infrastructure Services  
            6379: "Redis Stack",
            8002: "Redis Stack Web UI",
            8080: "AI Stack Container",
            11434: "Ollama LLM Server",
            
            # System Services (allowed)
            53: "DNS (WSL2)",
            22: "SSH (if enabled)",
            
            # Development Services (conditional)
            5174: "Vite HMR (Hot Module Reload)",
            4923: "VS Code Language Server",
            19069: "VS Code Extension Host",
            44623: "VS Code Remote",
        }
        
        self.security_violations = []
        self.warnings = []
        self.info = []

    def get_listening_ports(self) -> List[Tuple[str, int, str, str]]:
        """Get all listening ports with process info"""
        try:
            # Using netstat to get listening ports
            result = subprocess.run(
                ['netstat', '-tlnp'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            ports = []
            for line in result.stdout.split('\n'):
                if 'LISTEN' in line:
                    parts = line.split()
                    if len(parts) >= 7:
                        protocol = parts[0]
                        address = parts[3]
                        process_info = parts[6] if parts[6] != '-' else 'system'
                        
                        # Extract port from address
                        if ':' in address:
                            port_str = address.split(':')[-1]
                            try:
                                port = int(port_str)
                                ports.append((protocol, port, address, process_info))
                            except ValueError:
                                continue
            
            return ports
            
        except subprocess.CalledProcessError as e:
            print(f"Error getting port information: {e}")
            return []

    def get_docker_ports(self) -> Dict[str, List[str]]:
        """Get Docker container port mappings"""
        try:
            result = subprocess.run(
                ['docker', 'ps', '--format', '{{.Names}}\t{{.Ports}}'],
                capture_output=True,
                text=True,
                check=True
            )
            
            containers = {}
            for line in result.stdout.strip().split('\n'):
                if line and '\t' in line:
                    name, ports = line.split('\t', 1)
                    if name != 'NAMES':
                        containers[name] = ports.split(', ') if ports else []
            
            return containers
            
        except subprocess.CalledProcessError:
            return {}

    def check_process_legitimacy(self, process_info: str, port: int) -> bool:
        """Check if a process running on a port is legitimate"""
        # Extract PID and process name
        if '/' in process_info:
            try:
                pid, process_name = process_info.split('/', 1)
                pid = int(pid)
                
                # Get full process info
                result = subprocess.run(
                    ['ps', '-p', str(pid), '-o', 'pid,ppid,cmd'],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        process_line = lines[1]
                        return self._is_legitimate_process(process_line, port)
                        
            except (ValueError, IndexError):
                pass
                
        return True  # Default to allowing system processes

    def _is_legitimate_process(self, process_line: str, port: int) -> bool:
        """Check if a specific process is legitimate for AutoBot"""
        legitimate_patterns = [
            r'python.*uvicorn',      # FastAPI backend
            r'node.*vite',           # Frontend dev server  
            r'python.*main\.py',     # AutoBot main
            r'redis-server',         # Redis
            r'ollama',              # Ollama LLM
            r'docker',              # Docker containers
            r'node.*vscode',        # VS Code (development)
            r'/usr/sbin/dnsmasq',   # WSL2 DNS
        ]
        
        for pattern in legitimate_patterns:
            if re.search(pattern, process_line, re.IGNORECASE):
                return True
                
        # Flag unexpected processes
        self.warnings.append(
            f"Unexpected process on port {port}: {process_line[:100]}"
        )
        return False

    def audit_ports(self):
        """Main audit function"""
        print("🔍 Starting AutoBot Security Port Audit...")
        print("=" * 60)
        
        # Get all listening ports
        listening_ports = self.get_listening_ports()
        docker_containers = self.get_docker_ports()
        
        print(f"📊 Found {len(listening_ports)} listening ports")
        print(f"🐳 Found {len(docker_containers)} Docker containers")
        print()
        
        # Check each port
        found_ports = set()
        
        print("🔍 Port Analysis:")
        print("-" * 40)
        
        for protocol, port, address, process_info in listening_ports:
            found_ports.add(port)
            
            if port in self.expected_ports:
                print(f"✅ Port {port:5d} - {self.expected_ports[port]}")
                if process_info != 'system' and process_info != '-':
                    self.check_process_legitimacy(process_info, port)
                    
            elif port < 1024:
                # System ports - generally acceptable
                print(f"ℹ️  Port {port:5d} - System service ({address})")
                self.info.append(f"System service on port {port}")
                
            elif 49152 <= port <= 65535:
                # Ephemeral ports - usually temporary
                print(f"⚠️  Port {port:5d} - Ephemeral port ({process_info})")
                self.warnings.append(f"Ephemeral port {port} - may be temporary")
                
            else:
                # Unexpected application port
                print(f"🚨 Port {port:5d} - UNEXPECTED SERVICE ({process_info})")
                self.security_violations.append(
                    f"Unexpected port {port} running {process_info}"
                )
                
        print()
        
        # Check Docker containers
        print("🐳 Docker Container Analysis:")
        print("-" * 40)
        
        for container, ports_list in docker_containers.items():
            if not ports_list or ports_list == ['']:
                print(f"✅ {container} - No exposed ports")
                continue
                
            for port_mapping in ports_list:
                if '->' in port_mapping:
                    external_part = port_mapping.split('->')[0]
                    # Extract port numbers
                    external_ports = re.findall(r':(\d+)', external_part)
                    for port_str in external_ports:
                        port = int(port_str)
                        if port in self.expected_ports:
                            print(f"✅ {container} - Port {port} ({self.expected_ports[port]})")
                        else:
                            print(f"🚨 {container} - UNEXPECTED PORT {port}")
                            self.security_violations.append(
                                f"Container {container} exposes unexpected port {port}"
                            )
        print()
        
        # Check for missing expected services
        print("🔍 Expected Service Verification:")
        print("-" * 40)
        
        critical_services = {
            5173: "Frontend",
            8001: "Backend API", 
            6379: "Redis",
            11434: "Ollama"
        }
        
        for port, service in critical_services.items():
            if port in found_ports:
                print(f"✅ {service} - Running on port {port}")
            else:
                print(f"⚠️  {service} - NOT RUNNING on port {port}")
                self.warnings.append(f"Expected service {service} not found on port {port}")
        
        print()
        self._print_summary()

    def _print_summary(self):
        """Print audit summary"""
        print("📋 SECURITY AUDIT SUMMARY")
        print("=" * 60)
        
        if not self.security_violations and not self.warnings:
            print("🟢 PASSED - No security issues detected")
            print("   All ports are expected AutoBot services")
            
        else:
            if self.security_violations:
                print("🔴 SECURITY VIOLATIONS:")
                for violation in self.security_violations:
                    print(f"   ❌ {violation}")
                print()
                
            if self.warnings:
                print("🟡 WARNINGS:")
                for warning in self.warnings:
                    print(f"   ⚠️  {warning}")
                print()
                
            if self.info:
                print("ℹ️  INFORMATION:")
                for info_item in self.info:
                    print(f"   ℹ️  {info_item}")
        
        print()
        print("🔐 SECURITY RECOMMENDATIONS:")
        print("   • Only run AutoBot on trusted networks")
        print("   • Use firewall rules to restrict access")
        print("   • Monitor for unexpected processes")
        print("   • Keep Docker containers updated")
        
        # Return exit code based on findings
        if self.security_violations:
            print("\n❌ AUDIT FAILED - Security violations found")
            return 1
        elif self.warnings:
            print("\n⚠️  AUDIT COMPLETED - Warnings present")
            return 2
        else:
            print("\n✅ AUDIT PASSED - System secure")
            return 0

def main():
    """Main entry point"""
    auditor = AutoBotPortAuditor()
    exit_code = auditor.audit_ports()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()