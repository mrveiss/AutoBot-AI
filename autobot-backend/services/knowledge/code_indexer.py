# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AST-based code indexer using tree-sitter (#4820).

Two-pass extraction per source file:
  Pass 1 (structural): walk AST for function/class declarations → nodes.
  Pass 2 (call-graph): walk function bodies for call expressions → edges.

Results are embedded and upserted into ChromaDB following the same
SHA-256 content-hash cache + upsert pattern as DocIndexer.

Supported languages: Python, JavaScript/TypeScript.
"""

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def _make_node_id(name: str, source_path: str, parent: str | None = None) -> str:
    """Stable lowercase ID: '<stem>::<safe_name>' or '<stem>::<parent_safe>__<safe_name>'."""
    stem = Path(source_path).stem
    safe = re.sub(r"[^a-z0-9_]", "", name.lower().replace(".", "_"))
    if parent:
        parent_safe = re.sub(r"[^a-z0-9_]", "", parent.split("::")[-1].lower())
        return f"{stem}::{parent_safe}__{safe}"
    return f"{stem}::{safe}"


def extract_python(source_path: str, content: bytes) -> dict:
    """Two-pass tree-sitter extraction for Python.

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

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    _py_structural(tree.root_node, source_path, nodes, parent_scope=None)
    _py_call_graph(tree.root_node, source_path, nodes, edges, seen_edges, current_scope=None)

    return {"nodes": list(nodes.values()), "edges": edges}


def _py_structural(node: Any, source_path: str, nodes: dict, parent_scope: str | None) -> None:
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8")
            nid = _make_node_id(name, source_path, parent=parent_scope)
            nodes[nid] = {
                "id": nid,
                "name": name,
                "kind": "function",
                "source_path": source_path,
                "line": node.start_point[0] + 1,
                "parent": parent_scope,
            }
            for child in node.children:
                _py_structural(child, source_path, nodes, parent_scope=nid)
            return

    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8")
            nid = _make_node_id(name, source_path, parent=parent_scope)
            nodes[nid] = {
                "id": nid,
                "name": name,
                "kind": "class",
                "source_path": source_path,
                "line": node.start_point[0] + 1,
                "parent": parent_scope,
            }
            for child in node.children:
                _py_structural(child, source_path, nodes, parent_scope=nid)
            return

    for child in node.children:
        _py_structural(child, source_path, nodes, parent_scope)


def _py_call_graph(
    node: Any,
    source_path: str,
    nodes: dict,
    edges: list,
    seen: set,
    current_scope: str | None,
    parent_scope: str | None = None,
) -> None:
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        scope = (
            _make_node_id(name_node.text.decode("utf-8"), source_path, parent=current_scope)
            if name_node
            else current_scope
        )
        for child in node.children:
            _py_call_graph(child, source_path, nodes, edges, seen, scope, parent_scope=current_scope)
        return

    if node.type == "call" and current_scope:
        func_node = node.child_by_field_name("function")
        if func_node:
            raw = func_node.text.decode("utf-8").split("(")[0]
            target_name = raw.split(".")[-1]
            pair = (current_scope, target_name)
            if pair not in seen:
                seen.add(pair)
                edges.append(
                    {
                        "source": current_scope,
                        "target_name": target_name,
                        "kind": "calls",
                        "source_path": source_path,
                        "origin": "extracted",
                    }
                )

    for child in node.children:
        _py_call_graph(child, source_path, nodes, edges, seen, current_scope)


def _js_structural(node: Any, source_path: str, nodes: dict, parent_scope: str | None) -> None:
    """Helper for JS/TS structural extraction."""
    if node.type in ("function_declaration", "arrow_function", "function_expression"):
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode("utf-8") if name_node else f"anon_{node.start_point[0]}"
        nid = _make_node_id(name, source_path, parent=parent_scope)
        nodes[nid] = {
            "id": nid,
            "name": name,
            "kind": "function",
            "source_path": source_path,
            "line": node.start_point[0] + 1,
            "parent": parent_scope,
        }
        for child in node.children:
            _js_structural(child, source_path, nodes, parent_scope=nid)
        return
    if node.type == "class_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8")
            nid = _make_node_id(name, source_path, parent=parent_scope)
            nodes[nid] = {
                "id": nid,
                "name": name,
                "kind": "class",
                "source_path": source_path,
                "line": node.start_point[0] + 1,
                "parent": parent_scope,
            }
    for child in node.children:
        _js_structural(child, source_path, nodes, parent_scope)


def _js_call_graph(
    node: Any,
    source_path: str,
    nodes: dict,
    edges: list,
    seen: set,
    current_scope: str | None,
    parent_scope: str | None = None,
) -> None:
    """Helper for JS/TS call-graph extraction."""
    if node.type in ("function_declaration", "arrow_function", "function_expression"):
        name_node = node.child_by_field_name("name")
        scope = (
            _make_node_id(name_node.text.decode("utf-8"), source_path, parent=current_scope)
            if name_node
            else current_scope
        )
        for child in node.children:
            _js_call_graph(child, source_path, nodes, edges, seen, scope, parent_scope=current_scope)
        return
    if node.type == "call_expression" and current_scope:
        func_node = node.child_by_field_name("function")
        if func_node:
            raw = func_node.text.decode("utf-8").split("(")[0]
            target_name = raw.split(".")[-1]
            pair = (current_scope, target_name)
            if pair not in seen:
                seen.add(pair)
                edges.append(
                    {
                        "source": current_scope,
                        "target_name": target_name,
                        "kind": "calls",
                        "source_path": source_path,
                        "origin": "extracted",
                    }
                )
    for child in node.children:
        _js_call_graph(child, source_path, nodes, edges, seen, current_scope)


def extract_javascript(source_path: str, content: bytes) -> dict:
    """Two-pass extraction for JavaScript/TypeScript."""
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser
    except ImportError as exc:
        logger.error("tree-sitter-javascript not installed — AST indexing disabled: %s", exc)
        return {"nodes": [], "edges": [], "dep_error": str(exc)}

    lang = Language(tsjs.language())
    parser = Parser(lang)
    tree = parser.parse(content)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()
    _js_structural(tree.root_node, source_path, nodes, parent_scope=None)
    _js_call_graph(tree.root_node, source_path, nodes, edges, seen_edges, current_scope=None)
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
    Each function/class node becomes one ChromaDB document.
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

    async def index_file(
        self,
        file_path: str,
        root_dir: str,
        force: bool = False,
    ) -> CodeIndexResult:
        """Extract AST nodes from file_path and upsert into ChromaDB."""
        result = CodeIndexResult()
        ext = Path(file_path).suffix.lower()
        extractor = _EXTRACTORS.get(ext)
        if extractor is None:
            result.skipped += 1
            return result

        rel_path = str(Path(file_path).relative_to(root_dir))
        if not force:
            current_hash = self._compute_hash(file_path)
            if current_hash and self._hash_cache.get(rel_path) == current_hash:
                result.skipped += 1
                return result

        try:
            # #7467: was sync `Path(file_path).read_bytes()` blocking the event loop
            # during code indexing of potentially-large source files.
            content = await asyncio.to_thread(Path(file_path).read_bytes)
        except OSError as e:
            result.failed += 1
            result.errors.append(str(e))
            return result

        extracted = extractor(file_path, content)
        if extracted.get("dep_error"):
            result.failed += 1
            result.errors.append(f"{rel_path}: missing dependency — {extracted['dep_error']}")
            return result
        nodes = extracted["nodes"]
        edges = extracted["edges"]

        calls_by_source: dict[str, list[str]] = {}
        for e in edges:
            calls_by_source.setdefault(e["source"], []).append(e["target_name"])

        for node in nodes:
            ok = await self._upsert_node(node, rel_path, calls_by_source)
            if ok:
                result.success += 1
            else:
                result.failed += 1

        new_hash = self._compute_hash(file_path)
        if new_hash:
            self._hash_cache[rel_path] = new_hash
            self._save_cache()

        return result

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
            # Reload cache inside the lock so we start from the freshest snapshot
            # before this batch begins.
            self._hash_cache = self._load_cache()

            aggregate = CodeIndexResult()
            root = Path(root_dir)
            _SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", ".mypy_cache"}
            files = await asyncio.to_thread(lambda: sorted(root.rglob("*")))
            for path in files:
                if path.is_dir():
                    continue
                # Skip files inside ignored directories
                if any(part.startswith(".") or part in _SKIP_DIRS for part in path.parts):
                    continue
                if path.suffix.lower() not in _EXTRACTORS:
                    continue
                result = await self.index_file(str(path), root_dir=root_dir, force=force)
                aggregate.success += result.success
                aggregate.failed += result.failed
                aggregate.skipped += result.skipped
                aggregate.errors.extend(result.errors)
            return aggregate

    async def _upsert_node(self, node: dict, rel_path: str, calls_by_source: dict[str, list[str]]) -> bool:
        content = f"{node['kind'].upper()} {node['name']}\n" f"File: {rel_path} line {node.get('line', 0)}"
        metadata: dict[str, Any] = {
            "source": "autobot_code",
            "node_kind": node["kind"],
            "node_name": node["name"],
            "source_path": rel_path,
            "line": str(node.get("line", 0)),
            "parent": node.get("parent") or "",
            "calls": ",".join(calls_by_source.get(node["id"], [])),
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
            return True
        except Exception as e:
            logger.error("Failed to upsert node %s: %s", node["id"], e)
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
