#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Environment File Generator
Generates standardized .env files from complete.yaml configuration
"""

from pathlib import Path

import yaml


def load_config():
    """Load the complete.yaml configuration"""
    config_path = Path(__file__).parent.parent / "config" / "complete.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


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
        "# Redis Database Configuration",
        f"AUTOBOT_REDIS_DB_MAIN={config['redis']['databases']['main']}",
        f"AUTOBOT_REDIS_DB_KNOWLEDGE={config['redis']['databases']['knowledge']}",
        f"AUTOBOT_REDIS_DB_PROMPTS={config['redis']['databases']['prompts']}",
        f"AUTOBOT_REDIS_DB_AGENTS={config['redis']['databases']['agents']}",
        f"AUTOBOT_REDIS_DB_METRICS={config['redis']['databases']['metrics']}",
        f"AUTOBOT_REDIS_DB_CACHE={config['redis']['databases']['cache']}",
        f"AUTOBOT_REDIS_DB_SESSIONS={config['redis']['databases']['sessions']}",
        f"AUTOBOT_REDIS_DB_TASKS={config['redis']['databases']['tasks']}",
        f"AUTOBOT_REDIS_DB_LOGS={config['redis']['databases']['logs']}",
        f"AUTOBOT_REDIS_DB_TEMP={config['redis']['databases']['temp']}",
        f"AUTOBOT_REDIS_DB_BACKUP={config['redis']['databases']['backup']}",
        f"AUTOBOT_REDIS_DB_TESTING={config['redis']['databases']['testing']}",
        "",
        "# Service URLs (Computed)",
        f"AUTOBOT_BACKEND_URL=http://{config['infrastructure']['hosts']['backend']}:{config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_URL=http://{config['infrastructure']['hosts']['frontend']}:{config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_URL=redis://{config['infrastructure']['hosts']['redis']}:{config['infrastructure']['ports']['redis']}",
        f"AUTOBOT_OLLAMA_URL=http://{config['infrastructure']['hosts']['ollama']}:{config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_AI_STACK_URL=http://{config['infrastructure']['hosts']['ai_stack']}:{config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_URL=http://{config['infrastructure']['hosts']['npu_worker']}:{config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_URL=http://{config['infrastructure']['hosts']['browser_service']}:{config['infrastructure']['ports']['browser_service']}",
        "",
        "# WebSocket Configuration",
        f"AUTOBOT_WS_URL=ws://{config['infrastructure']['hosts']['backend']}:{config['infrastructure']['ports']['backend']}/ws",
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
        "# Legacy Compatibility (for existing code)",
        f"REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        f"OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        "",
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
        "# Redis Database Configuration (Standardized)",
        f"AUTOBOT_REDIS_DB_MAIN={config['redis']['databases']['main']}",
        f"AUTOBOT_REDIS_DB_KNOWLEDGE={config['redis']['databases']['knowledge']}",
        f"AUTOBOT_REDIS_DB_PROMPTS={config['redis']['databases']['prompts']}",
        f"AUTOBOT_REDIS_DB_AGENTS={config['redis']['databases']['agents']}",
        f"AUTOBOT_REDIS_DB_METRICS={config['redis']['databases']['metrics']}",
        f"AUTOBOT_REDIS_DB_CACHE={config['redis']['databases']['cache']}",
        f"AUTOBOT_REDIS_DB_SESSIONS={config['redis']['databases']['sessions']}",
        f"AUTOBOT_REDIS_DB_TASKS={config['redis']['databases']['tasks']}",
        f"AUTOBOT_REDIS_DB_LOGS={config['redis']['databases']['logs']}",
        f"AUTOBOT_REDIS_DB_TEMP={config['redis']['databases']['temp']}",
        f"AUTOBOT_REDIS_DB_BACKUP={config['redis']['databases']['backup']}",
        f"AUTOBOT_REDIS_DB_TESTING={config['redis']['databases']['testing']}",
        "",
        "# Service URLs (Localhost)",
        f"AUTOBOT_BACKEND_URL=http://127.0.0.1:{config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_URL=http://127.0.0.1:{config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_URL=redis://127.0.0.1:{config['infrastructure']['ports']['redis']}",
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
        "# Redis Database Configuration (Standardized)",
        f"AUTOBOT_REDIS_DB_MAIN={config['redis']['databases']['main']}",
        f"AUTOBOT_REDIS_DB_KNOWLEDGE={config['redis']['databases']['knowledge']}",
        f"AUTOBOT_REDIS_DB_PROMPTS={config['redis']['databases']['prompts']}",
        f"AUTOBOT_REDIS_DB_AGENTS={config['redis']['databases']['agents']}",
        f"AUTOBOT_REDIS_DB_METRICS={config['redis']['databases']['metrics']}",
        f"AUTOBOT_REDIS_DB_CACHE={config['redis']['databases']['cache']}",
        f"AUTOBOT_REDIS_DB_SESSIONS={config['redis']['databases']['sessions']}",
        f"AUTOBOT_REDIS_DB_TASKS={config['redis']['databases']['tasks']}",
        f"AUTOBOT_REDIS_DB_LOGS={config['redis']['databases']['logs']}",
        f"AUTOBOT_REDIS_DB_TEMP={config['redis']['databases']['temp']}",
        f"AUTOBOT_REDIS_DB_BACKUP={config['redis']['databases']['backup']}",
        f"AUTOBOT_REDIS_DB_TESTING={config['redis']['databases']['testing']}",
        "",
        "# Service URLs (Distributed)",
        f"AUTOBOT_BACKEND_URL=http://{config['infrastructure']['hosts']['backend']}:{config['infrastructure']['ports']['backend']}",
        f"AUTOBOT_FRONTEND_URL=http://{config['infrastructure']['hosts']['frontend']}:{config['infrastructure']['ports']['frontend']}",
        f"AUTOBOT_REDIS_URL=redis://{config['infrastructure']['hosts']['redis']}:{config['infrastructure']['ports']['redis']}",
        f"AUTOBOT_OLLAMA_URL=http://{config['infrastructure']['hosts']['ollama']}:{config['infrastructure']['ports']['ollama']}",
        f"AUTOBOT_AI_STACK_URL=http://{config['infrastructure']['hosts']['ai_stack']}:{config['infrastructure']['ports']['ai_stack']}",
        f"AUTOBOT_NPU_WORKER_URL=http://{config['infrastructure']['hosts']['npu_worker']}:{config['infrastructure']['ports']['npu_worker']}",
        f"AUTOBOT_BROWSER_SERVICE_URL=http://{config['infrastructure']['hosts']['browser_service']}:{config['infrastructure']['ports']['browser_service']}",
        "",
        "# WebSocket Configuration",
        f"AUTOBOT_WS_URL=ws://{config['infrastructure']['hosts']['backend']}:{config['infrastructure']['ports']['backend']}/ws",
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
        "# Legacy Compatibility",
        f"REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        f"OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        "",
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
        f"VITE_API_BASE_URL=http://{config['infrastructure']['hosts']['backend']}:{config['infrastructure']['ports']['backend']}",
        f"VITE_WS_BASE_URL=ws://{config['infrastructure']['hosts']['backend']}:{config['infrastructure']['ports']['backend']}/ws",
        f"VITE_API_TIMEOUT={config['timeouts']['http']['standard']}000",
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
        f"VITE_PLAYWRIGHT_VNC_URL=http://{config['infrastructure']['hosts']['browser_service']}:{config['infrastructure']['ports']['vnc']}/vnc.html",
        f"VITE_PLAYWRIGHT_API_URL=http://{config['infrastructure']['hosts']['browser_service']}:{config['infrastructure']['ports']['browser_service']}",
        f"VITE_OLLAMA_URL=http://{config['infrastructure']['hosts']['ollama']}:{config['infrastructure']['ports']['ollama']}",
        "",
        "# Redis Configuration (for frontend services)",
        f"VITE_REDIS_URL=redis://{config['infrastructure']['hosts']['redis']}:{config['infrastructure']['ports']['redis']}",
        f"VITE_AI_STACK_URL=http://{config['infrastructure']['hosts']['ai_stack']}:{config['infrastructure']['ports']['ai_stack']}",
        f"VITE_NPU_WORKER_URL=http://{config['infrastructure']['hosts']['npu_worker']}:{config['infrastructure']['ports']['npu_worker']}",
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
        "# Redis Database Configuration",
        f"AUTOBOT_REDIS_DB_MAIN={config['redis']['databases']['main']}",
        f"AUTOBOT_REDIS_DB_KNOWLEDGE={config['redis']['databases']['knowledge']}",
        f"AUTOBOT_REDIS_DB_PROMPTS={config['redis']['databases']['prompts']}",
        f"AUTOBOT_REDIS_DB_AGENTS={config['redis']['databases']['agents']}",
        f"AUTOBOT_REDIS_DB_METRICS={config['redis']['databases']['metrics']}",
        f"AUTOBOT_REDIS_DB_CACHE={config['redis']['databases']['cache']}",
        f"AUTOBOT_REDIS_DB_SESSIONS={config['redis']['databases']['sessions']}",
        f"AUTOBOT_REDIS_DB_TASKS={config['redis']['databases']['tasks']}",
        f"AUTOBOT_REDIS_DB_LOGS={config['redis']['databases']['logs']}",
        f"AUTOBOT_REDIS_DB_TEMP={config['redis']['databases']['temp']}",
        f"AUTOBOT_REDIS_DB_BACKUP={config['redis']['databases']['backup']}",
        f"AUTOBOT_REDIS_DB_TESTING={config['redis']['databases']['testing']}",
        "",
        "# Network Configuration",
        "DOCKER_SUBNET=172.16.168.0/24",
        "DOCKER_GATEWAY=172.16.168.1",
        "",
        "# Service URL Construction",
        f"BACKEND_URL=http://{config['infrastructure']['hosts']['backend']}:{config['infrastructure']['ports']['backend']}",
        f"FRONTEND_URL=http://{config['infrastructure']['hosts']['frontend']}:{config['infrastructure']['ports']['frontend']}",
        f"REDIS_URL=redis://{config['infrastructure']['hosts']['redis']}:{config['infrastructure']['ports']['redis']}",
        f"OLLAMA_URL=http://{config['infrastructure']['hosts']['ollama']}:{config['infrastructure']['ports']['ollama']}",
        f"AI_STACK_URL=http://{config['infrastructure']['hosts']['ai_stack']}:{config['infrastructure']['ports']['ai_stack']}",
        f"NPU_WORKER_URL=http://{config['infrastructure']['hosts']['npu_worker']}:{config['infrastructure']['ports']['npu_worker']}",
        f"BROWSER_SERVICE_URL=http://{config['infrastructure']['hosts']['browser_service']}:{config['infrastructure']['ports']['browser_service']}",
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
        "# Redis Database Configuration (Production)",
        f"AUTOBOT_REDIS_DB_MAIN={config['redis']['databases']['main']}",
        f"AUTOBOT_REDIS_DB_KNOWLEDGE={config['redis']['databases']['knowledge']}",
        f"AUTOBOT_REDIS_DB_PROMPTS={config['redis']['databases']['prompts']}",
        f"AUTOBOT_REDIS_DB_AGENTS={config['redis']['databases']['agents']}",
        f"AUTOBOT_REDIS_DB_METRICS={config['redis']['databases']['metrics']}",
        f"AUTOBOT_REDIS_DB_CACHE={config['redis']['databases']['cache']}",
        f"AUTOBOT_REDIS_DB_SESSIONS={config['redis']['databases']['sessions']}",
        f"AUTOBOT_REDIS_DB_TASKS={config['redis']['databases']['tasks']}",
        f"AUTOBOT_REDIS_DB_LOGS={config['redis']['databases']['logs']}",
        f"AUTOBOT_REDIS_DB_TEMP={config['redis']['databases']['temp']}",
        f"AUTOBOT_REDIS_DB_BACKUP={config['redis']['databases']['backup']}",
        f"AUTOBOT_REDIS_DB_TESTING={config['redis']['databases']['testing']}",
        "",
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
        "# Legacy Compatibility",
        f"REDIS_HOST={config['infrastructure']['hosts']['redis']}",
        f"REDIS_PORT={config['infrastructure']['ports']['redis']}",
        f"OLLAMA_HOST={config['infrastructure']['hosts']['ollama']}",
        f"OLLAMA_PORT={config['infrastructure']['ports']['ollama']}",
        "",
    ]

    return "\n".join(content)


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

            # Write file
            with open(full_path, "w") as f:
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
