# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Categorizer

Automatically categorizes systemd services as AutoBot or System services
based on pattern matching rules.
"""

import re
from typing import List, Tuple

from models.database import ServiceCategory


# Pattern rules for AutoBot services
# Each tuple: (pattern, description)
# Patterns are compiled regex, checked in order
AUTOBOT_SERVICE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Direct AutoBot services
    (re.compile(r"^autobot", re.IGNORECASE), "AutoBot service prefix"),
    (re.compile(r"^slm-", re.IGNORECASE), "SLM service prefix"),

    # Infrastructure services commonly used by AutoBot
    (re.compile(r"^redis", re.IGNORECASE), "Redis database"),
    (re.compile(r"^nginx$", re.IGNORECASE), "Nginx web server"),
    (re.compile(r"^postgresql", re.IGNORECASE), "PostgreSQL database"),
    (re.compile(r"^chromadb", re.IGNORECASE), "ChromaDB vector store"),
    (re.compile(r"^ollama", re.IGNORECASE), "Ollama LLM service"),

    # Python application servers
    (re.compile(r"^uvicorn", re.IGNORECASE), "Uvicorn ASGI server"),
    (re.compile(r"^gunicorn", re.IGNORECASE), "Gunicorn WSGI server"),
    (re.compile(r"^celery", re.IGNORECASE), "Celery task queue"),

    # Container orchestration
    (re.compile(r"^docker", re.IGNORECASE), "Docker service"),
    (re.compile(r"^containerd", re.IGNORECASE), "Container runtime"),
    (re.compile(r"^podman", re.IGNORECASE), "Podman container"),

    # AI/ML services
    (re.compile(r"^openvino", re.IGNORECASE), "OpenVINO inference"),
    (re.compile(r"^tensorrt", re.IGNORECASE), "TensorRT inference"),
    (re.compile(r"^triton", re.IGNORECASE), "Triton inference server"),

    # Message queues
    (re.compile(r"^rabbitmq", re.IGNORECASE), "RabbitMQ message broker"),
    (re.compile(r"^kafka", re.IGNORECASE), "Kafka message broker"),

    # Monitoring
    (re.compile(r"^prometheus", re.IGNORECASE), "Prometheus monitoring"),
    (re.compile(r"^grafana", re.IGNORECASE), "Grafana dashboards"),
    (re.compile(r"^node.exporter", re.IGNORECASE), "Node exporter metrics"),

    # Browser automation
    (re.compile(r"^playwright", re.IGNORECASE), "Playwright browser"),
    (re.compile(r"^puppeteer", re.IGNORECASE), "Puppeteer browser"),

    # Generic catch-all for services containing autobot/slm
    (re.compile(r"autobot", re.IGNORECASE), "Contains 'autobot'"),
    (re.compile(r"slm", re.IGNORECASE), "Contains 'slm'"),
]


def _strip_service_suffix(service_name: str) -> str:
    """Strip .service suffix for cleaner matching (Python 3.8 compatible)."""
    suffix = ".service"
    if service_name.endswith(suffix):
        return service_name[: -len(suffix)]
    return service_name


def categorize_service(service_name: str) -> str:
    """
    Determine the category for a service based on its name.

    Args:
        service_name: The systemd service name (e.g., 'redis-server.service')

    Returns:
        ServiceCategory value ('autobot' or 'system')
    """
    # Strip .service suffix if present for cleaner matching
    name = _strip_service_suffix(service_name)

    for pattern, _ in AUTOBOT_SERVICE_PATTERNS:
        if pattern.search(name):
            return ServiceCategory.AUTOBOT.value

    return ServiceCategory.SYSTEM.value


def get_category_reason(service_name: str) -> str:
    """
    Get the reason why a service was categorized a certain way.

    Args:
        service_name: The systemd service name

    Returns:
        Human-readable reason for the categorization
    """
    name = _strip_service_suffix(service_name)

    for pattern, description in AUTOBOT_SERVICE_PATTERNS:
        if pattern.search(name):
            return f"AutoBot: {description}"

    return "System: No matching AutoBot pattern"


def is_autobot_service(service_name: str) -> bool:
    """
    Quick check if a service is an AutoBot service.

    Args:
        service_name: The systemd service name

    Returns:
        True if the service is categorized as AutoBot
    """
    return categorize_service(service_name) == ServiceCategory.AUTOBOT.value
