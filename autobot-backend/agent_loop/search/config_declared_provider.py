# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data-driven search-source definitions (#12625, design §4.7).

Lets a non-code contributor add a simple, credential-less search source by
declaring a URL + a single query parameter + a declarative JSON response-parse
rule in ``config/research_sources.yaml`` — no Python subclass required.
Complex-auth sources stay Python classes (design §4.7, e.g. ``BraveSearchProvider``):
this mechanism intentionally supports only GET + one query parameter and plain
dict/list JSON traversal — never arbitrary code execution (no eval/Jinja).

SSRF (#6533/#12278): a config-declared ``base_url`` is fetched by the server on
every search — a server-side request forgery surface by construction. Every
request goes through the SAME layered guard the repo's other outbound-URL
sinks use (``api/provider_auth.py``, ``api/marketplace_sources.py``,
``content_reach/_url_guard.py``, ``knowledge/connectors/oauth_flow.py``,
``skills/external_importer.py``):

1. Scheme + hostname validated at config-load time (catches an authoring
   mistake before it ever reaches a request).
2. The host is re-resolved and the connector pinned to that IP via
   :func:`autobot_shared.security.ssrf_guard.pinned_connector` on **every**
   call (never cached) — the pre-resolved public IP defeats a DNS-rebind
   between the safety check and the socket connect (#12278).
3. The runtime query is passed **only** through aiohttp's ``params=`` dict,
   never string-interpolated into the URL, so a hostile query value can never
   alter the outbound request's scheme, host, or port.
4. Redirects are disabled (``allow_redirects=False``); any 3xx response is
   rejected outright rather than followed (mirrors
   ``autobot_shared.security.ssrf_guard.fetch_safe_url`` /
   ``api/marketplace_sources.py``).

Deliberately **not** routed through the shared pooled
``autobot_shared.http_client`` (#12979): a pinned connector is a
session-level object the pool would silently discard on reuse, reopening the
DNS-rebind hole #12278 closed — same carve-out category as
``knowledge/connectors/oauth_flow.py`` / ``skills/external_importer.py``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
import yaml

from agent_loop.search.base import DEFAULT_RESULT_COUNT, SearchResult, WebSearchProvider
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "research_sources.yaml")
_ALLOWED_SCHEMES = ("http", "https")

# Module-level constants (never inline literals): request timeout when a
# source definition omits ``timeout_seconds``, and a hard response-size cap
# so a misbehaving/malicious source can't exhaust memory.
_DEFAULT_TIMEOUT_SECONDS = 15.0
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass
class SourceDefinition:
    """One config-declared search source (design §4.7)."""

    name: str
    category: str
    base_url: str
    query_param: str
    extra_params: Dict[str, str] = field(default_factory=dict)
    result_path: str = ""
    title_field: str = "title"
    url_field: str = "url"
    snippet_field: str = ""
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS


def _validate_definition(raw: Dict[str, Any]) -> Optional[SourceDefinition]:
    """Build one ``SourceDefinition`` from a raw config dict, or None if malformed/unsafe.

    Never raises: a bad entry is logged and skipped so one malformed source
    can never take down the others or block startup.
    """
    name = str(raw.get("name", "")).strip()
    base_url = str(raw.get("base_url", "")).strip()
    query_param = str(raw.get("query_param", "")).strip()
    category = str(raw.get("category", "")).strip()
    if not (name and base_url and query_param and category):
        logger.warning("research_sources.yaml: skipping incomplete source entry: %r", raw)
        return None
    parsed = urlparse(base_url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        logger.warning("research_sources.yaml: skipping source %r — unsafe base_url %r", name, base_url)
        return None
    return SourceDefinition(
        name=name,
        category=category,
        base_url=base_url,
        query_param=query_param,
        extra_params={str(k): str(v) for k, v in (raw.get("extra_params") or {}).items()},
        result_path=str(raw.get("result_path", "")),
        title_field=str(raw.get("title_field", "title")),
        url_field=str(raw.get("url_field", "url")),
        snippet_field=str(raw.get("snippet_field", "")),
        timeout_seconds=float(raw.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)),
    )


def load_source_definitions(config_path: Optional[str] = None) -> List[SourceDefinition]:
    """Load + validate every source declared in ``research_sources.yaml``.

    Never raises: a missing file, empty file, or malformed entry degrades to
    an empty/partial list — matches
    ``agent_loop.search.registry._populate_default_providers`` (population
    failures are logged, never block startup).
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    try:
        with open(path, encoding="utf-8") as fh:
            raw_config = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        logger.debug("research_sources.yaml not found at %s — no config-declared sources", path)
        return []
    except Exception as exc:  # noqa: BLE001 — a broken config file must never block startup
        logger.warning("research_sources.yaml: failed to load %s: %s", path, exc)
        return []
    raw_sources = raw_config.get("sources", [])
    if not isinstance(raw_sources, list):
        return []
    return [d for d in (_validate_definition(raw) for raw in raw_sources) if d is not None]


def _dig(payload: Any, dotted_path: str) -> Any:
    """Traverse *payload* by a dotted key path (pure dict access — no eval/exec)."""
    node = payload
    if not dotted_path:
        return node
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _item_field(item: Dict[str, Any], dotted_path: str) -> str:
    """Extract one string field from a result item via a dotted path (or top-level key)."""
    if not dotted_path:
        return ""
    value = _dig(item, dotted_path)
    return str(value) if value is not None else ""


class ConfigDeclaredSearchProvider(WebSearchProvider):
    """A ``WebSearchProvider`` backed entirely by one data-driven ``SourceDefinition``.

    No credentials, no per-source Python subclass. See the module docstring
    for the SSRF guarantees every ``search()`` call enforces.
    """

    def __init__(self, definition: SourceDefinition) -> None:
        """Bind this provider instance to one config-declared source."""
        super().__init__(settings={})
        self.provider_name = definition.name
        self.supported_categories = (definition.category,)
        self._definition = definition

    async def is_available(self) -> bool:
        """Cheap pre-check only — the authoritative, DNS-rebind-safe check is
        the fresh ``pinned_connector`` resolve inside ``search()`` itself.
        """
        from autobot_shared.url_safety import is_public_url_async  # noqa: PLC0415

        return await is_public_url_async(self._definition.base_url)

    async def _pinned_session_kwargs(self) -> Dict[str, Any]:
        """Resolve-once + pin the connector to base_url — fresh on every call (#12278)."""
        from autobot_shared.security.ssrf_guard import pinned_connector  # noqa: PLC0415

        connector = await pinned_connector(self._definition.base_url)
        timeout = aiohttp.ClientTimeout(total=self._definition.timeout_seconds)
        return {"connector": connector, "timeout": timeout}

    def _build_params(self, query: str) -> Dict[str, str]:
        """Runtime query goes ONLY into the params dict — never string-built into the URL."""
        params = dict(self._definition.extra_params)
        params[self._definition.query_param] = query
        return params

    def _parse_results(self, payload: Any, count: int) -> List[SearchResult]:
        """Declarative dict/list traversal — no code execution on the response."""
        items = _dig(payload, self._definition.result_path)
        if not isinstance(items, list):
            return []
        results: List[SearchResult] = []
        for item in items[:count]:
            if not isinstance(item, dict):
                continue
            url = _item_field(item, self._definition.url_field)
            if not url:
                continue
            results.append(
                SearchResult(
                    title=_item_field(item, self._definition.title_field),
                    url=url,
                    snippet=_item_field(item, self._definition.snippet_field),
                    source=self._definition.name,
                )
            )
        return results

    async def search(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        count: int = DEFAULT_RESULT_COUNT,
    ) -> List[SearchResult]:
        """Query the config-declared source; raise on any unsafe/failed request
        so the registry's fallback chain takes over (design: "preserve
        graceful fallback").
        """
        from autobot_shared.security.ssrf_guard import SSRFError  # noqa: PLC0415

        try:
            session_kwargs = await self._pinned_session_kwargs()
        except SSRFError as exc:
            raise RuntimeError(f"source {self._definition.name!r} blocked by SSRF guard: {exc}") from exc

        async with aiohttp.ClientSession(**session_kwargs) as session:
            async with session.get(
                self._definition.base_url,
                params=self._build_params(query),
                allow_redirects=False,  # a redirect to an internal address must never be followed (#12278)
            ) as resp:
                if 300 <= resp.status < 400:
                    raise RuntimeError(
                        f"source {self._definition.name!r} returned a redirect (HTTP {resp.status}); "
                        "redirects are rejected by the SSRF guard"
                    )
                if resp.status != 200:
                    raise RuntimeError(f"source {self._definition.name!r} returned HTTP {resp.status}")
                body = await resp.content.read(_MAX_RESPONSE_BYTES + 1)

        try:
            payload = json.loads(body[:_MAX_RESPONSE_BYTES].decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"source {self._definition.name!r} returned invalid JSON: {exc}") from exc

        return self._parse_results(payload, count)
