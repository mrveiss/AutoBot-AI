#!/usr/bin/env python3
"""
Local DNS Resolver Sidecar
Runs inside each container to provide instant DNS resolution
"""

import asyncio
import json
import logging
import socket
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - DNS - %(message)s')
logger = logging.getLogger(__name__)

class LocalDNSResolver:
    def __init__(self):
        self.cache = {}
        self.hosts_file = "/etc/hosts.autobot"
        self.cache_file = "/tmp/dns-cache.json"
        
        # Key mappings for AutoBot infrastructure
        self.static_mappings = {
            # Host system
            "host.docker.internal": "host-gateway",
            "backend.autobot": "host-gateway",
            "api.autobot": "host-gateway",
            
            # Container services
            "redis.autobot": "redis",
            "frontend.autobot": "autobot-frontend", 
            "ai-stack.autobot": "autobot-ai-stack",
            "npu-worker.autobot": "autobot-npu-worker",
            "browser.autobot": "autobot-browser",
            "seq.autobot": "autobot-seq",
            
            # Fallbacks
            "localhost": "127.0.0.1",
        }
        
        self.load_cache()
        self.update_hosts_file()
    
    def load_cache(self):
        """Load DNS cache from file"""
        try:
            if Path(self.cache_file).exists():
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    # Only load recent entries (last 5 minutes)
                    cutoff = time.time() - 300
                    self.cache = {
                        k: v for k, v in data.items()
                        if v.get('timestamp', 0) > cutoff
                    }
                logger.info(f"Loaded {len(self.cache)} cached DNS entries")
        except Exception as e:
            logger.warning(f"Could not load DNS cache: {e}")
    
    def save_cache(self):
        """Save DNS cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            logger.warning(f"Could not save DNS cache: {e}")
    
    def resolve_hostname(self, hostname: str) -> Optional[str]:
        """Resolve hostname using cache and static mappings"""
        # Check static mappings first
        if hostname in self.static_mappings:
            target = self.static_mappings[hostname]
            if target == "host-gateway":
                return self.get_host_gateway_ip()
            return target
        
        # Check cache
        if hostname in self.cache:
            entry = self.cache[hostname]
            if time.time() - entry.get('timestamp', 0) < 60:  # 1 minute TTL
                return entry.get('ip')
        
        # Perform resolution
        try:
            ip = socket.gethostbyname(hostname)
            self.cache[hostname] = {
                'ip': ip,
                'timestamp': time.time()
            }
            logger.info(f"Resolved {hostname} → {ip}")
            return ip
        except socket.gaierror:
            logger.warning(f"Could not resolve {hostname}")
            return None
    
    def get_host_gateway_ip(self) -> str:
        """Get the host gateway IP (Docker host)"""
        try:
            # Try to resolve host.docker.internal
            return socket.gethostbyname("host.docker.internal")
        except:
            # Fallback: parse from route table
            try:
                import subprocess
                result = subprocess.run(['ip', 'route'], capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if 'default via' in line:
                        return line.split()[2]
            except:
                pass
            
            # Final fallback
            return "172.17.0.1"
    
    def update_hosts_file(self):
        """Update /etc/hosts with our mappings"""
        try:
            entries = ["# AutoBot Local DNS Resolver"]
            
            # Add static mappings
            for hostname, target in self.static_mappings.items():
                if target == "host-gateway":
                    ip = self.get_host_gateway_ip()
                    entries.append(f"{ip}\t{hostname}")
                elif not target.startswith("autobot-"):  # Don't map container names
                    try:
                        ip = socket.gethostbyname(target)
                        entries.append(f"{ip}\t{hostname}")
                    except:
                        pass
            
            # Add cached entries
            for hostname, entry in self.cache.items():
                if hostname not in self.static_mappings:
                    entries.append(f"{entry['ip']}\t{hostname}")
            
            # Write to hosts file
            with open(self.hosts_file, 'w') as f:
                f.write('\n'.join(entries))
            
            logger.info(f"Updated hosts file with {len(entries)-1} entries")
            
        except Exception as e:
            logger.error(f"Could not update hosts file: {e}")
    
    async def refresh_cache(self):
        """Refresh DNS cache periodically"""
        while True:
            try:
                # Resolve common hostnames
                hostnames_to_check = [
                    "host.docker.internal",
                    "redis", 
                    "autobot-frontend",
                    "autobot-ai-stack",
                    "autobot-npu-worker"
                ]
                
                for hostname in hostnames_to_check:
                    self.resolve_hostname(hostname)
                
                self.update_hosts_file()
                self.save_cache()
                
                await asyncio.sleep(30)  # Refresh every 30 seconds
                
            except Exception as e:
                logger.error(f"Error refreshing DNS cache: {e}")
                await asyncio.sleep(10)
    
    def start_background_refresh(self):
        """Start background cache refresh"""
        def run_refresh():
            asyncio.new_event_loop().run_until_complete(self.refresh_cache())
        
        thread = threading.Thread(target=run_refresh, daemon=True)
        thread.start()
        logger.info("Started background DNS cache refresh")

def install_resolver():
    """Install the DNS resolver in the container"""
    resolver = LocalDNSResolver()
    
    # Start background refresh
    resolver.start_background_refresh()
    
    # Initial resolution
    logger.info("🚀 Local DNS Resolver initialized")
    
    # Keep the process alive
    try:
        while True:
            time.sleep(60)
            logger.debug("DNS resolver running...")
    except KeyboardInterrupt:
        logger.info("DNS resolver stopped")

if __name__ == "__main__":
    install_resolver()