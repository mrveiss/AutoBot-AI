#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Daily Health Check
Runs 7-point checklist and posts findings to MVA-12
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class HealthCheck:
    def __init__(self):
        self.results = {}
        self.issues = []
        self.backend_url = os.getenv("AUTOBOT_BACKEND_URL", "http://10.255.255.254:8001")
        self.chromadb_url = os.getenv("CHROMADB_URL", "http://localhost:8100")
        self.slm_url = os.getenv("SLM_URL", "http://localhost:8000")

    def check_service_status(self):
        """Check 1: Services up"""
        logger.info("Checking service status...")
        services = [
            "autobot-backend.service",
            "autobot-chromadb.service",
            "autobot-slm-backend.service",
            "autobot-celery.service",
            "autobot-celery-beat.service",
            "autobot-npu-worker.service",
            "autobot-tts-worker.service",
        ]

        all_running = True
        failed_services = []

        for service in services:
            try:
                result = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True, timeout=5)
                is_running = result.returncode == 0
                if not is_running:
                    all_running = False
                    failed_services.append(service)
            except Exception as e:
                logger.error(f"Error checking {service}: {e}")
                all_running = False
                failed_services.append(f"{service} (check failed)")

        self.results["services_up"] = {
            "status": "OK" if all_running else "FAILED",
            "failed_services": failed_services,
            "timestamp": datetime.now().isoformat(),
        }

        if not all_running:
            self.issues.append(f"Services down: {', '.join(failed_services)}")

        return all_running

    def check_backend_api(self):
        """Check 2: Backend API responding"""
        logger.info("Checking backend API...")
        try:
            response = requests.get(f"{self.backend_url}/api/health", timeout=5)
            is_healthy = response.status_code == 200
            self.results["backend_api"] = {
                "status": "OK" if is_healthy else f"FAILED ({response.status_code})",
                "timestamp": datetime.now().isoformat(),
            }
            if not is_healthy:
                self.issues.append(f"Backend API returned {response.status_code}")
            return is_healthy
        except Exception as e:
            logger.error(f"Backend API check failed: {e}")
            self.results["backend_api"] = {"status": "FAILED", "error": str(e), "timestamp": datetime.now().isoformat()}
            self.issues.append(f"Backend API unreachable: {e}")
            return False

    def check_chromadb(self):
        """Check 3: ChromaDB status"""
        logger.info("Checking ChromaDB...")
        try:
            # ChromaDB health endpoint
            response = requests.get(f"{self.chromadb_url}/api/v2/heartbeat", timeout=5)
            is_healthy = response.status_code == 200
            self.results["chromadb"] = {
                "status": "OK" if is_healthy else f"FAILED ({response.status_code})",
                "timestamp": datetime.now().isoformat(),
            }
            if not is_healthy:
                self.issues.append(f"ChromaDB returned {response.status_code}")
            return is_healthy
        except Exception as e:
            logger.error(f"ChromaDB check failed: {e}")
            self.results["chromadb"] = {"status": "FAILED", "error": str(e), "timestamp": datetime.now().isoformat()}
            self.issues.append(f"ChromaDB unreachable: {e}")
            return False

    def check_slm_health(self):
        """Check 4: SLM health"""
        logger.info("Checking SLM health...")
        try:
            response = requests.get(f"{self.slm_url}/api/health", timeout=5)
            is_healthy = response.status_code == 200
            self.results["slm_health"] = {
                "status": "OK" if is_healthy else f"FAILED ({response.status_code})",
                "timestamp": datetime.now().isoformat(),
            }
            if not is_healthy:
                self.issues.append(f"SLM health check returned {response.status_code}")
            return is_healthy
        except Exception as e:
            logger.error(f"SLM health check failed: {e}")
            self.results["slm_health"] = {"status": "FAILED", "error": str(e), "timestamp": datetime.now().isoformat()}
            self.issues.append(f"SLM unreachable: {e}")
            return False

    def check_error_logs(self):
        """Check 5: Error logs (last 24h via journalctl)"""
        logger.info("Checking error logs...")

        try:
            # Use journalctl to get only the last 24h of error-priority entries for the backend service.
            # This avoids the previous bug where cutoff_time was computed but never applied to the file scan,
            # causing ALL historical errors to be counted instead of only the last 24 hours.
            result = subprocess.run(
                [
                    "journalctl",
                    "-u",
                    "autobot-backend.service",
                    "--since",
                    "24 hours ago",
                    "--no-pager",
                    "-q",
                    "-p",
                    "err",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            lines = [ln for ln in result.stdout.strip().split("\n") if ln] if result.stdout.strip() else []
            error_count = len(lines)
            recent_errors = [ln[:100] for ln in lines[-5:]] if lines else []

            has_errors = error_count > 20
            self.results["error_logs"] = {
                "status": "WARNING" if has_errors else "OK",
                "error_count_24h": error_count,
                "recent_errors": recent_errors,
                "timestamp": datetime.now().isoformat(),
            }

            if has_errors:
                self.issues.append(f"High error rate: {error_count} errors in last 24h")

            return not has_errors
        except Exception as e:
            logger.error(f"Error log check failed: {e}")
            self.results["error_logs"] = {"status": "FAILED", "error": str(e), "timestamp": datetime.now().isoformat()}
            return False

    def check_disk_usage(self):
        """Check 6: Disk usage"""
        logger.info("Checking disk usage...")
        try:
            result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().split("\n")

            if len(lines) < 2:
                self.results["disk_usage"] = {
                    "status": "FAILED",
                    "error": "Could not parse disk output",
                    "timestamp": datetime.now().isoformat(),
                }
                return False

            # Parse the second line (root filesystem)
            parts = lines[1].split()
            used_percent = int(parts[4].rstrip("%"))
            available = parts[3]

            is_healthy = used_percent < 85  # Alert if > 85%
            self.results["disk_usage"] = {
                "status": "OK" if is_healthy else "WARNING",
                "used_percent": used_percent,
                "available": available,
                "timestamp": datetime.now().isoformat(),
            }

            if not is_healthy:
                self.issues.append(f"Disk usage high: {used_percent}% used")

            return is_healthy
        except Exception as e:
            logger.error(f"Disk usage check failed: {e}")
            self.results["disk_usage"] = {"status": "FAILED", "error": str(e), "timestamp": datetime.now().isoformat()}
            return False

    def check_redis_connectivity(self):
        """Check 7: Redis connectivity"""
        logger.info("Checking Redis connectivity...")
        try:
            import redis

            r = redis.Redis(host="localhost", port=6379, db=0, socket_connect_timeout=5)
            r.ping()
            self.results["redis"] = {"status": "OK", "timestamp": datetime.now().isoformat()}
            return True
        except Exception as e:
            logger.error(f"Redis check failed: {e}")
            self.results["redis"] = {"status": "FAILED", "error": str(e), "timestamp": datetime.now().isoformat()}
            self.issues.append(f"Redis unreachable: {e}")
            return False

    def run_all_checks(self):
        """Run all health checks"""
        logger.info("Starting AutoBot health check...")

        checks = [
            self.check_service_status,
            self.check_backend_api,
            self.check_chromadb,
            self.check_slm_health,
            self.check_error_logs,
            self.check_disk_usage,
            self.check_redis_connectivity,
        ]

        for check in checks:
            try:
                check()
            except Exception as e:
                logger.error(f"Check {check.__name__} failed: {e}")

        return self.results, self.issues

    def format_report(self):
        """Format results for posting"""
        report = "## AutoBot Daily Health Check\n\n"
        report += f"**Timestamp:** {datetime.now().isoformat()}\n\n"

        # Summary
        all_ok = all(v.get("status") == "OK" for v in self.results.values())
        report += f"**Overall Status:** {'✅ HEALTHY' if all_ok else '⚠️ ISSUES DETECTED'}\n\n"

        # Details
        report += "### Checklist Results\n\n"
        for check_name, result in self.results.items():
            status = result.get("status", "UNKNOWN")
            emoji = "✅" if status == "OK" else "⚠️" if status == "WARNING" else "❌"
            report += f"{emoji} **{check_name.replace('_', ' ').title()}**: {status}\n"
            if "error" in result:
                report += f"   - Error: {result['error']}\n"
            if "failed_services" in result and result["failed_services"]:
                report += f"   - Failed: {', '.join(result['failed_services'])}\n"

        # Issues
        if self.issues:
            report += "\n### Issues Found\n\n"
            for issue in self.issues:
                report += f"- {issue}\n"
        else:
            report += "\n### Issues\n\nNo issues detected.\n"

        return report


def main():
    health_check = HealthCheck()
    results, issues = health_check.run_all_checks()

    report = health_check.format_report()
    print(report)

    # Save report
    report_file = Path("/tmp/autobot-health-check.md")
    report_file.write_text(report)
    logger.info(f"Report saved to {report_file}")

    # Return exit code based on issues
    return 0 if not issues else 1


if __name__ == "__main__":
    exit(main())
