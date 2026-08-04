# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for llm_shared.structured_ops (Issue #11520).

Covers:
- Pydantic model schema path (returns model instance)
- dict (JSON Schema) path (returns plain dict)
- Fence-wrapped JSON parsing via json_utils
- Invalid-JSON retry then raise after max retries
- Oversized-document chunking + merge with a mocked LLM
- ExtractionError surfaces after max retries (no swallowed errors)

Patching note: ``_call_llm`` resolves ``get_llm_service`` via a local import
from ``services.llm_service``.  In the test environment ``services.llm_service``
is a MagicMock stub (conftest.py); we set ``get_llm_service`` on that stub
directly so the import-inside-function path picks it up correctly.
"""

from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(content: str, error: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.error = error
    return resp


def _mock_llm_service(return_values: list[str]) -> MagicMock:
    svc = MagicMock()
    responses = [_make_llm_response(v) for v in return_values]
    svc.chat = AsyncMock(side_effect=responses)
    return svc


def _stub_semantic_chunker(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Return the module ``extract()``'s local ``get_semantic_chunker`` import resolves to.

    The real ``utils.semantic_chunker`` drags sentence-transformers in, so a
    hollow stand-in answers for it when it is absent.  ``monkeypatch.setitem``
    owns the removal: a bare assignment left the stand-in — and the hollow
    ``utils`` package under it — shadowing the real on-disk packages for every
    node the session handled afterwards (#13450).
    """
    for name in ("utils", "utils.semantic_chunker"):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    return sys.modules["utils.semantic_chunker"]


@contextmanager
def _patch_llm_service(svc: MagicMock):
    """Inject *svc* as the return value of ``services.llm_service.get_llm_service``.

    ``_call_llm`` resolves the service factory via a fresh import inside the
    function body, so the patch target is the attribute on the stub module that
    conftest already placed in ``sys.modules["services.llm_service"]``.
    """
    llm_svc_mod = sys.modules["services.llm_service"]
    original = getattr(llm_svc_mod, "get_llm_service", None)
    llm_svc_mod.get_llm_service = MagicMock(return_value=svc)
    try:
        yield
    finally:
        if original is None:
            try:
                del llm_svc_mod.get_llm_service
            except AttributeError:
                pass
        else:
            llm_svc_mod.get_llm_service = original


# ---------------------------------------------------------------------------
# json_utils.extract_json_object
# ---------------------------------------------------------------------------


def test_extract_json_plain() -> None:
    from .json_utils import extract_json_object

    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_fence() -> None:
    from .json_utils import extract_json_object

    raw = '```json\n{"b": 2}\n```'
    assert extract_json_object(raw) == {"b": 2}


def test_extract_json_unnamed_fence() -> None:
    from .json_utils import extract_json_object

    raw = '```\n{"c": 3}\n```'
    assert extract_json_object(raw) == {"c": 3}


def test_extract_json_raises_on_garbage() -> None:
    from .json_utils import extract_json_object

    with pytest.raises(json.JSONDecodeError):
        extract_json_object("not json at all")


# ---------------------------------------------------------------------------
# json_utils control-character sanitization tier (#11587)
# ---------------------------------------------------------------------------


def test_extract_json_raw_newline_in_value() -> None:
    from .json_utils import extract_json_object

    raw = '{"summary": "line one\nline two"}'
    assert extract_json_object(raw) == {"summary": "line one\nline two"}


def test_extract_json_control_char_in_key() -> None:
    from .json_utils import extract_json_object

    raw = '{"bad\tkey": 1, "esc\x01key": 2}'
    assert extract_json_object(raw) == {"bad\tkey": 1, "esc\x01key": 2}


def test_extract_json_fence_plus_control_chars() -> None:
    from .json_utils import extract_json_object

    raw = '```json\n{"a": "x\r\ny", "b": "tab\there"}\n```'
    assert extract_json_object(raw) == {"a": "x\r\ny", "b": "tab\there"}


def test_extract_json_pretty_printed_passthrough() -> None:
    from .json_utils import _escape_controls_in_strings, extract_json_object

    pretty = json.dumps({"a": 1, "b": {"c": [1, 2]}}, indent=2)
    # Structural whitespace outside string literals must be untouched.
    assert _escape_controls_in_strings(pretty) == pretty
    assert extract_json_object(pretty) == json.loads(pretty)


def test_extract_json_already_escaped_not_double_escaped() -> None:
    from .json_utils import extract_json_object

    # "\\n" is a literal backslash-n (already escaped); "\n" is a raw newline.
    raw = '{"a": "x\\ny", "b": "p\nq"}'
    result = extract_json_object(raw)
    assert result["a"] == "x\ny"  # single newline — NOT double-escaped to "\\ny"
    assert result["b"] == "p\nq"


def test_extract_json_escaped_quote_inside_string() -> None:
    from .json_utils import extract_json_object

    # \" must not terminate the string literal in the state machine.
    raw = '{"a": "he said \\"hi\\"\nok", "b": "back\\\\slash\tend"}'
    result = extract_json_object(raw)
    assert result["a"] == 'he said "hi"\nok'
    assert result["b"] == "back\\slash\tend"


# ---------------------------------------------------------------------------
# json_utils syntax-repair tier (#11688) — promoted from json_formatter_agent
# ---------------------------------------------------------------------------


def test_extract_json_trailing_commas() -> None:
    from .json_utils import extract_json_object

    raw = '{"a": 1, "b": [1, 2,],}'
    assert extract_json_object(raw) == {"a": 1, "b": [1, 2]}


def test_extract_json_bare_keys() -> None:
    from .json_utils import extract_json_object

    raw = '{status: "ok",\n  count: 3}'
    assert extract_json_object(raw) == {"status": "ok", "count": 3}


def test_extract_json_single_quotes() -> None:
    from .json_utils import extract_json_object

    raw = "{'a': 'b', 'n': 1}"
    assert extract_json_object(raw) == {"a": "b", "n": 1}


def test_extract_json_fence_plus_syntax_errors() -> None:
    from .json_utils import extract_json_object

    raw = '```json\n{result: "done",}\n```'
    assert extract_json_object(raw) == {"result": "done"}


def test_extract_json_syntax_repair_plus_control_chars() -> None:
    from .json_utils import extract_json_object

    raw = '{note: "line1\nline2",}'
    assert extract_json_object(raw) == {"note": "line1\nline2"}


def test_extract_json_repair_does_not_mangle_string_values() -> None:
    from .json_utils import extract_json_object

    # Colons/commas inside string values must survive the bare-key repair;
    # only reached when the direct parse fails (trailing comma forces repair).
    raw = '{"url": "http://x/y", "csv": "a, b: c",}'
    assert extract_json_object(raw) == {"url": "http://x/y", "csv": "a, b: c"}


def test_extract_json_syntax_tier_still_raises_on_garbage() -> None:
    from .json_utils import extract_json_object

    with pytest.raises(json.JSONDecodeError):
        extract_json_object("still {not json")


def test_repair_json_syntax_is_textual_only() -> None:
    from .json_utils import repair_json_syntax

    assert repair_json_syntax('{"a": 1,}') == '{"a": 1}'
    assert repair_json_syntax('{key: "v"}') == '{"key": "v"}'
    assert repair_json_syntax("no json here") == "no json here"


# ---------------------------------------------------------------------------
# structured_ops.extract — dict schema path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_dict_schema_happy_path() -> None:
    """Returns a plain dict when schema is a JSON Schema dict."""
    from .structured_ops import extract

    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    svc = _mock_llm_service(['{"name": "widget"}'])

    with _patch_llm_service(svc):
        result = await extract("some text", schema)

    assert isinstance(result, dict)
    assert result["name"] == "widget"


@pytest.mark.asyncio
async def test_extract_dict_schema_fence_json() -> None:
    """Fence-wrapped JSON is accepted via extract_json_object."""
    from .structured_ops import extract

    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    raw = '```json\n{"x": 42}\n```'
    svc = _mock_llm_service([raw])

    with _patch_llm_service(svc):
        result = await extract("text", schema)

    assert result["x"] == 42  # type: ignore[index]


# ---------------------------------------------------------------------------
# structured_ops.extract — Pydantic schema path
# ---------------------------------------------------------------------------


class _SampleModel(BaseModel):
    title: str
    count: int = 0


@pytest.mark.asyncio
async def test_extract_pydantic_schema_happy_path() -> None:
    """Returns a Pydantic model instance when schema is a model class."""
    from .structured_ops import extract

    svc = _mock_llm_service(['{"title": "Test", "count": 5}'])

    with _patch_llm_service(svc):
        result = await extract("some text", _SampleModel)

    assert isinstance(result, _SampleModel)
    assert result.title == "Test"
    assert result.count == 5


@pytest.mark.asyncio
async def test_extract_pydantic_fence_json() -> None:
    """Pydantic path also tolerates fence-wrapped JSON."""
    from .structured_ops import extract

    raw = '```json\n{"title": "Hello", "count": 1}\n```'
    svc = _mock_llm_service([raw])

    with _patch_llm_service(svc):
        result = await extract("text", _SampleModel)

    assert isinstance(result, _SampleModel)
    assert result.title == "Hello"


# ---------------------------------------------------------------------------
# Retry on invalid JSON / validation failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_bad_json_then_succeeds() -> None:
    """First response is bad JSON; second attempt succeeds."""
    from .structured_ops import extract

    schema = {"type": "object", "properties": {"k": {"type": "string"}}}
    svc = _mock_llm_service(["not json!", '{"k": "ok"}'])

    with _patch_llm_service(svc):
        result = await extract("text", schema, max_retries=3)

    assert result["k"] == "ok"  # type: ignore[index]
    assert svc.chat.call_count == 2
    # The retry prompt must feed the parse error back to the model (M2).
    second_prompt = svc.chat.call_args_list[1].kwargs["messages"][0]["content"]
    assert "JSONDecodeError" in second_prompt
    assert "previous response was invalid" in second_prompt


@pytest.mark.asyncio
async def test_raises_after_max_retries() -> None:
    """ExtractionError is raised (never swallowed) when all retries fail."""
    from .structured_ops import ExtractionError, extract

    schema = {"type": "object", "properties": {"k": {"type": "string"}}}
    svc = _mock_llm_service(["bad", "also bad", "still bad"])

    with _patch_llm_service(svc):
        with pytest.raises(ExtractionError):
            await extract("text", schema, max_retries=3)

    assert svc.chat.call_count == 3


@pytest.mark.asyncio
async def test_validation_error_triggers_retry() -> None:
    """Schema validation failure on first attempt triggers a retry."""
    from .structured_ops import extract

    schema = {
        "type": "object",
        "properties": {"score": {"type": "number", "minimum": 0}},
        "required": ["score"],
    }
    svc = _mock_llm_service(['{"score": "not-a-number"}', '{"score": 0.9}'])

    with _patch_llm_service(svc):
        result = await extract("text", schema, max_retries=3)

    assert result["score"] == 0.9  # type: ignore[index]
    assert svc.chat.call_count == 2
    # The retry prompt must feed the validation error back to the model (M2).
    second_prompt = svc.chat.call_args_list[1].kwargs["messages"][0]["content"]
    assert "not-a-number" in second_prompt
    assert "previous response was invalid" in second_prompt


# ---------------------------------------------------------------------------
# Chunking + merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunk_merge_combines_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Oversized input is split; per-chunk dicts are merged (last-non-null wins)."""
    from .structured_ops import extract

    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }

    chunk1_resp = '{"title": "First Title", "tags": ["a", "b"]}'
    chunk2_resp = '{"title": "Better Title", "tags": ["b", "c"]}'
    svc = _mock_llm_service([chunk1_resp, chunk2_resp])

    chunk_a = MagicMock()
    chunk_a.content = "chunk text one"
    chunk_b = MagicMock()
    chunk_b.content = "chunk text two"
    fake_chunker = AsyncMock()
    fake_chunker.chunk_text = AsyncMock(return_value=[chunk_a, chunk_b])

    ops_mod = sys.modules["llm_shared.structured_ops"]
    # get_semantic_chunker is a local import inside extract(); the module it
    # resolves has to carry the attribute before extract() runs. Both the module
    # entry and the attribute are undone at teardown (#13450).
    chunker_mod = _stub_semantic_chunker(monkeypatch)
    monkeypatch.setattr(chunker_mod, "get_semantic_chunker", MagicMock(return_value=fake_chunker), raising=False)
    with (
        _patch_llm_service(svc),
        patch.object(ops_mod, "EXTRACT_CHUNK_THRESHOLD_CHARS", 5),
    ):
        # The chunker is fully mocked, so the input content is irrelevant —
        # only its length matters (> patched threshold of 5) to trigger the
        # chunked code path.
        result = await extract("a" * 10, schema, chunking="auto")

    assert result["title"] == "Better Title"  # type: ignore[index]
    assert set(result["tags"]) == {"a", "b", "c"}  # type: ignore[index]


@pytest.mark.asyncio
async def test_chunking_never_skips_chunker() -> None:
    """chunking='never' bypasses the chunker even for oversized input."""
    from .structured_ops import extract

    schema = {"type": "object"}
    svc = _mock_llm_service(["{}"])

    ops_mod = sys.modules["llm_shared.structured_ops"]
    with (
        _patch_llm_service(svc),
        patch.object(ops_mod, "EXTRACT_CHUNK_THRESHOLD_CHARS", 0),
    ):
        result = await extract("some text", schema, chunking="never")

    assert isinstance(result, dict)
    assert svc.chat.call_count == 1


# ---------------------------------------------------------------------------
# _merge_dicts helper
# ---------------------------------------------------------------------------


def test_merge_dicts_scalar_last_non_null_wins() -> None:
    from .structured_ops import _merge_dicts

    merged = _merge_dicts({"a": "old", "b": None}, {"a": "new", "b": "value"})
    assert merged["a"] == "new"
    assert merged["b"] == "value"


def test_merge_dicts_null_does_not_overwrite() -> None:
    from .structured_ops import _merge_dicts

    merged = _merge_dicts({"a": "keep"}, {"a": None})
    assert merged["a"] == "keep"


def test_merge_dicts_list_concatenation_dedup() -> None:
    from .structured_ops import _merge_dicts

    merged = _merge_dicts({"tags": ["a", "b"]}, {"tags": ["b", "c"]})
    assert set(merged["tags"]) == {"a", "b", "c"}
    assert merged["tags"].count("b") == 1


@pytest.mark.asyncio
async def test_injected_llm_service_is_used_not_singleton() -> None:
    """extract(llm_service=...) must call the injected interface (#11520 M1).

    Guards per-agent SSOT provider/endpoint/model routing: callers with their
    own configured interface (e.g. KnowledgeExtractionAgent.llm_interface)
    must not silently fall back to the global service singleton.
    """
    from .structured_ops import extract

    schema = {"type": "object", "properties": {"k": {"type": "string"}}}
    injected = _mock_llm_service(['{"k": "from-injected"}'])

    # No _patch_llm_service here: if extract() ignored the injected service it
    # would import the real singleton and fail loudly in the stub test env.
    result = await extract("text", schema, llm_service=injected)

    assert result["k"] == "from-injected"  # type: ignore[index]
    assert injected.chat.call_count == 1


@pytest.mark.asyncio
async def test_extract_control_char_payload_parses_without_retry() -> None:
    """A control-char payload parses on the first attempt — no LLM retry (#11587).

    Before the sanitization tier, a raw newline inside a string value made
    extract_json_object raise JSONDecodeError and burned a full LLM retry
    round-trip. The single-response mock would raise StopAsyncIteration on a
    second chat() call, so call_count == 1 proves no retry happened.
    """
    from .structured_ops import extract

    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }
    raw = '```json\n{"summary": "first line\nsecond line"}\n```'
    svc = _mock_llm_service([raw])

    with _patch_llm_service(svc):
        result = await extract("some text", schema, max_retries=3)

    assert result["summary"] == "first line\nsecond line"  # type: ignore[index]
    assert svc.chat.call_count == 1
