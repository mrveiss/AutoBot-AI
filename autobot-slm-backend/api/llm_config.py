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
from autobot_shared.ssot_config import config as _ssot_config
from models.database import Node, Setting
from services.auth import require_permission
from services.database import get_db
from services.encryption import decrypt_data
from services.playbook_executor import get_playbook_executor
from user_management.services.llm_secrets import (
    MaskedKeySubmitted,
    merge_provider_secret,
    public_provider_view,
)
from user_management.services.vault_client import VaultClientError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings/admin/llm", tags=["llm-config"])

# Setting key prefix for LLM config
_PREFIX = "llm_"

# ``api_key`` is write-only. ``public_provider_view`` drops it, but the model
# refills its "" default, so both responses also exclude the field itself (#17826).
_NO_PROVIDER_KEYS = {"config": {"providers": {"__all__": {"api_key"}}}}


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
    ollama_host: str = "0.0.0.0"  # nosec B104  # intentional bind to all interfaces for service/test
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


def _decrypt_provider_key(encrypted_key: str) -> str:
    """Decrypt a legacy inline-encrypted provider API key. Helper for _load_llm_config (#2371)."""
    if not encrypted_key:
        return ""
    try:
        return decrypt_data(encrypted_key)
    except Exception:
        return encrypted_key


async def _load_llm_config(db: AsyncSession) -> LLMConfig:
    """Load LLM config from Setting table.

    Provider API keys are never loaded: every entry goes through
    ``public_provider_view``, so nothing built from this can carry a key to a
    client (#17826). Helper for get/put endpoints (Issue #2371).
    """
    result = await db.execute(select(Setting).where(Setting.key.startswith(_PREFIX)))
    rows = {s.key: s.value for s in result.scalars().all()}

    providers = [LLMProviderConfig(**public_provider_view(p)) for p in _stored_providers(rows).values()]
    return LLMConfig(providers=providers, **_ollama_settings(rows))


def _json_list(rows: Dict[str, str], key: str) -> List[str]:
    raw = rows.get(key)
    return json.loads(raw) if raw else []


def _ollama_settings(rows: Dict[str, str]) -> dict:
    """Every non-provider LLMConfig field from Setting rows. Helper for _load_llm_config."""
    return dict(
        active_provider=rows.get("llm_active_provider", "ollama"),
        ollama_host=rows.get(
            "llm_ollama_host",
            # Intentional bind to all interfaces for service/test.
            "0.0.0.0",  # nosec B104
        ),
        ollama_port=int(rows.get("llm_ollama_port", "11434")),
        gpu_models=_json_list(rows, "llm_gpu_models"),
        cpu_models=_json_list(rows, "llm_cpu_models"),
        max_loaded_models=int(rows.get("llm_max_loaded_models", "5")),
        num_parallel=int(rows.get("llm_num_parallel", "4")),
        keep_alive=rows.get("llm_keep_alive", "10m"),
        flash_attention=rows.get("llm_flash_attention", "true").lower() == "true",
        kv_cache_type=rows.get("llm_kv_cache_type", "q8_0"),
    )


def _stored_providers(rows: Dict[str, str]) -> Dict[str, dict]:
    """Stored provider entries by name, secret references included (#17826)."""
    raw = rows.get("llm_providers")
    return {p.get("name", ""): p for p in json.loads(raw)} if raw else {}


async def _merge_providers(db: AsyncSession, providers: List[LLMProviderConfig]) -> List[dict]:
    """Resolve submitted providers against the stored ones. Helper for save_llm_config.

    A provider submitted without a key keeps its stored secret untouched; a
    display mask is refused with 422 rather than written as a key (#17826).
    Secrets are matched to providers by name, so names must be present and
    unique -- two entries sharing one would share, and overwrite, one secret.
    """
    names = [p.name for p in providers]
    if not all(names) or len(set(names)) != len(names):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="provider names must be unique and non-empty"
        )
    result = await db.execute(select(Setting).where(Setting.key == "llm_providers"))
    stored = _stored_providers({s.key: s.value for s in result.scalars().all()})
    try:
        return [await merge_provider_secret(p.name, p.model_dump(), stored.get(p.name)) for p in providers]
    except MaskedKeySubmitted as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except VaultClientError as exc:
        logger.error("LLM config save: secrets vault unavailable: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="secrets vault unavailable"
        ) from exc


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


@router.get("", response_model=LLMConfigResponse, response_model_exclude=_NO_PROVIDER_KEYS)
async def get_llm_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_CONFIG_READ))],
) -> LLMConfigResponse:
    """Get current LLM configuration (admin only).

    API keys are omitted from the response, never masked. Before #17826 a mask
    round-tripped back as a value and overwrote every stored key on save; a
    submitted mask is now refused with 422.
    """
    return LLMConfigResponse(config=await _load_llm_config(db))


@router.put("", response_model=LLMConfigResponse, response_model_exclude=_NO_PROVIDER_KEYS)
async def save_llm_config(
    config: LLMConfig,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_CONFIG_WRITE))],
) -> LLMConfigResponse:
    """Save LLM configuration (admin only).

    A provider's ``api_key`` is write-only: send one to set or rotate it, send
    none to leave the stored key untouched. Keys go to the unified-secrets vault
    (#10503), or inline-encrypted while the vault is not configured.
    """
    providers_data = await _merge_providers(db, config.providers)

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
    return LLMConfigResponse(config=await _load_llm_config(db), message="Configuration saved")


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
        endpoint = request.endpoint or _ssot_config.llm.ollama_endpoint
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
