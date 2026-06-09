# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM LLM Configuration API Routes (#2371)

Admin-only endpoints for managing LLM provider configuration.
Config is stored in the Setting table and pushed to fleet nodes via Ansible.
"""

import json
import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from autobot_shared.auth.permissions import Permission
from models.database import Node, Setting
from services.auth import require_permission
from services.database import get_db
from services.encryption import decrypt_data, encrypt_data
from services.playbook_executor import get_playbook_executor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings/admin/llm", tags=["llm-config"])

# Setting key prefix for LLM config
_PREFIX = "llm_"


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    name: str
    enabled: bool = False
    api_key: str = ""
    endpoint: str = ""
    model: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=128000)


class LLMConfig(BaseModel):
    """Full LLM configuration stored in SLM settings."""

    active_provider: str = "ollama"
    providers: List[LLMProviderConfig] = []
    # Ollama server settings (pushed via Ansible)
    ollama_host: str = "0.0.0.0"  # nosec B104 - intentional bind to all interfaces for service/test
    ollama_port: int = 11434
    gpu_models: List[str] = []
    cpu_models: List[str] = []
    max_loaded_models: int = 5
    num_parallel: int = 4
    keep_alive: str = "10m"
    flash_attention: bool = True
    kv_cache_type: str = "q8_0"


class LLMConfigResponse(BaseModel):
    """Response wrapper for LLM config."""

    config: LLMConfig
    message: str = "OK"


class LLMTestRequest(BaseModel):
    """Request to test an LLM provider connection."""

    provider: str
    endpoint: str = ""
    api_key: str = ""
    model: str = ""


class LLMTestResponse(BaseModel):
    """Result of an LLM provider connection test."""

    success: bool
    message: str
    provider: str
    latency_ms: float | None = None


class LLMApplyRequest(BaseModel):
    """Request to push LLM config to fleet nodes."""

    node_ids: List[str] | None = None


class LLMApplyResponse(BaseModel):
    """Result of applying LLM config to fleet."""

    success: bool
    message: str
    node_count: int
    output: str | None = None


def _mask_api_key(key: str) -> str:
    """Mask API key for safe display. Helper for get_llm_config (#2371)."""
    if not key or len(key) < 8:
        return "****" if key else ""
    return f"{key[:4]}...{key[-4:]}"


def _decrypt_provider_key(encrypted_key: str) -> str:
    """Decrypt a provider API key. Helper for _load_llm_config (#2371)."""
    if not encrypted_key:
        return ""
    try:
        return decrypt_data(encrypted_key)
    except Exception:
        return encrypted_key


async def _load_llm_config(db: AsyncSession) -> LLMConfig:
    """Load LLM config from Setting table.

    Helper for get/put endpoints (Issue #2371).
    """
    result = await db.execute(select(Setting).where(Setting.key.startswith(_PREFIX)))
    rows = {s.key: s.value for s in result.scalars().all()}

    providers_raw = rows.get("llm_providers")
    if providers_raw:
        parsed = json.loads(providers_raw)
        for p in parsed:
            p["api_key"] = _decrypt_provider_key(p.get("api_key", ""))
        providers = [LLMProviderConfig(**p) for p in parsed]
    else:
        providers = []

    gpu_models_raw = rows.get("llm_gpu_models")
    gpu_models = json.loads(gpu_models_raw) if gpu_models_raw else []

    cpu_models_raw = rows.get("llm_cpu_models")
    cpu_models = json.loads(cpu_models_raw) if cpu_models_raw else []

    return LLMConfig(
        active_provider=rows.get("llm_active_provider", "ollama"),
        providers=providers,
        ollama_host=rows.get(
            "llm_ollama_host", "0.0.0.0"
        ),  # nosec B104 - intentional bind to all interfaces for service/test
        ollama_port=int(rows.get("llm_ollama_port", "11434")),
        gpu_models=gpu_models,
        cpu_models=cpu_models,
        max_loaded_models=int(rows.get("llm_max_loaded_models", "5")),
        num_parallel=int(rows.get("llm_num_parallel", "4")),
        keep_alive=rows.get("llm_keep_alive", "10m"),
        flash_attention=rows.get("llm_flash_attention", "true").lower() == "true",
        kv_cache_type=rows.get("llm_kv_cache_type", "q8_0"),
    )


async def _upsert_setting(db: AsyncSession, key: str, value: str, desc: str) -> None:
    """Insert or update a setting row.

    Helper for save_llm_config (Issue #2371).
    """
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value, description=desc))


@router.get("", response_model=LLMConfigResponse)
async def get_llm_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_CONFIG_READ))],
) -> LLMConfigResponse:
    """Get current LLM configuration (admin only).

    API keys are masked in the response for security.
    """
    config = await _load_llm_config(db)
    # Mask API keys — never send full keys to the frontend
    for provider in config.providers:
        provider.api_key = _mask_api_key(provider.api_key)
    return LLMConfigResponse(config=config)


@router.put("", response_model=LLMConfigResponse)
async def save_llm_config(
    config: LLMConfig,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_CONFIG_WRITE))],
) -> LLMConfigResponse:
    """Save LLM configuration (admin only).

    API keys are encrypted before storage via services.encryption.
    """
    # Encrypt API keys before persisting to Setting table
    providers_data = []
    for p in config.providers:
        d = p.model_dump()
        if d.get("api_key") and not d["api_key"].startswith("gAAA"):
            d["api_key"] = encrypt_data(d["api_key"])
        providers_data.append(d)

    settings_map = {
        "llm_active_provider": (config.active_provider, "Active LLM provider"),
        "llm_providers": (
            json.dumps(providers_data),
            "LLM providers (JSON, keys encrypted)",
        ),
        "llm_ollama_host": (config.ollama_host, "Ollama listen host"),
        "llm_ollama_port": (str(config.ollama_port), "Ollama listen port"),
        "llm_gpu_models": (json.dumps(config.gpu_models), "GPU model list (JSON)"),
        "llm_cpu_models": (json.dumps(config.cpu_models), "CPU model list (JSON)"),
        "llm_max_loaded_models": (
            str(config.max_loaded_models),
            "Max models hot in RAM",
        ),
        "llm_num_parallel": (str(config.num_parallel), "Concurrent requests per model"),
        "llm_keep_alive": (config.keep_alive, "Model idle timeout"),
        "llm_flash_attention": (str(config.flash_attention).lower(), "Flash attention"),
        "llm_kv_cache_type": (config.kv_cache_type, "KV cache quantization type"),
    }
    for key, (value, desc) in settings_map.items():
        await _upsert_setting(db, key, value, desc)

    await db.commit()
    logger.info(
        "LLM config saved: provider=%s models=%d+%d",
        config.active_provider,
        len(config.gpu_models),
        len(config.cpu_models),
    )
    return LLMConfigResponse(config=config, message="Configuration saved")


async def _test_ollama(endpoint: str) -> LLMTestResponse:
    """Test Ollama connection. Helper for test_llm_connection (#2371)."""
    import time

    import httpx

    url = f"{endpoint}/api/tags"
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
        latency = (time.monotonic() - t0) * 1000
        if resp.status_code == 200:
            model_count = len(resp.json().get("models", []))
            return LLMTestResponse(
                success=True,
                message=f"Connected. {model_count} models available.",
                provider="ollama",
                latency_ms=round(latency, 1),
            )
        return LLMTestResponse(success=False, message=f"HTTP {resp.status_code}", provider="ollama")
    except Exception:
        return LLMTestResponse(success=False, message="Connection failed", provider="ollama")


async def _test_cloud_provider(provider: str, endpoint: str, api_key: str) -> LLMTestResponse:
    """Test cloud provider connection. Helper for test_llm_connection (#2371)."""
    import time

    import httpx

    try:
        t0 = time.monotonic()
        headers: Dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{endpoint.rstrip('/')}/models", headers=headers)
        latency = (time.monotonic() - t0) * 1000
        if resp.status_code == 200:
            return LLMTestResponse(
                success=True,
                message="Connected successfully.",
                provider=provider,
                latency_ms=round(latency, 1),
            )
        return LLMTestResponse(
            success=False,
            message=f"HTTP {resp.status_code}",
            provider=provider,
        )
    except Exception:
        return LLMTestResponse(success=False, message="Connection failed", provider=provider)


@router.post("/test", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_CONFIG_READ))],
) -> LLMTestResponse:
    """Test LLM provider connection (admin only)."""
    provider = request.provider.lower()
    if provider == "ollama":
        endpoint = request.endpoint or "http://localhost:11434"
        return await _test_ollama(endpoint)

    if not request.endpoint:
        return LLMTestResponse(
            success=False,
            message="Endpoint URL required for cloud providers",
            provider=provider,
        )
    return await _test_cloud_provider(provider, request.endpoint, request.api_key)


@router.post("/apply", response_model=LLMApplyResponse)
async def apply_llm_config(
    request: LLMApplyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_CONFIG_WRITE))],
) -> LLMApplyResponse:
    """Push LLM config to fleet nodes via Ansible (admin only)."""
    config = await _load_llm_config(db)

    # Resolve target nodes
    node_count = 0
    limit: List[str] | None = None
    if request.node_ids:
        node_result = await db.execute(select(Node).where(Node.node_id.in_(request.node_ids)))
        nodes = node_result.scalars().all()
        limit = [n.node_id for n in nodes]
        node_count = len(limit)
    else:
        node_result = await db.execute(select(Node))
        node_count = len(node_result.scalars().all())

    # Build extra_vars for the Ansible llm role
    extra_vars = {
        "llm_host": config.ollama_host,
        "llm_port": config.ollama_port,
        "llm_gpu_models_csv": ",".join(config.gpu_models),
        "llm_cpu_models_csv": ",".join(config.cpu_models),
        "llm_max_loaded_models": config.max_loaded_models,
        "llm_num_parallel": config.num_parallel,
        "llm_keep_alive": config.keep_alive,
        "llm_flash_attention": config.flash_attention,
        "llm_kv_cache_type": config.kv_cache_type,
        "llm_pull_models": True,
    }

    try:
        executor = get_playbook_executor()
        play_result = await executor.execute_playbook(
            playbook_name="playbooks/update-llm-config.yml",
            limit=limit,
            tags=["llm"],
            extra_vars=extra_vars,
        )
        logger.info(
            "LLM config applied: nodes=%d success=%s",
            node_count,
            play_result.get("success"),
        )
        return LLMApplyResponse(
            success=play_result.get("success", False),
            message=play_result.get("message", "Apply complete"),
            node_count=node_count,
            output=play_result.get("output"),
        )
    except Exception as exc:
        logger.error("LLM config apply failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc
