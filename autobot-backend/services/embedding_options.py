# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The embedding models the user can switch to right now (#19378, part of #19373).

One listing: the configured providers' models (``model_manager_service``), kept only where the
canonical ``is_embedding_model_id`` says the id is an embedding model, so a chat model such as
``phi3:mini`` never appears as a choice (#18834). The resolver's active model is marked. It is
listed even when no provider reports it, so the user always sees what is in use.

``dimension`` is ``None`` for every option: nothing records a model's vector width before it has
embedded (the knowledge base's own figure is a per-provider guess). The switch flow (#19379)
learns it by embedding once.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from autobot_shared.embedding_model import active_embedding_model, is_embedding_model_id
from services.model_manager_service import get_available_models

# Ollama resolves an untagged name to ``:latest``, so the two spellings name one model.
_IMPLIED_TAG = ":latest"


def _same_model(listed: str, active: str) -> bool:
    def canonical(name: str) -> str:
        return name if ":" in name.rsplit("/", 1)[-1] else name + _IMPLIED_TAG

    return canonical(listed.strip().lower()) == canonical(active.strip().lower())


def _option(name: str, provider: str | None, available: bool, active: bool) -> Dict[str, Any]:
    return {"name": name, "provider": provider, "available": available, "active": active, "dimension": None}


def build_embedding_options(listing: Dict[str, Any], active: str) -> Dict[str, Any]:
    """The options payload from a provider *listing* and the *active* model id."""
    options: List[Dict[str, Any]] = [
        _option(m["name"], m.get("provider"), bool(m.get("available", True)), _same_model(m["name"], active))
        for m in listing.get("models", [])
        if is_embedding_model_id(m.get("name", ""))
    ]
    if not any(option["active"] for option in options):
        options.insert(0, _option(active, None, False, True))
    return {
        "active": active,
        "models": options,
        "total_count": len(options),
        "providers_errored": list(listing.get("providers_errored", [])),
    }


async def embedding_model_options() -> Dict[str, Any]:
    """The embedding-model choices, with the active one marked."""
    listing = await get_available_models()
    active = await asyncio.to_thread(active_embedding_model)  # may read Redis; off the event loop
    return build_embedding_options(listing, active)
