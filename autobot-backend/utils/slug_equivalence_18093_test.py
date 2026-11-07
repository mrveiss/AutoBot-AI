# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every migrated sanitizer site still produces its previous output, byte for byte (#18093).

Three proofs per site:

1. The site's source really calls `sanitize_token` with exactly the keywords recorded in
   `SITES` (read from the AST, so the table cannot drift from the code).
2. The helper, given those keywords, equals the site's PREVIOUS implementation (kept
   below as `_old_*`, verbatim) over a corpus: unicode, punctuation runs, edge
   separators, empty, over-length.
3. Where the site function is importable, the real function is compared too.

Several sites write stored keys (Redis key, Chroma collection, KB tag, temp-dir and key
filename, MCP tool prefix, company/org slug input); a different output would orphan the
data, which is why this is an equality test and not a behaviour test.
"""

import ast
import re
from pathlib import Path

import pytest

from autobot_shared.slug import sanitize_token

_ROOT = Path(__file__).resolve().parents[2]

_CORPUS = [
    "",
    " ",
    "---",
    "___",
    "...",
    "Hello, World!",
    "  Leading and trailing  ",
    "Zürich Café Müller",
    "日本語 テキスト",
    "naïve — dash ‒ test",
    "a" * 200,
    "ab-" * 50,
    "A_B-C.D@E+F:G/H\\I",
    "a\tb\nc\r\nd",
    "x" * 59 + "-y-z",
    "__init__.py",
    "01-Backend",
    "Ünï-çödé_2²³ ½",
    "http://Example.COM:8080/path?q=1",
    "UPPER lower MiXeD 123",
    "with 'quotes' and \"doubles\" & <tags>",
    "../../etc/passwd",
    "tab\x00nul\x1besc",
    "٣٤٥ arabic-indic digits",
    "!@#$%^&*()",
    "a..b__c--d  e",
    "-lead",
    "trail-",
    "_lead",
    "trail_",
    ".lead.",
    "-_.-mixed._-",
]


# --- previous implementations, verbatim -------------------------------------------
def _old_text_utils(t):
    t = t.lower().strip()
    t = re.sub(r"[^\w\s-]", "", t)
    t = re.sub(r"[\s_-]+", "_", t)
    return t[:80]


def _old_scope(t):
    return re.sub(r"[^A-Za-z0-9._@+-]+", "-", t).strip("-")[:80]


def _old_env(t):
    s = re.sub(r"[^A-Z0-9_]", "_", t)
    return re.sub(r"_+", "_", s).strip("_")


def _old_redis(t):
    return re.sub(r"[^a-zA-Z0-9_:.-]", "_", t)


def _old_tag(t):
    return re.sub(r"[^a-zA-Z0-9-_]", "", t.lower())


def _old_tee(t):
    return re.sub(r"[^\w-]", "_", t)[:60]


def _old_mcp(t):
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def _old_pep503(t):
    return re.sub(r"[-_.]+", "-", t).strip("-").lower()


def _old_chroma(t):
    return re.sub(r"[^a-zA-Z0-9._-]", "_", t)


def _old_isalnum(t):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in t)


def _old_nls(t):
    return re.sub(r"[^\w\s\-_]", " ", t)


def _old_captcha(t):
    return re.sub(r"[^A-Za-z0-9]", "", t)


#: (site file, old implementation, keywords exactly as written at the site)
SITES = {
    "text_utils": (
        "autobot-backend/agent_loop/text_utils.py",
        _old_text_utils,
        {
            "allowed": 'r"\\w\\s-"',
            "replacement": '""',
            "collapse": "False",
            "separator_chars": 'r"\\s_-"',
            "separator": '"_"',
            "case": '"lower"',
            "strip_input": "True",
            "max_length": "80",
        },
    ),
    "scope_enforcement": (
        "autobot-backend/agents/scope_enforcement.py",
        _old_scope,
        {"allowed": '"A-Za-z0-9._@+-"', "strip_edges": '"-"', "max_length": "_MAX_SEGMENT"},
    ),
    "env_analyzer": (
        "autobot-backend/code_analysis/src/env_analyzer.py",
        _old_env,
        {"allowed": '"A-Z0-9_"', "replacement": '"_"', "separator_chars": '"_"', "strip_edges": '"_"'},
    ),
    "analytics_redis_key": (
        "autobot-backend/code_intelligence/analytics_infrastructure.py",
        _old_redis,
        {"allowed": '"a-zA-Z0-9_:.-"', "replacement": '"_"', "collapse": "False"},
    ),
    "doc_indexer_tag": (
        "autobot-backend/services/knowledge/doc_indexer.py",
        _old_tag,
        {"allowed": '"a-zA-Z0-9_-"', "replacement": '""', "case": '"lower"'},
    ),
    "tool_output_tee": (
        "autobot-backend/services/tool_output_filter.py",
        _old_tee,
        {"allowed": 'r"\\w-"', "replacement": '"_"', "collapse": "False", "max_length": "60"},
    ),
    "mcp_aggregation": (
        "autobot-backend/services/mcp_aggregation.py",
        _old_mcp,
        {"replacement": '"_"', "strip_edges": '"_"'},
    ),
    "venv_reconcile": (
        "autobot-slm-backend/api/venv_reconcile.py",
        _old_pep503,
        {"allowed": "None", "separator_chars": '"-_."', "case": '"lower"', "strip_edges": '"-"'},
    ),
    "chroma_collection": (
        "autobot-backend/knowledge/backends/async_chromadb_adapter.py",
        _old_chroma,
        {"allowed": '"a-zA-Z0-9._-"', "replacement": '"_"', "collapse": "False"},
    ),
    "terminal_session_dir": (
        "autobot-backend/services/terminal_secrets_service.py",
        _old_isalnum,
        {"allowed": 'r"\\w-"', "replacement": '"_"', "collapse": "False"},
    ),
    "natural_language_search": (
        "autobot-backend/api/natural_language_search.py",
        _old_nls,
        {"allowed": 'r"\\w\\s\\-_"', "replacement": '" "', "collapse": "False"},
    ),
    "captcha_ocr": (
        "autobot-backend/services/captcha_solver.py",
        _old_captcha,
        {"allowed": '"A-Za-z0-9"', "replacement": '""', "collapse": "False"},
    ),
}
_CONSTS = {"_MAX_SEGMENT": 80}


def _site_calls(path: str) -> list:
    tree = ast.parse((_ROOT / path).read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "sanitize_token":
            out.append({k.arg: ast.unparse(k.value) for k in node.keywords})
    return out


def _eval(kwargs: dict) -> dict:
    return {k: eval(v, {}, _CONSTS) for k, v in kwargs.items()}  # noqa: S307 - literals from our table


@pytest.mark.parametrize("name", sorted(SITES))
def test_site_calls_the_helper_with_the_recorded_keywords(name):
    path, _old, kwargs = SITES[name]
    want = {k: ast.unparse(ast.parse(v, mode="eval")) for k, v in kwargs.items()}  # normalise quotes
    assert want in _site_calls(path), f"{path} does not call sanitize_token({kwargs})"


@pytest.mark.parametrize("name", sorted(SITES))
def test_helper_equals_previous_implementation(name):
    _path, old, kwargs = SITES[name]
    params = _eval(kwargs)
    bad = [(t, old(t), sanitize_token(t, **params)) for t in _CORPUS if old(t) != sanitize_token(t, **params)]
    assert not bad, bad[:3]


def test_real_site_functions_match_previous_output():
    from agent_loop.text_utils import slugify
    from knowledge.backends.async_chromadb_adapter import _chroma_safe_name
    from services.mcp_aggregation import server_id_from_uri

    for t in _CORPUS:
        assert slugify(t) == _old_text_utils(t)
        assert _chroma_safe_name(t) == _old_chroma(t)
        uri = t.lower()
        expect = _old_mcp(re.sub(r"^[a-z]+://", "", uri).split("/")[0]) or "mcp"
        assert server_id_from_uri(t) == expect


def test_unicode_isalnum_and_word_class_agree_on_every_bmp_character():
    """terminal_secrets_service replaced a `str.isalnum()` filter with `[^\\w-]`."""
    for cp in range(0x110000):
        c = chr(cp)
        assert (c.isalnum() or c == "_") == bool(re.match(r"\w", c)), hex(cp)


def test_the_two_tag_classes_are_the_same_set():
    """`[^a-zA-Z0-9-_]` (old) and `[^a-zA-Z0-9_-]` (new) must be the same class."""
    for cp in range(0x300):
        c = chr(cp)
        assert bool(re.match(r"[^a-zA-Z0-9-_]", c)) == bool(re.match(r"[^a-zA-Z0-9_-]", c)), hex(cp)
