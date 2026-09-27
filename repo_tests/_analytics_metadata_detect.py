# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST detectors for the codebase-analytics metadata contract (#17651).

Separated from the test module so each detector can be exercised against
synthetic source in a contrast pair -- a fixture it must recognise and one it
must reject -- rather than only against today's tree. A detector checked only
against the live repository is checked against the one input it is guaranteed
to agree with.
"""

from __future__ import annotations

import ast

#: Chroma supplies this itself; no writer emits it.
ENGINE_SUPPLIED = frozenset({"chroma:document"})

#: Mongo-style operators appearing as keys inside a `where` filter. They are
#: structure, not metadata field names, so they are never required of a writer.
_FILTER_OPERATORS = frozenset({"$and", "$or", "$in", "$nin", "$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$not"})


def _is_metadata_target(node: ast.AST) -> bool:
    """`metadata` as a bare name or as the object of a subscript assignment."""
    if isinstance(node, ast.Name):
        return node.id == "metadata"
    if isinstance(node, ast.Subscript):
        return isinstance(node.value, ast.Name) and node.value.id == "metadata"
    return False


def metadata_keys_of(func: ast.AST) -> set[str]:
    """Keys actually written onto the emitted `metadata` dict in *func*.

    #17672 review: the first version collected every dict key and every
    constant subscript anywhere in the function. A preparer that stopped
    assigning `source_id` to `metadata` but mentioned the name in some other
    dict still satisfied the test -- the detector measured the function, not
    the emission. This follows the binding instead.
    """
    keys: set[str] = set()
    for node in ast.walk(func):
        # metadata = {"k": ...}
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            if any(_is_metadata_target(t) for t in node.targets):
                keys |= {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        # metadata["k"] = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript) and _is_metadata_target(target):
                    if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                        keys.add(target.slice.value)
        # metadata.update({"k": ...})
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update":
            if _is_metadata_target(node.func.value):
                for arg in node.args:
                    if isinstance(arg, ast.Dict):
                        keys |= {k.value for k in arg.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def preparers(source: str) -> dict[str, set[str]]:
    """`_prepare_*_document` functions mapped to the keys they emit."""
    tree = ast.parse(source)
    return {
        node.name: metadata_keys_of(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("_prepare_")
        and node.name.endswith("_document")
    }


def metadata_binders(source: str) -> set[str]:
    """Functions that bind a dict to `metadata` -- discovery by behaviour."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Dict):
                if any(isinstance(t, ast.Name) and t.id == "metadata" for t in sub.targets):
                    found.add(node.name)
    return found


def inline_write_site_keys(source: str) -> set[str]:
    """Keys in a dict passed inline as `metadatas=[...]` to a write call.

    #17672 review: a future writer can pass `metadatas=[{"source_id": x}]`
    directly and escape both name-based and binding-based discovery. This is
    the third population, and it is empty today by construction rather than by
    luck -- which is exactly why it needs its own contrast fixture.
    """
    tree = ast.parse(source)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "metadatas":
                continue
            for element in ast.walk(kw.value):
                if isinstance(element, ast.Dict):
                    keys |= {k.value for k in element.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return keys


def filter_keys(source: str) -> set[str]:
    """Metadata keys an endpoint filters on, discovered from the filter itself.

    #17672 review: the first version regex-matched dict keys and then
    intersected with a hardcoded set of six names. A `where` filter on a new
    key was silently discarded, so the contract passed even when no writer
    emitted it -- an allowlist that goes stale exactly like the thing it
    guards, which is the objection I had raised against a different allowlist
    an hour earlier.

    A key is a filter key when it appears as a dict key whose value is either
    an operator dict (`{"$in": [...]}`) or a plain comparison, inside a dict
    that is assigned to a `*filter*`/`where*` name or passed as `where=`.
    Operators themselves are structure and are excluded.
    """
    tree = ast.parse(source)
    keys: set[str] = set()

    def harvest(node: ast.AST) -> None:
        for element in ast.walk(node):
            if isinstance(element, ast.Dict):
                for k in element.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        if k.value not in _FILTER_OPERATORS:
                            keys.add(k.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = target.id if isinstance(target, ast.Name) else None
                if name and ("filter" in name or name.startswith("where")):
                    harvest(node.value)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "where":
                    harvest(kw.value)
    return keys
