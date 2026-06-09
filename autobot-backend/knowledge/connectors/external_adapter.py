# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
External Connector Adapter

Issue #8150: Wraps any third-party Python connector package that implements the
subprocess/stdout newline-delimited JSON protocol into an AutoBot AbstractConnector.
One adapter supports the full set of compatible connector packages.

Subprocess protocol
-------------------
Compatible packages accept commands via argv and emit newline-delimited JSON:

    python main.py spec                              -> connector specification
    python main.py check --config cfg.json          -> connection status
    python main.py discover --config cfg.json       -> available streams/catalog
    python main.py read --config cfg.json --catalog cat.json  -> record stream

Message types emitted during ``read``:
    RECORD -- a data record {stream, data: {...}}
    STATE  -- incremental cursor checkpoint
    LOG    -- log line from the connector process
    TRACE  -- error/exception trace

Config keys (inside ``config.config``)
---------------------------------------
    entrypoint:       Path to the connector package's main.py.
    source_config:    Dict of credentials/settings passed as --config JSON.
    selected_streams: List of stream names to ingest (empty = all streams).
    field_map:        Per-stream mapping {field_name: "title"|"body"|"metadata"}.
                      Unmapped fields are serialized as JSON and appended to content.
    state_key:        Redis key for persisting STATE checkpoints.
                      Defaults to ``connector:{connector_id}:external_state``.
"""

import asyncio
import hashlib
import json
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
    SyncResult,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

# Message type constants from the subprocess protocol
_MSG_RECORD = "RECORD"
_MSG_STATE = "STATE"
_MSG_LOG = "LOG"
_MSG_TRACE = "TRACE"

# Subprocess timeouts (seconds)
_CHECK_TIMEOUT = 30
_DISCOVER_TIMEOUT = 60


@ConnectorRegistry.register("external_adapter")
class ExternalConnectorAdapter(AbstractConnector):
    """Wraps a third-party connector package using the subprocess/stdout JSON protocol.

    Converts RECORD messages to ContentResult for KB ingestion.
    Persists STATE messages to Redis for incremental sync resumption.
    """

    connector_type = "external_adapter"
    tier = 2  # Requires credentials in source_config

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._entrypoint: str = cfg.get("entrypoint", "")
        self._source_config: Dict[str, Any] = cfg.get("source_config", {})
        self._selected_streams: List[str] = cfg.get("selected_streams", [])
        self._field_map: Dict[str, Any] = cfg.get("field_map", {})
        self._state_key: str = cfg.get("state_key", "connector:%s:external_state" % config.connector_id)

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Run the check command and return True if status is SUCCEEDED."""
        config_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump(self._source_config, f)
                config_path = f.name

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                self._entrypoint,
                "check",
                "--config",
                config_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CHECK_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                self.logger.warning("check command timed out after %ds", _CHECK_TIMEOUT)
                return False

            if stderr:
                for line in stderr.decode("utf-8", errors="replace").splitlines():
                    if line.strip():
                        self.logger.warning("check stderr: %s", line)

            for line in stdout.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "CONNECTION_STATUS":
                        status = (msg.get("connectionStatus") or {}).get("status", "")
                        return status == "SUCCEEDED"
                except json.JSONDecodeError:
                    continue
            return False
        except Exception as exc:
            self.logger.error("test_connection failed: %s", exc)
            return False
        finally:
            if config_path:
                import os

                try:
                    os.unlink(config_path)
                except OSError:
                    pass

    async def discover_sources(self) -> List[SourceInfo]:
        """Run the discover command and return one SourceInfo per selected stream."""
        config_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump(self._source_config, f)
                config_path = f.name

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                self._entrypoint,
                "discover",
                "--config",
                config_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_DISCOVER_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                self.logger.warning("discover command timed out after %ds", _DISCOVER_TIMEOUT)
                return []

            if stderr:
                for line in stderr.decode("utf-8", errors="replace").splitlines():
                    if line.strip():
                        self.logger.warning("discover stderr: %s", line)

            catalog = None
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "CATALOG":
                        catalog = msg.get("catalog", {})
                        break
                    # Some connectors emit the catalog directly
                    if "streams" in msg:
                        catalog = msg
                        break
                except json.JSONDecodeError:
                    continue

            if not catalog:
                return []

            streams = catalog.get("streams", [])
            sources: List[SourceInfo] = []
            for stream_def in streams:
                name = stream_def.get("stream", {}).get("name") or stream_def.get("name", "")
                if not name:
                    continue
                if self._selected_streams and name not in self._selected_streams:
                    continue
                source_id = "stream:%s" % name
                sources.append(
                    SourceInfo(
                        source_id=source_id,
                        name=name,
                        path=name,
                        content_type="application/json",
                        size_bytes=0,
                        last_modified=now_utc(),
                        metadata={"stream_name": name},
                    )
                )
            return sources

        except Exception as exc:
            self.logger.error("discover_sources failed: %s", exc)
            return []
        finally:
            if config_path:
                import os

                try:
                    os.unlink(config_path)
                except OSError:
                    pass

    async def fetch_content(self, source_id: str) -> ContentResult | None:
        """Not meaningful for streaming adapters -- use sync() instead."""
        raise NotImplementedError(
            "ExternalConnectorAdapter uses streaming sync(); "
            "fetch_content() is not supported for this connector type."
        )

    async def detect_changes(self, since: datetime | None = None) -> List[ChangeInfo]:
        """Returns empty list -- sync() drives change detection via STATE cursor."""
        return []

    async def sync(self, incremental: bool = True) -> SyncResult:
        """Stream the read command stdout, convert RECORD messages to KB content.

        STATE messages are persisted to Redis for incremental resumption.
        LOG messages are forwarded to the logger.
        TRACE messages are captured as errors in the SyncResult.
        """
        started_at = now_utc()
        result = SyncResult(
            connector_id=self.config.connector_id,
            started_at=started_at,
            completed_at=None,
            status="failed",
        )

        config_path = None
        catalog_path = None
        state_path = None

        try:
            # Write source_config to temp file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump(self._source_config, f)
                config_path = f.name

            # Build catalog from selected_streams
            streams_catalog = {
                "streams": [
                    {
                        "stream": {"name": s, "json_schema": {}},
                        "sync_mode": "incremental" if incremental else "full_refresh",
                        "destination_sync_mode": "append",
                    }
                    for s in self._selected_streams
                ]
            }
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump(streams_catalog, f)
                catalog_path = f.name

            # Build command
            cmd = [
                sys.executable,
                self._entrypoint,
                "read",
                "--config",
                config_path,
                "--catalog",
                catalog_path,
            ]

            # Load and pass state for incremental sync
            if incremental:
                state = await self._load_state()
                if state:
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
                        json.dump(state, f)
                        state_path = f.name
                    cmd.extend(["--state", state_path])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream stdout line by line
            assert proc.stdout is not None
            assert proc.stderr is not None

            stderr_task = asyncio.create_task(self._drain_stderr(proc.stderr))

            async for line in proc.stdout:
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    self.logger.debug("Non-JSON stdout line: %s", line_str[:200])
                    continue

                msg_type = msg.get("type", "")
                if msg_type == _MSG_RECORD:
                    await self._handle_record(msg, result)
                elif msg_type == _MSG_STATE:
                    await self._handle_state(msg)
                elif msg_type == _MSG_LOG:
                    self._handle_log(msg)
                elif msg_type == _MSG_TRACE:
                    self._handle_trace(msg, result)

            await proc.wait()
            await stderr_task

            result.status = "success" if not result.errors else "partial"

        except Exception as exc:
            self.logger.error("External adapter sync failed: %s", exc)
            result.errors.append(str(exc))
            result.status = "failed"
        finally:
            result.completed_at = now_utc()
            import os

            for path in (config_path, catalog_path, state_path):
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

        return result

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    async def _handle_record(self, msg: Dict[str, Any], result: SyncResult) -> None:
        """Convert a RECORD message to ContentResult and ingest into KB."""
        stream_name = msg.get("stream", "")
        data = msg.get("record", {}).get("data", msg.get("data", {}))
        if not data:
            return
        content = self._convert_record(stream_name, data)
        if content is None:
            return
        try:
            await self._ingest_content(content)
            result.added += 1
        except Exception as exc:
            self.logger.error("Record ingestion failed for stream %s: %s", stream_name, exc)
            result.errors.append("stream=%s: %s" % (stream_name, exc))

    async def _handle_state(self, msg: Dict[str, Any]) -> None:
        """Persist STATE cursor to Redis for incremental resumption."""
        state_data = msg.get("state", {}).get("data", msg.get("data", {}))
        if state_data:
            await self._save_state(state_data)
            self.logger.debug("Persisted STATE checkpoint for connector %s", self.config.connector_id)

    def _handle_log(self, msg: Dict[str, Any]) -> None:
        """Forward LOG message from subprocess to logger."""
        level = msg.get("log", {}).get("level", "INFO").upper()
        text = msg.get("log", {}).get("message", str(msg))
        if level in ("ERROR", "FATAL"):
            self.logger.error("connector log: %s", text)
        elif level == "WARN":
            self.logger.warning("connector log: %s", text)
        else:
            self.logger.info("connector log: %s", text)

    def _handle_trace(self, msg: Dict[str, Any], result: SyncResult) -> None:
        """Capture a TRACE error message into the SyncResult."""
        error = msg.get("trace", {}).get("error", {})
        message = error.get("message") or str(msg)
        self.logger.error("connector trace: %s", message)
        result.errors.append("TRACE: %s" % message)

    async def _drain_stderr(self, stderr) -> None:
        """Read and log subprocess stderr at WARNING level."""
        async for line in stderr:
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                self.logger.warning("connector stderr: %s", text)

    # ------------------------------------------------------------------
    # Record conversion
    # ------------------------------------------------------------------

    def _convert_record(self, stream_name: str, data: Dict[str, Any]) -> ContentResult | None:
        """Map record fields to ContentResult using field_map config.

        Fields mapped to "title" and "body" are joined as content.
        Fields mapped to "metadata" (list) are stored in metadata dict.
        Unmapped fields are serialized as JSON and appended to content.
        """
        stream_map = self._field_map.get(stream_name, self._field_map)

        title_field = stream_map.get("title", "")
        body_field = stream_map.get("body", "")
        metadata_fields = stream_map.get("metadata", [])
        if isinstance(metadata_fields, str):
            metadata_fields = [metadata_fields]

        title = str(data.get(title_field, "")) if title_field else ""
        body = str(data.get(body_field, "")) if body_field else ""

        mapped_keys = {title_field, body_field} | set(metadata_fields)
        unmapped = {k: v for k, v in data.items() if k not in mapped_keys and k}

        parts = []
        if title:
            parts.append(title)
        if body:
            parts.append(body)
        if unmapped:
            parts.append(json.dumps(unmapped, ensure_ascii=False))

        content_text = "\n\n".join(parts)
        if not content_text.strip():
            return None

        metadata: Dict[str, Any] = {
            "stream_name": stream_name,
            "connector_id": self.config.connector_id,
        }
        for field_name in metadata_fields:
            if field_name in data:
                metadata[field_name] = data[field_name]

        source_id = "ext:%s:%s" % (
            stream_name,
            hashlib.md5(content_text.encode("utf-8"), usedforsecurity=False).hexdigest()[:12],
        )

        return ContentResult(
            source_id=source_id,
            content=content_text,
            content_type="application/json",
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # State persistence (incremental sync)
    # ------------------------------------------------------------------

    async def _load_state(self) -> Optional[Dict[str, Any]]:
        """Load the last STATE checkpoint from Redis."""
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            if redis is None:
                return None
            raw = await redis.get(self._state_key)
            if raw is None:
                return None
            return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except Exception as exc:
            self.logger.warning("Failed to load external state: %s", exc)
            return None

    async def _save_state(self, state: Dict[str, Any]) -> None:
        """Persist STATE checkpoint to Redis."""
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.set(self._state_key, json.dumps(state, ensure_ascii=False))
        except Exception as exc:
            self.logger.warning("Failed to save external state: %s", exc)
