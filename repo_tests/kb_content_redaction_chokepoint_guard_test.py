# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every write of *new* content into a KB persistence sink is reached only
through sanitize_fact_content, or is an explicitly justified exception (#13708).

#13708's review found two ways to skip the redaction chokepoint that a guard
scoped only to entry points (repo_tests/ingestion_redaction_guard_test.py)
cannot see: update_fact writes new content through a completely separate path
from store_fact, and reverting a fact to a previous version pushes that
version's (possibly pre-fix, possibly never-sanitized) content back into the
live Redis projection. Both are fixed; this guard is the sweep that stops a
THIRD one from landing silently.

A third way surfaced reviewing the second fix: _apply_version_to_fact
redacted the live Redis projection but left a local variable only, so
revert_to_version's later create_version() call re-serialized the RAW
version content straight into version history seconds later. Fixed by
redacting in place; test_create_version_still_only_reachable_with_already_
redacted_content below is the hand-verified guard for that one call chain,
since it is one function parameter passed across a call boundary, not a
pattern the AST sweep's per-function dict-literal tracking follows.

Scope: the persistence primitives content actually reaches --
fact_store.persist_fact, FactsMixin._project_fact_to_redis,
FactsMixin._vectorize_fact_in_chromadb, FactProjectionMixin.
_durable_update_or_adopt, FactsMixin._revectorize_fact, any
redis_client.hset(...) call whose mapping writes a "content" key (inline or
via a same-function local variable), and any redis_client.lpush(...) call
serializing a json.dumps(...) payload that does the same -- every real
redis_client write in this codebase runs through
asyncio.to_thread(self.redis_client.<verb>, ...), so the sweep normalizes
that form (see _deref) rather than only matching a direct <verb>(...) call.
For each call site, found by AST across knowledge/facts.py,
knowledge/fact_projection.py and knowledge/versioning.py, the enclosing
function must be in _KNOWN_TO_REDACT (calls sanitize_fact_content or
redact_content itself, directly or one call away) or in
_EXEMPT_REDERIVES_EXISTING_CONTENT (does not accept new content -- it
re-persists/re-embeds what a durable read already returned, so there is
nothing here for redaction to intercept; backfilling already-stored raw
content is explicitly out of scope, tracked separately). A call site whose
enclosing function is in neither list fails the guard.

Not tree-scanning (repo_tests._reach doesn't apply): a fixed set of 3 files,
not a directory walk.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()

_SINK_CALL_NAMES = frozenset(
    {
        "persist_fact",
        "update_fact",  # fact_store.update_fact -- the durable-store write, not FactsMixin.update_fact
        "_project_fact_to_redis",
        "_vectorize_fact_in_chromadb",
        "_durable_update_or_adopt",
        "_revectorize_fact",
    }
)

_FILES = (
    "autobot-backend/knowledge/facts.py",
    "autobot-backend/knowledge/fact_projection.py",
    "autobot-backend/knowledge/versioning.py",
)

#: Enclosing functions confirmed (by reading, at guard-authoring time) to run
#: content through sanitize_fact_content or redact_content before any sink
#: call below them executes.
_KNOWN_TO_REDACT = frozenset(
    {
        "_store_and_vectorize_fact",  # store_fact's only caller of this; store_fact redacts first
        "update_fact",  # calls sanitize_fact_content itself, before any sink call
        "_apply_version_to_fact",  # calls redact_content itself, right before the hset
        # Pass-through: update_fact() is its ONLY caller (verified when this guard was
        # written) and already redacted before calling it; this function does not
        # itself need to redact, only to stay reached from nowhere else.
        "_durable_update_or_adopt",
        # Pass-through, its own hset writes "content" too: called by
        # _store_and_vectorize_fact (pre-redacted, see above) AND by
        # rebuild_fact_projections (exempt below, re-derives existing content) --
        # both of its callers are already covered, so this function needs no
        # redaction of its own.
        "_project_fact_to_redis",
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
    }
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
                )
                if is_sink:
                    sites.append((self._stack[-1], node.lineno))
            self.generic_visit(node)

    _Visitor().visit(tree)
    return sites


def test_every_content_sink_call_site_is_redacted_or_explicitly_exempt():
    offenders: list[str] = []
    reached_any = False
    for rel in _FILES:
        for func_name, line in _sink_call_sites(_read(rel)):
            reached_any = True
            if func_name in _KNOWN_TO_REDACT or func_name in _EXEMPT_REDERIVES_EXISTING_CONTENT:
                continue
            offenders.append(f"{rel}:{line} in {func_name}()")

    assert reached_any, "swept 0 sink call sites across the 3 files -- the AST walk itself is broken"
    assert not offenders, (
        "content reaches a KB persistence sink from a function not known to redact and not an "
        "explicitly justified exception (#13708):\n  " + "\n  ".join(offenders) + "\n\n"
        "Either route this function's content through sanitize_fact_content/redact_content "
        "before the sink call, or -- only if it genuinely re-persists content a durable read "
        "already returned, never NEW content -- add it to _EXEMPT_REDERIVES_EXISTING_CONTENT "
        "with that justification."
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


def test_negative_control_hset_without_a_content_key_is_not_flagged():
    """The hset detector must key off the actual mapping, not just the call name."""
    fake_source = """
class TagsMixin:
    async def _tag_only_write(self, fact_key, metadata):
        await asyncio.to_thread(self.redis_client.hset, fact_key, mapping={"metadata": metadata})
"""
    assert _sink_call_sites(fake_source) == []


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
