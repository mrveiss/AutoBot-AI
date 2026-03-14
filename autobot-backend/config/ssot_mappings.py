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

All patterns are derived dynamically from ssot_config Pydantic model defaults.
No hardcoded IPs or ports in this file — they live in ssot_config.py only.
VM roles are assigned by the SLM machine; IPs vary per deployment.

Issue: #642 - Centralize Environment Variables with SSOT Config Validation
Related: #599 - SSOT Configuration System Epic
Refactored: #1653 - Dynamic patterns from ssot_config model defaults
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from autobot_shared.ssot_config import AutoBotConfig, LLMConfig, PortConfig, VMConfig


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
# Helpers — read Pydantic model defaults (immune to env-var overrides)
# =============================================================================


def _vm_default(field_name: str) -> str:
    """Get the Pydantic model default for a VM field."""
    return VMConfig.model_fields[field_name].default


def _port_default(field_name: str) -> int:
    """Get the Pydantic model default for a port field."""
    return PortConfig.model_fields[field_name].default


def _llm_default(field_name: str) -> str:
    """Get the Pydantic model default for an LLM field."""
    return LLMConfig.model_fields[field_name].default


def _url_default(attr_name: str) -> str:
    """Get computed URL from a clean SSOTConfig (no env overrides)."""
    clean = AutoBotConfig.model_construct(
        vm=VMConfig.model_construct(),
        port=PortConfig.model_construct(),
    )
    return getattr(clean, attr_name)


# =============================================================================
# SSOT Mappings Registry — all patterns from ssot_config model defaults
# =============================================================================

# VM IP metadata: (field_name, config_path, description, severity)
_VM_REGISTRY = [
    ("slm", "vm.slm", "SLM Server VM IP", "high"),
    ("main", "vm.main", "Main machine IP", "high"),
    ("frontend", "vm.frontend", "Frontend VM IP", "high"),
    ("npu", "vm.npu", "NPU Worker VM IP", "high"),
    ("redis", "vm.redis", "Redis VM IP", "high"),
    ("aistack", "vm.aistack", "AI Stack VM IP", "high"),
    ("browser", "vm.browser", "Browser Service VM IP", "high"),
    ("ollama", "vm.ollama", "Ollama host", "medium"),
]

VM_IP_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern=_vm_default(field),
        is_regex=False,
        category=SSOTCategory.VM_IP,
        python_config=f"config.{path}",
        typescript_config=f"config.{path}",
        env_var=VMConfig.model_fields[field].alias,
        description=desc,
        severity=sev,
    )
    for field, path, desc, sev in _VM_REGISTRY
]

# Port metadata: (field_name, config_path, description, severity)
_PORT_REGISTRY = [
    ("slm", "port.slm", "SLM Server API port", "high"),
    ("backend", "port.backend", "Backend API port", "high"),
    ("frontend", "port.frontend", "Frontend port", "medium"),
    ("redis", "port.redis", "Redis port", "high"),
    ("ollama", "port.ollama", "Ollama API port", "high"),
    ("vnc", "port.vnc", "VNC noVNC port", "medium"),
    ("aistack", "port.aistack", "AI Stack port", "medium"),
    ("npu", "port.npu", "NPU Worker port", "medium"),
    ("tts", "port.tts", "TTS Worker port", "medium"),
]

PORT_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern=rf":{_port_default(field)}\b",
        is_regex=True,
        category=SSOTCategory.PORT,
        python_config=f"config.{path}",
        typescript_config=f"config.{path}",
        env_var=PortConfig.model_fields[field].alias,
        description=desc,
        severity=sev,
    )
    for field, path, desc, sev in _PORT_REGISTRY
]

# URL metadata: (py_attr, ts_attr, env_var, description)
_URL_REGISTRY = [
    ("backend_url", "backendUrl", "AUTOBOT_BACKEND_URL", "Backend API URL"),
    ("frontend_url", "frontendUrl", "AUTOBOT_FRONTEND_URL", "Frontend URL"),
    ("redis_url", "redisUrl", "AUTOBOT_REDIS_URL", "Redis URL"),
    ("ollama_url", "ollamaUrl", "AUTOBOT_OLLAMA_URL", "Ollama API URL"),
    ("websocket_url", "websocketUrl", "AUTOBOT_WS_URL", "WebSocket URL"),
    (
        "tts_worker_url",
        "ttsWorkerUrl",
        "AUTOBOT_TTS_WORKER_URL",
        "TTS Worker URL",
    ),
]

URL_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern=re.escape(_url_default(py_attr)),
        is_regex=True,
        category=SSOTCategory.URL,
        python_config=f"config.{py_attr}",
        typescript_config=f"config.{ts_attr}",
        env_var=env,
        description=desc,
        severity="high",
    )
    for py_attr, ts_attr, env, desc in _URL_REGISTRY
]

# LLM Model Mappings
LLM_MODEL_MAPPINGS: List[SSOTMapping] = [
    SSOTMapping(
        pattern=_llm_default("default_model"),
        is_regex=False,
        category=SSOTCategory.LLM_MODEL,
        python_config="config.llm.default_model",
        typescript_config="config.llm.defaultModel",
        env_var="AUTOBOT_DEFAULT_LLM_MODEL",
        description="Default LLM model",
        severity="high",
    ),
    SSOTMapping(
        pattern=_llm_default("embedding_model"),
        is_regex=False,
        category=SSOTCategory.LLM_MODEL,
        python_config="config.llm.embedding_model",
        typescript_config="config.llm.embeddingModel",
        env_var="AUTOBOT_EMBEDDING_MODEL",
        description="Embedding model",
        severity="high",
    ),
    SSOTMapping(
        pattern=(
            r"(llama3|mistral|dolphin|openchat|gemma|phi"
            r"|deepseek|qwen).*:[0-9]+(b|B)"
        ),
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


def get_mappings_by_category(
    category: SSOTCategory,
) -> List[SSOTMapping]:
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
        return f"Use {mapping.python_config} " f"from autobot_shared.ssot_config"
    return f"Use {mapping.typescript_config} from @/config/ssot-config"


def validate_against_ssot(
    hardcoded_values: List[Dict],
) -> List[Dict]:
    """
    Validate detected hardcoded values against SSOT mappings.

    Args:
        hardcoded_values: List of detected hardcoded values
            from EnvironmentAnalyzer

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


def _group_violations_by_category(
    violations: List[Dict],
) -> Dict[str, List]:
    """
    Group violations by their SSOT category.

    Issue #620.
    """
    by_category: Dict[str, List] = {}
    for v in violations:
        cat = v["ssot_mapping"]["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(v)
    return by_category


def _count_violations_by_severity(
    violations: List[Dict],
) -> Dict[str, int]:
    """
    Count violations by severity level.

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


def generate_ssot_coverage_report(
    hardcoded_values: List[Dict],
) -> Dict:
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
            round(
                (1 - len(with_ssot) / len(hardcoded_values)) * 100,
                1,
            )
            if hardcoded_values
            else 100
        ),
        "violations_by_category": {k: len(v) for k, v in by_category.items()},
        "violations_by_severity": by_severity,
        "high_priority_violations": _get_high_priority_violations(with_ssot),
    }


# =============================================================================
# Shell Script Helper — derived from config model defaults
# =============================================================================

SSOT_VALUES_FOR_SHELL = {
    **{
        _vm_default(f): (f"config.{p} ({VMConfig.model_fields[f].alias})")
        for f, p, _, _ in _VM_REGISTRY
    },
    **{
        str(_port_default(f)): (f"config.{p} ({PortConfig.model_fields[f].alias})")
        for f, p, _, _ in _PORT_REGISTRY
    },
    _llm_default("default_model"): (
        "config.llm.default_model (AUTOBOT_DEFAULT_LLM_MODEL)"
    ),
    _llm_default("embedding_model"): (
        "config.llm.embedding_model (AUTOBOT_EMBEDDING_MODEL)"
    ),
}


if __name__ == "__main__":
    print(export_mappings_as_json())  # noqa: print
