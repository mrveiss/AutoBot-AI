# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSOT Configuration Mappings for Hardcoded Value Detection
==========================================================

Provides mappings between hardcoded values and their SSOT config equivalents.
Used by:
- detect-hardcoded-values.sh (pre-commit hook)
- EnvironmentAnalyzer (codebase analysis)
- CI/CD coverage reports

Issue: #642 - Centralize Environment Variables with SSOT Config Validation
Related: #599 - SSOT Configuration System Epic
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class SSOTCategory(Enum):
    """Categories of SSOT configuration values."""

    VM_IP = "vm_ip"
    PORT = "port"
    URL = "url"
    LLM_MODEL = "llm_model"
    TIMEOUT = "timeout"
    REDIS_DB = "redis_db"
    FEATURE_FLAG = "feature_flag"


@dataclass
class SSOTMapping:
    """Mapping between a hardcoded value and its SSOT config equivalent."""

    # The detected hardcoded value (can be regex pattern)
    pattern: str
    # Whether pattern is a regex or exact match
    is_regex: bool
    # Category of the value
    category: SSOTCategory
    # Python SSOT config access path
    python_config: str
    # TypeScript SSOT config access path
    typescript_config: str
    # Environment variable name
    env_var: str
    # Human-readable description
    description: str
    # Severity level (high, medium, low)
    severity: str = "medium"


# =============================================================================
# SSOT Mappings Registry
# =============================================================================

# VM IP Address Mappings
VM_IP_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern="172.16.168.20",
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config="config.vm.main",
        typescript_config="config.vm.main",
        env_var="AUTOBOT_BACKEND_HOST",
        description="Main machine (WSL) IP - Backend API",
        severity="high",
    ),
    SSOTMapping(
        pattern="172.16.168.21",
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config="config.vm.frontend",
        typescript_config="config.vm.frontend",
        env_var="AUTOBOT_FRONTEND_HOST",
        description="Frontend VM IP",
        severity="high",
    ),
    SSOTMapping(
        pattern="172.16.168.22",
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config="config.vm.npu",
        typescript_config="config.vm.npu",
        env_var="AUTOBOT_NPU_WORKER_HOST",
        description="NPU Worker VM IP",
        severity="high",
    ),
    SSOTMapping(
        pattern="172.16.168.23",
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config="config.vm.redis",
        typescript_config="config.vm.redis",
        env_var="AUTOBOT_REDIS_HOST",
        description="Redis VM IP",
        severity="high",
    ),
    SSOTMapping(
        pattern="172.16.168.24",
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config="config.vm.aistack",
        typescript_config="config.vm.aistack",
        env_var="AUTOBOT_AI_STACK_HOST",
        description="AI Stack VM IP",
        severity="high",
    ),
    SSOTMapping(
        pattern="172.16.168.25",
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config="config.vm.browser",
        typescript_config="config.vm.browser",
        env_var="AUTOBOT_BROWSER_SERVICE_HOST",
        description="Browser Service VM IP",
        severity="high",
    ),
    SSOTMapping(
        pattern="127.0.0.1",
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config="config.vm.ollama",
        typescript_config="config.vm.ollama",
        env_var="AUTOBOT_OLLAMA_HOST",
        description="Ollama host (localhost)",
        severity="medium",
    ),
]

# Port Mappings
PORT_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern=r":8001\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.backend",
        typescript_config="config.port.backend",
        env_var="AUTOBOT_BACKEND_PORT",
        description="Backend API port",
        severity="high",
    ),
    SSOTMapping(
        pattern=r":5173\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.frontend",
        typescript_config="config.port.frontend",
        env_var="AUTOBOT_FRONTEND_PORT",
        description="Frontend dev server port",
        severity="medium",
    ),
    SSOTMapping(
        pattern=r":6379\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.redis",
        typescript_config="config.port.redis",
        env_var="AUTOBOT_REDIS_PORT",
        description="Redis port",
        severity="high",
    ),
    SSOTMapping(
        pattern=r":11434\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.ollama",
        typescript_config="config.port.ollama",
        env_var="AUTOBOT_OLLAMA_PORT",
        description="Ollama API port",
        severity="high",
    ),
    SSOTMapping(
        pattern=r":6080\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.vnc",
        typescript_config="config.port.vnc",
        env_var="AUTOBOT_VNC_PORT",
        description="VNC noVNC port",
        severity="medium",
    ),
    SSOTMapping(
        pattern=r":8080\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.aistack",
        typescript_config="config.port.aistack",
        env_var="AUTOBOT_AI_STACK_PORT",
        description="AI Stack port",
        severity="medium",
    ),
    SSOTMapping(
        pattern=r":8081\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.npu",
        typescript_config="config.port.npu",
        env_var="AUTOBOT_NPU_WORKER_PORT",
        description="NPU Worker port",
        severity="medium",
    ),
    SSOTMapping(
        pattern=r":8082\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config="config.port.npu",
        typescript_config="config.port.npu",
        env_var="AUTOBOT_NPU_WORKER_PORT",
        description="NPU Worker port (alternate)",
        severity="medium",
    ),
]

# URL Mappings
URL_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern=r"http://172\.16\.168\.20:8001",
        is_regex=True,
        category=SSOTCategory.URL,
        python_config="config.backend_url",
        typescript_config="config.backendUrl",
        env_var="AUTOBOT_BACKEND_URL",
        description="Backend API URL",
        severity="high",
    ),
    SSOTMapping(
        pattern=r"http://172\.16\.168\.21:5173",
        is_regex=True,
        category=SSOTCategory.URL,
        python_config="config.frontend_url",
        typescript_config="config.frontendUrl",
        env_var="AUTOBOT_FRONTEND_URL",
        description="Frontend URL",
        severity="high",
    ),
    SSOTMapping(
        pattern=r"redis://172\.16\.168\.23:6379",
        is_regex=True,
        category=SSOTCategory.URL,
        python_config="config.redis_url",
        typescript_config="config.redisUrl",
        env_var="AUTOBOT_REDIS_URL",
        description="Redis URL",
        severity="high",
    ),
    SSOTMapping(
        pattern=r"http://127\.0\.0\.1:11434",
        is_regex=True,
        category=SSOTCategory.URL,
        python_config="config.ollama_url",
        typescript_config="config.ollamaUrl",
        env_var="AUTOBOT_OLLAMA_URL",
        description="Ollama API URL",
        severity="high",
    ),
    SSOTMapping(
        pattern=r"ws://172\.16\.168\.20:8001/ws",
        is_regex=True,
        category=SSOTCategory.URL,
        python_config="config.websocket_url",
        typescript_config="config.websocketUrl",
        env_var="AUTOBOT_WS_URL",
        description="WebSocket URL",
        severity="high",
    ),
]

# LLM Model Mappings
LLM_MODEL_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern=r"mistral:7b-instruct",
        is_regex=False,
        category=SSOTCategory.LLM_MODEL,
        python_config="config.llm.default_model",
        typescript_config="config.llm.defaultModel",
        env_var="AUTOBOT_DEFAULT_LLM_MODEL",
        description="Default LLM model",
        severity="high",
    ),
    SSOTMapping(
        pattern=r"nomic-embed-text:latest",
        is_regex=False,
        category=SSOTCategory.LLM_MODEL,
        python_config="config.llm.embedding_model",
        typescript_config="config.llm.embeddingModel",
        env_var="AUTOBOT_EMBEDDING_MODEL",
        description="Embedding model",
        severity="high",
    ),
    SSOTMapping(
        pattern=r"(llama3|mistral|dolphin|openchat|gemma|phi|deepseek|qwen).*:[0-9]+(b|B)",
        is_regex=True,
        category=SSOTCategory.LLM_MODEL,
        python_config="config.llm.default_model",
        typescript_config="config.llm.defaultModel",
        env_var="AUTOBOT_DEFAULT_LLM_MODEL",
        description="LLM model name",
        severity="high",
    ),
]

# All mappings combined
ALL_MAPPINGS: List[SSOTMapping] = (
    VM_IP_MAPPINGS + PORT_MAPPINGS + URL_MAPPINGS + LLM_MODEL_MAPPINGS
)


def get_mapping_for_value(value: str) -> Optional[SSOTMapping]:
    """
    Find SSOT mapping for a detected hardcoded value.

    Args:
        value: The detected hardcoded value

    Returns:
        SSOTMapping if found, None otherwise
    """
    for mapping in ALL_MAPPINGS:
        if mapping.is_regex:
            if re.search(mapping.pattern, value):
                return mapping
        else:
            if mapping.pattern in value:
                return mapping
    return None


def get_mappings_by_category(category: SSOTCategory) -> List[SSOTMapping]:
    """Get all mappings for a specific category."""
    return [m for m in ALL_MAPPINGS if m.category == category]


def get_high_severity_mappings() -> List[SSOTMapping]:
    """Get all high severity mappings (most important to fix)."""
    return [m for m in ALL_MAPPINGS if m.severity == "high"]


def export_mappings_as_json() -> str:
    """Export mappings as JSON for shell script consumption."""
    data = []
    for m in ALL_MAPPINGS:
        data.append(
            {
                "pattern": m.pattern,
                "is_regex": m.is_regex,
                "category": m.category.value,
                "python_config": m.python_config,
                "typescript_config": m.typescript_config,
                "env_var": m.env_var,
                "description": m.description,
                "severity": m.severity,
            }
        )
    return json.dumps(data, indent=2)


def get_ssot_suggestion(value: str, file_type: str = "python") -> Optional[str]:
    """
    Get SSOT config suggestion for a hardcoded value.

    Args:
        value: The detected hardcoded value
        file_type: 'python' or 'typescript'

    Returns:
        Suggestion string or None
    """
    mapping = get_mapping_for_value(value)
    if not mapping:
        return None

    if file_type == "python":
        return f"Use {mapping.python_config} from autobot_shared.ssot_config"
    else:
        return f"Use {mapping.typescript_config} from @/config/ssot-config"


def validate_against_ssot(
    hardcoded_values: List[Dict],
) -> List[Dict]:
    """
    Validate detected hardcoded values against SSOT mappings.

    Args:
        hardcoded_values: List of detected hardcoded values from EnvironmentAnalyzer

    Returns:
        List of values with SSOT mapping information added
    """
    results = []
    for hv in hardcoded_values:
        value = hv.get("value", "")
        mapping = get_mapping_for_value(value)

        result = hv.copy()
        if mapping:
            result["ssot_mapping"] = {
                "has_ssot_equivalent": True,
                "python_config": mapping.python_config,
                "typescript_config": mapping.typescript_config,
                "env_var": mapping.env_var,
                "description": mapping.description,
                "category": mapping.category.value,
                "severity": mapping.severity,
                "status": "NOT_USING_SSOT",
            }
        else:
            result["ssot_mapping"] = {
                "has_ssot_equivalent": False,
                "status": "NO_SSOT_MAPPING",
            }

        results.append(result)

    return results


def _group_violations_by_category(violations: List[Dict]) -> Dict[str, List]:
    """
    Group violations by their SSOT category.

    Args:
        violations: List of validated values with SSOT equivalents.

    Returns:
        Dictionary mapping category names to lists of violations.

    Issue #620.
    """
    by_category: Dict[str, List] = {}
    for v in violations:
        cat = v["ssot_mapping"]["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(v)
    return by_category


def _count_violations_by_severity(violations: List[Dict]) -> Dict[str, int]:
    """
    Count violations by severity level.

    Args:
        violations: List of validated values with SSOT equivalents.

    Returns:
        Dictionary with counts for high, medium, and low severity.

    Issue #620.
    """
    by_severity = {"high": 0, "medium": 0, "low": 0}
    for v in violations:
        sev = v["ssot_mapping"]["severity"]
        by_severity[sev] += 1
    return by_severity


def _get_high_priority_violations(
    violations: List[Dict], limit: int = 20
) -> List[Dict]:
    """
    Extract top high-priority violations with fix suggestions.

    Args:
        violations: List of validated values with SSOT equivalents.
        limit: Maximum number of violations to return.

    Returns:
        List of high-priority violation details.

    Issue #620.
    """
    return [
        {
            "file": v.get("file"),
            "line": v.get("line"),
            "value": v.get("value"),
            "suggestion": v["ssot_mapping"]["python_config"],
        }
        for v in violations
        if v["ssot_mapping"]["severity"] == "high"
    ][:limit]


def generate_ssot_coverage_report(hardcoded_values: List[Dict]) -> Dict:
    """
    Generate a coverage report showing SSOT usage vs hardcoded values.

    Args:
        hardcoded_values: List of detected hardcoded values

    Returns:
        Coverage report dictionary
    """
    validated = validate_against_ssot(hardcoded_values)

    with_ssot = [v for v in validated if v["ssot_mapping"]["has_ssot_equivalent"]]
    without_ssot = [
        v for v in validated if not v["ssot_mapping"]["has_ssot_equivalent"]
    ]

    by_category = _group_violations_by_category(with_ssot)
    by_severity = _count_violations_by_severity(with_ssot)

    return {
        "total_hardcoded": len(hardcoded_values),
        "with_ssot_equivalent": len(with_ssot),
        "without_ssot_equivalent": len(without_ssot),
        "ssot_compliance_pct": (
            round((1 - len(with_ssot) / len(hardcoded_values)) * 100, 1)
            if hardcoded_values
            else 100
        ),
        "violations_by_category": {k: len(v) for k, v in by_category.items()},
        "violations_by_severity": by_severity,
        "high_priority_violations": _get_high_priority_violations(with_ssot),
    }


# =============================================================================
# Shell Script Helper
# =============================================================================

# Known SSOT values for shell script (exact matches)
SSOT_VALUES_FOR_SHELL = {
    # VM IPs
    "172.16.168.20": "config.vm.main (AUTOBOT_BACKEND_HOST)",
    "172.16.168.21": "config.vm.frontend (AUTOBOT_FRONTEND_HOST)",
    "172.16.168.22": "config.vm.npu (AUTOBOT_NPU_WORKER_HOST)",
    "172.16.168.23": "config.vm.redis (AUTOBOT_REDIS_HOST)",
    "172.16.168.24": "config.vm.aistack (AUTOBOT_AI_STACK_HOST)",
    "172.16.168.25": "config.vm.browser (AUTOBOT_BROWSER_SERVICE_HOST)",
    # Ports (without colon for detection in different contexts)
    "8001": "config.port.backend (AUTOBOT_BACKEND_PORT)",
    "5173": "config.port.frontend (AUTOBOT_FRONTEND_PORT)",
    "6379": "config.port.redis (AUTOBOT_REDIS_PORT)",
    "11434": "config.port.ollama (AUTOBOT_OLLAMA_PORT)",
    "6080": "config.port.vnc (AUTOBOT_VNC_PORT)",
    # Models
    "mistral:7b-instruct": "config.llm.default_model (AUTOBOT_DEFAULT_LLM_MODEL)",
    "nomic-embed-text:latest": "config.llm.embedding_model (AUTOBOT_EMBEDDING_MODEL)",
}


if __name__ == "__main__":
    # Print JSON export for shell script consumption
    print(export_mappings_as_json())
