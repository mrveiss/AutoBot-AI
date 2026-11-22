#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Environment File Generator
Generates standardized .env files from complete.yaml configuration
"""

import sys
from pathlib import Path

# autobot_shared is the repo-root package; this script runs standalone from
# autobot-infrastructure/shared/scripts.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from autobot_shared.network_constants import NetworkConstants  # noqa: E402
from autobot_shared.ssot_config import TimeoutConfig  # noqa: E402

# Sibling helper module: the importing script may have been loaded by file path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_files_config import load_config  # noqa: E402

#: Frontend API timeout in ms, from the SSOT field default (#17856 row 6).
#: complete.yaml's http.standard is seconds as a float, and appending "000" to
#: it wrote "30.0000" -- a 30 ms timeout.
API_TIMEOUT_MS = TimeoutConfig.model_fields["api"].default


def resolve_template_value(value, config):
    """Resolve template variables in configuration values"""
    if not isinstance(value, str) or "${" not in value:
        return value

    # Simple template resolution for ${section.key} syntax
    import re

    templates = re.findall(r"\$\{([^}]+)\}", value)

    for template in templates:
        keys = template.split(".")
        resolved_value = config

        try:
            for key in keys:
                resolved_value = resolved_value[key]

            value = value.replace(f"${{{template}}}", str(resolved_value))
        except (KeyError, TypeError):
            # Keep original if can't resolve
            pass

    return value


def _redis_database_lines() -> list:
    """The ``AUTOBOT_REDIS_DB_<NAME>`` overrides in effect here, read from the one table (#19232).

    complete.yaml has no ``redis.databases`` section, so the hand-listed lookups this
    replaces raised KeyError. redis-databases.yaml holds the numbers, so a generated file
    carries only the databases this environment moves -- never a copy of the table.
    """
    from autobot_shared.redis_management.database_overrides import env_var_name
    from autobot_shared.redis_management.types import DATABASE_MAPPING, DECLARED_DATABASES

    moved = [
        f"{env_var_name(name)}={DATABASE_MAPPING[name]}"
        for name, number in DECLARED_DATABASES.items()
        if DATABASE_MAPPING[name] != number
    ]
    return ["# Redis database numbers: redis-databases.yaml; overrides only (#19232)", *moved]


#: (service, scheme) for each computed service URL, in output order.
#: Redis is not here: its URL comes from RedisEndpoint.url, the one Redis URL builder (#19232).
_SERVICE_URLS = (
    ("backend", "http"),
    ("frontend", "http"),
    ("ollama", "http"),
    ("ai_stack", "http"),
    ("npu_worker", "http"),
    ("browser_service", "http"),
)


def _redis_url(host, port) -> str:
    """A credential-free Redis URL for a generated file, from the one URL builder (#19232).

    The generator describes a TARGET deployment from complete.yaml, so it formats that
    host and port with ``RedisEndpoint.url`` rather than resolving this process's endpoint.
    """
    from autobot_shared.redis_management.endpoint import RedisEndpoint

    return RedisEndpoint(host=str(host), port=int(port)).url(with_auth=False)


def _legacy_lines(config) -> list:
    """The legacy REDIS_*/OLLAMA_* names some older code still reads."""
    hosts, ports = config["infrastructure"]["hosts"], config["infrastructure"]["ports"]
    return [
        "# Legacy Compatibility",
        f"REDIS_HOST={hosts['redis']}",
        f"REDIS_PORT={ports['redis']}",
        f"OLLAMA_HOST={hosts['ollama']}",
        f"OLLAMA_PORT={ports['ollama']}",
        "",
    ]


def _service_url_lines(config, label: str) -> list:
    """The computed service URLs and the WebSocket URL, from the hosts and ports."""
    hosts, ports = config["infrastructure"]["hosts"], config["infrastructure"]["ports"]
    lines = [f"# Service URLs ({label})"]
    lines += [f"AUTOBOT_{name.upper()}_URL={scheme}://{hosts[name]}:{ports[name]}" for name, scheme in _SERVICE_URLS]
    lines.append(f"AUTOBOT_REDIS_URL={_redis_url(hosts['redis'], ports['redis'])}")
    return [*lines, "", "# WebSocket Configuration", f"AUTOBOT_WS_URL=ws://{hosts['backend']}:{ports['backend']}/ws"]


def _bare_service_url_lines(config) -> list:
    """The service URLs under their unprefixed names (``BACKEND_URL``, ...) for .env.network."""
    hosts, ports = config["infrastructure"]["hosts"], config["infrastructure"]["ports"]
    urls = [f"{name.upper()}_URL={scheme}://{hosts[name]}:{ports[name]}" for name, scheme in _SERVICE_URLS]
    urls.append(f"REDIS_URL={_redis_url(hosts['redis'], ports['redis'])}")
    return ["# Service URL Construction", *urls]


def _docker_ops_lines() -> list:
    """Static monitoring, logging and Docker settings for the production compose file."""
    return [
        "# Monitoring Configuration (Optional)",
        "AUTOBOT_PROMETHEUS_PORT=9090",
        "AUTOBOT_GRAFANA_PORT=3000",
        "AUTOBOT_GRAFANA_PASSWORD=autobot123  # pragma: allowlist secret",
        "",
        "# Centralized Logging Configuration",
        "AUTOBOT_FLUENTD_HOST=localhost",
        "AUTOBOT_FLUENTD_PORT=24224",
        "AUTOBOT_FLUENTD_EXTERNAL_PORT=24224",
        "AUTOBOT_FLUENTD_INTERNAL_PORT=24224",
        "AUTOBOT_SEQ_EXTERNAL_PORT=5341",
        "AUTOBOT_SEQ_INTERNAL_PORT=80",
        "AUTOBOT_SEQ_ADMIN_PASSWORD=Autobot123!  # pragma: allowlist secret",
        "",
        "# Docker Configuration",
        "AUTOBOT_DOCKER_SUBNET=172.20.0.0/16",
        "AUTOBOT_HOST_DOCKER_CONTAINERS=/var/lib/docker/containers",
        "AUTOBOT_HOST_DOCKER_SOCKET=/var/run/docker.sock",
        "",
    ]


def generate_main_env(config):
    """Generate main .env file for backend"""
    content = [
        "# AutoBot Main Environment Configuration",
        "# Generated from config/complete.yaml - DO NOT EDIT MANUALLY",
        "# Run 'python scripts/generate-env-files.py' to regenerate",
        "",
        "# Deployment Mode Configuration",
        "AUTOBOT_DEPLOYMENT_MODE=hybrid",
        "AUTOBOT_DEBUG=true",
        f"AUTOBOT_LOG_LEVEL={config['monitoring']['log_level']}",
        "",
        "# Core Infrastructure Hosts",
        f"AUTOBOT_BACKEND_HOST={config['infrastructure']['hosts']['backend']}",
        f"AUTOBOT_FRONTEND_HOST={config['infrastructure']['hosts']['frontend']}",
        f"AUTOBOT_REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"AUTOBOT_OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        f"AUTOBOT_AI_STACK_HOST={config['infrastructure']['hosts']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_HOST={config['infrastructure']['hosts']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_HOST={config['infrastructure']['hosts']['browser_service']}",
        "",
        "# Service Ports",
        f"AUTOBOT_BACKEND_PORT={config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_PORT={config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"AUTOBOT_OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_AI_STACK_PORT={config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_PORT={config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_PORT={config['infrastructure']['ports']['browser_service']}",
        f"AUTOBOT_VNC_PORT={config['infrastructure']['ports']['vnc']}",
        "",
        *_redis_database_lines(),
        "",
        *_service_url_lines(config, "Computed"),
        "",
        "# Performance and Limits",
        f"AUTOBOT_API_TIMEOUT={config['timeouts']['http']['standard']}000",  # Convert to milliseconds
        f"AUTOBOT_LLM_TIMEOUT={config['timeouts']['llm']['chat']}",
        f"AUTOBOT_MAX_CONCURRENT_REQUESTS={config['limits']['api']['concurrent_requests']}",
        "",
        "# Feature Flags",
        f"AUTOBOT_USE_UNIFIED_CONFIG={str(config['features']['use_unified_config']).lower()}",
        f"AUTOBOT_SEMANTIC_CHUNKING={str(config['features']['semantic_chunking']).lower()}",
        f"AUTOBOT_DEBUG_MODE={str(config['features']['enable_debug_mode']).lower()}",
        f"AUTOBOT_HOT_RELOAD={str(config['features']['enable_hot_reload']).lower()}",
        "",
        "# Hardware Acceleration Compatibility",
        "TF_USE_LEGACY_KERAS=1",
        "KERAS_BACKEND=tensorflow",
        "",
        *_legacy_lines(config),
    ]

    return "\n".join(content)


def generate_localhost_env(config):
    """Generate .env.localhost for local development"""
    content = [
        "# AutoBot Localhost Development Configuration",
        "# Generated from config/complete.yaml - DO NOT EDIT MANUALLY",
        "# Run 'python scripts/generate-env-files.py' to regenerate",
        "# Use this for local development with all services on localhost",
        "",
        "# Core Infrastructure - All Local",
        f"AUTOBOT_BACKEND_HOST={config['infrastructure']['defaults']['localhost']}",
        f"AUTOBOT_FRONTEND_HOST={config['infrastructure']['defaults']['localhost']}",
        f"AUTOBOT_REDIS_HOST={config['infrastructure']['defaults']['localhost']}",
        f"AUTOBOT_OLLAMA_HOST={config['infrastructure']['defaults']['localhost']}",
        f"AUTOBOT_AI_STACK_HOST={config['infrastructure']['defaults']['localhost']}",
        f"AUTOBOT_NPU_WORKER_HOST={config['infrastructure']['defaults']['localhost']}",
        f"AUTOBOT_BROWSER_SERVICE_HOST={config['infrastructure']['defaults']['localhost']}",
        "",
        "# Service Ports (Same as distributed)",
        f"AUTOBOT_BACKEND_PORT={config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_PORT={config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"AUTOBOT_OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_AI_STACK_PORT={config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_PORT={config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_PORT={config['infrastructure']['ports']['browser_service']}",
        f"AUTOBOT_VNC_PORT={config['infrastructure']['ports']['vnc']}",
        "",
        *_redis_database_lines(),
        "",
        "# Service URLs (Localhost)",
        f"AUTOBOT_BACKEND_URL=http://127.0.0.1:{config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_URL=http://127.0.0.1:{config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_URL={_redis_url(NetworkConstants.LOCALHOST_IP, config['infrastructure']['ports']['redis'])}",
        f"AUTOBOT_OLLAMA_URL=http://127.0.0.1:{config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_AI_STACK_URL=http://127.0.0.1:{config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_URL=http://127.0.0.1:{config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_URL=http://127.0.0.1:{config['infrastructure']['ports']['browser_service']}",
        "",
        "# WebSocket Configuration",
        f"AUTOBOT_WS_URL=ws://127.0.0.1:{config['infrastructure']['ports']['backend']}/ws",
        "",
        "# Development Mode Configuration",
        "AUTOBOT_DEPLOYMENT_MODE=local",
        f"AUTOBOT_DEBUG={str(config['development']['debug']).lower()}",
        f"AUTOBOT_LOG_LEVEL={config['monitoring']['log_level']}",
        "",
        "# Performance Settings",
        f"AUTOBOT_API_TIMEOUT={config['timeouts']['http']['standard']}000",
        f"AUTOBOT_LLM_TIMEOUT={config['timeouts']['llm']['chat']}",
        "",
        "# Hardware Acceleration Compatibility",
        "TF_USE_LEGACY_KERAS=1",
        "KERAS_BACKEND=tensorflow",
        "",
        "# Legacy Compatibility",
        "REDIS_HOST=127.0.0.1",
        f"REDIS_PORT={config['infrastructure']['ports']['redis']}",
        "OLLAMA_HOST=127.0.0.1",
        f"OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        "",
    ]

    return "\n".join(content)


def generate_native_vm_env(config):
    """Generate .env.native-vm for distributed VM deployment"""
    content = [
        "# AutoBot Native VM Deployment Configuration",
        "# Generated from config/complete.yaml - DO NOT EDIT MANUALLY",
        "# Run 'python scripts/generate-env-files.py' to regenerate",
        "# Configuration for distributed native VM architecture",
        "",
        "# Core Infrastructure - Distributed VMs",
        f"AUTOBOT_BACKEND_HOST={config['infrastructure']['hosts']['backend']}",
        f"AUTOBOT_FRONTEND_HOST={config['infrastructure']['hosts']['frontend']}",
        f"AUTOBOT_REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"AUTOBOT_OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        f"AUTOBOT_AI_STACK_HOST={config['infrastructure']['hosts']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_HOST={config['infrastructure']['hosts']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_HOST={config['infrastructure']['hosts']['browser_service']}",
        "",
        "# Service Ports",
        f"AUTOBOT_BACKEND_PORT={config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_PORT={config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"AUTOBOT_OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_AI_STACK_PORT={config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_PORT={config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_PORT={config['infrastructure']['ports']['browser_service']}",
        f"AUTOBOT_VNC_PORT={config['infrastructure']['ports']['vnc']}",
        "",
        *_redis_database_lines(),
        "",
        *_service_url_lines(config, "Distributed"),
        "",
        "# Deployment Configuration",
        "AUTOBOT_DEPLOYMENT_MODE=distributed",
        f"AUTOBOT_DEBUG={str(config['development']['debug']).lower()}",
        f"AUTOBOT_LOG_LEVEL={config['monitoring']['log_level']}",
        "AUTOBOT_DOCKER_ENABLED=false",
        "AUTOBOT_VM_ARCHITECTURE=true",
        "",
        "# Performance Settings",
        f"AUTOBOT_API_TIMEOUT={config['timeouts']['http']['standard']}000",
        f"AUTOBOT_LLM_TIMEOUT={config['timeouts']['llm']['chat']}",
        "",
        "# Hardware Acceleration Compatibility",
        "TF_USE_LEGACY_KERAS=1",
        "KERAS_BACKEND=tensorflow",
        "",
        *_legacy_lines(config),
    ]

    return "\n".join(content)


def generate_frontend_env(config):
    """Generate autobot-vue/.env for frontend"""
    content = [
        "# AutoBot Frontend Environment Configuration",
        "# Generated from config/complete.yaml - DO NOT EDIT MANUALLY",
        "# Run 'python scripts/generate-env-files.py' to regenerate",
        "",
        "# API Configuration - Use proxy in development",
        "# Direct URLs for production deployment",
        f"VITE_API_BASE_URL=http://"
        f"{config['infrastructure']['hosts']['backend']}:"
        f"{config['infrastructure']['ports']['backend']}",
        f"VITE_WS_BASE_URL=ws://"
        f"{config['infrastructure']['hosts']['backend']}:"
        f"{config['infrastructure']['ports']['backend']}/ws",
        f"VITE_API_TIMEOUT={API_TIMEOUT_MS}",
        "",
        "# Service Host Configuration",
        f"VITE_BACKEND_HOST={config['infrastructure']['hosts']['backend']}",
        f"VITE_BACKEND_HOST_DOCKER={config['infrastructure']['defaults']['docker_internal']}",
        f"VITE_BACKEND_PORT={config['infrastructure']['ports']['backend']}",
        "",
        "# Frontend Configuration",
        f"VITE_FRONTEND_HOST={config['infrastructure']['hosts']['frontend']}",
        f"VITE_FRONTEND_PORT={config['infrastructure']['ports']['frontend']}",
        "VITE_HTTP_PROTOCOL=http",
        "VITE_WS_PROTOCOL=ws",
        "",
        "# External Service URLs",
        f"VITE_PLAYWRIGHT_VNC_URL=http://"
        f"{config['infrastructure']['hosts']['browser_service']}:"
        f"{config['infrastructure']['ports']['vnc']}/vnc.html",
        f"VITE_PLAYWRIGHT_API_URL=http://"
        f"{config['infrastructure']['hosts']['browser_service']}:"
        f"{config['infrastructure']['ports']['browser_service']}",
        f"VITE_OLLAMA_URL=http://"
        f"{config['infrastructure']['hosts']['ollama']}:"
        f"{config['infrastructure']['ports']['ollama']}",
        "",
        f"VITE_AI_STACK_URL=http://"
        f"{config['infrastructure']['hosts']['ai_stack']}:"
        f"{config['infrastructure']['ports']['ai_stack']}",
        f"VITE_NPU_WORKER_URL=http://"
        f"{config['infrastructure']['hosts']['npu_worker']}:"
        f"{config['infrastructure']['ports']['npu_worker']}",
        "",
        "# Upload and Pagination Configuration",
        "VITE_UPLOAD_TIMEOUT=300000",
        "VITE_DEFAULT_PAGE_SIZE=20",
        "VITE_MAX_SEARCH_RESULTS=50",
        "",
        "# Development Settings",
        "VITE_ENV=development",
        f"VITE_DEBUG={str(config['development']['debug']).lower()}",
        "",
    ]

    return "\n".join(content)


def generate_network_env(config):
    """Generate .env.network for network configuration"""
    content = [
        "# AutoBot Network Configuration",
        "# Generated from config/complete.yaml - DO NOT EDIT MANUALLY",
        "# Run 'python scripts/generate-env-files.py' to regenerate",
        "# Production-ready network settings",
        "",
        "# Service Host IP Addresses",
        f"AUTOBOT_BACKEND_HOST={config['infrastructure']['hosts']['backend']}",
        f"AUTOBOT_FRONTEND_HOST={config['infrastructure']['hosts']['frontend']}",
        f"AUTOBOT_NPU_WORKER_HOST={config['infrastructure']['hosts']['npu_worker']}",
        f"AUTOBOT_REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"AUTOBOT_AI_STACK_HOST={config['infrastructure']['hosts']['ai_stack']}",
        f"AUTOBOT_BROWSER_SERVICE_HOST={config['infrastructure']['hosts']['browser_service']}",
        f"AUTOBOT_OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        "",
        "# Service Ports (Standardized)",
        f"AUTOBOT_BACKEND_PORT={config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_PORT={config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"AUTOBOT_OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_AI_STACK_PORT={config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_PORT={config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_PORT={config['infrastructure']['ports']['browser_service']}",
        f"AUTOBOT_VNC_PORT={config['infrastructure']['ports']['vnc']}",
        f"AUTOBOT_WEBSOCKET_PORT={config['infrastructure']['ports']['websocket']}",
        "",
        *_redis_database_lines(),
        "",
        "# Network Configuration — set at install time via install.sh",
        "DOCKER_SUBNET=",
        "DOCKER_GATEWAY=",
        "",
        *_bare_service_url_lines(config),
        "",
        "# Legacy Compatibility",
        f"REDIS_HOST_IP={config['infrastructure']['hosts']['redis']}",
        f"BACKEND_HOST_IP={config['infrastructure']['hosts']['backend']}",
        f"FRONTEND_HOST_IP={config['infrastructure']['hosts']['frontend']}",
        f"OLLAMA_HOST_IP={config['infrastructure']['hosts']['ollama']}",
        f"REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        f"OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        "",
    ]

    return "\n".join(content)


def generate_docker_production_env(config):
    """Generate docker/compose/.env.production for Docker production deployment"""
    content = [
        "# AutoBot Production Docker Environment Variables",
        "# Generated from config/complete.yaml - DO NOT EDIT MANUALLY",
        "# Run 'python scripts/generate-env-files.py' to regenerate",
        "",
        "# Core Infrastructure Hosts (for production deployment)",
        f"AUTOBOT_BACKEND_HOST={config['infrastructure']['hosts']['backend']}",
        f"AUTOBOT_REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"AUTOBOT_OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        "",
        "# Backend Configuration",
        f"AUTOBOT_BACKEND_PORT={config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_BACKEND_INTERNAL_PORT={config['infrastructure']['ports']['backend']}",
        "",
        "# Frontend Configuration",
        f"AUTOBOT_FRONTEND_HTTP_PORT={config['infrastructure']['ports']['nginx']}",
        "AUTOBOT_FRONTEND_HTTPS_PORT=443",
        "",
        "# Redis Configuration",
        f"AUTOBOT_REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"AUTOBOT_REDIS_INTERNAL_PORT={config['infrastructure']['ports']['redis']}",
        "",
        "# Ollama LLM Configuration",
        f"AUTOBOT_OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_OLLAMA_INTERNAL_PORT={config['infrastructure']['ports']['ollama']}",
        "",
        "# AI Services Configuration",
        f"AUTOBOT_AI_STACK_PORT={config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_PORT={config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_PORT={config['infrastructure']['ports']['browser_service']}",
        f"AUTOBOT_VNC_PORT={config['infrastructure']['ports']['vnc']}",
        "",
        *_redis_database_lines(),
        "",
        *_docker_ops_lines(),
        "# Application Configuration",
        "AUTOBOT_ENVIRONMENT=production",
        f"AUTOBOT_LOG_LEVEL={config['monitoring']['log_level']}",
        "AUTOBOT_SECURITY_ENABLED=true",
        f"AUTOBOT_MONITORING_ENABLED={str(config['monitoring']['enabled']).lower()}",
        "",
        "# Volume Paths (Customize for your deployment)",
        "DOCKER_VOLUMES_PATH=./docker/volumes",
        "HOST_DATA_PATH=./data",
        "HOST_LOGS_PATH=./logs",
        "HOST_REPORTS_PATH=./reports",
        "",
        *_legacy_lines(config),
    ]

    return "\n".join(content)


#: Native overlays on .env.base (#18555): written holding only what differs from the base.
NATIVE_OVERLAYS = {".env.localhost", ".env.native-vm", ".env.network"}


def strip_base_keys(content: str, base_text: str) -> str:
    """Drop every KEY=value line that repeats .env.base exactly, so a generated overlay passes the
    base/overlay guard (repo_tests/env_file_family_18555_test.py)."""
    base = {}
    for line in base_text.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            base[key] = value
    kept = []
    for line in content.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#") and base.get(key) == value:
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def main():
    """Main function to generate all environment files"""
    print("AutoBot Environment File Generator")
    print("=" * 40)

    # Load configuration
    try:
        config = load_config()
        print("✓ Loaded config/complete.yaml")
    except Exception as e:
        print(f"✗ Error loading configuration: {e}")
        return 1

    # Define environment files to generate
    env_files = {
        ".env": generate_main_env,
        ".env.localhost": generate_localhost_env,
        ".env.native-vm": generate_native_vm_env,
        ".env.network": generate_network_env,
        "autobot-vue/.env": generate_frontend_env,
        "docker/compose/.env.production": generate_docker_production_env,
    }

    project_root = Path(__file__).parent.parent
    generated_count = 0

    # Generate each environment file
    for file_path, generator_func in env_files.items():
        try:
            full_path = project_root / file_path

            # Create directory if it doesn't exist
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate content
            content = generator_func(config)
            base_path = full_path.parent / ".env.base"
            if file_path in NATIVE_OVERLAYS and base_path.exists():
                content = strip_base_keys(content, base_path.read_text(encoding="utf-8"))

            # Write file
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            print(f"✓ Generated {file_path}")
            generated_count += 1

        except Exception as e:
            print(f"✗ Error generating {file_path}: {e}")

    print(f"\nGenerated {generated_count}/{len(env_files)} environment files")
    print("\n" + "=" * 40)
    print("Environment files have been standardized!")
    print("All files now reference unified configuration from config/complete.yaml")
    print("\nTo regenerate files after config changes:")
    print("  python scripts/generate-env-files.py")

    return 0


if __name__ == "__main__":
    exit(main())
