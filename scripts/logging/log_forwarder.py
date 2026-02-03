#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Unified Log Forwarding Service
=======================================

Forwards logs from AutoBot services to external logging systems.
Supports multiple destinations: Seq, Elasticsearch, Loki, Syslog, Webhooks.

Features:
- Multi-destination log forwarding
- Docker container log streaming
- Backend process log monitoring
- Configurable via API/GUI
- Batched sending for efficiency
- Automatic retry with backoff
- Health checks for destinations

Usage:
    python scripts/logging/log_forwarder.py --start
    python scripts/logging/log_forwarder.py --config /path/to/config.json
    python scripts/logging/log_forwarder.py --test-destinations
"""

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

import aiohttp
import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None


class DestinationType(str, Enum):
    """Supported log forwarding destinations."""
    SEQ = "seq"
    ELASTICSEARCH = "elasticsearch"
    LOKI = "loki"
    SYSLOG = "syslog"
    WEBHOOK = "webhook"
    FILE = "file"


class DestinationScope(str, Enum):
    """Scope for log forwarding destination configuration."""
    GLOBAL = "global"  # Applies to all hosts
    PER_HOST = "per_host"  # Applies only to specific hosts


class SyslogProtocol(str, Enum):
    """Syslog transport protocol."""
    UDP = "udp"
    TCP = "tcp"
    TCP_TLS = "tcp_tls"  # TCP with SSL/TLS


class LogLevel(str, Enum):
    """Standard log levels."""
    DEBUG = "Debug"
    INFO = "Information"
    WARNING = "Warning"
    ERROR = "Error"
    CRITICAL = "Fatal"


@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: str
    level: str
    message: str
    source: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_seq_format(self) -> Dict[str, Any]:
        """Convert to Seq CLEF format."""
        return {
            "@t": self.timestamp,
            "@l": self.level,
            "@mt": self.message,
            "Source": self.source,
            **self.properties
        }

    def to_elasticsearch_format(self) -> Dict[str, Any]:
        """Convert to Elasticsearch format."""
        return {
            "@timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "source": self.source,
            "fields": self.properties
        }

    def to_loki_format(self) -> Dict[str, Any]:
        """Convert to Loki/Grafana format."""
        return {
            "streams": [{
                "stream": {
                    "source": self.source,
                    "level": self.level,
                    **{k: str(v) for k, v in self.properties.items() if isinstance(v, (str, int, float, bool))}
                },
                "values": [[str(int(datetime.fromisoformat(self.timestamp.replace('Z', '+00:00')).timestamp() * 1e9)), self.message]]
            }]
        }

    def to_syslog_format(self) -> str:
        """Convert to syslog format."""
        severity_map = {
            "Debug": 7, "Information": 6, "Warning": 4, "Error": 3, "Fatal": 2
        }
        severity = severity_map.get(self.level, 6)
        facility = 1  # user-level messages
        priority = facility * 8 + severity
        return f"<{priority}>{self.timestamp} {self.source}: {self.message}"


@dataclass
class DestinationConfig:
    """Configuration for a log destination."""
    name: str
    type: DestinationType
    enabled: bool = True
    url: Optional[str] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    index: Optional[str] = None  # For Elasticsearch
    file_path: Optional[str] = None  # For file destination
    min_level: str = "Information"
    batch_size: int = 10
    batch_timeout: float = 5.0
    retry_count: int = 3
    retry_delay: float = 1.0
    # Scope configuration (global vs per-host)
    scope: DestinationScope = DestinationScope.GLOBAL
    target_hosts: List[str] = field(default_factory=list)  # For per_host scope
    # Syslog-specific options
    syslog_protocol: SyslogProtocol = SyslogProtocol.UDP
    ssl_verify: bool = True  # Verify SSL certificates for TCP_TLS
    ssl_ca_cert: Optional[str] = None  # Path to CA certificate
    ssl_client_cert: Optional[str] = None  # Path to client certificate (mutual TLS)
    ssl_client_key: Optional[str] = None  # Path to client key (mutual TLS)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DestinationConfig":
        """Create config from dictionary."""
        # Parse scope
        scope_str = data.get("scope", "global")
        try:
            scope = DestinationScope(scope_str)
        except ValueError:
            scope = DestinationScope.GLOBAL

        # Parse syslog protocol
        protocol_str = data.get("syslog_protocol", "udp")
        try:
            syslog_protocol = SyslogProtocol(protocol_str)
        except ValueError:
            syslog_protocol = SyslogProtocol.UDP

        return cls(
            name=data.get("name", "unnamed"),
            type=DestinationType(data.get("type", "seq")),
            enabled=data.get("enabled", True),
            url=data.get("url"),
            api_key=data.get("api_key"),
            username=data.get("username"),
            password=data.get("password"),
            index=data.get("index", "autobot-logs"),
            file_path=data.get("file_path"),
            min_level=data.get("min_level", "Information"),
            batch_size=data.get("batch_size", 10),
            batch_timeout=data.get("batch_timeout", 5.0),
            retry_count=data.get("retry_count", 3),
            retry_delay=data.get("retry_delay", 1.0),
            scope=scope,
            target_hosts=data.get("target_hosts", []),
            syslog_protocol=syslog_protocol,
            ssl_verify=data.get("ssl_verify", True),
            ssl_ca_cert=data.get("ssl_ca_cert"),
            ssl_client_cert=data.get("ssl_client_cert"),
            ssl_client_key=data.get("ssl_client_key"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.type.value,
            "enabled": self.enabled,
            "url": self.url,
            "api_key": self.api_key,
            "username": self.username,
            "password": self.password,
            "index": self.index,
            "file_path": self.file_path,
            "min_level": self.min_level,
            "batch_size": self.batch_size,
            "batch_timeout": self.batch_timeout,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
            "scope": self.scope.value,
            "target_hosts": self.target_hosts,
            "syslog_protocol": self.syslog_protocol.value,
            "ssl_verify": self.ssl_verify,
            "ssl_ca_cert": self.ssl_ca_cert,
            "ssl_client_cert": self.ssl_client_cert,
            "ssl_client_key": self.ssl_client_key,
        }

    def to_dict_sanitized(self) -> Dict[str, Any]:
        """Convert to dictionary with sensitive fields masked for API responses."""
        data = self.to_dict()
        # Mask sensitive fields
        if data.get("api_key"):
            data["api_key"] = "****" + data["api_key"][-4:] if len(data["api_key"]) > 4 else "****"
        if data.get("password"):
            data["password"] = "****"
        return data

    def applies_to_host(self, hostname: str) -> bool:
        """Check if this destination applies to the given host."""
        if self.scope == DestinationScope.GLOBAL:
            return True
        # Per-host scope: check if hostname is in target_hosts
        if not self.target_hosts:
            return False
        # Support wildcards and exact matching
        for target in self.target_hosts:
            if target == "*":
                return True
            if target == hostname:
                return True
            # Simple wildcard matching (e.g., "vm-*" matches "vm-frontend")
            if target.endswith("*") and hostname.startswith(target[:-1]):
                return True
            if target.startswith("*") and hostname.endswith(target[1:]):
                return True
        return False


class LogDestination(ABC):
    """Abstract base class for log destinations."""

    def __init__(self, config: DestinationConfig):
        self.config = config
        self.logger = logging.getLogger(f"LogForwarder.{config.name}")
        self._healthy = True
        self._last_error: Optional[str] = None
        self._sent_count = 0
        self._failed_count = 0

    @abstractmethod
    def send(self, entries: List[LogEntry]) -> bool:
        """Send log entries to destination."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if destination is healthy."""
        pass

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.config.name,
            "type": self.config.type.value,
            "healthy": self._healthy,
            "last_error": self._last_error,
            "sent_count": self._sent_count,
            "failed_count": self._failed_count
        }


class SeqDestination(LogDestination):
    """Seq log destination."""

    def send(self, entries: List[LogEntry]) -> bool:
        if not self.config.url:
            return False

        try:
            headers = {
                "Content-Type": "application/vnd.serilog.clef",
                "User-Agent": "AutoBot-LogForwarder/1.0"
            }
            if self.config.api_key:
                headers["X-Seq-ApiKey"] = self.config.api_key

            # CLEF format: one JSON per line
            payload = "\n".join(json.dumps(e.to_seq_format()) for e in entries) + "\n"

            response = requests.post(
                f"{self.config.url.rstrip('/')}/api/events/raw",
                headers=headers,
                data=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                self._sent_count += len(entries)
                self._healthy = True
                return True
            else:
                self._last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                self._failed_count += len(entries)
                return False

        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            self._failed_count += len(entries)
            return False

    def health_check(self) -> bool:
        if not self.config.url:
            return False
        try:
            response = requests.get(f"{self.config.url.rstrip('/')}/api", timeout=5)
            self._healthy = response.status_code == 200
            return self._healthy
        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            return False


class ElasticsearchDestination(LogDestination):
    """Elasticsearch log destination."""

    def send(self, entries: List[LogEntry]) -> bool:
        if not self.config.url:
            return False

        try:
            headers = {"Content-Type": "application/x-ndjson"}
            auth = None
            if self.config.username and self.config.password:
                auth = (self.config.username, self.config.password)

            # Bulk format for Elasticsearch
            lines = []
            index_name = f"{self.config.index}-{datetime.now().strftime('%Y.%m.%d')}"
            for entry in entries:
                lines.append(json.dumps({"index": {"_index": index_name}}))
                lines.append(json.dumps(entry.to_elasticsearch_format()))

            payload = "\n".join(lines) + "\n"

            response = requests.post(
                f"{self.config.url.rstrip('/')}/_bulk",
                headers=headers,
                auth=auth,
                data=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                self._sent_count += len(entries)
                self._healthy = True
                return True
            else:
                self._last_error = f"HTTP {response.status_code}"
                self._failed_count += len(entries)
                return False

        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            self._failed_count += len(entries)
            return False

    def health_check(self) -> bool:
        if not self.config.url:
            return False
        try:
            auth = None
            if self.config.username and self.config.password:
                auth = (self.config.username, self.config.password)
            response = requests.get(f"{self.config.url.rstrip('/')}/_cluster/health", auth=auth, timeout=5)
            self._healthy = response.status_code == 200
            return self._healthy
        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            return False


class LokiDestination(LogDestination):
    """Grafana Loki log destination."""

    def _batch_entries_to_loki_payload(self, entries: List[LogEntry]) -> Dict[str, Any]:
        """Batch multiple log entries into a single Loki push payload.

        Groups entries by (source, level) to create efficient streams.
        """
        from collections import defaultdict
        from datetime import datetime

        # Group entries by stream labels (source + level)
        streams_dict = defaultdict(list)

        for entry in entries:
            # Create stream key from labels
            stream_key = (entry.source, entry.level)
            # Convert timestamp to nanoseconds
            ts_ns = str(int(datetime.fromisoformat(
                entry.timestamp.replace('Z', '+00:00')
            ).timestamp() * 1e9))
            streams_dict[stream_key].append([ts_ns, entry.message])

        # Build Loki payload with all streams
        streams = []
        for (source, level), values in streams_dict.items():
            streams.append({
                "stream": {"source": source, "level": level},
                "values": values
            })

        return {"streams": streams}

    def send(self, entries: List[LogEntry]) -> bool:
        if not self.config.url or not entries:
            return False

        try:
            headers = {"Content-Type": "application/json"}
            if self.config.username and self.config.password:
                import base64
                credentials = base64.b64encode(f"{self.config.username}:{self.config.password}".encode()).decode()
                headers["Authorization"] = f"Basic {credentials}"

            # Batch all entries into a single Loki push request
            payload = self._batch_entries_to_loki_payload(entries)

            response = requests.post(
                f"{self.config.url.rstrip('/')}/loki/api/v1/push",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code not in [200, 204]:
                self._last_error = f"HTTP {response.status_code}"
                self._failed_count += len(entries)
                return False

            self._sent_count += len(entries)
            self._healthy = True
            return True

        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            self._failed_count += len(entries)
            return False

    def health_check(self) -> bool:
        if not self.config.url:
            return False
        try:
            response = requests.get(f"{self.config.url.rstrip('/')}/ready", timeout=5)
            self._healthy = response.status_code == 200
            return self._healthy
        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            return False


class WebhookDestination(LogDestination):
    """Generic webhook log destination."""

    def send(self, entries: List[LogEntry]) -> bool:
        if not self.config.url:
            return False

        try:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            payload = {
                "logs": [e.to_elasticsearch_format() for e in entries],
                "source": "AutoBot",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

            response = requests.post(
                self.config.url,
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201, 202, 204]:
                self._sent_count += len(entries)
                self._healthy = True
                return True
            else:
                self._last_error = f"HTTP {response.status_code}"
                self._failed_count += len(entries)
                return False

        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            self._failed_count += len(entries)
            return False

    def health_check(self) -> bool:
        # Webhooks don't have standard health endpoints
        return self._healthy


class FileDestination(LogDestination):
    """File-based log destination."""

    def __init__(self, config: DestinationConfig):
        super().__init__(config)
        self._file_lock = threading.Lock()

    def send(self, entries: List[LogEntry]) -> bool:
        if not self.config.file_path:
            return False

        try:
            with self._file_lock:
                with open(self.config.file_path, "a", encoding="utf-8") as f:
                    for entry in entries:
                        f.write(json.dumps(entry.to_elasticsearch_format()) + "\n")

            self._sent_count += len(entries)
            self._healthy = True
            return True

        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            self._failed_count += len(entries)
            return False

    def health_check(self) -> bool:
        if not self.config.file_path:
            return False
        try:
            Path(self.config.file_path).parent.mkdir(parents=True, exist_ok=True)
            self._healthy = True
            return True
        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            return False


class SyslogDestination(LogDestination):
    """Syslog destination supporting UDP, TCP, and TCP with SSL/TLS."""

    def _parse_url(self) -> tuple:
        """Parse host and port from URL."""
        url = self.config.url
        # Remove protocol prefixes
        for prefix in ["syslog://", "udp://", "tcp://", "tcp+tls://", "tls://"]:
            url = url.replace(prefix, "")

        if ":" in url:
            host, port_str = url.rsplit(":", 1)
            port = int(port_str)
        else:
            host = url
            port = 514

        return host, port

    def _validate_cert_path(self, path: str) -> bool:
        """Validate certificate path is safe and accessible."""
        if not path:
            return True
        try:
            resolved = Path(path).resolve()
            # Security: Block path traversal attempts
            if ".." in path:
                return False
            # Allowed system directories for certificates
            system_dirs = [
                Path("/etc/ssl"),
                Path("/etc/pki"),
                Path("/usr/share/ca-certificates"),
                Path("/usr/local/share/ca-certificates"),
            ]
            # User directories
            user_dirs = [
                Path.home() / ".ssl",
                Path.home() / ".certs",
            ]
            # Project-relative certs directory (works regardless of project location)
            # Find project root by looking for known markers
            project_root = Path(__file__).resolve().parent
            while project_root != project_root.parent:
                if (project_root / "pyproject.toml").exists() or (project_root / "setup.py").exists():
                    break
                project_root = project_root.parent
            project_dirs = [
                project_root / "certs",
                project_root / "ssl",
                project_root / "certificates",
            ]
            all_allowed = system_dirs + user_dirs + project_dirs
            # Check if path is within allowed directories
            for allowed in all_allowed:
                try:
                    if allowed.exists() and str(resolved).startswith(str(allowed.resolve())):
                        return True
                except (OSError, PermissionError):
                    continue
            # Final check: file must exist and be readable
            return resolved.is_file() and os.access(resolved, os.R_OK)
        except (ValueError, OSError):
            return False

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for TLS connections."""
        context = ssl.create_default_context()

        # Configure certificate verification
        if not self.config.ssl_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        else:
            context.verify_mode = ssl.CERT_REQUIRED

        # Load CA certificate if provided (with path validation)
        if self.config.ssl_ca_cert:
            if not self._validate_cert_path(self.config.ssl_ca_cert):
                raise ValueError(f"Invalid CA certificate path: {self.config.ssl_ca_cert}")
            context.load_verify_locations(self.config.ssl_ca_cert)

        # Load client certificate for mutual TLS if provided (with path validation)
        if self.config.ssl_client_cert and self.config.ssl_client_key:
            if not self._validate_cert_path(self.config.ssl_client_cert):
                raise ValueError(f"Invalid client certificate path: {self.config.ssl_client_cert}")
            if not self._validate_cert_path(self.config.ssl_client_key):
                raise ValueError(f"Invalid client key path: {self.config.ssl_client_key}")
            context.load_cert_chain(
                certfile=self.config.ssl_client_cert,
                keyfile=self.config.ssl_client_key
            )

        return context

    def _send_udp(self, entries: List[LogEntry], host: str, port: int) -> bool:
        """Send logs via UDP."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for entry in entries:
                message = entry.to_syslog_format()
                sock.sendto(message.encode("utf-8"), (host, port))
                self._sent_count += 1
            return True
        finally:
            sock.close()

    def _send_tcp(self, entries: List[LogEntry], host: str, port: int, use_tls: bool = False) -> bool:
        """Send logs via TCP, optionally with TLS."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)

        try:
            if use_tls:
                context = self._create_ssl_context()
                # Wrap socket with SSL
                if self.config.ssl_verify:
                    sock = context.wrap_socket(sock, server_hostname=host)
                else:
                    sock = context.wrap_socket(sock)

            sock.connect((host, port))

            for entry in entries:
                # RFC 5425: Use octet counting for TCP syslog
                message = entry.to_syslog_format()
                # Format: <length> <message>
                framed_message = f"{len(message)} {message}"
                sock.sendall(framed_message.encode("utf-8"))
                self._sent_count += 1

            return True
        finally:
            sock.close()

    def send(self, entries: List[LogEntry]) -> bool:
        if not self.config.url:
            return False

        try:
            host, port = self._parse_url()
            protocol = self.config.syslog_protocol

            if protocol == SyslogProtocol.UDP:
                success = self._send_udp(entries, host, port)
            elif protocol == SyslogProtocol.TCP:
                success = self._send_tcp(entries, host, port, use_tls=False)
            elif protocol == SyslogProtocol.TCP_TLS:
                success = self._send_tcp(entries, host, port, use_tls=True)
            else:
                self._last_error = f"Unknown syslog protocol: {protocol}"
                return False

            if success:
                self._healthy = True
                return True
            return False

        except ssl.SSLError as e:
            self._last_error = f"SSL error: {e}"
            self._healthy = False
            self._failed_count += len(entries)
            return False
        except socket.timeout:
            self._last_error = "Connection timeout"
            self._healthy = False
            self._failed_count += len(entries)
            return False
        except ConnectionRefusedError:
            self._last_error = "Connection refused"
            self._healthy = False
            self._failed_count += len(entries)
            return False
        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            self._failed_count += len(entries)
            return False

    def health_check(self) -> bool:
        """Check connectivity to syslog server."""
        if not self.config.url:
            return False

        try:
            host, port = self._parse_url()
            protocol = self.config.syslog_protocol

            # UDP doesn't have reliable health checks
            if protocol == SyslogProtocol.UDP:
                return True

            # For TCP/TLS, try to establish a connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)

            try:
                if protocol == SyslogProtocol.TCP_TLS:
                    context = self._create_ssl_context()
                    if self.config.ssl_verify:
                        sock = context.wrap_socket(sock, server_hostname=host)
                    else:
                        sock = context.wrap_socket(sock)

                sock.connect((host, port))
                self._healthy = True
                return True
            finally:
                sock.close()

        except Exception as e:
            self._last_error = str(e)
            self._healthy = False
            return False


def create_destination(config: DestinationConfig) -> LogDestination:
    """Factory function to create destination instance."""
    destination_classes = {
        DestinationType.SEQ: SeqDestination,
        DestinationType.ELASTICSEARCH: ElasticsearchDestination,
        DestinationType.LOKI: LokiDestination,
        DestinationType.WEBHOOK: WebhookDestination,
        DestinationType.FILE: FileDestination,
        DestinationType.SYSLOG: SyslogDestination,
    }

    cls = destination_classes.get(config.type)
    if not cls:
        raise ValueError(f"Unknown destination type: {config.type}")

    return cls(config)


class LogForwarder:
    """Main log forwarding service."""

    def __init__(self, config_path: Optional[str] = None):
        self.project_root = Path(__file__).parent.parent.parent
        self.config_path = config_path or str(self.project_root / "config" / "log_forwarding.json")
        self.destinations: Dict[str, LogDestination] = {}
        self.log_queue: Queue = Queue(maxsize=10000)
        self.running = False
        self.threads: List[threading.Thread] = []
        self.docker_client = None
        self.hostname = socket.gethostname()
        self.auto_start = False  # Issue #553: Auto-start on backend startup

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        )
        self.logger = logging.getLogger("LogForwarder")

        # Initialize Docker client
        if DOCKER_AVAILABLE:
            try:
                self.docker_client = docker.from_env()
                self.logger.info("Docker client initialized")
            except Exception as e:
                self.logger.warning(f"Docker client not available: {e}")

        # Load configuration
        self.load_config()

    def load_config(self):
        """Load forwarding configuration."""
        if Path(self.config_path).exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                # Issue #553: Load auto_start setting
                self.auto_start = config.get("auto_start", False)

                for dest_config in config.get("destinations", []):
                    dest = create_destination(DestinationConfig.from_dict(dest_config))
                    self.destinations[dest.config.name] = dest
                    self.logger.info(f"Loaded destination: {dest.config.name} ({dest.config.type.value})")

            except Exception as e:
                self.logger.error(f"Failed to load config: {e}")
        else:
            self.logger.info("No config file found, using defaults")

    def save_config(self):
        """Save current configuration."""
        config = {
            "auto_start": self.auto_start,  # Issue #553: Persist auto_start setting
            "destinations": [dest.config.to_dict() for dest in self.destinations.values()]
        }

        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        self.logger.info(f"Configuration saved to {self.config_path}")

    def add_destination(self, config: DestinationConfig) -> bool:
        """Add a new log destination."""
        try:
            dest = create_destination(config)
            self.destinations[config.name] = dest
            self.save_config()
            self.logger.info(f"Added destination: {config.name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add destination: {e}")
            return False

    def remove_destination(self, name: str) -> bool:
        """Remove a log destination."""
        if name in self.destinations:
            del self.destinations[name]
            self.save_config()
            self.logger.info(f"Removed destination: {name}")
            return True
        return False

    def update_destination(self, name: str, config: DestinationConfig) -> bool:
        """Update an existing destination."""
        if name in self.destinations:
            self.destinations[name] = create_destination(config)
            self.save_config()
            self.logger.info(f"Updated destination: {name}")
            return True
        return False

    def get_destinations_status(self) -> List[Dict[str, Any]]:
        """Get status of all destinations."""
        return [dest.stats for dest in self.destinations.values()]

    def test_destinations(self) -> Dict[str, bool]:
        """Test connectivity to all destinations."""
        results = {}
        for name, dest in self.destinations.items():
            results[name] = dest.health_check()
            status = "healthy" if results[name] else "unhealthy"
            self.logger.info(f"Destination {name}: {status}")
        return results

    def queue_log(self, message: str, level: str = "Information", source: str = "AutoBot",
                  properties: Optional[Dict[str, Any]] = None):
        """Queue a log entry for forwarding."""
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat() + "Z",
            level=level,
            message=message,
            source=source,
            properties={
                "Host": self.hostname,
                "Application": "AutoBot",
                "Environment": os.getenv("AUTOBOT_ENV", "development"),
                **(properties or {})
            }
        )

        try:
            self.log_queue.put_nowait(entry)
        except Exception:
            # Queue full - track dropped logs but avoid log storms
            self._dropped_count = getattr(self, '_dropped_count', 0) + 1
            # Log every 100th drop to provide visibility without flooding
            if self._dropped_count % 100 == 1:
                self.logger.warning(
                    "Log queue full, dropped %d logs (queue size: %d)",
                    self._dropped_count, self.log_queue.qsize()
                )

    def _log_sender_thread(self):
        """Background thread that sends logs to destinations."""
        batch: Dict[str, List[LogEntry]] = {name: [] for name in self.destinations}
        last_send_time = time.time()

        while self.running or not self.log_queue.empty():
            try:
                entry = self.log_queue.get(timeout=1.0)

                # Add to batch for each enabled destination that applies to this host
                for name, dest in self.destinations.items():
                    if dest.config.enabled and dest.config.applies_to_host(self.hostname):
                        batch[name].append(entry)

                self.log_queue.task_done()

            except Empty:
                pass

            # Send batches that are full or timed out
            current_time = time.time()
            for name, dest in self.destinations.items():
                if not dest.config.enabled:
                    continue
                if not dest.config.applies_to_host(self.hostname):
                    continue

                should_send = (
                    len(batch[name]) >= dest.config.batch_size or
                    (batch[name] and current_time - last_send_time >= dest.config.batch_timeout)
                )

                if should_send and batch[name]:
                    success = dest.send(batch[name])
                    if not success:
                        self.logger.warning(f"Failed to send to {name}: {dest._last_error}")
                    batch[name] = []
                    last_send_time = current_time

        # Send remaining logs
        for name, dest in self.destinations.items():
            if batch[name] and dest.config.enabled and dest.config.applies_to_host(self.hostname):
                dest.send(batch[name])

    def _docker_log_streamer(self, container):
        """Stream logs from a Docker container."""
        try:
            self.logger.info(f"Starting log stream for container: {container.name}")

            for log_line in container.logs(stream=True, follow=True, timestamps=True):
                if not self.running:
                    break

                try:
                    log_text = log_line.decode("utf-8", errors="ignore").strip()
                    if not log_text:
                        continue

                    # Parse timestamp if present
                    timestamp_match = re.match(
                        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(.*)$",
                        log_text
                    )
                    if timestamp_match:
                        _, message = timestamp_match.groups()
                    else:
                        message = log_text

                    # Determine log level
                    level = "Information"
                    message_lower = message.lower()
                    if any(kw in message_lower for kw in ["error", "exception", "failed", "fatal"]):
                        level = "Error"
                    elif any(kw in message_lower for kw in ["warning", "warn"]):
                        level = "Warning"
                    elif any(kw in message_lower for kw in ["debug"]):
                        level = "Debug"

                    self.queue_log(
                        message,
                        level=level,
                        source=f"Docker-{container.name}",
                        properties={
                            "ContainerID": container.id[:12],
                            "ContainerName": container.name,
                            "Image": container.image.tags[0] if container.image.tags else "unknown",
                            "LogType": "DockerContainer"
                        }
                    )

                except Exception as e:
                    self.logger.debug(f"Error processing log from {container.name}: {e}")

        except Exception as e:
            self.logger.error(f"Error streaming logs from {container.name}: {e}")

    def _get_autobot_containers(self) -> List:
        """Get AutoBot-related Docker containers."""
        if not self.docker_client:
            return []

        containers = []
        try:
            for container in self.docker_client.containers.list():
                name = container.name.lower()
                is_autobot = (
                    name.startswith("autobot") or
                    any(kw in name for kw in ["redis", "seq", "playwright", "npu", "ai-stack"])
                )
                if is_autobot:
                    containers.append(container)
                    self.logger.info(f"Found container: {container.name}")
        except Exception as e:
            self.logger.error(f"Error listing containers: {e}")

        return containers

    def _file_log_monitor(self, log_path: Path, source: str):
        """Monitor a log file and forward new entries."""
        try:
            if not log_path.exists():
                return

            self.logger.info(f"Monitoring log file: {log_path}")

            with open(log_path, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # Go to end

                while self.running:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    line = line.strip()
                    if not line:
                        continue

                    # Try to parse as JSON
                    level = "Information"
                    message = line
                    properties = {}

                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                            message = data.get("message", line)
                            level = data.get("level", data.get("levelname", "Information"))
                            properties = {k: v for k, v in data.items() if k not in ["message", "level", "levelname"]}
                        except json.JSONDecodeError:
                            pass
                    else:
                        # Detect level from text
                        if any(kw in line.upper() for kw in ["ERROR", "EXCEPTION"]):
                            level = "Error"
                        elif any(kw in line.upper() for kw in ["WARNING", "WARN"]):
                            level = "Warning"
                        elif "DEBUG" in line.upper():
                            level = "Debug"

                    self.queue_log(message, level=level, source=source, properties=properties)

        except Exception as e:
            self.logger.error(f"Error monitoring {log_path}: {e}")

    def start(self):
        """Start the log forwarding service."""
        if not self.destinations:
            self.logger.warning("No destinations configured")
            return

        self.running = True
        self.logger.info("Starting log forwarding service...")

        # Test destinations
        self.test_destinations()

        # Start log sender thread
        sender_thread = threading.Thread(target=self._log_sender_thread, daemon=True)
        sender_thread.start()
        self.threads.append(sender_thread)

        # Start Docker container monitoring
        containers = self._get_autobot_containers()
        for container in containers:
            thread = threading.Thread(target=self._docker_log_streamer, args=(container,), daemon=True)
            thread.start()
            self.threads.append(thread)

        # Monitor log files
        logs_dir = self.project_root / "logs"
        log_files = [
            (logs_dir / "backend.log", "Backend-File"),
            (logs_dir / "frontend.log", "Frontend-File"),
            (logs_dir / "system.log", "System-File"),
        ]

        for log_path, source in log_files:
            thread = threading.Thread(target=self._file_log_monitor, args=(log_path, source), daemon=True)
            thread.start()
            self.threads.append(thread)

        # Send startup event
        self.queue_log(
            "Log Forwarding Service Started",
            level="Information",
            source="LogForwarder",
            properties={"Event": "Startup", "Destinations": list(self.destinations.keys())}
        )

        self.logger.info(f"Log forwarding active with {len(self.destinations)} destination(s)")
        self.logger.info("Press Ctrl+C to stop")

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the log forwarding service."""
        self.logger.info("Stopping log forwarding service...")
        self.running = False

        # Wait for queue to empty
        try:
            self.log_queue.join()
        except:
            pass

        self.logger.info("Log forwarding service stopped")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="AutoBot Log Forwarding Service")
    parser.add_argument("--start", action="store_true", help="Start the log forwarder")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--test-destinations", action="store_true", help="Test all destinations")
    parser.add_argument("--add-seq", type=str, metavar="URL", help="Add Seq destination")
    parser.add_argument("--add-elasticsearch", type=str, metavar="URL", help="Add Elasticsearch destination")
    parser.add_argument("--add-loki", type=str, metavar="URL", help="Add Loki destination")
    parser.add_argument("--add-syslog", type=str, metavar="HOST:PORT", help="Add Syslog destination (e.g., 192.168.168.49:514)")
    parser.add_argument("--syslog-protocol", type=str, choices=["udp", "tcp", "tcp_tls"], default="udp",
                        help="Syslog protocol: udp (default), tcp, or tcp_tls")
    parser.add_argument("--syslog-name", type=str, default="syslog-default", help="Name for syslog destination")
    parser.add_argument("--ssl-verify", action="store_true", help="Verify SSL certificates (for tcp_tls)")
    parser.add_argument("--ssl-ca-cert", type=str, help="Path to CA certificate for SSL verification")
    parser.add_argument("--scope", type=str, choices=["global", "per_host"], default="global",
                        help="Destination scope: global (all hosts) or per_host")
    parser.add_argument("--target-hosts", type=str, help="Comma-separated list of target hosts (for per_host scope)")
    parser.add_argument("--list", action="store_true", help="List configured destinations")

    args = parser.parse_args()

    forwarder = LogForwarder(config_path=args.config)

    # Handle signal for graceful shutdown
    def signal_handler(signum, frame):
        forwarder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.add_seq:
        config = DestinationConfig(
            name="seq-default",
            type=DestinationType.SEQ,
            url=args.add_seq
        )
        forwarder.add_destination(config)
        print(f"Added Seq destination: {args.add_seq}")

    if args.add_elasticsearch:
        config = DestinationConfig(
            name="elasticsearch-default",
            type=DestinationType.ELASTICSEARCH,
            url=args.add_elasticsearch
        )
        forwarder.add_destination(config)
        print(f"Added Elasticsearch destination: {args.add_elasticsearch}")

    if args.add_loki:
        config = DestinationConfig(
            name="loki-default",
            type=DestinationType.LOKI,
            url=args.add_loki
        )
        forwarder.add_destination(config)
        print(f"Added Loki destination: {args.add_loki}")

    if args.add_syslog:
        # Parse scope and target hosts
        scope = DestinationScope(args.scope)
        target_hosts = []
        if args.target_hosts:
            target_hosts = [h.strip() for h in args.target_hosts.split(",")]

        config = DestinationConfig(
            name=args.syslog_name,
            type=DestinationType.SYSLOG,
            url=args.add_syslog,
            syslog_protocol=SyslogProtocol(args.syslog_protocol),
            ssl_verify=args.ssl_verify,
            ssl_ca_cert=args.ssl_ca_cert,
            scope=scope,
            target_hosts=target_hosts
        )
        forwarder.add_destination(config)
        protocol_info = f" ({args.syslog_protocol})"
        scope_info = f" [scope: {args.scope}]"
        hosts_info = f" [hosts: {args.target_hosts}]" if args.target_hosts else ""
        print(f"Added Syslog destination: {args.add_syslog}{protocol_info}{scope_info}{hosts_info}")

    if args.list:
        print("\nConfigured Destinations:")
        for dest in forwarder.destinations.values():
            status = "enabled" if dest.config.enabled else "disabled"
            scope = dest.config.scope.value
            url = dest.config.url or dest.config.file_path
            line = f"  - {dest.config.name} ({dest.config.type.value}): {url} [{status}] [scope: {scope}]"

            # Add protocol info for syslog
            if dest.config.type == DestinationType.SYSLOG:
                line += f" [protocol: {dest.config.syslog_protocol.value}]"

            # Add target hosts for per_host scope
            if dest.config.scope == DestinationScope.PER_HOST and dest.config.target_hosts:
                line += f" [hosts: {', '.join(dest.config.target_hosts)}]"

            print(line)

    if args.test_destinations:
        print("\nTesting destinations...")
        results = forwarder.test_destinations()
        for name, healthy in results.items():
            status = "OK" if healthy else "FAILED"
            print(f"  {name}: {status}")

    if args.start:
        forwarder.start()

    if not any([args.start, args.add_seq, args.add_elasticsearch, args.add_loki, args.add_syslog, args.list, args.test_destinations]):
        parser.print_help()


if __name__ == "__main__":
    main()
