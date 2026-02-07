#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DNS Cache Service for AutoBot
Runs on host to provide fast DNS resolution for Docker containers
"""

import asyncio
import json
import logging
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DNSCacheService:
    def __init__(
        self,
        cache_file: str = "/tmp/autobot-dns-cache.json",
        refresh_interval: int = 30,
    ):
        self.cache_file = Path(cache_file)
        self.refresh_interval = refresh_interval
        self.cache: Dict[str, Dict] = {}

        # Key hostnames to resolve
        self.hostnames = {
            "host.docker.internal": {"priority": "high", "port_checks": [8001]},
            "localhost": {"priority": "high", "port_checks": [8001, 6379]},
            "redis": {"priority": "medium", "port_checks": [6379]},
            "autobot-frontend": {"priority": "medium", "port_checks": [5173]},
            "autobot-redis": {"priority": "medium", "port_checks": [6379]},
            "autobot-ai-stack": {"priority": "low", "port_checks": [8080]},
            "autobot-npu-worker": {"priority": "low", "port_checks": [8081]},
        }

        self.load_cache()

    def load_cache(self):
        """Load existing cache from disk"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    # Filter out old entries (older than 5 minutes)
                    cutoff = time.time() - 300
                    self.cache = {
                        k: v for k, v in data.items() if v.get("timestamp", 0) > cutoff
                    }
                logger.info("Loaded %s cached DNS entries", len(self.cache))
        except Exception as e:
            logger.warning("Could not load DNS cache: %s", e)
            self.cache = {}

    def save_cache(self):
        """Save cache to disk"""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error("Could not save DNS cache: %s", e)

    async def resolve_hostname(self, hostname: str, config: Dict) -> Dict:
        """Resolve a hostname and check port connectivity"""
        result = {
            "hostname": hostname,
            "timestamp": time.time(),
            "resolved_ip": None,
            "resolution_time_ms": 0,
            "ports": {},
            "status": "unknown",
        }

        # DNS Resolution
        start_time = time.time()
        try:
            ip = socket.gethostbyname(hostname)
            resolution_time = (time.time() - start_time) * 1000

            result.update(
                {
                    "resolved_ip": ip,
                    "resolution_time_ms": round(resolution_time, 2),
                    "status": "resolved",
                }
            )

            logger.info("✓ %s → %s (%.1fms)", hostname, ip, resolution_time)

        except socket.gaierror as e:
            result.update(
                {
                    "status": "failed",
                    "error": str(e),
                    "resolution_time_ms": round((time.time() - start_time) * 1000, 2),
                }
            )
            logger.warning("✗ %s DNS failed: %s", hostname, e)
            return result

        # Port Connectivity Checks
        for port in config.get("port_checks", []):
            port_start = time.time()
            try:
                # Quick TCP connection test
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)  # 2-second timeout
                connection_result = sock.connect_ex((ip, port))
                sock.close()

                port_time = (time.time() - port_start) * 1000
                result["ports"][port] = {
                    "status": "open" if connection_result == 0 else "closed",
                    "response_time_ms": round(port_time, 2),
                }

            except Exception as e:
                result["ports"][port] = {
                    "status": "error",
                    "error": str(e),
                    "response_time_ms": round((time.time() - port_start) * 1000, 2),
                }

        return result

    async def refresh_cache(self):
        """Refresh DNS cache for all hostnames"""
        logger.info("🔄 Refreshing DNS cache...")
        start_time = time.time()

        # Group by priority for efficient processing
        high_priority = [
            h for h, c in self.hostnames.items() if c["priority"] == "high"
        ]
        medium_priority = [
            h for h, c in self.hostnames.items() if c["priority"] == "medium"
        ]
        low_priority = [h for h, c in self.hostnames.items() if c["priority"] == "low"]

        # Process high priority first, then others concurrently
        for hostname in high_priority:
            config = self.hostnames[hostname]
            self.cache[hostname] = await self.resolve_hostname(hostname, config)

        # Process medium and low priority concurrently
        tasks = []
        for hostname in medium_priority + low_priority:
            config = self.hostnames[hostname]
            tasks.append(self.resolve_hostname(hostname, config))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, hostname in enumerate(medium_priority + low_priority):
                if not isinstance(results[i], Exception):
                    self.cache[hostname] = results[i]

        total_time = time.time() - start_time
        logger.info(
            f"✅ DNS cache refreshed in {total_time:.1f}s ({len(self.cache)} entries)"
        )

        self.save_cache()

    def get_cache_status(self) -> Dict:
        """Get current cache status"""
        now = time.time()
        fresh_entries = sum(
            1
            for entry in self.cache.values()
            if now - entry.get("timestamp", 0) < self.refresh_interval * 2
        )

        return {
            "total_entries": len(self.cache),
            "fresh_entries": fresh_entries,
            "last_refresh": datetime.fromtimestamp(
                max(entry.get("timestamp", 0) for entry in self.cache.values())
                if self.cache
                else 0
            ).isoformat(),
            "cache_file": str(self.cache_file),
            "refresh_interval": self.refresh_interval,
        }

    def generate_hosts_entries(self) -> str:
        """Generate /etc/hosts entries from cache"""
        entries = []
        entries.append(
            "# AutoBot DNS Cache - Generated at " + datetime.now().isoformat()
        )

        for hostname, data in self.cache.items():
            ip = data.get("resolved_ip")
            if ip and data.get("status") == "resolved":
                entries.append(f"{ip}\t{hostname}")

        return "\n".join(entries)

    async def run_daemon(self):
        """Run DNS cache service daemon"""
        logger.info(
            "🚀 Starting DNS Cache Service (refresh every %ss)", self.refresh_interval
        )

        # Initial cache refresh
        await self.refresh_cache()

        # Periodic refresh
        while True:
            try:
                await asyncio.sleep(self.refresh_interval)
                await self.refresh_cache()

                # Log cache status every 5 minutes
                if int(time.time()) % 300 == 0:
                    status = self.get_cache_status()
                    logger.info(
                        "📊 Cache: %s/%s fresh entries",
                        status["fresh_entries"],
                        status["total_entries"],
                    )

            except KeyboardInterrupt:
                logger.info("🛑 DNS Cache Service stopped")
                break
            except Exception as e:
                logger.error("❌ Error in DNS cache refresh: %s", e)
                await asyncio.sleep(5)  # Wait before retry


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot DNS Cache Service")
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Refresh interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--cache-file", default="/tmp/autobot-dns-cache.json", help="Cache file path"
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--status", action="store_true", help="Show cache status and exit"
    )
    parser.add_argument(
        "--hosts", action="store_true", help="Generate /etc/hosts entries and exit"
    )

    args = parser.parse_args()

    service = DNSCacheService(
        cache_file=args.cache_file, refresh_interval=args.interval
    )

    if args.status:
        status = service.get_cache_status()
        print(json.dumps(status, indent=2))
        return

    if args.hosts:
        print(service.generate_hosts_entries())
        return

    if args.once:
        await service.refresh_cache()
        return

    # Run daemon
    await service.run_daemon()


if __name__ == "__main__":
    asyncio.run(main())
