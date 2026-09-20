---
type: fix
scope: backend
issue: 17138
pr: 0000
---
`knowledge/connectors/__init__.py` no longer imports every connector module (and their third-party deps: aiohttp, defusedxml, ...) at package-import time -- `registry.ConnectorRegistry` now resolves and imports a connector's module lazily, on first `create()`/`get_registered_class()`/`list_types()` call. Same fix for `autobot_shared/plugin_sdk/loader.py`'s `jsonschema` import, reached via `middleware/__init__.py`. Removed `defusedxml` and `jsonschema` from `.github/workflows/migration-gate.yml`'s install list (verified empirically); `aiohttp` and `prometheus_client` stay -- they're still needed via two other, unrelated eager `__init__.py` files (`autobot_shared.security`, `autobot_shared.monitoring`), tracked as a follow-up (#17143).
