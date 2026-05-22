# Writing a Connector

This guide explains how to implement a new AutoBot knowledge-source connector.

## Overview

All connectors extend `AbstractConnector` from `knowledge.connectors.base`.  The class
requires four abstract methods that define the connector contract:

| Method | Purpose |
|---|---|
| `test_connection()` | Verify the source is reachable and credentials are valid |
| `discover_sources()` | Return all sources currently available |
| `fetch_content(source_id)` | Fetch content for a single source |
| `detect_changes(since)` | Return sources that changed since a datetime |

A default `sync()` orchestrates these methods for you.  Override it only when
your connector needs a custom sync strategy (see `WebCrawlerConnector` for an example).

## Minimal Skeleton

```python
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import ChangeInfo, ConnectorConfig, ContentResult, SourceInfo, SyncResult
from knowledge.connectors.registry import ConnectorRegistry

@ConnectorRegistry.register("my_source")
class MySourceConnector(AbstractConnector):
    connector_type = "my_source"
    tier = 0  # 0=zero-config, 1=free API key, 2=credentials

    async def test_connection(self) -> bool: ...
    async def discover_sources(self) -> list[SourceInfo]: ...
    async def fetch_content(self, source_id: str) -> ContentResult | None: ...
    async def detect_changes(self, since=None) -> list[ChangeInfo]: ...
```

## Acceptance Testing Requirement

**Every new connector MUST ship with an acceptance test subclass that exercises
the full interface contract.**

The acceptance harness lives in `knowledge.connectors.testing.acceptance` and
provides a ready-made suite of interface-level tests.  Subclass it, set
`self.connector` in an `autouse` fixture, and all contract tests are inherited
automatically:

```python
# autobot-backend/knowledge/connectors/tests/test_my_source_acceptance.py

import pytest
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.my_source import MySourceConnector
from knowledge.connectors.testing.acceptance import ConnectorAcceptanceTest


class TestMySourceConnectorAcceptance(ConnectorAcceptanceTest):

    @pytest.fixture(autouse=True)
    def setup(self):
        self.connector = MySourceConnector(ConnectorConfig(
            connector_id="test-my-source",
            connector_type="my_source",
            name="Test",
            config={...},
        ))
        # Mock external transports here, not in the harness.
        yield
```

The harness tests the following:

- `test_connection()` returns `bool`
- `discover_sources()` returns `list[SourceInfo]` with non-empty `source_id` and `name`
- `fetch_content()` returns `ContentResult | None` with required fields
- `detect_changes()` returns `list[ChangeInfo]` with valid `change_type`
- `sync(incremental=False)` returns a valid `SyncResult`
- `sync(incremental=True)` returns a valid `SyncResult`
- Incremental sync count does not exceed full sync count

### Key rules

- The harness asserts on **return types and shapes only** — mocking transports
  is the subclass's responsibility.
- Tests must run without live external services.  Use `unittest.mock.patch`
  to mock HTTP clients, file systems, or databases.
- Place acceptance tests in `knowledge/connectors/tests/test_<type>_acceptance.py`.
- All tests must pass in CI alongside existing unit tests (no special setup
  beyond `pytest`).

### Reference implementations

- `FileServerConnector` → `tests/test_file_server_acceptance.py` — uses `tmp_path`
- `WebCrawlerConnector` → `tests/test_web_crawler_acceptance.py` — mocks WebFetcher

## Registering Your Connector

Decorate the class with `@ConnectorRegistry.register("<type>")` (see skeleton
above).  The registry is loaded automatically by the knowledge base router; no
additional wiring is required.

## Tiers

Set the `tier` class attribute to document setup complexity for the UI:

- `0` — Zero-config (local file, unauthenticated URL)
- `1` — Free API key or environment variable
- `2` — OAuth, credentials, or private connection string
