# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical callee resolver (#13470).

Extracted from ``api/codebase_analytics/endpoints/call_graph.py`` (#713),
which was the more complete of the two call-graph resolvers that existed
before this module: import-aware, and able to tell an external-library call
apart from one that genuinely does not resolve. ``call_graph.py`` now imports
from here instead of keeping its own copy (see that module's ``_resolve_callee_id``
and ``_resolve_via_import_context``, kept as thin wrappers for backward
compatibility with existing importers/tests).

``services/knowledge/code_indexer.py`` (#13469) is the second caller and the
reason this needed to stop being private to one endpoint module. Its
tree-sitter extraction does not build an import context (that remains future
work — see the PR description for #13469), so it only ever exercises the
direct-construction and suffix-scan paths below, never the import-context one.

Provenance (#13482 Q2 — three tiers, no confidence score):
  - "extracted": the target was found by direct construction — the same
    module or the current class — which needs no heuristics, it is either a
    fact about the source file or it isn't.
  - "inferred":  no direct construction matched, but exactly one candidate
    elsewhere in the project has a matching trailing name. Includes the
    zero-candidate case (call exists, nothing matches it — we did not read a
    resolution from the source either way).
  - "ambiguous": the trailing-name scan found two or more candidates and
    picking one would be a guess presented as fact.
"""

from dataclasses import dataclass
from typing import Collection

# Standard library modules (used by multiple endpoints/callers).
STDLIB_MODULES = {
    "os",
    "sys",
    "re",
    "json",
    "time",
    "datetime",
    "logging",
    "asyncio",
    "pathlib",
    "typing",
    "collections",
    "functools",
    "itertools",
    "subprocess",
    "threading",
    "multiprocessing",
    "uuid",
    "hashlib",
    "base64",
    "io",
    "contextlib",
    "abc",
    "dataclasses",
    "enum",
    "copy",
    "math",
    "random",
    "socket",
    "http",
    "urllib",
    "traceback",
    "inspect",
    "ast",
    "shutil",
    "tempfile",
    "warnings",
    "signal",
    "argparse",
    "pickle",
    "csv",
    "sqlite3",
    "email",
    "html",
    "xml",
    "struct",
    "array",
    "queue",
    "heapq",
    "bisect",
    "weakref",
    "types",
    "operator",
    "string",
    "textwrap",
    "codecs",
}

# Common third-party packages to exclude from resolution (#713).
COMMON_THIRD_PARTY = {
    "fastapi",
    "pydantic",
    "redis",
    "aiofiles",
    "aiohttp",
    "requests",
    "numpy",
    "pandas",
    "sqlalchemy",
    "alembic",
    "pytest",
    "httpx",
    "celery",
    "chromadb",
    "openai",
    "anthropic",
    "langchain",
    "torch",
    "transformers",
    "PIL",
    "cv2",
    "sklearn",
    "scipy",
    "matplotlib",
    "websockets",
    "uvicorn",
    "starlette",
    "jinja2",
    "click",
    "rich",
    "yaml",
    "toml",
    "dotenv",
    "paramiko",
    "fabric",
    "boto3",
    "google",
    "azure",
    "docker",
    "kubernetes",
    "jwt",
    "cryptography",
    "bcrypt",
}

# O(1) lookup for internal module top-level packages (#326).
INTERNAL_MODULE_PREFIXES = {
    "a2a",
    "agents",
    "api",
    "autobot",
    "autobot_shared",
    "backend",
    "cache",
    "chat_workflow",
    "config",
    "constants",
    "database",
    "extensions",
    "initialization",
    "knowledge",
    "models",
    "orchestration",
    "routers",
    "security",
    "services",
    "src",
    "utils",
}


def is_external_module(module_name: str) -> bool:
    """True when *module_name* is stdlib or a known third-party package.

    Unknown top-level packages are assumed external unless they match a
    known internal prefix (#713).
    """
    base = module_name.split(".")[0]
    if base in STDLIB_MODULES or base in COMMON_THIRD_PARTY:
        return True
    if base in INTERNAL_MODULE_PREFIXES:
        return False
    return True


class ImportContext:
    """Tracks import statements for one source file for cross-module resolution.

    Extracted from ``call_graph.py`` (#713); behaviour unchanged.
    """

    def __init__(self) -> None:
        self.name_to_module: dict[str, str] = {}
        self.module_to_names: dict[str, list[str]] = {}
        self.aliases: dict[str, str] = {}

    def add_import(self, module: str, name: str | None = None, alias: str | None = None) -> None:
        """Register one import statement (``import x`` or ``from x import y``)."""
        if name:
            effective_name = alias if alias else name
            self.name_to_module[effective_name] = f"{module}.{name}"
            if alias:
                self.aliases[alias] = name
        else:
            effective_name = alias if alias else module.split(".")[-1]
            self.name_to_module[effective_name] = module
            if alias:
                self.aliases[alias] = module

        self.module_to_names.setdefault(module, [])
        if name and name not in self.module_to_names[module]:
            self.module_to_names[module].append(name)

    def resolve_name(self, name: str) -> str | None:
        """Return the full module path a called *name* was imported from, if any."""
        return self.name_to_module.get(name)

    def is_external(self, name: str) -> bool:
        """True when *name* was imported from stdlib or a third-party package.

        Deliberately narrower than :func:`is_external_module` — it only ever
        checks the two explicit sets, never falling back to "assume
        external" for an unrecognised top-level package, because an unknown
        import here is far more likely to be an unindexed project module
        than a genuinely external one. Preserved as-is from ``call_graph.py``
        (#713); behaviour unchanged by the #13470 extraction.
        """
        module_path = self.name_to_module.get(name)
        if not module_path:
            return False
        base_module = module_path.split(".")[0]
        return base_module in STDLIB_MODULES or base_module in COMMON_THIRD_PARTY


def _resolve_via_import_context(
    callee_name: str,
    import_context: ImportContext,
    known_ids: Collection[str],
) -> tuple[str | None, bool]:
    """Resolve *callee_name* using the file's own import statements.

    Returns ``(resolved_id, is_external)``; ``is_external=True`` means the
    call was to an imported stdlib/third-party name, which is a known
    non-resolution rather than an unresolved one.
    """
    imported_path = import_context.resolve_name(callee_name)
    if not imported_path:
        return None, False
    if import_context.is_external(callee_name):
        return None, True
    if imported_path in known_ids:
        return imported_path, False
    parts = imported_path.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i]) + "." + parts[-1]
        if candidate in known_ids:
            return candidate, False
    return None, False


def resolve_callee(
    callee_name: str,
    module_path: str,
    current_class: str | None,
    known_ids: Collection[str],
    import_context: ImportContext | None = None,
) -> tuple[str | None, bool]:
    """Resolve a callee name to a node id via direct construction or imports.

    Deterministic — either the module-local/class-local candidate id is a
    member of *known_ids*, or the import context names an already-known id.
    Never guesses between multiple candidates; that is :func:`resolve_callee_by_suffix`'s
    job. Returns ``(resolved_id, is_external)``.
    """
    possible_id = f"{module_path}.{callee_name}"
    if possible_id in known_ids:
        return possible_id, False
    if current_class:
        possible_id = f"{module_path}.{current_class}.{callee_name}"
        if possible_id in known_ids:
            return possible_id, False
    if import_context:
        result = _resolve_via_import_context(callee_name, import_context, known_ids)
        if result[0] or result[1]:
            return result
    return None, False


def resolve_callee_by_suffix(callee_name: str, known_ids: Collection[str]) -> tuple[str | None, int]:
    """Heuristic fallback when direct construction finds nothing.

    Scans *known_ids* for any id whose trailing dotted component equals
    *callee_name* — the only option when no import context is available to
    confirm which module a name came from (code_indexer's tree-sitter
    extraction does not parse imports yet).

    Returns ``(resolved_id, candidate_count)``:
      - 0 candidates: ``(None, 0)`` — nothing matches.
      - 1 candidate:  ``(that_id, 1)`` — resolved.
      - 2+ candidates: ``(None, count)`` — ambiguous, caller must not guess.
    """
    matches = [nid for nid in known_ids if nid.rsplit(".", 1)[-1] == callee_name]
    if len(matches) == 1:
        return matches[0], 1
    return None, len(matches)


@dataclass(frozen=True)
class ResolvedCall:
    """Outcome of resolving one call edge, with honest provenance (#13482 Q2)."""

    target_id: str | None
    origin: str  # "extracted" | "inferred" | "ambiguous"
    candidate_count: int

    @property
    def resolved(self) -> bool:
        return self.target_id is not None


def resolve_call(
    callee_name: str,
    module_path: str,
    current_class: str | None,
    known_ids: Collection[str],
    import_context: ImportContext | None = None,
) -> ResolvedCall:
    """Resolve one call edge end-to-end, mapping the result onto the three
    provenance tiers instead of leaving the caller to decide.

    External calls (resolved via ``import_context`` to a stdlib/third-party
    name) resolve to no target id and are tagged "inferred" — a call exists,
    but there is no project node it can point at.
    """
    direct_id, is_external = resolve_callee(callee_name, module_path, current_class, known_ids, import_context)
    if direct_id:
        return ResolvedCall(target_id=direct_id, origin="extracted", candidate_count=1)
    if is_external:
        return ResolvedCall(target_id=None, origin="inferred", candidate_count=0)
    suffix_id, count = resolve_callee_by_suffix(callee_name, known_ids)
    if count == 1:
        return ResolvedCall(target_id=suffix_id, origin="inferred", candidate_count=1)
    if count >= 2:
        return ResolvedCall(target_id=None, origin="ambiguous", candidate_count=count)
    return ResolvedCall(target_id=None, origin="inferred", candidate_count=0)
