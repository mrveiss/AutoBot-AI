#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
r"""#13264 — a live ``os.getenv``/``os.environ.get`` default must agree with
the ``ssot_config`` ``Field`` default it duplicates.

Commit ``122793bbf`` (#7437) migrated ~675 ``os.getenv(NAME, DEFAULT)`` call
sites onto ``ssot_config`` fields, and in ~130 cases the new field's default
silently disagreed with the literal it replaced (``False``/``""``/``0``
instead of the value actually shipped). That migration is done and its
casualties are tracked as data in the #13264 issue, not by this guard — this
guard is about what comes *after*: a call site that still reads the
environment directly, for a name that is *also* an ``ssot_config`` alias,
with a literal default that disagrees with the field's. That shape is either
a second migration regression waiting to happen, or a merge that never
happened at all; either way, one source of truth should say one thing.

Scope is deliberately narrow: only ``autobot-backend/`` and
``autobot_shared/`` are scanned, because those are the two trees
``ssot_config`` actually governs. ``autobot-slm-backend``,
``autobot-npu-worker`` and ``autobot-infrastructure`` are separately
deployed services/scripts with their own environment namespace; a shared
variable *name* there is not necessarily the same variable, and scanning
them produced nothing but false positives when this guard was prototyped
(#13264 comment). Test code and fixtures are excluded for the same reason:
they deliberately construct isolated environments.

Uses ``ast`` — comments and docstrings are not part of the parse tree, so
they cannot be mistaken for a call site or a default. The repo's existing
``# ssot-config-exempt: <reason>`` trailing-comment convention (already used
across ~25 files for exactly this kind of deliberate divergence, but until
now checked by nothing) is honored: a call site so annotated is skipped, not
flagged. Discrimination tests live in ``check_getenv_ssot_drift_test.py``.

Evidence for the ten defaults this same #13264 PR restored in
``ssot_config.py`` (the ``ssot_config.py``/``ssot_config_test.py`` line-count
ratchet is down-only, so the per-field reasoning lives here rather than as
inline comments there — see ``ssot_config_defaults_13264_test.py`` for the
assertions):

- ``log_max_bytes``/``log_backup_count``: ``utils/memory_optimization.py``
  passes both straight to ``RotatingFileHandler``/``TimedRotatingFileHandler``
  unguarded. ``maxBytes=0`` means "never rotate"; ``backupCount=0`` means zero
  backups retained. Pre-#7437: 52428800 and 5 (the size-based rotator) / 7
  (the time-based one, collapsed onto one field by the migration — 5 restored
  as the more conservative value).
- ``memory_pool_size``/``weak_cache_size``/``cache_size``: unguarded defaults
  for ``MemoryPool``, ``WeakCache`` and the ``memory_efficient_cache``
  decorator in the same module. 0 collapses each to zero capacity.
  Pre-#7437: 100 / 128 / 128.
- ``memory_threshold_mb``/``memory_log_threshold_mb``: ``MemoryMonitor``'s
  warning threshold, same module. 0 makes ``abs(diff) > threshold`` true for
  almost every allocation. Pre-#7437: 500 / 1.
- ``chat_timeout``: ``api/chat.py`` reads it unguarded; 0 timed out every
  chat request immediately. Pre-#7437: 30.
- ``cache_enabled``/``vllm_async_output``/``vllm_prefix_caching``:
  ``config/defaults.py`` guards all three with
  ``X if X is not None else True`` (or the ``"" if ... else True`` string
  form) — a guard that can never fire for a field whose own default is
  ``False``/``""`` and never ``None``, so it read the broken default through
  unchanged. Same defect class as the MCP-registry-cache one-off fix
  (#13262). Pre-#7437: enabled / enabled / "true".

Evidence for the 22 defaults restored in a follow-up #13264 PR (gateway config,
provider base URLs/vLLM, SMTP, MCP isolation, codebase indexing — the
"live, unguarded, unfixed" table posted on the issue, minus the batch above).
Each pre-#7437 literal was re-verified against ``122793bbf~1`` (the migration
commit's pre-image), not carried over from the issue table unchecked; see
``ssot_config_defaults_13264_batch2_test.py`` for the assertions:

- ``gateway_rate_limit_user``/``gateway_rate_limit_channel``/
  ``gateway_session_timeout``/``gateway_max_message_size``:
  ``services/gateway/config.py``'s ``GatewayConfig.from_env`` reads all four
  as ``int(config.gateway_*)`` with no fallback; ``0`` silently zeroes the
  rate limit, session timeout, and max message size. Pre-#7437 (then
  ``autobot-backend/services/gateway/config.py``): 60 / 100 / 1800 /
  ``1024*1024`` (1048576).
- ``gateway_max_sessions_user``/``gateway_heartbeat_interval``/
  ``gateway_message_retention_hours``: same module, but already rescued at
  the call site by ``_int_or_default`` (#14028) because these three are
  ``str`` fields whose ``""`` default would otherwise raise on ``int("")``.
  Runtime behaviour is already correct via that guard; this restores the
  SSOT default itself so it stops disagreeing with the value actually used.
  Pre-#7437: 5 / 30 / 24.
- ``smtp_host``/``smtp_port``/``smtp_from``/``smtp_tls``:
  ``services/notification_service.py`` reads all four unguarded. ``""``
  host/from and ``0`` port break outbound mail; ``smtp_tls=""`` fails the
  ``.lower() != "false"`` check into "TLS off" instead of "TLS on"
  (pre-#7437 default was "true"). Pre-#7437: "localhost" / 587 /
  "autobot@localhost" / "true".
- ``mcp_worker_log_level``: ``services/mcp_bridge_workers/worker_entrypoint.py``
  passes it straight to ``logging.basicConfig(level=...)`` unguarded; ``""``
  is not a valid level name. Pre-#7437: "INFO".
- ``mcp_isolation_mode``: the live isolation-mode decision in
  ``services/mcp_isolation_config.py`` reads ``os.environ.get`` directly
  (marked ``# ssot-config-exempt`` for #12443 — it must re-read lazily per
  test, not cache through the ``ssot_config`` singleton), so this field
  itself has no live reader today; restored for SSOT self-consistency only,
  not a behaviour fix. Pre-#7437: "inprocess".
- ``codebase_index_embed_batch_size``: ``api/codebase_analytics/chromadb_storage.py``
  reads it unguarded as ``int(config.codebase_index_embed_batch_size)``;
  ``0`` means every embedding call is chunked to a zero-size batch.
  Pre-#7437: 100.
- ``codebase_index_parallel_files``/``codebase_scan_parallel_files``:
  ``api/codebase_analytics/file_analyzer.py``/``scanner.py`` both already
  guard with ``blank_to_none(config.x) or 50``, so runtime behaviour is
  already correct; restored for SSOT self-consistency, not a live fix.
  Pre-#7437: 50 / 50.
- ``anthropic_api_base_url``/``vllm_host``: ``services/provider_health/providers.py``
  assigns both straight from ``ssot_config`` unguarded; an empty base URL
  breaks every request built from it. Pre-#7437: "https://api.anthropic.com/v1"
  / "http://127.0.0.1:8000".
- ``openrouter_default_model``/``vllm_dtype``/``vllm_gpu_memory_utilization``/
  ``vllm_tensor_parallel_size``: ``llm_shared/provider_registry.py`` (moved
  from the pre-#7437 ``llm_interface_pkg/provider_registry.py``) reads all
  four unguarded; ``vllm_gpu_memory_utilization=""`` raises on
  ``float("")``, ``vllm_tensor_parallel_size=0`` silently zeroes the vLLM
  tensor-parallel degree. Pre-#7437: "gpt-3.5-turbo" / "auto" / "0.9" / 1.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from tools.lint._scan_helpers import EXCLUDED_DIR_NAMES

#: Trees ``ssot_config`` actually governs. A name collision outside these
#: (a different service, an ops script) is not the same variable.
GOVERNED_ROOTS = ("autobot-backend", "autobot_shared")

#: Trailing-comment marker (already in use repo-wide) that suppresses a
#: single call site: ``os.getenv(...)  # ssot-config-exempt: <reason>``.
EXEMPT_MARKER = "ssot-config-exempt"

#: Floor for the ``ssot_config`` field-default population this guard reads.
#: ``ssot_config.py`` held 530+ literal-default ``Field(...)`` calls when
#: this landed; a sweep that suddenly finds a handful has broken.
FIELD_DEFAULT_FLOOR = 300

#: Floor for the number of in-scope ``os.getenv``/``os.environ.get`` call
#: sites this guard must find that name an existing ``ssot_config`` alias
#: (i.e. an actually-comparable pair). Only 10 such pairs exist today — most
#: direct env reads are for names ``ssot_config`` never migrated — so the
#: floor is set just below that, not at the much larger raw call-site count.
#: An empty offender list from a sweep that matched zero pairs asserts
#: nothing.
GETENV_CALL_FLOOR = 8


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)


def _literal(node: ast.AST) -> Any:
    """A plain constant, or a negative-number literal; ``None`` otherwise."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        return -node.operand.value
    return None


def extract_field_defaults(source: str) -> dict[str, Any]:
    """alias -> literal ``Field(default=...)`` value, from ``ssot_config.py`` source.

    Fields using ``default_factory`` (lazy/computed) or a non-literal
    ``default`` are excluded — there is nothing to literal-compare.
    """
    out: dict[str, Any] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or _call_name(node) != "Field":
            continue
        default: Any = "__UNSET__"
        alias: str | None = None
        lazy = False
        for kw in node.keywords:
            if kw.arg == "default":
                default = _literal(kw.value)
            elif kw.arg == "default_factory":
                lazy = True
            elif kw.arg in ("alias", "validation_alias"):
                value = _literal(kw.value)
                if isinstance(value, str):
                    alias = value
        if alias and not lazy and default not in ("__UNSET__", None):
            out[alias] = default
    return out


def _is_os_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "os"


def _is_getenv_call(node: ast.Call) -> bool:
    """``os.getenv(...)`` or ``os.environ.get(...)``, either spelling."""
    fn = node.func
    is_getenv = isinstance(fn, ast.Attribute) and fn.attr == "getenv" and _is_os_name(fn.value)
    is_environ_get = (
        isinstance(fn, ast.Attribute)
        and fn.attr == "get"
        and isinstance(fn.value, ast.Attribute)
        and fn.value.attr == "environ"
    )
    return is_getenv or is_environ_get


def _is_exempted(node: ast.Call, lines: list[str]) -> bool:
    """Does the call's own source span carry the ``ssot-config-exempt``
    marker on any line (``lineno``..``end_lineno``, covering a multi-line
    call too)?"""
    end = getattr(node, "end_lineno", node.lineno) or node.lineno
    span_text = "\n".join(lines[node.lineno - 1 : end])
    return EXEMPT_MARKER in span_text


def extract_getenv_defaults(source: str) -> list[tuple[str, Any, int]]:
    """(NAME, default, lineno) for every 2-arg literal ``os.getenv``/
    ``os.environ.get`` call in *source*, skipping exempted ones."""
    lines = source.splitlines()
    out: list[tuple[str, Any, int]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) != 2 or not _is_getenv_call(node):
            continue
        name = _literal(node.args[0])
        default = _literal(node.args[1])
        if not isinstance(name, str) or default is None:
            continue
        if _is_exempted(node, lines):
            continue
        out.append((name, default, node.lineno))
    return out


def _normalize(value: Any) -> Any:
    """Collapse spelling differences that are not behaviour differences.

    ``"true"``/``"false"`` (any case) compare equal to the matching bool, a
    numeric string compares equal to the matching int/float, and every
    falsy value (``""``, ``False``, ``0``, ``0.0``, ``None``) compares equal
    to every other falsy value — a field typed ``bool`` and a call site
    still typed ``str`` frequently disagree only in spelling, not in the
    "off" they both mean.
    """
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            value = True
        elif lowered == "false":
            value = False
        else:
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                pass
    return "__FALSY__" if not value else value


def values_disagree(call_site_default: Any, field_default: Any) -> bool:
    """True when the two literals describe a different effective default."""
    return _normalize(call_site_default) != _normalize(field_default)


def _in_scope(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    parts = rel.parts
    if not parts or parts[0] not in GOVERNED_ROOTS:
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in parts):
        return False
    if "tests" in parts:
        return False
    if path.name in ("ssot_config.py",) or path.name.endswith("_test.py"):
        return False
    return True


def find_drift(repo_root: Path) -> tuple[list[str], int]:
    """Offender strings, and the number of in-scope call sites examined."""
    ssot_source = (repo_root / "autobot_shared" / "ssot_config.py").read_text(encoding="utf-8")
    field_defaults = extract_field_defaults(ssot_source)
    assert (
        len(field_defaults) >= FIELD_DEFAULT_FLOOR
    ), f"only {len(field_defaults)} ssot_config field defaults reached — the sweep broke"

    offenders: list[str] = []
    calls_examined = 0
    for path in sorted(repo_root.rglob("*.py")):
        if not _in_scope(path, repo_root):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, default, lineno in extract_getenv_defaults(source):
            if name not in field_defaults:
                continue
            calls_examined += 1
            field_default = field_defaults[name]
            if values_disagree(default, field_default):
                rel = path.relative_to(repo_root)
                offenders.append(
                    f"{rel}:{lineno}: {name} call-site default={default!r} "
                    f"disagrees with ssot_config default={field_default!r}"
                )
    return offenders, calls_examined
