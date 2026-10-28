# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A value with an SSOT definition is not written out again under the same name (#19730).

The scan groups every assignment, and every pydantic ``Field(default=...)``, by
(normalised name, literal value) across the Python trees. A group with a member in an
SSOT file and a member anywhere else is a re-hardcode: changing the SSOT value would
leave the copy behind. Each copy imports the SSOT symbol instead, or is renamed when it
is a different concept that only shares the name.

``PENDING`` holds the copies not fixed yet, each with the reason it waits. It only
shrinks. ``DISTINCT`` holds public names (API fields, enum members) that are a
different concept, where a rename would change a wire contract.
"""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ROOTS = ("autobot-backend", "autobot_shared", "autobot-slm-backend")
SSOT = frozenset({"autobot_shared/ssot_config.py", "autobot_shared/ssot_constants.py"})
_TEST_PATH = re.compile(r"(^|/)(tests?|testing|fixtures)/|_test\.py$|(^|/)test_[^/]*\.py$")

_BUSY = "fixed once the open PR that also edits this file lands"
_CEILING = "the file is at its size ceiling with no line to absorb the import; fixed with its split"
PENDING: dict[str, tuple[int, str]] = {
    "autobot-backend/api/schemas_knowledge.py::page_size=50": (1, f"QueryDefaults; {_BUSY} (#19711)"),
    "autobot-backend/api/schemas_knowledge.py::quality_threshold=0.7": (1, f"AgentThresholds; {_BUSY} (#19711)"),
    "autobot-backend/api/schemas_knowledge.py::top_k=10": (2, f"QueryDefaults; {_BUSY} (#19711)"),
    "autobot-backend/code_analysis/src/ownership_analyzer.py::TTL_1_HOUR=3600": (1, f"{_BUSY} (#19696)"),
    "autobot-backend/llc/models/enums.py::CLOSED='closed'": (1, f"classified with the fix; {_BUSY} (#19598)"),
    "autobot-backend/llc/models/enums.py::PLAN='plan'": (1, f"classified with the fix; {_BUSY} (#19598)"),
    "autobot_shared/redis_management/config.py::_BACKOFF_BASE=2.0": (
        1,
        f"RetryConfig; {_BUSY} (#19365, #19400, #19722)",
    ),
    "autobot_shared/redis_management/config.py::_CIRCUIT_BREAKER_THRESHOLD=5": (1, f"{_BUSY} (#19365, #19400, #19722)"),
    "autobot_shared/redis_management/connection_manager.py::_BACKOFF_BASE=2.0": (1, f"RetryConfig; {_BUSY} (#19365)"),
    "autobot_shared/ssot_tls.py::ssh_user='autobot'": (1, f"config.path.ssh_user; {_BUSY} (#19400, #19722)"),
    "autobot-backend/api/http_client_mcp.py::DEFAULT_TIMEOUT=30": (1, f"config.timeout.mcp_call; {_CEILING}"),
    "autobot-backend/api/schemas_analytics.py::provider='ollama'": (
        1,
        f"config.llm.llamaindex_embedding_provider; {_CEILING}",
    ),
    "autobot-backend/api/schemas_system.py::admin_username='admin'": (1, f"config.auth.admin_username; {_CEILING}"),
    "autobot_shared/redis_management/config.py::_DEFAULT_RETRIES=3": (1, f"RetryConfig; {_BUSY} (#19400, #19722)"),
    "autobot_shared/redis_management/connection_manager.py::_DEFAULT_RETRIES=3": (1, f"RetryConfig; {_BUSY}"),
    "autobot_shared/logging_manager.py::_DEFAULT_LOG_LEVEL='INFO'": (
        1,
        "logging cannot import config; ssot_config's log_level defaults read this one instead, once #19429 frees ssot_config.py",
    ),
}

DISTINCT: dict[str, tuple[int, str]] = {
    "autobot-backend/agents/base_agent_types.py::timeout=30.0": (
        1,
        "AgentRequest's deadline, not a circuit-breaker call timeout",
    ),
    "autobot-backend/config/settings.py::cache_ttl=300": (
        1,
        "config-file cache TTL (CONFIG_CACHE_TTL), not the LLM cache TTL",
    ),
    "autobot-backend/security/session_posture.py::DEFAULT='default'": (
        1,
        "a session ownership posture, not a permission mode",
    ),
    "autobot-backend/services/gateway/types.py::CLOSED='closed'": (
        1,
        "a gateway session status, not a circuit-breaker state",
    ),
    "autobot-backend/services/permission_matcher.py::DEFAULT='default'": (
        1,
        "MatchResult 'no rule matched', not a permission mode",
    ),
    "autobot-backend/skills/models.py::HTTP='http'": (
        1,
        "a skill-repo source kind (git/local/http/mcp), not a network protocol",
    ),
    "autobot-backend/type_defs/common.py::DEFAULT='default'": (1, "a chat message type, not a permission mode"),
    "autobot-slm-backend/models/manifest.py::retries=3": (
        1,
        "a manifest health-probe failure count, not an operation retry budget",
    ),
    "autobot-backend/llc/kb/ac_suggester.py::_DEFAULT_CACHE_TTL=300": (
        1,
        "the AC suggester's own cache, with its own AUTOBOT_AC_SUGGESTER_CACHE_TTL; not the LLM cache TTL",
    ),
    "autobot-backend/services/topic_retrieval_cache.py::_DEFAULT_SIMILARITY_THRESHOLD=0.7": (
        1,
        "topic text similarity; the SSOT match is ComputerVisionThresholds.SIMILARITY_THRESHOLD",
    ),
    "autobot-backend/services/workflow_automation/safety_limits.py::_DEFAULT_MAX_CONCURRENT=3": (
        1,
        "a per-execution quota (ConcurrentWorkflowLimiter), not the scheduler's run slots (WorkflowConfig)",
    ),
}


def normalise(name: str) -> str:
    """``DEFAULT_TIMEOUT``, ``_DEFAULT_TIMEOUT``, ``_timeout`` and ``llm_timeout`` all name a timeout.

    Leading underscores go first, so ``_DEFAULT_RETRIES`` meets ``DEFAULT_RETRIES`` (#19730 review).
    """
    bare = re.sub(r"^default_", "", name.lstrip("_"), flags=re.IGNORECASE).lower()
    return re.sub(r"^(llm_|ollama_)", "", bare)


def _literal(value: ast.AST | None) -> object | None:
    """The literal a binding sets, reading through ``Field(default=...)``; None when not one."""
    if isinstance(value, ast.Call) and getattr(value.func, "id", getattr(value.func, "attr", "")) == "Field":
        value = next((k.value for k in value.keywords if k.arg == "default"), value.args[0] if value.args else None)
    if not isinstance(value, ast.Constant) or isinstance(value.value, bool):
        return None
    v = value.value
    if isinstance(v, str):
        return v if 3 <= len(v) <= 80 else None
    return v if isinstance(v, int | float) and v not in (0, 1, -1) else None


def bindings(source: str) -> list[tuple[str, object]]:
    """``(name, literal)`` for every single-name assignment in *source* that binds a literal."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        else:
            continue
        literal = _literal(value)
        if literal is not None:
            out.append((name, literal))
    return out


def occurrences(sources: dict[str, str]) -> Counter[str]:
    """How many times each ``path::name=value`` literal binding occurs, SSOT files excluded."""
    return Counter(
        f"{rel}::{name}={literal!r}"
        for rel, source in sources.items()
        if rel not in SSOT
        for name, literal in bindings(source)
    )


def rehardcodes(sources: dict[str, str]) -> Counter[str]:
    """``path::name=value`` -> occurrences, for every copy of a value an SSOT file defines.

    Counted, not a set: a second identical binding in a recorded file is a new copy, and fixing one
    of two is visible (#19730 review).
    """
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for rel, source in sources.items():
        for name, literal in bindings(source):
            groups[(normalise(name), repr(literal))].add(rel)
    copies = Counter()
    every = occurrences(sources)
    for key, count in every.items():
        rel, binding = key.split("::", 1)
        name, value = binding.split("=", 1)
        files = groups[(normalise(name), value)]
        if files & SSOT and len(files) > 1:
            copies[key] = count
    return copies


def _live_paths(root: Path) -> list[str]:
    """Tracked non-test Python under the three roots; ``[]`` on an empty tree, so the floor refuses it."""
    try:
        paths = tracked_paths(root, *(f"{r}/*.py" for r in _ROOTS))
    except EmptyEnumeration:
        return []
    return [p for p in paths if not _TEST_PATH.search(p)]


REACH = declare(
    "ssot-rehardcode-scan-19730",
    discover=_live_paths,
    floor=3190,  # measured at 3341 tracked files, pinned mid-window (#15928)
    growth=300,
    what="non-test Python files scanned for a re-hardcoded SSOT value (#19730)",
    roots=_ROOTS,
)


def _live_sources() -> dict[str, str]:
    return {p: (_ROOT / p).read_text(encoding="utf-8") for p in REACH.examined(_ROOT)}


def test_no_ssot_value_is_rehardcoded_on_the_live_tree() -> None:
    sources = _live_sources()
    found, every = rehardcodes(sources), occurrences(sources)
    recorded = {key: count for key, (count, _why) in (PENDING | DISTINCT).items()}
    new = sorted(f"{k} x{n}" for k, n in found.items() if n > recorded.get(k, 0))
    # Stale when the binding itself is gone or converted -- not when the SSOT value moved (#19730 review).
    stale = sorted(f"{k} x{n}, now {every[k]}" for k, n in recorded.items() if every[k] < n)
    assert not new, "import the SSOT symbol, or rename a different concept:\n" + "\n".join(new)
    assert not stale, "fixed or gone -- delete the record entry:\n" + "\n".join(stale)


def test_a_planted_copy_of_an_ssot_value_is_caught() -> None:
    sources = {
        "autobot_shared/ssot_constants.py": "class RetryConfig:\n    MAX_RETRIES = 5\n",
        "autobot-backend/x.py": "class C(BaseModel):\n    max_retries: int = Field(default=5, ge=0)\n",
        "autobot-backend/y.py": "_MAX_RETRIES = 5\nmax_retries = 4\nother_name = 5\n",
    }
    assert rehardcodes(sources) == {"autobot-backend/x.py::max_retries=5": 1, "autobot-backend/y.py::_MAX_RETRIES=5": 1}


def test_a_second_identical_copy_in_one_file_is_counted() -> None:
    sources = {
        "autobot_shared/ssot_constants.py": "class C:\n    QUALITY_THRESHOLD = 0.7\n",
        "autobot-backend/s.py": "class A:\n    quality_threshold = 0.7\nclass B:\n    quality_threshold = 0.7\n",
    }
    assert rehardcodes(sources) == {"autobot-backend/s.py::quality_threshold=0.7": 2}


def test_a_leading_underscore_before_default_still_normalises() -> None:
    sources = {
        "autobot_shared/ssot_constants.py": "class RetryConfig:\n    DEFAULT_RETRIES = 3\n",
        "autobot_shared/x.py": "_DEFAULT_RETRIES = 3\n_RETRY_LIMIT = 3\n",
    }
    assert rehardcodes(sources) == {"autobot_shared/x.py::_DEFAULT_RETRIES=3": 1}


def test_a_recorded_copy_stays_recorded_when_the_ssot_value_moves() -> None:
    """The copy is still there after the SSOT changes 0.7 -> 0.8; only removing it may clear the entry."""
    sources = {
        "autobot_shared/ssot_constants.py": "QUALITY_THRESHOLD = 0.8\n",
        "autobot-backend/s.py": "quality_threshold = 0.7\n",
    }
    assert rehardcodes(sources) == {}
    assert occurrences(sources)["autobot-backend/s.py::quality_threshold=0.7"] == 1


def test_a_value_no_ssot_file_defines_is_not_a_rehardcode() -> None:
    sources = {"autobot-backend/a.py": 'STATUS = "failed"\n', "autobot-backend/b.py": 'status = "failed"\n'}
    assert rehardcodes(sources) == {}


def test_every_record_entry_says_why() -> None:
    assert all(n >= 1 and why.strip() for n, why in (*PENDING.values(), *DISTINCT.values()))
