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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autobot_shared.code_graph import ResolvedCall, compute_node_id, module_path_from_rel_path, resolve_call
from autobot_shared.logging_manager import get_logger
from constants.path_constants import PATH

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


_EXTRACTORS: dict[str, Any] = {
    ".py": extract_python,
    ".js": extract_javascript,
    ".ts": extract_javascript,
    ".jsx": extract_javascript,
    ".tsx": extract_javascript,
    ".vue": extract_javascript,
}


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
        await self._index_extraction(rel_path, extracted, result)
        self._update_hash_cache(file_path, rel_path)
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
        return extracted

    def _update_hash_cache(self, file_path: str, rel_path: str) -> None:
        new_hash = self._compute_hash(file_path)
        if new_hash:
            self._hash_cache[rel_path] = new_hash
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
            for path in await self._collect_source_files(root_dir):
                result = await self.index_file(str(path), root_dir=root_dir, force=force)
                aggregate.success += result.success
                aggregate.failed += result.failed
                aggregate.skipped += result.skipped
                aggregate.errors.extend(result.errors)
            return aggregate

    @staticmethod
    async def _collect_source_files(root_dir: str) -> list[Path]:
        """List indexable files under *root_dir*, skipping hidden/vendor dirs."""
        root = Path(root_dir)
        skip_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", ".mypy_cache"}

        def _walk() -> list[Path]:
            found = []
            for path in sorted(root.rglob("*")):
                if path.is_dir() or any(part.startswith(".") or part in skip_dirs for part in path.parts):
                    continue
                if path.suffix.lower() in _EXTRACTORS:
                    found.append(path)
            return found

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

        resolved_by_source = self._resolve_edges(extracted["edges"])
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
        content = f"{node['kind'].upper()} {node['name']}\n" f"File: {rel_path} line {node.get('line', 0)}"
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
        if self._cache_file.exists():
            try:
                return json.loads(self._cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_cache(self) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps(self._hash_cache, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("Could not save code index cache: %s", e)


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
