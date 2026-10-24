# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No production module chooses an embedding model by string literal (#18143).

A pipeline with stored vectors embeds in the space its index was built in
(``knowledge/index_embedding_space.py``); a pipeline without one asks
``autobot_shared.embedding_model.active_embedding_model()``. A literal in a third place is a model
choice nothing moves with the other two, so a model change leaves it embedding in a different space.

Every literal that is still allowed is allowed by path, with the reason it is not a choice (or the
class it was left in). The allowlist is checked both ways: a stale entry fails as loudly as a new literal.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.embedding_model import is_embedding_model_id
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

# The two infra collection builders sit outside the package roots, so they are named by file (#18328).
_INFRA_BUILDERS = (
    "autobot-infrastructure/shared/scripts/populate_kb_chromadb.py",
    "autobot-infrastructure/shared/tools/index_documentation.py",
)
_ROOTS = ("autobot-backend", "autobot_shared", *_INFRA_BUILDERS)
_TEST_PART = re.compile(r"(^|/)(tests?|test_[^/]*|[^/]*_test\.py|conftest\.py)(/|$)")
_SPACE_TABLE = "autobot-backend/knowledge/index_embedding_space.py"
_SSOT = "autobot_shared/ssot_config.py"
_PRICING = "not a choice: a pricing/cost table keyed by every model the analytics page may display"
_CATALOGUE = "not a choice: a catalogue/listing shown to the user, nothing embeds with it"
_DIMS = "not a choice: model name -> dimension lookup consulted for whichever model is configured"
_CHUNKER = "local sentence-transformer, owned by the semantic-chunker branch (#14485); no stored-index query"

ALLOWED: dict[str, str] = {
    "autobot_shared/embedding_model.py": "the list: KNOWN_EMBEDDING_MODEL_PREFIXES names the families the matcher itself looks for",
    "autobot_shared/pinned_model_registry.py": "not a choice: a revision/digest pin keyed by repo id for a model the code index already names (CODEBERT_MODEL_NAME)",
    "autobot-backend/code_embedding_generator.py": "index-bound: CODEBERT_MODEL_NAME is the code index's recorded space; index_embedding_space.py:80-85 reads it into CODE_INDEX",
    _SPACE_TABLE: "the table: the one place an index's recorded model is written",
    _SSOT: "ssot default of the active model (DEFAULT_EMBEDDING_MODEL)",
    "autobot-backend/api/analytics_embedding_patterns.py": _PRICING,
    "autobot-backend/api/embeddings.py": _CATALOGUE + " (embedding provider/model listing)",
    "autobot-backend/models/npu_models.py": _CATALOGUE + " (loaded_models status payload)",
    "autobot-backend/services/model_manager_service.py": _CATALOGUE + " (capability table by name prefix)",
    "autobot-backend/services/knowledge/doc_indexer.py": _DIMS
    + " (_KNOWN_DIMS); the model itself comes from org config / ssot"
    + "; the 'or' default is the org-config fallback (follow-up)",
    "autobot-backend/utils/entity_resolver.py": "default of a config key for an in-memory sentence-transformer; it stores and queries no vectors",
    "autobot-backend/utils/semantic_chunker.py": _CHUNKER,
    "autobot-backend/utils/semantic_chunker_base.py": _CHUNKER,
    "autobot-backend/utils/semantic_chunker_gpu.py": _CHUNKER,
}


def _py_files(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, *((r if r.endswith(".py") else f"{r}/*.py") for r in _ROOTS))
    except EmptyEnumeration:
        return []
    return [p for p in paths if not _TEST_PART.search(p)]


REACH_PY = declare(
    "embedding-model-literal-sites",
    discover=_py_files,
    # Mid-window (2454..2754) from REACH_PY.window(): population 2754, growth 300; two infra builders added (#18328).
    floor=2725,  # train 30: re-pinned mid-window (#15928)
    what="production python files, parsed for embedding-model string constants",
    roots=_ROOTS,
    growth=300,
)


def literals_in(source: str) -> list[tuple[int, str]]:
    """(line, value) of every string constant that is a bare embedding-model id; docstrings are skipped."""
    tree = ast.parse(source)
    skip: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            skip.add(id(body[0].value))
    return [
        (n.lineno, n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and id(n) not in skip
        and is_embedding_model_id(n.value)
    ]


def _scan(root: Path) -> dict[str, list[tuple[int, str]]]:
    found: dict[str, list[tuple[int, str]]] = {}
    for rel in REACH_PY.examined(root):
        hits = literals_in((root / rel).read_text(encoding="utf-8", errors="replace"))
        if hits:
            found[rel] = hits
    return found


def test_no_module_outside_the_allowlist_holds_an_embedding_model_literal() -> None:
    found = _scan(repo_root())
    stray = {p: h for p, h in found.items() if p not in ALLOWED}
    assert stray == {}, f"#18143: resolve these from the index-space table or active_embedding_model(): {stray}"


def test_every_allowlist_entry_still_holds_a_literal() -> None:
    found = _scan(repo_root())
    stale = sorted(p for p in ALLOWED if p not in found)
    assert stale == [], f"#18143: allowlist entries with no literal left; remove them: {stale}"


def test_every_allowlist_entry_states_its_reason() -> None:
    assert all(len(reason) > 20 for reason in ALLOWED.values())


@pytest.mark.parametrize(
    "source",
    [
        'MODEL = "nomic-embed-text"',
        'MODEL = "nomic-embed-text:latest"',
        'f(model_name="all-MiniLM-L6-v2")',
        'x = {"bge-small-en-v1.5": 384}',
        'M = "sentence-transformers/all-MiniLM-L6-v2"',
        'M = "BAAI/bge-small-en-v1.5"',
        'M = "microsoft/codebert-base"',
        'M = "intfloat/e5-large-v2"',
        'M = "intfloat/multilingual-e5-base"',
        'M = "e5-small"',
        'M = "thenlper/gte-base"',
        'M = "jinaai/jina-embeddings-v2-base-en"',
    ],
)
def test_a_bare_or_namespaced_model_id_is_found(source: str) -> None:
    assert literals_in(source)


@pytest.mark.parametrize(
    "source",
    [
        'M = "meta-llama/Llama-3.1-8B-Instruct"',
        'M = "mistralai/Mistral-7B-v0.1"',
        'M = "microsoft/phi-3-mini"',
        'M = "BAAI/bge-reranker-v2-m3"',  # a cross-encoder reranker shares the bge- prefix, not the role
        'M = "llama3:8b"',
        'M = "gte"',
        'M = "sentence-transformers/"',
        'M = "BAAI/bge-small en"',
    ],
)
def test_a_chat_model_or_malformed_id_is_not_an_embedding_model(source: str) -> None:
    assert literals_in(source) == []


@pytest.mark.parametrize(
    "source",
    [
        '"""Uses nomic-embed-text for embeddings."""\nx = 1',
        "x = 'nomic-embed-text is the default model'",
        "# MODEL = 'nomic-embed-text'\nx = 1",
        "x = 'text-embedding models need a prefix'",
        'def f():\n    """all-MiniLM-L6-v2"""\n    return 1',
    ],
)
def test_prose_comments_and_docstrings_are_not_a_choice(source: str) -> None:
    assert literals_in(source) == []
