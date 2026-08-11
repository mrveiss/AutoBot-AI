# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AST-based code indexer using tree-sitter (#4820).

Two-pass extraction per source file:
  Pass 1 (structural): walk AST for function/class declarations -> nodes.
  Pass 2 (call-graph): walk function bodies for call expressions -> edges.

Results are embedded and upserted into ChromaDB following the same
SHA-256 content-hash cache + upsert pattern as DocIndexer.

Issue #13469: edges used to be flattened into a comma-joined string of raw
callee names on the node's own metadata (a "calls" field with zero readers)
and stamped "extracted" unconditionally. They are now resolved against the
canonical identity/resolver in autobot_shared/code_graph/ (#13470) and
persisted as their own documents in the same collection
(``metadata["record_type"] == "edge"``), each carrying the target node id
(when resolved), the raw target name (always), and one of the three
provenance tiers (#13482 Q2) so "who calls X" is an exact metadata lookup
instead of a string nobody could parse back into a graph.

Supported languages: Python, JavaScript/TypeScript.
"""

import asyncio
import hashlib
import json
import os
import re
import subprocess  # nosec B404  # read-only git queries for graph provenance (#13508)
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autobot_shared.code_graph import ResolvedCall, compute_node_id, module_path_from_rel_path, resolve_call
from autobot_shared.logging_manager import get_logger
from constants.path_constants import PATH
from utils.file_categorization import (
    ALL_CODE_EXTENSIONS,
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    TS_EXTENSIONS,
    VUE_EXTENSIONS,
)

logger = get_logger(__name__)

# Process-level locks keyed by cache file path.  Two concurrent index_directory()
# calls that share the same cache file (same CodeIndexer instance or different
# instances pointing at the same path) will serialize through this lock so that
# neither loses the other's cache entries.
_CACHE_FILE_LOCKS: dict[str, asyncio.Lock] = {}


def _get_cache_lock(path: str) -> asyncio.Lock:
    """Return (creating if necessary) the asyncio.Lock for *path*."""
    if path not in _CACHE_FILE_LOCKS:
        _CACHE_FILE_LOCKS[path] = asyncio.Lock()
    return _CACHE_FILE_LOCKS[path]


@dataclass
class CodeIndexResult:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    # #13510: extension -> count of code files this indexer has no grammar for.
    # Reported rather than dropped at collection time, so a consumer can tell an
    # under-covered graph from a complete one.
    unsupported_extensions: dict[str, int] = field(default_factory=dict)
    # #13508: edge-resolution roll-up. Already computed per file to build the edge
    # metadata; totalling it is what turns a resolver regression into a number
    # that goes down, rather than something inferred from a wrong answer later.
    nodes: int = 0
    edges: int = 0
    resolved_edges: int = 0
    unresolved_edges: int = 0
    files_with_extractor: int = 0
    files_total: int = 0


# #13508: bump when extraction, resolution or node identity changes in a way that
# makes previously-indexed records wrong rather than merely stale. A bump
# invalidates the whole hash cache on the next run, so every file is re-extracted
# instead of being skipped on an unchanged content hash — a content hash cannot
# notice that the *extractor* changed.
EXTRACTOR_VERSION = 1

# One provenance document per collection, at a fixed id so a run overwrites the
# previous record instead of accumulating history.
_PROVENANCE_ID = "code_graph::provenance"
_PROVENANCE_RECORD_TYPE = "graph_provenance"

# Key under which the hash cache carries the version that wrote it. Deliberately
# not a valid relative path, so it can never collide with a cached file entry.
_CACHE_VERSION_KEY = "::extractor_version"

# #13509: graph-shape fingerprints live in the same cache dict under this prefix,
# so the existing EXTRACTOR_VERSION gate discards them too rather than needing a
# second versioning mechanism. The prefix cannot collide with a relative path.
_SIGNATURE_KEY_PREFIX = "::sig::"

# Bound on the read-only git calls provenance makes; never hard-coded inline.
_GIT_TIMEOUT_SECONDS = int(os.environ.get("AUTOBOT_CODE_INDEX_GIT_TIMEOUT_SECONDS", "10"))


@dataclass
class GraphProvenance:
    """How and when the code graph was built (#13508).

    Absence of this record means **unknown**, never fresh: a collection indexed
    before provenance existed must not read as current, which is why every
    consumer goes through ``load_graph_provenance`` returning ``None`` rather
    than a zero-valued default.

    ``nodes``/``edges``/``resolved_edges`` describe **the graph**, counted from the
    collection. ``last_run_*`` describe the run that wrote this record. Keeping
    them apart is the point: an incremental run extracts nothing, and per-run
    totals would report a healthy graph as empty.

    Every field carries a default so a record written by an older version stays
    readable — a missing field must degrade one value, not the whole record.
    """

    root_dir: str = ""
    indexed_at_commit: str = ""
    indexed_at: str = ""
    extractor_version: int = 0
    files_with_extractor: int = 0
    files_total: int = 0
    nodes: int = 0
    edges: int = 0
    resolved_edges: int = 0
    unresolved_edges: int = 0
    last_run_nodes_stored: int = 0
    last_run_failures: int = 0

    @property
    def extractor_coverage(self) -> float:
        """Fraction of the code the registry recognises that this indexer can read.

        Deliberately not called "coverage": it says nothing about whether those
        files were successfully extracted on any given run, only that a grammar
        exists for them (#13510).
        """
        return self.files_with_extractor / self.files_total if self.files_total else 0.0

    @property
    def resolution_rate(self) -> float:
        """Fraction of edges in the graph that resolved to a known node."""
        return self.resolved_edges / self.edges if self.edges else 0.0

    @property
    def is_current_extractor(self) -> bool:
        """Whether the graph was built by the extractor this process is running."""
        return self.extractor_version == EXTRACTOR_VERSION


def _count_by_extension(paths: "list[Path]") -> dict[str, int]:
    """Tally *paths* by lowercased suffix (#13510)."""
    counts: dict[str, int] = {}
    for path in paths:
        suffix = path.suffix.lower()
        counts[suffix] = counts.get(suffix, 0) + 1
    return counts


def _make_node_id(name: str, module_path: str, parent_class: str | None = None) -> str:
    """Node id via the canonical autobot_shared.code_graph scheme (#13470).

    Thin wrapper kept so callers in this module read the same as before;
    ``compute_node_id`` is the single implementation shared with
    ``api/codebase_analytics/endpoints/call_graph.py``.
    """
    return compute_node_id(name, module_path, parent_class)


def extract_python(source_path: str, content: bytes) -> dict:
    """Two-pass tree-sitter extraction for Python.

    *source_path* must be project-relative (e.g. ``"services/knowledge/code_indexer.py"``);
    it is used to derive the module path both passes key nodes/edges on.

    Returns {"nodes": [...], "edges": [...]}.
    """
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
    except ImportError as exc:
        logger.error("tree-sitter-python not installed — AST indexing disabled: %s", exc)
        return {"nodes": [], "edges": [], "dep_error": str(exc)}

    lang = Language(tspython.language())
    parser = Parser(lang)
    tree = parser.parse(content)

    module_path = module_path_from_rel_path(source_path)
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    _py_structural(tree.root_node, module_path, source_path, nodes, current_class=None)
    _py_call_graph(tree.root_node, module_path, source_path, edges, seen_edges, current_scope=None, current_class=None)

    return {"nodes": list(nodes.values()), "edges": edges}


def _store_node(
    node: Any, name: str, module_path: str, source_path: str, nodes: dict, kind: str, current_class: str | None
) -> None:
    """Record one structural node. Shared by the Python and JS/TS structural passes."""
    nid = _make_node_id(name, module_path, current_class)
    nodes[nid] = {
        "id": nid,
        "name": name,
        "kind": kind,
        "source_path": source_path,
        "line": node.start_point[0] + 1,
        "parent": _make_node_id(current_class, module_path) if current_class else None,
    }


def _record_call_edge(
    node: Any,
    module_path: str,
    source_path: str,
    current_scope: str,
    current_class: str | None,
    edges: list,
    seen: set,
) -> None:
    """Record one raw call edge (target not yet resolved). Shared by Python and JS/TS."""
    func_node = node.child_by_field_name("function")
    if not func_node:
        return
    raw = func_node.text.decode("utf-8").split("(")[0]
    target_name = raw.split(".")[-1]
    pair = (current_scope, target_name)
    if pair in seen:
        return
    seen.add(pair)
    edges.append(
        {
            "source": current_scope,
            "target_name": target_name,
            "module_path": module_path,
            "current_class": current_class,
            "kind": "calls",
            "source_path": source_path,
            "line": node.start_point[0] + 1,  # call site, not the callee's def line (#13471)
        }
    )


def _py_structural(node: Any, module_path: str, source_path: str, nodes: dict, current_class: str | None) -> None:
    """Structural pass: record function/class nodes, tracking class scope (#13469).

    Fixes a pre-existing bug where class scope was tracked here but not by
    ``_py_call_graph`` (below), so a method's node id and its call-graph
    scope disagreed and its outgoing calls never attached to it — see
    ``test_class_method_call_graph``, which failed on this before #13469.
    """
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8")
            _store_node(node, name, module_path, source_path, nodes, "function", current_class)
            for child in node.children:
                _py_structural(child, module_path, source_path, nodes, current_class)
            return
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            class_name = name_node.text.decode("utf-8")
            _store_node(node, class_name, module_path, source_path, nodes, "class", current_class)
            for child in node.children:
                _py_structural(child, module_path, source_path, nodes, class_name)
            return
    for child in node.children:
        _py_structural(child, module_path, source_path, nodes, current_class)


def _py_call_graph(
    node: Any,
    module_path: str,
    source_path: str,
    edges: list,
    seen: set,
    current_scope: str | None,
    current_class: str | None,
) -> None:
    """Call-graph pass: record raw call edges, now tracking class scope (#13469;
    see the docstring on ``_py_structural`` for the bug this fixes)."""
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        scope = (
            _make_node_id(name_node.text.decode("utf-8"), module_path, current_class) if name_node else current_scope
        )
        for child in node.children:
            _py_call_graph(child, module_path, source_path, edges, seen, scope, current_class)
        return
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        class_name = name_node.text.decode("utf-8") if name_node else current_class
        for child in node.children:
            _py_call_graph(child, module_path, source_path, edges, seen, current_scope, class_name)
        return
    if node.type == "call" and current_scope:
        _record_call_edge(node, module_path, source_path, current_scope, current_class, edges, seen)
    for child in node.children:
        _py_call_graph(child, module_path, source_path, edges, seen, current_scope, current_class)


def _js_structural(node: Any, module_path: str, source_path: str, nodes: dict, current_class: str | None) -> None:
    """Structural pass for JS/TS/Vue. Fixes the same class-scope bug as ``_py_structural``:
    the original never updated ``parent_scope`` when descending into a ``class_declaration``,
    so JS/TS methods never nested under their class."""
    if node.type in ("function_declaration", "arrow_function", "function_expression"):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else f"anon_{node.start_point[0]}"
        _store_node(node, name, module_path, source_path, nodes, "function", current_class)
        for child in node.children:
            _js_structural(child, module_path, source_path, nodes, current_class)
        return
    if node.type == "class_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            class_name = name_node.text.decode("utf-8")
            _store_node(node, class_name, module_path, source_path, nodes, "class", current_class)
            for child in node.children:
                _js_structural(child, module_path, source_path, nodes, class_name)
            return
    for child in node.children:
        _js_structural(child, module_path, source_path, nodes, current_class)


def _js_call_graph(
    node: Any,
    module_path: str,
    source_path: str,
    edges: list,
    seen: set,
    current_scope: str | None,
    current_class: str | None,
) -> None:
    """Call-graph pass for JS/TS/Vue; mirrors ``_py_call_graph``."""
    if node.type in ("function_declaration", "arrow_function", "function_expression"):
        name_node = node.child_by_field_name("name")
        scope = (
            _make_node_id(name_node.text.decode("utf-8"), module_path, current_class) if name_node else current_scope
        )
        for child in node.children:
            _js_call_graph(child, module_path, source_path, edges, seen, scope, current_class)
        return
    if node.type == "class_declaration":
        name_node = node.child_by_field_name("name")
        class_name = name_node.text.decode("utf-8") if name_node else current_class
        for child in node.children:
            _js_call_graph(child, module_path, source_path, edges, seen, current_scope, class_name)
        return
    if node.type == "call_expression" and current_scope:
        _record_call_edge(node, module_path, source_path, current_scope, current_class, edges, seen)
    for child in node.children:
        _js_call_graph(child, module_path, source_path, edges, seen, current_scope, current_class)


def extract_javascript(source_path: str, content: bytes) -> dict:
    """Two-pass extraction for JavaScript/TypeScript. *source_path* must be project-relative."""
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser
    except ImportError as exc:
        logger.error("tree-sitter-javascript not installed — AST indexing disabled: %s", exc)
        return {"nodes": [], "edges": [], "dep_error": str(exc)}

    lang = Language(tsjs.language())
    parser = Parser(lang)
    tree = parser.parse(content)

    module_path = module_path_from_rel_path(source_path)
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()
    _js_structural(tree.root_node, module_path, source_path, nodes, current_class=None)
    _js_call_graph(tree.root_node, module_path, source_path, edges, seen_edges, current_scope=None, current_class=None)
    return {"nodes": list(nodes.values()), "edges": edges}


# #13510: the grammars here cannot parse Cython, so the two Cython members of
# PYTHON_EXTENSIONS are held back rather than mapped to the Python extractor.
# Measured: on a file declaring ``cdef add``, ``cpdef scale`` and ``def normal``,
# tree-sitter-python sees only ``normal`` — the cdef/cpdef definitions become
# invisible while calls to them survive as unresolvable edges. That is worse than
# not indexing the file, which is why this list exists instead of a blanket map.
_NO_GRAMMAR_EXTENSIONS: "frozenset[str]" = frozenset({".pyx", ".pxd"})

# #13510: a stub shares its implementation's module path — ``module_path_from_rel_path``
# strips the suffix, so ``foo.py`` and ``foo.pyi`` compute the *same* node ids and the
# stub's declarations would overwrite the real ones in the shared collection. Held back
# until node identity carries the extension (#13824). Distinct from the set above: the
# grammar reads these fine, the identity scheme cannot tell them apart.
_COLLIDING_STUB_EXTENSIONS: "frozenset[str]" = frozenset({".pyi"})

_HELD_BACK_EXTENSIONS: "frozenset[str]" = _NO_GRAMMAR_EXTENSIONS | _COLLIDING_STUB_EXTENSIONS

# #13510: derived from the canonical registry in ``utils/file_categorization``
# rather than restated here, so "what the platform calls source code" and "what the
# indexer will read" cannot drift apart silently. ``.ts``/``.tsx`` were already
# parsed with the JavaScript grammar; ``.mts``/``.cts`` join them on the same terms.
_EXTRACTORS: dict[str, Any] = {
    **{ext.lower(): extract_python for ext in PYTHON_EXTENSIONS - _HELD_BACK_EXTENSIONS},
    **{ext.lower(): extract_javascript for ext in JS_EXTENSIONS | TS_EXTENSIONS | VUE_EXTENSIONS},
}

# Extensions the canonical registry calls code but this indexer has no extractor
# for. Files with these extensions are *counted* as skipped (#13510) — previously
# they were dropped during collection, so they could not appear in any total and a
# partially-covered graph reported itself as complete.
#
# Lowercased because the walk matches on ``suffix.lower()``. The registry carries
# uppercase members (``.R``, ``.Rmd``, ``.S``) that would otherwise sit in this set
# and never match anything — invisible again, which is the defect this issue fixes.
UNSUPPORTED_CODE_EXTENSIONS: "frozenset[str]" = frozenset(ext.lower() for ext in ALL_CODE_EXTENSIONS) - frozenset(
    _EXTRACTORS
)


_DEFAULT_CACHE = PATH.DATA_DIR / ".code_index_hashes.json"


class CodeIndexer:
    """Index source files into ChromaDB using AST extraction.

    Mirrors DocIndexer's SHA-256 hash cache + upsert pattern.
    Each function/class node becomes one ChromaDB document; each resolved
    call edge becomes a second document (``record_type == "edge"``, #13469)
    in the same collection — no fourth store, per the #13467 umbrella.
    """

    def __init__(
        self,
        collection: Any,
        embed_model: Any,
        cache_file: Path = _DEFAULT_CACHE,
    ) -> None:
        self._collection = collection
        self._embed_model = embed_model
        self._cache_file = cache_file
        self._hash_cache: dict[str, str] = self._load_cache()
        # Node ids known to the collection plus everything indexed so far this
        # run; lazily seeded (#13469) so cross-file/cross-run call resolution
        # does not require every source file to be reprocessed on every run.
        self._known_ids: set[str] | None = None

    async def index_file(
        self,
        file_path: str,
        root_dir: str,
        force: bool = False,
    ) -> CodeIndexResult:
        """Extract AST nodes+edges from file_path and upsert into ChromaDB."""
        result = CodeIndexResult()
        ext = Path(file_path).suffix.lower()
        if ext not in _EXTRACTORS:
            result.skipped += 1
            return result

        rel_path = str(Path(file_path).relative_to(root_dir))
        extracted = await self._extract_file(file_path, rel_path, ext, force, result)
        if extracted is None:
            return result

        await self._ensure_known_ids()
        if extracted.get("shape_unchanged"):
            # #13509: the interface is identical, so every embedding would be
            # recomputed for the same text. Line numbers still move, and a stale
            # line makes "go to definition" drift — so the records are updated,
            # just not re-embedded.
            await self._refresh_line_ranges(rel_path, extracted, result)
        else:
            await self._index_extraction(rel_path, extracted, result)
        self._update_hash_cache(file_path, rel_path, extracted.get("shape"))
        return result

    async def _extract_file(
        self, file_path: str, rel_path: str, ext: str, force: bool, result: CodeIndexResult
    ) -> dict | None:
        """Hash-check, read and extract one file; updates *result* and returns
        None on skip/failure. Split from index_file() to keep it under 30 lines."""
        if not force:
            current_hash = self._compute_hash(file_path)
            if current_hash and self._hash_cache.get(rel_path) == current_hash:
                result.skipped += 1
                return None
        try:
            # #7467: was sync `Path(file_path).read_bytes()` blocking the event loop
            # during code indexing of potentially-large source files.
            content = await asyncio.to_thread(Path(file_path).read_bytes)
        except OSError as e:
            result.failed += 1
            result.errors.append(str(e))
            return None
        extracted = _EXTRACTORS[ext](rel_path, content)
        if extracted.get("dep_error"):
            result.failed += 1
            result.errors.append(f"{rel_path}: missing dependency — {extracted['dep_error']}")
            return None
        extracted["shape"] = self._shape_of(extracted)
        extracted["shape_unchanged"] = not force and self._shape_unchanged(rel_path, extracted["shape"])
        return extracted

    def _shape_unchanged(self, rel_path: str, current: str | None) -> bool:
        """Whether *rel_path* produced exactly the graph shape stored last run.

        The import is deferred so ``code_indexer`` degrades rather than failing
        to import if the ``code_intelligence`` package chain is unavailable in a
        standalone worker context. Any import failure answers False — re-analyse.
        """
        try:
            from code_intelligence.fingerprinting.graph_shape import shape_matches  # noqa: PLC0415
        except Exception:  # pragma: no cover - defensive
            return False
        return shape_matches(self._hash_cache.get(_SIGNATURE_KEY_PREFIX + rel_path), current)

    @staticmethod
    def _shape_of(extracted: dict) -> str | None:
        """Fingerprint the extractor's own output (#13509).

        Language-agnostic on purpose: it reads the emitted nodes/edges rather
        than re-parsing the source, so it cannot disagree with what gets
        persisted the way an AST-derived signature did.
        """
        try:
            from code_intelligence.fingerprinting.graph_shape import (  # noqa: PLC0415
                compute_graph_shape_fingerprint,
            )

            return compute_graph_shape_fingerprint(extracted)
        except Exception:
            return None

    async def _refresh_line_ranges(self, rel_path: str, extracted: dict, result: CodeIndexResult) -> None:
        """Update node line numbers without recomputing a single embedding (#13509).

        Metadata-only: a node's embedded text is its kind, name and path, and an
        edge document reuses its source node's embedding — all unchanged by
        definition when the fingerprint matched, since it covers every persisted
        field except the line. Re-embedding to move a line number is the waste
        this issue is about.
        """
        nodes = extracted["nodes"]
        edges = extracted.get("edges") or []
        self._known_ids.update(n["id"] for n in nodes)
        if not nodes:
            return

        ids = [n["id"] for n in nodes]
        metadatas: list[dict] = [{"line": str(n.get("line", 0))} for n in nodes]
        # The line is part of the embedded text, so the stored document is
        # rewritten too — the *embedding* is what stays, and a line number moves
        # it immeasurably. Leaving the document behind would make the record
        # disagree with its own metadata.
        documents: list[str] = [_node_document(n, rel_path) for n in nodes]
        # #13509 (review): edges move too. Their identity is in the fingerprint,
        # so a match means only the call site's line shifted — but leaving
        # call_line stale makes impact analysis point at the wrong line, which is
        # the same silent drift for edges that stale node lines are for nodes.
        for edge in edges:
            ids.append(f"edge::{edge.get('source')}::{edge.get('target_name')}")
            metadatas.append({"call_line": edge.get("line", 0)})
            documents.append(f"CALLS {edge.get('target_name')}")

        try:
            await asyncio.to_thread(self._collection.update, ids=ids, metadatas=metadatas, documents=documents)
            result.success += len(nodes)
        except Exception as exc:
            # Fail open: a failed refresh must not leave the cache claiming the
            # file is current, or the drift becomes permanent.
            logger.warning("%s: line-range refresh failed, forcing re-index next run: %s", rel_path, exc)
            extracted["shape"] = None
            result.failed += len(nodes)
        result.nodes += len(nodes)
        result.edges += len(edges)

    def _update_hash_cache(self, file_path: str, rel_path: str, shape: str | None = None) -> None:
        new_hash = self._compute_hash(file_path)
        if new_hash:
            self._hash_cache[rel_path] = new_hash
            # A missing fingerprint clears any stored one, so the next run takes
            # the full path rather than comparing against a stale fingerprint.
            key = _SIGNATURE_KEY_PREFIX + rel_path
            if shape:
                self._hash_cache[key] = shape
            else:
                self._hash_cache.pop(key, None)
            self._save_cache()

    async def index_directory(
        self,
        root_dir: str,
        force: bool = False,
    ) -> CodeIndexResult:
        """Walk *root_dir* recursively and index every supported source file.

        Skips hidden directories (starting with '.') and node_modules/venv/
        directories to avoid indexing third-party code.

        A process-level asyncio.Lock serialises concurrent calls that share the
        same cache file, preventing last-write-wins cache corruption (#4895).
        """
        async with _get_cache_lock(str(self._cache_file)):
            # Reload cache and known node ids inside the lock so this batch
            # starts from the freshest snapshot of both (#4895, #13469).
            self._hash_cache = self._load_cache()
            self._known_ids = await self._seed_known_ids_from_collection()

            aggregate = CodeIndexResult()
            paths, unsupported = await self._collect_source_files(root_dir)
            # #13510: code the registry recognises but no grammar here can read.
            # Counted rather than dropped, so a partially covered graph says so.
            aggregate.skipped += len(unsupported)
            if unsupported:
                aggregate.unsupported_extensions = _count_by_extension(unsupported)
                logger.info(
                    "code_indexer: %d code file(s) skipped — no extractor for %s (#13510)",
                    len(unsupported),
                    sorted(aggregate.unsupported_extensions),
                )
            for path in paths:
                result = await self.index_file(str(path), root_dir=root_dir, force=force)
                aggregate.success += result.success
                aggregate.failed += result.failed
                aggregate.skipped += result.skipped
                aggregate.errors.extend(result.errors)
                aggregate.nodes += result.nodes
                aggregate.edges += result.edges
                aggregate.resolved_edges += result.resolved_edges
                aggregate.unresolved_edges += result.unresolved_edges
            aggregate.files_with_extractor = len(paths)
            aggregate.files_total = len(paths) + len(unsupported)
            await self._write_provenance(root_dir, aggregate)
            return aggregate

    async def _write_provenance(self, root_dir: str, aggregate: CodeIndexResult) -> None:
        """Persist how this run built the graph (#13508).

        Best-effort: a graph that indexed correctly must not be reported as failed
        because its provenance could not be stored. A missing record already means
        "unknown" to every reader, which is the safe reading.
        """
        provenance = await self._build_provenance(root_dir, aggregate)
        if provenance is None:
            return
        document = f"code graph built at {provenance.indexed_at_commit or 'unknown commit'} from {provenance.root_dir}"
        # The provenance record shares the docs collection, whose vector dimension
        # is fixed by its first insert. A placeholder vector would be rejected on a
        # populated collection and — far worse — *accepted* on an empty one,
        # pinning it to that dimension and permanently breaking every later real
        # upsert. So it is embedded with the same model as every other record.
        try:
            embedding = await asyncio.to_thread(self._embed_model.get_text_embedding, document)
        except Exception as exc:
            logger.warning("code_indexer: could not embed graph provenance, not recording it: %s (#13508)", exc)
            return
        try:
            await asyncio.to_thread(
                self._collection.upsert,
                ids=[_PROVENANCE_ID],
                embeddings=[embedding],
                documents=[document],
                metadatas=[{"record_type": _PROVENANCE_RECORD_TYPE, **asdict(provenance)}],
            )
        except Exception as exc:
            logger.warning("code_indexer: could not write graph provenance: %s (#13508)", exc)
            return
        logger.info(
            "code_indexer: graph provenance commit=%s coverage=%d/%d nodes=%d edges=%d "
            "resolved=%d run(stored=%d failed=%d)",
            provenance.indexed_at_commit[:12] or "unknown",
            provenance.files_with_extractor,
            provenance.files_total,
            provenance.nodes,
            provenance.edges,
            provenance.resolved_edges,
            provenance.last_run_nodes_stored,
            provenance.last_run_failures,
        )

    async def _build_provenance(self, root_dir: str, aggregate: CodeIndexResult) -> "GraphProvenance | None":
        """Assemble the record, counting the graph rather than the run (#13508).

        The distinction matters and was wrong in the first draft of this feature:
        an incremental run hash-skips every unchanged file and therefore extracts
        nothing, so per-run counters would overwrite a healthy record with
        ``nodes=0, resolution_rate=0.0``. The stated purpose of these numbers is
        that a resolver regression shows up as a value going *down* — a value that
        drops to zero on every no-op nightly run can never do that.

        So the graph totals are read back from the collection, which is the graph,
        and the run's own outcome is recorded beside them under ``last_run_*``.
        """
        totals = await self._count_graph_records()
        if totals is None:
            return None
        nodes, edges, resolved = totals
        return GraphProvenance(
            root_dir=str(Path(root_dir).resolve()),
            indexed_at_commit=await asyncio.to_thread(_git_head_commit, root_dir),
            indexed_at=datetime.now(timezone.utc).isoformat(),
            extractor_version=EXTRACTOR_VERSION,
            files_with_extractor=aggregate.files_with_extractor,
            files_total=aggregate.files_total,
            nodes=nodes,
            edges=edges,
            resolved_edges=resolved,
            unresolved_edges=edges - resolved,
            last_run_nodes_stored=aggregate.success,
            last_run_failures=aggregate.failed,
        )

    async def _count_graph_records(self) -> "tuple[int, int, int] | None":
        """Return ``(nodes, edges, resolved_edges)`` held in the collection, or None.

        None means the store could not be counted, and the caller then writes no
        record at all — leaving the previous one in place rather than replacing it
        with numbers this run could not verify.
        """
        try:
            node_ids = await asyncio.to_thread(self._collection.get, where={"record_type": {"$eq": "node"}}, include=[])
            edge_records = await asyncio.to_thread(
                self._collection.get, where={"record_type": {"$eq": "edge"}}, include=["metadatas"]
            )
        except Exception as exc:
            logger.warning("code_indexer: could not count graph records: %s (#13508)", exc)
            return None
        edge_metadatas = (edge_records or {}).get("metadatas") or []
        resolved = sum(1 for m in edge_metadatas if isinstance(m, dict) and str(m.get("resolved")).lower() == "true")
        return len((node_ids or {}).get("ids") or []), len(edge_metadatas), resolved

    @staticmethod
    async def _collect_source_files(root_dir: str) -> "tuple[list[Path], list[Path]]":
        """Return ``(indexable, unsupported)`` files under *root_dir*.

        *unsupported* are files the canonical registry classifies as code but for
        which this indexer has no extractor (#13510). They are returned rather than
        discarded so the caller can count them: dropping them here is what let the
        indexer report full coverage of a corpus it had never fully seen.
        """
        root = Path(root_dir)
        skip_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", ".mypy_cache"}

        def _walk() -> "tuple[list[Path], list[Path]]":
            found: list[Path] = []
            unsupported: list[Path] = []
            for path in sorted(root.rglob("*")):
                # #13510: match against the path *below* root. Testing `path.parts`
                # tested the absolute path, so any component above root — a checkout
                # under `.worktrees/`, a home directory, a `.cache` — matched the
                # hidden-directory rule and the walk silently collected nothing.
                relative_parts = path.relative_to(root).parts
                if path.is_dir() or any(part.startswith(".") or part in skip_dirs for part in relative_parts):
                    continue
                suffix = path.suffix.lower()
                if suffix in _EXTRACTORS:
                    found.append(path)
                elif suffix in UNSUPPORTED_CODE_EXTENSIONS:
                    unsupported.append(path)
            return found, unsupported

        return await asyncio.to_thread(_walk)

    async def _ensure_known_ids(self) -> None:
        """Seed ``self._known_ids`` once, lazily, for standalone index_file() callers.

        index_directory() seeds eagerly (and refreshes) at the top of its own
        run; this only fires the first time a CodeIndexer is used via
        index_file() directly (as the tests do).
        """
        if self._known_ids is None:
            self._known_ids = await self._seed_known_ids_from_collection()

    async def _seed_known_ids_from_collection(self) -> set[str]:
        """Return the set of node ids already upserted into the collection (#13469).

        The where-clause only scopes to this indexer's own records
        (``source == "autobot_code"``, shared with edge documents and with
        pre-#13469 node records); the client-side filter on ``node_kind``
        (present only on node records, never on edge ones) is what actually
        separates the two, so this seeds correctly whether or not a given
        record carries the new ``record_type`` field — required for
        cross-run backward compatibility with collections indexed before
        this PR.
        """
        try:
            existing = await asyncio.to_thread(
                self._collection.get,
                where={"source": "autobot_code"},
                include=["metadatas"],
            )
            ids = existing.get("ids") or []
            metadatas = existing.get("metadatas") or []
            return {nid for nid, meta in zip(ids, metadatas) if meta and meta.get("node_kind")}
        except Exception as e:
            logger.warning("Could not seed known code-graph node ids from collection: %s", e)
            return set()

    async def _index_extraction(self, rel_path: str, extracted: dict, result: CodeIndexResult) -> None:
        """Register nodes, upsert them, resolve their outgoing edges, upsert those too."""
        nodes = extracted["nodes"]
        self._known_ids.update(n["id"] for n in nodes)

        node_embeddings: dict[str, list[float]] = {}
        for node in nodes:
            embedding = await self._upsert_node(node, rel_path)
            if embedding is not None:
                result.success += 1
                node_embeddings[node["id"]] = embedding
            else:
                result.failed += 1

        result.nodes += len(nodes)

        resolved_by_source = self._resolve_edges(extracted["edges"])
        # #13508: count what resolution achieved while the outcome is in hand.
        for calls in resolved_by_source.values():
            for _edge, resolved in calls:
                result.edges += 1
                if resolved.resolved:
                    result.resolved_edges += 1
                else:
                    result.unresolved_edges += 1
        if not await self._upsert_edges(resolved_by_source, rel_path, node_embeddings):
            result.errors.append(f"{rel_path}: failed to upsert call edges")

    def _resolve_edges(self, edges: list[dict]) -> dict[str, list[tuple[dict, ResolvedCall]]]:
        """Resolve every raw edge's target_name to a node id with honest provenance (#13469, #13482 Q2)."""
        resolved_by_source: dict[str, list[tuple[dict, ResolvedCall]]] = {}
        for edge in edges:
            resolved = resolve_call(edge["target_name"], edge["module_path"], edge["current_class"], self._known_ids)
            resolved_by_source.setdefault(edge["source"], []).append((edge, resolved))
        return resolved_by_source

    async def _upsert_node(self, node: dict, rel_path: str) -> list[float] | None:
        """Upsert one function/class node. Returns its embedding on success (reused
        for that node's outgoing edge documents to avoid extra model calls),
        None on failure."""
        content = _node_document(node, rel_path)
        metadata: dict[str, Any] = {
            "source": "autobot_code",
            "record_type": "node",
            "node_kind": node["kind"],
            "node_name": node["name"],
            "source_path": rel_path,
            "line": str(node.get("line", 0)),
            "parent": node.get("parent") or "",
            "origin": "extracted",
        }
        try:
            embedding = await asyncio.to_thread(self._embed_model.get_text_embedding, content)
            await asyncio.to_thread(
                self._collection.upsert,
                ids=[node["id"]],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata],
            )
            return embedding
        except Exception as e:
            logger.error("Failed to upsert node %s: %s", node["id"], e)
            return None

    async def _upsert_edges(
        self,
        resolved_by_source: dict[str, list[tuple[dict, ResolvedCall]]],
        rel_path: str,
        node_embeddings: dict[str, list[float]],
    ) -> bool:
        """Upsert resolved call edges as their own documents (#13469)."""
        ids, embeddings, documents, metadatas = _build_edge_batch(resolved_by_source, rel_path, node_embeddings)
        if not ids:
            return True
        try:
            await asyncio.to_thread(
                self._collection.upsert, ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
            )
            return True
        except Exception as e:
            logger.error("Failed to upsert %d call edges for %s: %s", len(ids), rel_path, e)
            return False

    @staticmethod
    def _compute_hash(file_path: str) -> str:
        try:
            return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
        except OSError:
            return ""

    def _load_cache(self) -> dict[str, str]:
        """Load the per-file content-hash cache, discarding it on a version bump.

        #13508: a content hash answers "did this file change", never "did the
        thing that reads it change". Without this gate, bumping
        ``EXTRACTOR_VERSION`` would leave every unchanged file skipped and the
        graph permanently built by the old extractor.
        """
        if not self._cache_file.exists():
            return {}
        try:
            cached = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(cached, dict):
            return {}
        written_by = cached.pop(_CACHE_VERSION_KEY, None)
        if written_by != EXTRACTOR_VERSION:
            logger.info(
                "code_indexer: hash cache was written by extractor version %s, now %s — "
                "re-extracting every file (#13508)",
                written_by,
                EXTRACTOR_VERSION,
            )
            return {}
        return cached

    def _save_cache(self) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {**self._hash_cache, _CACHE_VERSION_KEY: EXTRACTOR_VERSION}
            self._cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("Could not save code index cache: %s", e)


def _git(root_dir: str, *args: str) -> str:
    """Run a read-only git command in *root_dir*; empty string on any failure.

    #13508: provenance must degrade to "unknown" rather than raise. A checkout
    without git, a detached worktree, or a missing binary all mean the same thing
    to a consumer — the commit could not be determined — and none of them should
    fail an index run that otherwise succeeded.
    """
    try:
        completed = (
            subprocess.run(  # nosec B603 B607  # fixed argv, shell=False, no user-supplied option can be injected
                ["git", "-C", root_dir, *args],
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
                check=False,
            )
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("code_indexer: git %s failed in %s: %s", args, root_dir, exc)
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _git_head_commit(root_dir: str) -> str:
    """Full SHA of *root_dir*'s HEAD, or "" when it cannot be determined."""
    return _git(root_dir, "rev-parse", "HEAD")


_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


async def load_graph_provenance(collection: Any) -> "GraphProvenance | None":
    """Return how the graph in *collection* was built, or ``None`` if unknown.

    ``None`` covers every uncertain case — no record, an unreadable store, a
    record this build cannot parse. A collection indexed before #13508 has no
    record and therefore reads as unknown, never as fresh, which is the
    constraint the issue is explicit about.

    Async because the read is blocking store I/O; the first caller on an event
    loop would otherwise stall it.
    """
    try:
        found = await asyncio.to_thread(collection.get, ids=[_PROVENANCE_ID], include=["metadatas"])
    except Exception as exc:
        logger.warning("code_indexer: could not read graph provenance: %s", exc)
        return None
    metadatas = (found or {}).get("metadatas") or []
    if not metadatas or not isinstance(metadatas[0], dict):
        return None
    known = {f.name for f in dataclass_fields(GraphProvenance)}
    payload = {k: v for k, v in metadatas[0].items() if k in known}
    try:
        return GraphProvenance(**payload)
    except TypeError as exc:
        logger.warning("code_indexer: graph provenance record is not readable: %s", exc)
        return None


async def graph_commits_behind(collection: Any, root_dir: str) -> "int | None":
    """How many commits *root_dir*'s HEAD is ahead of the indexed commit.

    ``None`` means unanswerable, and it is deliberately returned in more cases
    than "no record":

    - the graph was built by a **different extractor version**, so a commit
      distance of 0 would read as "current" for a graph this build cannot trust;
    - the record describes a **different tree** than the one being asked about;
    - the recorded commit is **not in this history** — after a rebase or a
      force-push it is gone, and ``0`` would be the worst possible answer, since
      it reads as current for a graph built on a commit that no longer exists.

    ``0`` therefore means current, and only that. Answered without re-walking the
    repo: one ``rev-list --count``.
    """
    provenance = await load_graph_provenance(collection)
    if provenance is None or not provenance.indexed_at_commit:
        return None
    if not provenance.is_current_extractor:
        logger.info(
            "code_indexer: graph was built by extractor version %s, running %s — staleness unanswerable (#13508)",
            provenance.extractor_version,
            EXTRACTOR_VERSION,
        )
        return None
    if provenance.root_dir and provenance.root_dir != str(Path(root_dir).resolve()):
        return None
    # Validated before reaching a subprocess: this value came back out of the
    # store, and a commit id is the one untrusted string in this path.
    if not _SHA_RE.match(provenance.indexed_at_commit):
        return None
    counted = await asyncio.to_thread(_git, root_dir, "rev-list", "--count", f"{provenance.indexed_at_commit}..HEAD")
    if not counted.isdigit():
        return None
    return int(counted)


def _node_document(node: dict, rel_path: str) -> str:
    """The text embedded for one node record.

    Shared with the #13509 refresh path so the two can never drift: that path
    rewrites this string when a line moves *without* re-embedding, which is only
    sound while both sides format it identically.
    """
    return f"{node['kind'].upper()} {node['name']}\n" f"File: {rel_path} line {node.get('line', 0)}"


def _build_edge_batch(
    resolved_by_source: dict[str, list[tuple[dict, ResolvedCall]]],
    rel_path: str,
    node_embeddings: dict[str, list[float]],
) -> tuple[list[str], list[list[float]], list[str], list[dict]]:
    """Flatten resolved edges into ChromaDB upsert-shaped parallel lists.

    Edge documents are never semantically searched, so each reuses its
    source node's already-computed embedding instead of paying for another
    embedding-model call (#13469).
    """
    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    for source_id, calls in resolved_by_source.items():
        fallback_embedding = node_embeddings.get(source_id)
        if fallback_embedding is None:
            continue  # source node's own upsert failed; nothing to embed the edge with
        for edge, resolved in calls:
            ids.append(f"edge::{source_id}::{edge['target_name']}")
            embeddings.append(fallback_embedding)
            documents.append(f"CALLS {edge['target_name']}")
            metadatas.append(_build_edge_metadata(source_id, edge, resolved, rel_path))
    return ids, embeddings, documents, metadatas


def _build_edge_metadata(source_id: str, edge: dict, resolved: ResolvedCall, rel_path: str) -> dict[str, Any]:
    """Build the metadata for one persisted call-edge document (#13469).

    ``target_id`` is "" (not None — ChromaDB metadata values must be scalar)
    when unresolved; ``resolved``/``candidate_count`` give callers a coverage
    count instead of the invented confidence score #13482 Q2 rejected.
    """
    return {
        "source": "autobot_code",
        "record_type": "edge",
        "kind": edge["kind"],
        "source_id": source_id,
        "target_id": resolved.target_id or "",
        "target_name": edge["target_name"],
        "origin": resolved.origin,
        "resolved": resolved.resolved,
        "candidate_count": resolved.candidate_count,
        "source_path": rel_path,
        # #13471: call-site line within source_path, consumed by impact analysis
        # to report "where do I click" instead of the callee's definition line.
        "call_line": edge.get("line", 0),
    }


async def find_callers(collection: Any, target_id: str) -> list[dict[str, Any]]:
    """Return every persisted "calls" edge whose target resolved to *target_id* (#13469).

    The first real consumer of the persisted edge documents: an exact
    metadata lookup, not a scan of the (now-removed) CSV ``calls`` string
    nothing could parse. ``source_id`` on each returned edge is a node id
    from the same collection, so callers can chain this to walk the graph.
    """
    result = await asyncio.to_thread(
        collection.get,
        where={
            "$and": [
                {"record_type": {"$eq": "edge"}},
                {"target_id": {"$eq": target_id}},
            ]
        },
        include=["metadatas"],
    )
    return list(result.get("metadatas") or [])
