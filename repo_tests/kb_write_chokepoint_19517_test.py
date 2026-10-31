# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every KB write path is classified, and a caller-controlled one enters the write scope (#19517).

``KnowledgeBase.store_fact`` / ``update_fact`` strip a caller's ownership and visibility and stamp
the caller's own id (``knowledge/write_scope.py``) -- but only for a write made inside a
``caller_write_scope``, which the code that took the metadata from a caller must enter. This guard
fails when a module gains a KB write call it has not been classified for, when a module classified
as caller-scoped stops entering the scope, when a write reaches the persistence functions around
``store_fact``, or when ``store_fact`` / ``update_fact`` stop calling the guard.

WHAT MATCHES (syntax tree only, so a comment or string naming these is not a site)
    Any ``Name`` or ``Attribute`` node -- a call, a reference passed to ``run_in_executor``, a
    ``getattr``-free alias -- spelling a write API (``WRITE_APIS``) or one of the shared ingest
    helpers that end in one (``INGEST_HELPERS``), in a non-test ``.py`` under ``autobot-*``.
BOUNDARY
    NOT seen: a write through a dynamic name (``getattr(kb, "store_" + "fact")``), a module outside
    ``autobot-*``, and the ECL pipeline loaders that write straight to the stores without reaching
    ``store_fact`` at all (the class tracked in #17649): those never meet this chokepoint and are a
    separate finding. ``update_fact`` callers are not enumerated; the chokepoint covers them, the
    scope does not.
THE TABLE (``WRITE_PATHS``) is exact: a new module fails until someone decides its class, and an
entry whose module no longer writes fails. ``OPEN_GAP`` entries are writes known to take a caller's
metadata without entering the scope; the set may only shrink.
"""

from __future__ import annotations

import ast
import functools
import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

REPO = Path(__file__).resolve().parent.parent

WRITE_APIS = frozenset({"store_fact", "add_document", "add_file", "add_content", "_add_document_internal"})
INGEST_HELPERS = frozenset(
    {"ingest_in_kb", "ingest_document", "ingest_markdown", "ingest_watched_file", "add_document_as"}
)
#: The persistence steps ``store_fact`` runs after the guard; reached from anywhere else they skip it.
LOW_LEVEL_WRITES = frozenset({"persist_fact", "_store_and_vectorize_fact", "_project_fact_to_redis"})
LOW_LEVEL_HOMES = frozenset({"autobot-backend/knowledge/facts.py", "autobot-backend/knowledge/fact_projection.py"})
SCOPE_NAMES = frozenset({"caller_write_scope", "caller_write_scope_for", "agent_write_scope", "add_document_as"})

CALLER_SCOPED = "CALLER_SCOPED"  # takes metadata from a caller; must reference a scope helper
DELEGATED = "DELEGATED"  # a shared layer below the entry points, or a dispatcher onto one
ROUTE_ADMIN = "ROUTE_ADMIN"  # HTTP route: spells check_admin_permission or drop_ownership_unless_admin (checked)
ROUTE_BUILT = "ROUTE_BUILT"  # HTTP route: builds its metadata; reads no ownership key from a request (checked)
SYSTEM = "SYSTEM"  # system-internal ingest: no caller metadata, ownership set by its own code
OPEN_GAP = "OPEN_GAP"  # caller metadata, no principal in reach, not scoped

_B = "autobot-backend/"
WRITE_PATHS: dict[str, tuple[str, str]] = {
    _B + "tools/kb_write_tools.py": (CALLER_SCOPED, "agent store_fact / add_file tools: the LLM's metadata"),
    _B + "task_handlers/knowledge_base_handlers.py": (CALLER_SCOPED, "task payload metadata; user from ctx.metadata"),
    _B + "api/knowledge_mcp.py": (CALLER_SCOPED, "MCP add_to_knowledge_base: the authenticated user"),
    _B + "knowledge/write_scope.py": (CALLER_SCOPED, "defines add_document_as"),
    _B + "tools/tool_registry.py": (DELEGATED, "dispatch table onto KnowledgeWriteToolsMixin"),
    _B + "knowledge/documents.py": (DELEGATED, "add_document -> store_fact"),
    _B + "knowledge/document_ingest.py": (DELEGATED, "ingest_document -> _add_document_internal"),
    _B + "knowledge/kb_ingest_result.py": (DELEGATED, "ingest_in_kb -> add_document"),
    _B + "knowledge/bulk.py": (SYSTEM, "backup restore / bulk import: admin routes, stored facts"),
    _B + "api/knowledge.py": (ROUTE_ADMIN, "upload / add_text routes: admin or owner checks at the route"),
    _B + "api/knowledge_extract.py": (ROUTE_BUILT, "extraction route"),
    _B + "api/knowledge_scrape.py": (ROUTE_BUILT, "scrape route"),
    _B + "api/knowledge_maintenance.py": (ROUTE_ADMIN, "man-page vectorization: metadata built by code"),
    _B + "api/knowledge_population.py": (ROUTE_ADMIN, "population routes: metadata built by code"),
    _B + "api/knowledge_ai_stack_extraction.py": (ROUTE_BUILT, "extraction route"),
    _B + "api/transcripts.py": (ROUTE_BUILT, "transcript push: owner stamped from the verified caller"),
    _B + "api/workflow.py": (SYSTEM, "workflow step result: metadata built by code"),
    _B + "api/chat_knowledge_manager.py": (ROUTE_ADMIN, "guarded at site with drop_ownership_unless_admin"),
    _B + "conversation_file_manager.py": (ROUTE_BUILT, "conversation uploads"),
    _B + "services/kb_folder_watcher.py": (SYSTEM, "admin-configured watch folders"),
    _B + "services/kb_watch_ingest.py": (SYSTEM, "admin-configured watch folders"),
    _B + "knowledge_sync_incremental.py": (SYSTEM, "repo documentation sync"),
    _B + "knowledge/connectors/base.py": (SYSTEM, "connectors: owner from the connector config"),
    _B + "knowledge/adapters/okf_adapter.py": (SYSTEM, "OKF import"),
    _B + "knowledge/claude_memory_importer.py": (SYSTEM, "owner chosen by the importing code"),
    _B + "tasks/knowledge_tasks.py": (SYSTEM, "man-page background tasks"),
    _B + "llc/kb/diary_writer.py": (SYSTEM, "company-OS agent diaries"),
    _B + "memory/agent_diary.py": (SYSTEM, "agent diaries: metadata built by code"),
    _B + "agents/kb_librarian/librarian.py": (SYSTEM, "librarian summaries"),
    _B + "agents/kb_librarian/stable_ids.py": (SYSTEM, "librarian stable ids"),
    _B + "agents/librarian_assistant.py": (SYSTEM, "librarian documents"),
    _B + "agents/web_researcher.py": (SYSTEM, "research documents: metadata built by code"),
    _B + "services/research/orchestrator.py": (SYSTEM, "research output: metadata built by code"),
    _B + "services/codebase_indexing_service.py": (SYSTEM, "codebase index chunks"),
    _B + "services/fact_extraction_service.py": (SYSTEM, "extracted facts; spreads its caller's metadata"),
    _B + "intelligence/intelligent_agent.py": (SYSTEM, "system context fact: literal metadata"),
    _B + "orchestration/workflow_documentation.py": (SYSTEM, "workflow docs: metadata built by code"),
    _B + "transcriber/knowledge/kb_push.py": (SYSTEM, "transcriber push: metadata built by code"),
    "autobot-infrastructure/shared/mcp/tools/knowledge-base-mcp/autobot_knowledge_mcp/embedded.py": (
        OPEN_GAP,
        "embedded MCP client: caller metadata, no principal",
    ),
}
for _script in (
    "scripts/identity_config_utility.py",
    "scripts/quick_populate_kb.py",
    "scripts/reset_kb_dimensions.py",
    "scripts/utilities/index_all_man_pages.py",
    "scripts/utilities/integrate_system_knowledge.py",
    "scripts/utilities/quick_test_os_context.py",
):
    WRITE_PATHS["autobot-infrastructure/shared/" + _script] = (SYSTEM, "operator-run script")


def _is_production_python(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if not path.startswith("autobot-") or not path.endswith(".py"):
        return False
    skipped = ("/tests/", "/testkit/")
    return not (
        name.endswith("_test.py")
        or name.startswith("test_")
        or name == "conftest.py"
        or any(s in path for s in skipped)
    )


#: Every name any detector below looks for. A file whose text holds none of them is never parsed.
_CANDIDATES = (
    WRITE_APIS
    | INGEST_HELPERS
    | LOW_LEVEL_WRITES
    | SCOPE_NAMES
    | {"check_admin_permission", "drop_ownership_unless_admin"}
)
#: Metadata keys a caller names to own, scope or show a fact (``OWNERSHIP_KEYS`` and the owner keys).
OWNERSHIP_FIELDS = frozenset(
    {"visibility", "source_type", "shared_with", "organization_id", "group_ids", "access_level", "owner_id", "user_id"}
)


def _tracked_sources() -> dict[str, str]:
    """Text of the production ``.py`` files that spell a candidate name; the rest are not read into the scan."""
    out = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        cwd=REPO,
        env=scrubbed_git_env(),
    )
    paths = [p for p in out.decode("utf-8").split("\0") if p and _is_production_python(p)]
    texts = {p: (REPO / p).read_text(encoding="utf-8") for p in paths}
    return {p: t for p, t in texts.items() if any(name in t for name in _CANDIDATES)}


@functools.lru_cache(maxsize=None)
def _tree(source: str) -> ast.AST:
    """One parse per distinct source text, shared by every detector."""
    return ast.parse(source)


def _spelled(source: str, names: frozenset[str]) -> set[str]:
    """The ``names`` spelled as a Name or Attribute anywhere in *source*."""
    found = set()
    for node in ast.walk(_tree(source)):
        if isinstance(node, ast.Name) and node.id in names:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in names:
            found.add(node.attr)
    return found


def write_modules(sources: dict[str, str]) -> set[str]:
    return {p for p, s in sources.items() if _spelled(s, WRITE_APIS | INGEST_HELPERS)}


def unscoped_caller_modules(sources: dict[str, str]) -> set[str]:
    classed = {p for p, (kind, _) in WRITE_PATHS.items() if kind == CALLER_SCOPED}
    return {p for p in classed if p in sources and not _spelled(sources[p], SCOPE_NAMES)}


def low_level_bypasses(sources: dict[str, str]) -> set[str]:
    return {p for p, s in sources.items() if p not in LOW_LEVEL_HOMES and _spelled(s, LOW_LEVEL_WRITES)}


def routes_without_admin_check(sources: dict[str, str]) -> set[str]:
    admin = frozenset({"check_admin_permission", "drop_ownership_unless_admin"})
    return {
        p for p, (kind, _) in WRITE_PATHS.items() if kind == ROUTE_ADMIN and not _spelled(sources.get(p, ""), admin)
    }


def request_ownership_reads(source: str) -> list[int]:
    """Lines reading an ownership field out of something: ``x.get("owner_id")`` or ``x["owner_id"]``."""
    lines = []
    for node in ast.walk(_tree(source)):
        key = None
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
        ):
            key = node.args[0]
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            key = node.slice
        if isinstance(key, ast.Constant) and key.value in OWNERSHIP_FIELDS:
            lines.append(node.lineno)
    return lines


def built_routes_reading_ownership(sources: dict[str, str]) -> dict[str, list[int]]:
    found = {
        p: request_ownership_reads(sources[p]) for p, (k, _) in WRITE_PATHS.items() if k == ROUTE_BUILT and p in sources
    }
    return {p: lines for p, lines in found.items() if lines}


def passthrough_writes(source: str) -> set[str]:
    """Functions that hand one of their own parameters to a KB write as its metadata."""
    found = set()
    for fn in ast.walk(_tree(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        for call in ast.walk(fn):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in WRITE_APIS:
                meta = [kw.value for kw in call.keywords if kw.arg == "metadata"] or call.args[1:2]
                if meta and isinstance(meta[0], ast.Name) and meta[0].id in params:
                    found.add(fn.name)
    return found


#: SYSTEM functions that forward a parameter as metadata. Each is reached only from system code (see the
#: reason); a new one fails until someone reads its callers and adds it here.
PASSTHROUGH_ACKNOWLEDGED: dict[tuple[str, str], str] = {
    (_B + "agents/kb_librarian/stable_ids.py", "store_or_update_fact"): "librarian: metadata built in librarian.py",
    (_B + "knowledge/bulk.py", "_store_restored_fact"): "backup restore: metadata is the stored fact's own",
    (_B + "services/codebase_indexing_service.py", "_store_single_chunk"): "indexer builds the chunk metadata",
    (
        "autobot-infrastructure/shared/scripts/identity_config_utility.py",
        "_add_identity_to_kb",
    ): "operator script, literal identity metadata",
}


def unacknowledged_passthroughs(sources: dict[str, str]) -> set[tuple[str, str]]:
    found = {
        (p, fn)
        for p, (k, _) in WRITE_PATHS.items()
        if k == SYSTEM and p in sources
        for fn in passthrough_writes(sources[p])
    }
    return found - set(PASSTHROUGH_ACKNOWLEDGED)


def _function_spells(source: str, func: str, names: frozenset[str]) -> bool:
    for node in ast.walk(_tree(source)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func:
            if any(
                isinstance(n, ast.Name) and n.id in names or isinstance(n, ast.Attribute) and n.attr in names
                for n in ast.walk(node)
            ):
                return True
    return False


_SOURCES = _tracked_sources()
_HOW = "Add the module to WRITE_PATHS in repo_tests/kb_write_chokepoint_19517_test.py with a class and reason; "


def test_every_write_module_is_classified_and_every_classification_still_writes():
    found = write_modules(_SOURCES)
    new, stale = sorted(found - set(WRITE_PATHS)), sorted(set(WRITE_PATHS) - found)
    assert (
        not new
    ), f"{new} write to the KB with no WRITE_PATHS row. {_HOW}if it takes a caller's metadata, enter caller_write_scope (knowledge/write_scope.py)."
    assert not stale, f"{stale} no longer write to the KB. Delete their WRITE_PATHS rows."


def test_a_caller_scoped_module_enters_the_write_scope():
    bare = sorted(unscoped_caller_modules(_SOURCES))
    assert (
        not bare
    ), f"{bare} are CALLER_SCOPED but spell no scope helper. Wrap the write in caller_write_scope / agent_write_scope / add_document_as."


def test_the_open_gaps_may_only_shrink():
    gaps = sorted(p for p, (kind, _) in WRITE_PATHS.items() if kind == OPEN_GAP)
    assert len(gaps) <= 1, f"{gaps}: OPEN_GAP may only shrink. Give the new write a principal and a scope instead."


def test_no_write_reaches_the_persistence_steps_around_the_guard():
    bypass = sorted(low_level_bypasses(_SOURCES))
    assert (
        not bypass
    ), f"{bypass} call persist_fact / _store_and_vectorize_fact / _project_fact_to_redis directly. Go through KnowledgeBase.store_fact so the ownership guard runs."


def test_an_admin_route_checks_admin():
    bare = sorted(routes_without_admin_check(_SOURCES))
    assert (
        not bare
    ), f"{bare} are ROUTE_ADMIN but spell neither check_admin_permission nor drop_ownership_unless_admin. Add the check, or reclassify the route."


def test_a_built_route_reads_no_ownership_from_a_request():
    reads = built_routes_reading_ownership(_SOURCES)
    assert (
        not reads
    ), f"{reads} read an ownership field out of a mapping. A route that takes owner/visibility from its request is ROUTE_ADMIN: add check_admin_permission, or stamp from the verified principal."


def test_a_system_site_forwards_no_unacknowledged_parameter_as_metadata():
    new = sorted(unacknowledged_passthroughs(_SOURCES))
    assert (
        not new
    ), f"{new} pass a parameter through as KB metadata. If a caller reaches it, enter caller_write_scope at that caller; else add it to PASSTHROUGH_ACKNOWLEDGED with the reason."


def test_the_acknowledged_passthroughs_still_exist():
    stale = sorted(k for k in PASSTHROUGH_ACKNOWLEDGED if k[1] not in passthrough_writes(_SOURCES.get(k[0], "")))
    assert not stale, f"{stale} no longer forward a parameter as metadata. Delete them from PASSTHROUGH_ACKNOWLEDGED."


def test_store_fact_and_update_fact_call_the_guard():
    facts = _SOURCES["autobot-backend/knowledge/facts.py"]
    assert _function_spells(
        facts, "store_fact", frozenset({"sanitize_new_fact"})
    ), "store_fact must call sanitize_new_fact (the ownership guard)."
    assert _function_spells(
        facts, "update_fact", frozenset({"sanitize_update_metadata"})
    ), "update_fact must call sanitize_update_metadata."
    assert _function_spells(
        facts, "update_fact", frozenset({"guard_update"})
    ), "update_fact must call guard_update (caller owns the fact)."


def test_the_agent_tool_registry_carries_the_scoped_write_tools():
    registry = _SOURCES["autobot-backend/tools/tool_registry.py"]
    assert _spelled(
        registry, frozenset({"KnowledgeWriteToolsMixin"})
    ), "ToolRegistry must extend KnowledgeWriteToolsMixin."


def test_the_chokepoint_scope_is_not_read_from_metadata():
    scope = _SOURCES["autobot-backend/knowledge/write_scope.py"]
    assert _spelled(scope, frozenset({"ContextVar"})), "the scope must be a ContextVar set by code"
    assert not _spelled(scope, frozenset({"ingest_route"})), "a metadata claim must not decide who is internal"


# --- controls: the detectors must see each way a bypass can appear, planted as source ---------------

_PLANTED_WRITES = {
    "direct call": "async def f(kb):\n    await kb.store_fact('x', {})\n",
    "awaited chain": "async def f(g):\n    return await (await g()).add_document('x', {})\n",
    "gathered": "import asyncio\nasync def f(kb):\n    await asyncio.gather(kb.add_file('p', 't', {}))\n",
    "bare reference": "async def f(kb, loop):\n    await loop.run_in_executor(None, kb.store_fact, 'x', {})\n",
    "shared helper": "from knowledge.kb_ingest_result import ingest_in_kb\nasync def f(kb):\n    await ingest_in_kb(kb, 'x', {})\n",
    "attribute alias": "async def f(self):\n    write = self.kb.add_content\n    await write('x', {})\n",
}


def test_the_write_detector_sees_every_planted_shape():
    for shape, source in _PLANTED_WRITES.items():
        assert write_modules({"planted.py": source}) == {"planted.py"}, shape


def test_the_write_detector_ignores_a_comment_and_a_string():
    source = "# kb.store_fact(x)\nTEXT = 'kb.store_fact(x)'\n"
    assert write_modules({"planted.py": source}) == set()


def test_the_scope_check_flags_a_caller_scoped_module_that_does_not_enter_it():
    path = _B + "tools/kb_write_tools.py"
    assert unscoped_caller_modules({path: "async def f(kb):\n    await kb.store_fact('x', {})\n"}) == {path}
    assert unscoped_caller_modules({path: _SOURCES[path]}) == set()


def test_the_low_level_check_flags_a_planted_bypass_and_not_the_home():
    planted = "async def f(store):\n    await store.persist_fact('i', 'c', {'visibility': 'system'})\n"
    assert low_level_bypasses({"autobot-backend/api/x.py": planted}) == {"autobot-backend/api/x.py"}
    assert low_level_bypasses({"autobot-backend/knowledge/facts.py": planted}) == set()


def test_the_admin_route_check_flags_a_route_with_no_check_and_passes_one_with_it():
    path = next(p for p, (k, _) in WRITE_PATHS.items() if k == ROUTE_ADMIN)
    assert routes_without_admin_check({path: "async def r(kb):\n    await kb.store_fact('x', {})\n"}) >= {path}
    assert path not in routes_without_admin_check({path: "def r(a=Depends(check_admin_permission)):\n    pass\n"})


def test_the_ownership_read_check_sees_get_and_subscript_and_ignores_a_dict_literal():
    assert request_ownership_reads("def r(req):\n    return req.get('owner_id')\n")
    assert request_ownership_reads("def r(req):\n    return req['visibility']\n")
    assert not request_ownership_reads("def r(uid):\n    return {'owner_id': uid}\n")


def test_the_passthrough_check_sees_positional_and_keyword_metadata_and_not_a_literal():
    assert passthrough_writes("async def f(kb, m):\n    await kb.store_fact('x', m)\n") == {"f"}
    assert passthrough_writes("async def f(kb, m):\n    await kb.add_document(content='x', metadata=m)\n") == {"f"}
    assert not passthrough_writes("async def f(kb, m):\n    await kb.store_fact('x', {'a': m})\n")
