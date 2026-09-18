# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every write of *new* content into a KB persistence sink, anywhere under
knowledge/, is reached only through sanitize_fact_content, or is an
explicitly justified exception (#13708).

#13708's review found four ways to skip the redaction chokepoint a guard
scoped to 3 hand-picked files couldn't see: update_fact writes new content
through a separate path from store_fact; reverting a fact to a previous
version pushed that version's content back into the live Redis projection
(and, one level deeper, into a NEW version-history entry via create_version);
the ECL pipeline (knowledge/pipeline/) never ran the chokepoint at all; and
backup restore's ChromaDB embedding upsert used its own original content copy
instead of what store_fact actually persisted. Each is fixed; this guard is
now a genuine tree sweep of knowledge/ (repo_tests._reach floored, per
convention) instead of 3 named files, so a fifth way can't land silently
either.

Sink shapes detected, across every file the sweep reaches:
- fact_store.persist_fact, fact_store.update_fact (not FactsMixin.update_fact
  -- see _deref), FactsMixin._project_fact_to_redis,
  FactsMixin._vectorize_fact_in_chromadb, FactProjectionMixin.
  _durable_update_or_adopt, FactsMixin._revectorize_fact,
  BulkOperationsMixin._restore_fact_embedding.
- redis_client.hset(...) writing a "content" key (inline dict, or a
  same-function local variable already known to be one).
- redis_client.lpush(...) serializing a json.dumps(...) payload that does
  the same.
- A ChromaDB-shaped .upsert(...)/.add(...)/.update(...) call passing a
  documents= keyword (knowledge/pipeline/loaders/chromadb_loader.py's own
  shape -- the LlamaIndex Document()+vector_store.add([doc]) shape
  knowledge/facts.py itself uses is covered by name
  (_vectorize_fact_in_chromadb/_revectorize_fact) instead, since it has no
  documents= kwarg to key on).

Every real redis_client call in this codebase runs through
asyncio.to_thread(self.redis_client.<verb>, ...) -- the callee is passed BY
REFERENCE, never syntactically written as <verb>(...), so there is no
ast.Call node whose own .func is that Attribute. _deref normalizes this
(and the direct-call form) to one shape before any sink check runs; an
earlier draft of this guard's hset/lpush detection matched nothing at all
in this codebase until that normalization was added.

For each call site the sweep finds, the enclosing function must be in
_KNOWN_TO_REDACT (calls sanitize_fact_content/redact_content itself, or is a
pass-through whose only caller already does) or in
_EXEMPT_REDERIVES_EXISTING_CONTENT (re-persists/re-embeds content a durable
read already returned -- not new content, so there is nothing here for
redaction to intercept; backfilling already-stored raw content is a separate,
tracked, deliberately out-of-scope concern) or _EXEMPT_INFRASTRUCTURE (a
generic, content-agnostic adapter/test-fixture that forwards whatever its
caller already decided, or has no production write path at all -- the
redaction responsibility belongs to the caller, which the sweep already
checks independently). A call site in none of the three fails the guard.

Scope is knowledge/ specifically, not all of autobot-backend: a broader
sweep (during this guard's own authoring) found several OTHER subsystems
with a similar content->ChromaDB write shape -- an LLC "project KB" that is
a wholly separate storage/chunking pipeline from this package
(llc/kb/artifact_ingestor.py, sprint_summarizer.py), a security-findings
memory store, an autoresearch synthesizer, and others. None of them share
knowledge/facts.py's sanitize_fact_content chokepoint architecture, so
"exempt them here" would be exactly the silent, undocumented gap this guard
exists to prevent. Filed as #17025 instead of folded into this one (see
that issue for the specific list) -- extending this sweep's scope to cover
them is the natural next step once each has its own, individually-reviewed,
redaction plan.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()

_SINK_CALL_NAMES = frozenset(
    {
        "persist_fact",
        "update_fact",  # fact_store.update_fact -- the durable-store write, not FactsMixin.update_fact
        "_project_fact_to_redis",
        "_vectorize_fact_in_chromadb",
        "_durable_update_or_adopt",
        "_revectorize_fact",
        "_restore_fact_embedding",
    }
)

#: Enclosing functions confirmed (by reading, at guard-authoring time) to run
#: content through sanitize_fact_content or redact_content before any sink
#: call below them executes -- or are a pass-through whose only caller does.
_KNOWN_TO_REDACT = frozenset(
    {
        "_store_and_vectorize_fact",  # store_fact's only caller of this; store_fact redacts first
        "update_fact",  # calls sanitize_fact_content itself, before any sink call
        "_apply_version_to_fact",  # calls redact_content itself, right before the hset
        "_durable_update_or_adopt",  # pass-through: update_fact() is its only caller, already redacted
        "_project_fact_to_redis",  # pass-through: both its callers (below) already covered
        # bulk.py's backup restore: _store_restored_fact calls store_fact (redacts),
        # then passes store_fact's own RETURNED (redacted) content -- not its own
        # original copy -- into _restore_fact_embedding, which is where the actual
        # sink call sits (both need listing: _SINK_CALL_NAMES flags a call to a
        # named sink function from ITS caller too, not just the sink's own body).
        "_restore_fact_embedding",
        "_store_restored_fact",
        # ECL pipeline (#13708 round 4): _run_extract_stage redacts input_data before
        # any extract task runs, so every chunk/summary derived from it downstream is
        # already clean by the time these two ChromaDB batch-upsert helpers run.
        "_upsert_chunk_batch",
        "_upsert_summary_batch",
    }
)

#: Enclosing functions that re-persist or re-embed content a durable read
#: already returned -- not new content, so there is nothing for a redaction
#: pass to intercept here. Pre-existing raw content already in the durable
#: store is a backfill problem, deliberately out of scope for this guard.
_EXEMPT_REDERIVES_EXISTING_CONTENT = frozenset(
    {
        "adopt_legacy_facts",  # re-persists a Redis-only fact's existing content into the durable store
        "rebuild_fact_projections",  # rebuilds Redis from the durable store's own content
        "vectorize_existing_fact",  # re-embeds a fact's already-stored content in ChromaDB
        # knowledge/index.py: copies documents/embeddings/metadatas verbatim from an
        # OLD ChromaDB collection's own .get() into a NEW one during a collection
        # migration -- not new content, a read-then-rewrite of what is already there.
        "_migrate_vectors_batch",
    }
)

#: Generic, content-agnostic infrastructure: forwards whatever its caller
#: already decided (the caller is what this sweep independently checks), or
#: has no production write path at all. Keyed (file, function), not bare name
#: (#13708 round 4 review, MEDIUM 4): a bare-name exemption would silently
#: cover any future function anywhere in the 141-file sweep that happens to
#: share one of these common names (add/upsert/update) without ever being the
#: specific adapter/fixture this exemption was written for.
_EXEMPT_INFRASTRUCTURE = frozenset(
    {
        # knowledge/backends/{chromadb_adapter,async_chromadb_adapter}.py: thin ABC
        # wrappers over the raw ChromaDB client ("does NOT reimplement any ChromaDB
        # behaviour" -- their own module docstring). documents= here is whatever the
        # CALLER already passed; that caller is a separate, independently-checked
        # sink of its own.
        ("autobot-backend/knowledge/backends/chromadb_adapter.py", "add"),
        ("autobot-backend/knowledge/backends/chromadb_adapter.py", "upsert"),
        ("autobot-backend/knowledge/backends/chromadb_adapter.py", "update"),
        ("autobot-backend/knowledge/backends/async_chromadb_adapter.py", "add"),
        ("autobot-backend/knowledge/backends/async_chromadb_adapter.py", "upsert"),
        ("autobot-backend/knowledge/backends/async_chromadb_adapter.py", "update"),
        # knowledge/backends/async_memory_adapter.py: the same thin-wrapper shape,
        # an async shim over the in-memory test-only InMemoryCollection (#5316) --
        # no production write path, documents= here is whatever the caller passed.
        # The bare-name form of this exemption (pre-MEDIUM-4-fix) silently covered
        # this file too, without it ever having been reviewed by name -- listing it
        # explicitly is this fix's own proof the gap was real, not hypothetical.
        ("autobot-backend/knowledge/backends/async_memory_adapter.py", "add"),
        ("autobot-backend/knowledge/backends/async_memory_adapter.py", "upsert"),
        ("autobot-backend/knowledge/backends/async_memory_adapter.py", "update"),
        # knowledge/rag_benchmarks.py: a pytest fixture seeding an ephemeral,
        # in-memory ChromaDB client with a hardcoded synthetic corpus for benchmark
        # timing -- no production write path, no user-controllable content.
        ("autobot-backend/knowledge/rag_benchmarks.py", "chroma_collection"),
    }
)


def _connector_module_files(root: Path) -> list[str]:
    # A single "*.py" here already matches recursively (git pathspec glob is
    # fnmatch-style, not shell-style) -- measured returning a strict superset
    # of the equivalent "**/*.py" pattern, so only one pattern is needed.
    try:
        tracked = tracked_paths(root, "autobot-backend/knowledge/*.py")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if not Path(rel).name.startswith("test_") and not rel.endswith("_test.py")]


#: Bound at the 141 non-test files under knowledge/ measured when this guard
#: was widened from 3 named files to a real tree sweep.
REACH = declare(
    "kb-content-redaction-chokepoint",
    discover=_connector_module_files,
    floor=141,
    growth=10,
    skips=0,
    what="non-test files under knowledge/",
)


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _attr_or_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _deref(node: ast.Call) -> tuple[str | None, list[ast.expr], list[ast.keyword]]:
    """Normalize a Call node to (callee_name, args, keywords).

    Every redis_client call in this codebase runs through
    ``asyncio.to_thread(self.redis_client.hset, key, mapping={...})`` -- the
    callee is passed BY REFERENCE as to_thread's first argument, never
    syntactically written as ``hset(...)``, so there is no ast.Call node whose
    own .func is that Attribute. Direct calls stay a fallback for anything not
    routed through to_thread.
    """
    name = _attr_or_name(node.func)
    if name == "to_thread" and node.args:
        deferred_name = _attr_or_name(node.args[0])
        if deferred_name is not None:
            return deferred_name, node.args[1:], node.keywords
    if name == "update_fact":
        # fact_store.update_fact(...) is the durable-store write sink 66 named, but
        # self.update_fact(...)/kb.update_fact(...) is FactsMixin's own public method
        # -- itself a caller INTO this chokepoint (it redacts internally when content
        # is passed), not a sink. Scope the name to the fact_store.* form specifically.
        func = node.func
        if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "fact_store"):
            name = None
    return name, node.args, node.keywords


def _dict_literal_has_content_key(node: ast.AST) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
    return "content" in keys


def _hset_writes_content(args: list[ast.expr], keywords: list[ast.keyword], content_dict_vars: set[str]) -> bool:
    """True if this hset(...) call's mapping= (or positional dict) writes 'content' --
    either inline, or via a local variable already known (same function) to be a
    dict literal with a 'content' key."""
    candidates = list(args) + [kw.value for kw in keywords if kw.arg in (None, "mapping")]
    for arg in candidates:
        if _dict_literal_has_content_key(arg):
            return True
        if isinstance(arg, ast.Name) and arg.id in content_dict_vars:
            return True
    return False


def _lpush_writes_content(args: list[ast.expr], keywords: list[ast.keyword], content_dict_vars: set[str]) -> bool:
    """True if this lpush(key, json.dumps(<dict with a 'content' key>)) call would
    serialize a fact's content into a list (#13708: version history is exactly this
    shape -- _store_version_data's lpush(version_list_key, json.dumps(version_data)),
    the gap a version-rollback review found this guard's first cut didn't see)."""
    for arg in list(args) + [kw.value for kw in keywords]:
        if isinstance(arg, ast.Call) and _attr_or_name(arg.func) == "dumps" and arg.args:
            payload = arg.args[0]
            if _dict_literal_has_content_key(payload):
                return True
            if isinstance(payload, ast.Name) and payload.id in content_dict_vars:
                return True
    return False


def _chromadb_upsert_writes_documents(name: str | None, keywords: list[ast.keyword]) -> bool:
    """True for a .upsert(...)/.add(...)/.update(...)-shaped call passing documents=
    (knowledge/pipeline/loaders/chromadb_loader.py's shape: a raw ChromaDB
    collection.upsert(ids=..., documents=..., metadatas=...) call, distinct from
    the LlamaIndex Document()+vector_store.add([doc]) shape covered by name via
    _vectorize_fact_in_chromadb/_revectorize_fact instead)."""
    if name not in ("add", "upsert", "update"):
        return False
    return any(kw.arg == "documents" for kw in keywords)


def _sink_call_sites(source: str) -> list[tuple[str, int]]:
    """(enclosing_function_name, line) for every sink call in *source*."""
    tree = ast.parse(source)
    sites: list[tuple[str, int]] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._stack: list[str] = []
            # dict-literal-with-"content"-key local variable names, reset per function
            self._content_dict_vars_stack: list[set[str]] = []

        def _visit_function(self, node: ast.AST) -> None:
            self._stack.append(node.name)  # type: ignore[attr-defined]
            self._content_dict_vars_stack.append(set())
            self.generic_visit(node)
            self._content_dict_vars_stack.pop()
            self._stack.pop()

        visit_FunctionDef = _visit_function
        visit_AsyncFunctionDef = _visit_function

        def visit_Assign(self, node: ast.Assign) -> None:
            if self._content_dict_vars_stack and _dict_literal_has_content_key(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._content_dict_vars_stack[-1].add(target.id)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if self._stack:
                content_dict_vars = self._content_dict_vars_stack[-1]
                name, args, keywords = _deref(node)
                is_sink = (
                    name in _SINK_CALL_NAMES
                    or (name == "hset" and _hset_writes_content(args, keywords, content_dict_vars))
                    or (name == "lpush" and _lpush_writes_content(args, keywords, content_dict_vars))
                    or _chromadb_upsert_writes_documents(name, keywords)
                )
                if is_sink:
                    sites.append((self._stack[-1], node.lineno))
            self.generic_visit(node)

    _Visitor().visit(tree)
    return sites


def test_every_content_sink_call_site_is_redacted_or_explicitly_exempt():
    offenders: list[str] = []
    files = REACH.examined(REPO_ROOT)
    completed = 0
    for rel in files:
        for func_name, line in _sink_call_sites(_read(rel)):
            completed += 1
            if (
                func_name in _KNOWN_TO_REDACT
                or func_name in _EXEMPT_REDERIVES_EXISTING_CONTENT
                or (rel, func_name) in _EXEMPT_INFRASTRUCTURE
            ):
                continue
            offenders.append(f"{rel}:{line} in {func_name}()")
    REACH.completed(len(files))

    assert not offenders, (
        "content reaches a KB persistence sink from a function not known to redact and not an "
        "explicitly justified exception (#13708):\n  " + "\n  ".join(offenders) + "\n\n"
        "Either route this function's content through sanitize_fact_content/redact_content "
        "before the sink call, or -- only if it genuinely re-persists content a durable read "
        "already returned, or is generic content-agnostic infrastructure -- add it to the "
        "appropriate exemption set with that justification."
    )


def test_negative_control_an_unredacted_write_path_is_caught():
    """Proves the sweep can actually fail, not just always pass on the real files."""
    fake_source = """
class FactsMixin:
    async def _new_write_path_nobody_reviewed(self, fact_id, content, metadata):
        await fact_store.persist_fact(fact_id, content, metadata)
"""
    sites = _sink_call_sites(fake_source)
    assert sites == [("_new_write_path_nobody_reviewed", 4)]
    func_name, _line = sites[0]
    assert func_name not in _KNOWN_TO_REDACT
    assert func_name not in _EXEMPT_REDERIVES_EXISTING_CONTENT
    assert not any(fn == func_name for _file, fn in _EXEMPT_INFRASTRUCTURE)


def test_negative_control_infrastructure_exemption_is_scoped_to_its_own_file():
    """#13708 round 4 review, MEDIUM 4: a function elsewhere in the swept tree
    that happens to share one of _EXEMPT_INFRASTRUCTURE's common names
    (add/upsert/update) and forwards a documents= kwarg into a real ChromaDB
    sink must still be caught -- the exemption is scoped to the specific file
    it was written for, not to the bare name."""
    fake_source = """
class NotTheRealAdapter:
    def add(self, ids, documents, metadatas):
        self._collection.add(ids=ids, documents=documents, metadatas=metadatas)
"""
    sites = _sink_call_sites(fake_source)
    assert sites == [("add", 4)]
    func_name, _line = sites[0]
    assert ("some/other/file.py", func_name) not in _EXEMPT_INFRASTRUCTURE


def test_negative_control_hset_without_a_content_key_is_not_flagged():
    """The hset detector must key off the actual mapping, not just the call name."""
    fake_source = """
class TagsMixin:
    async def _tag_only_write(self, fact_key, metadata):
        await asyncio.to_thread(self.redis_client.hset, fact_key, mapping={"metadata": metadata})
"""
    assert _sink_call_sites(fake_source) == []


def test_negative_control_a_chromadb_upsert_without_documents_is_not_flagged():
    """A collection.upsert(...) call with only ids/embeddings/metadatas (no
    documents=) doesn't write fact content and must not be flagged."""
    fake_source = """
async def _reindex_embeddings_only(collection, ids, embeddings):
    await collection.upsert(ids=ids, embeddings=embeddings)
"""
    assert _sink_call_sites(fake_source) == []


def test_negative_control_an_unredacted_chromadb_upsert_is_caught():
    fake_source = """
async def _new_loader_nobody_reviewed(collection, ids, chunks, metadatas):
    await collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
"""
    sites = _sink_call_sites(fake_source)
    assert sites == [("_new_loader_nobody_reviewed", 3)]


def test_create_version_still_only_reachable_with_already_redacted_content():
    """A documented, hand-verified exception the AST sweep above cannot see.

    _store_version_data's lpush(version_list_key, json.dumps(version_data))
    serializes version_data -- but version_data is a PARAMETER built one call
    frame up, in create_version, not a local dict literal in the same function
    the sweep's per-function dict-literal tracking follows across a call
    boundary. This is exactly the shape the version-rollback review found
    unredacted (revert_to_version -> create_version -> _store_version_data ->
    lpush), and the fix was to make _apply_version_to_fact mutate
    target_version["content"] IN PLACE so revert_to_version's later
    create_version(content=target_version["content"]) call reads the
    already-redacted value.

    Grep-based, not full AST, because this is one hand-verified fact about a
    specific 3-line call chain, not a general pattern -- verified here so a
    later refactor that reintroduces a local-only redaction (the exact
    regression this test exists for) fails loudly instead of silently, the
    same way test_revert_to_version_redacts_the_new_version_it_records_too
    (knowledge/versioning_redaction_16985_test.py) proves it via runtime
    behaviour rather than source text.
    """
    source = _read("autobot-backend/knowledge/versioning.py")

    # create_version has exactly one caller (revert_to_version) as of this
    # writing -- if that changes, the new caller needs the same review this
    # comment documents, not silent inheritance of an old guarantee.
    assert source.count("create_version(") == 2, (
        "create_version gained or lost a caller -- re-verify every caller passes "
        "already-redacted content, then update this count"
    )
    assert 'target_version["content"] = redact_content(target_version["content"])' in source, (
        '_apply_version_to_fact no longer mutates target_version["content"] in place -- '
        'revert_to_version\'s later create_version(content=target_version["content"]) call '
        "would read the raw value again (the exact gap this test guards)"
    )


def test_the_ecl_pipeline_redacts_before_the_extract_stage():
    """A second documented, hand-verified exception: the ECL pipeline's real
    chokepoint (runner.py's _run_extract_stage) redacts input_data BEFORE
    chunking, which is why _upsert_chunk_batch/_upsert_summary_batch in
    chromadb_loader.py are exempt above rather than redacting themselves --
    their content already is, several call frames up. Source-text checked
    for the same reason as the test above: the AST sweep's per-function
    tracking doesn't follow "redacted N calls ago, N files away".
    """
    source = _read("autobot-backend/knowledge/pipeline/runner.py")
    assert "input_data = redact_content(input_data)" in source, (
        "_run_extract_stage no longer redacts input_data before the extract task loop -- "
        "every chunk/summary chromadb_loader.py persists downstream would be unredacted again"
    )
