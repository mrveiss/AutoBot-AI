# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Signature-scoped fingerprint for cache invalidation (#13509).

`CodeIndexer` invalidates on a whole-file content hash, so a reformat, a
copyright-header touch or a docstring typo re-embeds every node in the file.
Our own PostToolUse hook auto-formats every `.py` we write, which makes that
churn routine rather than rare.

None of the three existing hashers answers this, and each is wrong in an
instructive way:

- ``ASTHasher.hash_structural`` recurses through every child, so the **body is
  included** — correct for Type-1 clone detection, useless for invalidation
- ``ASTHasher.hash_normalized`` replaces identifiers with placeholders — Type-2
  detection, deliberately blind to the names the graph is keyed on
- ``SemanticHasher.hash_semantic`` is designed to be *equal* for
  functionally-equivalent-but-different code — the opposite property

What is needed is a hash that is **stable under body edits and changes when the
interface changes**. That is this module. It lives beside its siblings rather
than as a fourth hasher inside `code_indexer` (Rule 2), and reuses
``ASTHasher._args_to_structure`` for parameter normalisation instead of
re-implementing AST traversal.

**Fail open.** Every error path returns ``None``, and the caller must treat
``None`` as "re-analyse", never as "unchanged". Serving a stale graph is worse
than re-embedding a file — see ``signature_matches``.
"""

import ast
import hashlib
from typing import Any, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from code_intelligence.fingerprinting.ast_hasher import ASTHasher

logger = get_logger(__name__)

#: Bumping this invalidates every stored fingerprint. Raise it whenever the
#: extractor or the definition below changes, otherwise a stored hash computed
#: under the old rules is silently compared against a new one (#13509).
SIGNATURE_FINGERPRINT_VERSION = 1


def _decorator_name(node: ast.AST) -> str:
    """Best-effort dotted name for a decorator expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return type(node).__name__


def _annotation(node: Optional[ast.AST]) -> str:
    """Source-ish text for an annotation; '' when absent."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def _function_signature(node: ast.AST, hasher: ASTHasher) -> Tuple:
    """Everything about a function except what it does.

    Deliberately excludes ``node.body`` — that exclusion *is* the feature.
    """
    return (
        "AsyncFunctionDef" if isinstance(node, ast.AsyncFunctionDef) else "FunctionDef",
        node.name,
        hasher._args_to_structure(node.args),
        _annotation(node.returns),
        tuple(_decorator_name(d) for d in node.decorator_list),
    )


def _class_signature(node: ast.ClassDef, hasher: ASTHasher) -> Tuple:
    """Class name, bases, decorators, and its members' signatures.

    Members are included because a method appearing or changing shape alters
    what the graph must hold; their bodies are not, for the same reason a
    function's is not.
    """
    members = tuple(
        _function_signature(m, hasher) for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return (
        "ClassDef",
        node.name,
        tuple(_annotation(b) for b in node.bases),
        tuple(_decorator_name(d) for d in node.decorator_list),
        members,
    )


def _import_signature(node: ast.AST) -> Tuple:
    """Imports are part of the interface: they decide how calls resolve."""
    if isinstance(node, ast.Import):
        return ("Import", tuple(sorted((a.name, a.asname or "") for a in node.names)))
    return (
        "ImportFrom",
        node.module or "",
        node.level,
        tuple(sorted((a.name, a.asname or "") for a in node.names)),
    )


def compute_signature_fingerprint(source: str) -> Optional[str]:
    """Hash a module's interface, ignoring function and method bodies.

    Returns ``None`` on any failure — an unparseable file has no signature, and
    the caller must re-analyse rather than assume it is unchanged.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        logger.debug("Signature fingerprint skipped — unparseable source: %s", exc)
        return None

    try:
        hasher = ASTHasher()
        parts: list = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parts.append(_function_signature(node, hasher))
            elif isinstance(node, ast.ClassDef):
                parts.append(_class_signature(node, hasher))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                parts.append(_import_signature(node))

        payload = repr((SIGNATURE_FINGERPRINT_VERSION, tuple(parts)))
        digest = hashlib.sha256(payload.encode("utf-8"), usedforsecurity=False).hexdigest()
        return f"v{SIGNATURE_FINGERPRINT_VERSION}:{digest}"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Signature fingerprint failed, falling back to re-analysis: %s", exc)
        return None


def signature_matches(stored: Any, current: Any) -> bool:
    """True only when both fingerprints are present, versioned alike, and equal.

    Every other outcome is False, which the caller reads as "re-analyse". The
    asymmetry is deliberate: a false negative costs one re-embed, a false
    positive serves a stale graph indefinitely.
    """
    if not stored or not current:
        return False
    if not isinstance(stored, str) or not isinstance(current, str):
        return False
    prefix = f"v{SIGNATURE_FINGERPRINT_VERSION}:"
    if not stored.startswith(prefix) or not current.startswith(prefix):
        # An unknown or older version is not comparable — re-analyse.
        return False
    return stored == current
