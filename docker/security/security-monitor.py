#!/usr/bin/env python3
"""
Enhanced Security Monitor for AutoBot Sandbox

Real-time monitoring of sandbox security, resource usage, and anomaly detection.
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import psutil


class SecurityMonitor:
    """
    Advanced security monitoring for the sandbox environment.

    Features:
    - Resource usage monitoring
    - Process anomaly detection
    - File system integrity checking
    - Network activity monitoring
    - Security event logging
    """

    def __init__(self, config_path: str = "/sandbox/config/monitor.json"):
        """Initialize the security monitor"""
        self.config_path = config_path
        self.running = False
        self.start_time = time.time()

        # Load configuration
        self.config = self._load_config()

        # Set up logging
        self._setup_logging()

        # Initialize monitoring data
        self.baseline_metrics = {}
        self.alert_history = []
        self.process_whitelist = set()

        # Security thresholds
        self.cpu_threshold = self.config.get("cpu_threshold", 80.0)
        self.memory_threshold = self.config.get("memory_threshold", 80.0)
        self.disk_threshold = self.config.get("disk_threshold", 90.0)
        self.network_threshold = self.config.get("network_threshold", 1000000)  # 1MB/s

        self.logger.info("Security monitor initialized")

    def _load_config(self) -> Dict:
        """Load monitoring configuration"""
        default_config = {
            "monitor_interval": 5,
            "log_level": "INFO",
            "enable_network_monitoring": True,
            "enable_file_monitoring": True,
            "enable_process_monitoring": True,
            "alert_cooldown": 60,
            "max_alerts_per_hour": 10,
        }

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                return {**default_config, **config}
        except Exception as e:
            print(f"Failed to load config: {e}, using defaults")

        return default_config

    def _setup_logging(self):
        """Set up security logging"""
        log_level = getattr(logging, self.config.get("log_level", "INFO"))

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("/var/log/autobot/security-monitor.log"),
                logging.StreamHandler(sys.stdout),
            ],
        )

        self.logger = logging.getLogger("SecurityMonitor")

    def start_monitoring(self):
        """Start the security monitoring loop"""
        self.running = True
        self.logger.info("Starting security monitoring")

        # Establish baseline metrics
        self._establish_baseline()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            while self.running:
                self._monitor_cycle()
                time.sleep(self.config.get("monitor_interval", 5))

        except Exception as e:
            self.logger.error(f"Monitoring error: {e}")
        finally:
            self.logger.info("Security monitoring stopped")

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _establish_baseline(self):
        """Establish baseline metrics for anomaly detection"""
        self.logger.info("Establishing baseline metrics...")

        # Collect initial metrics
        cpu_samples = []
        memory_samples = []

        for _ in range(10):  # 10 samples over 50 seconds
            cpu_samples.append(psutil.cpu_percent(interval=1))
            memory_samples.append(psutil.virtual_memory().percent)
            time.sleep(4)

        self.baseline_metrics = {
            "cpu_baseline": sum(cpu_samples) / len(cpu_samples),
            "memory_baseline": sum(memory_samples) / len(memory_samples),
            "process_count_baseline": len(psutil.pids()),
            "established_at": time.time(),
        }

        self.logger.info(f"Baseline established: {self.baseline_metrics}")

    def _monitor_cycle(self):
        """Single monitoring cycle"""
        try:
            # Collect current metrics
            metrics = self._collect_metrics()

            # Check for anomalies
            anomalies = self._detect_anomalies(metrics)

            # Log and alert if necessary
            if anomalies:
                self._handle_anomalies(anomalies, metrics)

            # Update monitoring log
            self._log_metrics(metrics)

        except Exception as e:
            self.logger.error(f"Monitor cycle error: {e}")

    def _collect_metrics(self) -> Dict:
        """Collect current system metrics"""
        try:
            # System metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/sandbox")

            # Network metrics
            network = psutil.net_io_counters()

            # Process metrics
            processes = []
            for proc in psutil.process_iter(
                ["pid", "name", "username", "cpu_percent", "memory_percent"]
            ):
                try:
                    proc_info = proc.info
                    if proc_info["username"] in ["sandbox", "sandbox-restricted"]:
                        processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return {
                "timestamp": time.time(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used": memory.used,
                "disk_percent": disk.percent,
                "disk_used": disk.used,
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv,
                "process_count": len(processes),
                "processes": processes,
                "uptime": time.time() - self.start_time,
            }

        except Exception as e:
            self.logger.error(f"Metrics collection error: {e}")
            return {}

    def _detect_anomalies(self, metrics: Dict) -> List[Dict]:
        """Detect security and performance anomalies"""
        anomalies = []

        if not metrics:
            return anomalies

        # CPU usage anomaly
        if metrics.get("cpu_percent", 0) > self.cpu_threshold:
            anomalies.append(
                {
                    "type": "high_cpu_usage",
                    "severity": "medium",
                    "value": metrics["cpu_percent"],
                    "threshold": self.cpu_threshold,
                    "message": f"CPU usage {metrics['cpu_percent']:.1f}% exceeds threshold {self.cpu_threshold}%",
                }
            )

        # Memory usage anomaly
        if metrics.get("memory_percent", 0) > self.memory_threshold:
            anomalies.append( { "type": "high_memory_usage",
    "severity": "medium",
    "value": metrics["memory_percent"],
    "threshold": self.memory_threshold,
    "message": f"Memory usage {metrics['memory_percent']:.1f}% exceeds threshold {self.memory_threshold}%",
     } )

        # Disk usage anomaly
        if metrics.get("disk_percent", 0) > self.disk_threshold:
            anomalies.append(
                {
                    "type": "high_disk_usage",
                    "severity": "high",
                    "value": metrics["disk_percent"],
                    "threshold": self.disk_threshold,
                    "message": f"Disk usage {metrics['disk_percent']:.1f}% exceeds threshold {self.disk_threshold}%",
                }
            )

        # Process count anomaly
        baseline_procs = self.baseline_metrics.get("process_count_baseline", 10)
        current_procs = metrics.get("process_count", 0)
        if current_procs > baseline_procs * 2:
            anomalies.append(
                {
                    "type": "excessive_processes",
                    "severity": "medium",
                    "value": current_procs,
                    "threshold": baseline_procs * 2,
                    "message": f"Process count {current_procs} significantly exceeds baseline {baseline_procs}",
                }
            )

        # Suspicious process detection
        for proc in metrics.get("processes", []):
            if self._is_suspicious_process(proc):
                anomalies.append(
                    {
                        "type": "suspicious_process",
                        "severity": "high",
                        "value": proc,
                        "message": f"Suspicious process detected: {proc['name']} (PID: {proc['pid']})",
                    }
                )

        return anomalies

    def _is_suspicious_process(self, proc: Dict) -> bool:
        """Check if a process is suspicious"""
        suspicious_names = [
            "nc",
            "netcat",
            "ncat",  # Network tools
            "tcpdump",
            "wireshark",  # Network sniffing
            "nmap",
            "masscan",  # Network scanning
            "ssh",
            "scp",
            "rsync",  # Remote access
            "wget",
            "curl",  # Only suspicious if downloading executables
            "python",
            "python3",  # Check for suspicious scripts
            "perl",
            "ruby",
            "php",  # Scripting languages
            "gcc",
            "make",
            "cmake",  # Compilers
            "su",
            "sudo",
            "doas",  # Privilege escalation
        ]

        proc_name = proc.get("name", "").lower()

        # Check against suspicious names
        if proc_name in suspicious_names:
            # Additional checks for legitimate use
            if proc_name in ["python", "python3"]:
                # Allow if it's our security monitor
                return "security-monitor" not in str(proc)
            return True

        # Check for high CPU usage
        if proc.get("cpu_percent", 0) > 50:
            return True

        # Check for high memory usage
        if proc.get("memory_percent", 0) > 25:
            return True

        return False

    def _handle_anomalies(self, anomalies: List[Dict], metrics: Dict):
        """Handle detected anomalies"""
        for anomaly in anomalies:
            severity = anomaly.get("severity", "medium")

            # Log the anomaly
            log_method = getattr(
                self.logger,
                severity if severity in ["info", "warning", "error"] else "warning",
            )
            log_method(f"ANOMALY DETECTED: {anomaly['message']}")

            # Store in alert history
            alert = {**anomaly, "timestamp": time.time(), "metrics_snapshot": metrics}
            self.alert_history.append(alert)

            # Keep alert history size manageable
            if len(self.alert_history) > 100:
                self.alert_history = self.alert_history[-50:]

            # Take action based on severity
            if severity == "high":
                self._take_emergency_action(anomaly)

    def _take_emergency_action(self, anomaly: Dict):
        """Take emergency action for high-severity anomalies"""
        action_type = anomaly.get("type")

        if action_type == "suspicious_process":
            # Log detailed process information
            proc = anomaly.get("value", {})
            self.logger.critical(f"EMERGENCY: Suspicious process - {proc}")

            # Could implement process termination here
            # os.kill(proc.get("pid"), signal.SIGTERM)

        elif action_type == "high_disk_usage":
            # Clean up temporary files
            self._cleanup_temp_files()

        self.logger.critical(f"Emergency action taken for: {anomaly['message']}")

    def _cleanup_temp_files(self):
        """Clean up temporary files to free disk space"""
        try:
            temp_dirs = ["/tmp", "/var/tmp", "/sandbox/tmp"]

            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    for file_path in Path(temp_dir).glob("*"):
                        try:
                            if (
                                file_path.is_file()
                                and file_path.stat().st_mtime < time.time() - 3600
                            ):  # 1 hour old
                                file_path.unlink()
                        except Exception:
                            continue

            self.logger.info("Temporary file cleanup completed")

        except Exception as e:
            self.logger.error(f"Temp file cleanup error: {e}")

    def _log_metrics(self, metrics: Dict):
        """Log metrics to file for analysis"""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(
                    metrics.get("timestamp", time.time())
                ).isoformat(),
                "cpu_percent": metrics.get("cpu_percent"),
                "memory_percent": metrics.get("memory_percent"),
                "disk_percent": metrics.get("disk_percent"),
                "process_count": metrics.get("process_count"),
                "uptime": metrics.get("uptime"),
            }

            # Write to metrics log
            with open("/var/log/autobot/security-metrics.jsonl", "a") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            self.logger.error(f"Metrics logging error: {e}")

    def health_check(self) -> bool:
        """Perform health check for Docker health check"""
        try:
            # Check if monitoring is running
            if not self.running:
                return False

            # Check system resources
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/sandbox").percent

            # Health check fails if resources are critically low
            if disk > 95 or memory > 95 or cpu > 95:
                return False

            # Check for critical alerts in last 5 minutes
            recent_alerts = [
                alert
                for alert in self.alert_history
                if time.time() - alert.get("timestamp", 0) < 300
                and alert.get("severity") == "high"
            ]

            if len(recent_alerts) > 3:  # Too many recent critical alerts
                return False

            return True

        except Exception:
            return False

    def get_status(self) -> Dict:
        """Get current monitoring status"""
        try:
            current_metrics = self._collect_metrics()

            return {
                "status": "running" if self.running else "stopped",
                "uptime": time.time() - self.start_time,
                "current_metrics": current_metrics,
                "baseline_metrics": self.baseline_metrics,
                "recent_alerts": self.alert_history[-10:],  # Last 10 alerts
                "health": self.health_check(),
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="AutoBot Security Monitor")
    parser.add_argument(
        "--config",
        default="/sandbox/config/monitor.json",
        help="Configuration file path",
    )
    parser.add_argument(
        "--health-check", action="store_true", help="Perform health check and exit"
    )
    parser.add_argument("--status", action="store_true", help="Show status and exit")

    args = parser.parse_args()

    monitor = SecurityMonitor(args.config)

    if args.health_check:
        sys.exit(0 if monitor.health_check() else 1)

    if args.status:
        status = monitor.get_status()
        print(json.dumps(status, indent=2))
        sys.exit(0)

    # Start monitoring
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
