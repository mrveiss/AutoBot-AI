# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend's client of the SLM self-model API (#22277, #22278).

SLM Postgres is the system of record; the backend holds no copy. Both calls go through the SLM
client's credentialed, egress-guarded request path (``SLMNodeServicesMixin._slm_json``) and raise
``aiohttp.ClientResponseError`` on a non-2xx answer, so a refused credential is not read as an empty model.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from autobot_shared import node_proxy
from services.slm_client import get_slm_client

SELF_MODEL_PATH = "/api/nodes/self-model"


class SelfModelUnavailable(RuntimeError):
    """The SLM client is not configured, so the self-model cannot be reached."""


def _client():
    client = get_slm_client()
    if client is None:
        raise SelfModelUnavailable("SLM client is not initialised")
    return client


async def push_observations(source: str, scope_kinds: Iterable[str], observations: List[Dict[str, Any]]) -> dict:
    """POST one producer's complete batch; returns ``{"upserted", "changed", "revision"}``."""
    body = {"source": source, "scope_kinds": list(scope_kinds), "observations": observations}
    headers = node_proxy.internal_headers()  # the SLM accepts observations only from the backend's service key
    return await _client()._slm_json("POST", f"{SELF_MODEL_PATH}/observations", json=body, headers=headers)


async def query_entities(filters: Dict[str, Any]) -> dict:
    """GET entities matching the non-empty *filters* (kind, name, node_id, status, limit)."""
    params = {key: str(value) for key, value in filters.items() if value not in (None, "")}
    return await _client()._slm_json("GET", f"{SELF_MODEL_PATH}/entities", params=params)


async def node_ids_for_hosts(hosts: Iterable[str]) -> Dict[str, str]:
    """The SLM node id of each of *hosts* (addresses) that is a managed node; an unmanaged host is absent."""
    wanted = sorted({h for h in hosts if h})
    if not wanted:
        return {}
    return await _client()._slm_json("GET", f"{SELF_MODEL_PATH}/node-ids", params={"hosts": ",".join(wanted)})
