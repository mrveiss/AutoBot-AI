# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
llm_shared.structured_ops — Canonical schema-typed LLM extraction helper.

Issue #11520: Consolidates three hand-rolled extraction paths that each
re-implemented JSON parsing, retries, and chunking:
    - web_fetch/extractors.py  (JSON Schema / dict)
    - agents/knowledge_extraction_agent.py  (JSON dict → AtomicFact objects)
    - api/entity_extraction.py  (delegates to graph_entity_extractor)

Public API
----------
    async def extract(
        text: str,
        schema: type[BaseModel] | dict,
        *,
        llm_type: LLMType = LLMType.EXTRACTION,
        max_retries: int = EXTRACT_MAX_RETRIES,
        chunking: str = "auto",
    ) -> BaseModel | dict

Schema types
~~~~~~~~~~~~
* ``pydantic.BaseModel`` subclass → the helper validates the parsed JSON and
  returns a model instance.
* ``dict`` (JSON Schema) → validated via ``jsonschema.Draft202012Validator``;
  returns a plain ``dict``.

Chunking
~~~~~~~~
When ``chunking="auto"`` (default) and the input exceeds
``EXTRACT_CHUNK_THRESHOLD_CHARS`` characters the text is split via the existing
``utils.semantic_chunker.get_semantic_chunker()`` factory.  Each chunk is
extracted independently and merged as follows:

  * Object schemas: non-null field values from later chunks overwrite nulls /
    absences from earlier chunks (last-non-null wins).
  * List/array fields: concatenated across chunks, deduplicating exact
    string duplicates.

The merge strategy is deliberately simple and documented here; call sites that
need custom merge logic should call ``extract()`` per chunk themselves.

Retries
~~~~~~~
On ``json.JSONDecodeError`` or schema validation failure the error message is
fed back to the LLM in a retry prompt so the model can self-correct.  After
``max_retries`` attempts a ``ExtractionError`` is raised — errors are never
swallowed.

Import safety
~~~~~~~~~~~~~
``llm_shared`` must never import from ``judges``.  The fence-tolerant JSON
parser lives in ``llm_shared.json_utils`` and is imported from there by both
this module and ``judges/__init__.py``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Union

import pydantic

from llm_shared.json_utils import extract_json_object
from llm_shared.types import LLMType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level env-configurable constants (never hard-coded)
# ---------------------------------------------------------------------------

#: Maximum number of LLM call attempts before raising ExtractionError.
EXTRACT_MAX_RETRIES: int = int(os.environ.get("AUTOBOT_EXTRACT_MAX_RETRIES", "3"))

#: Inputs larger than this many characters trigger auto-chunking.
EXTRACT_CHUNK_THRESHOLD_CHARS: int = int(os.environ.get("AUTOBOT_EXTRACT_CHUNK_THRESHOLD", "8000"))


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class ExtractionError(RuntimeError):
    """Raised after all retry attempts are exhausted without a valid result."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_system_prompt(schema_repr: str) -> str:
    """Return the system prompt for schema-driven extraction."""
    return (
        "You are a structured data extraction assistant. "
        "Extract information from the provided text and return ONLY a valid JSON object "
        f"that conforms to this schema:\n\n{schema_repr}\n\n"
        "Respond with only the JSON object, no explanation or markdown fences."
    )


def _build_retry_prompt(previous_prompt: str, error_msg: str) -> str:
    """Return a follow-up prompt that feeds the validation error back to the LLM."""
    return (
        f"{previous_prompt}\n\n"
        f"Your previous response was invalid: {error_msg}\n"
        "Please fix the JSON and try again. Return ONLY a valid JSON object."
    )


def _validate_pydantic(data: dict, schema: type[pydantic.BaseModel]) -> pydantic.BaseModel:
    """Validate dict against a Pydantic model. Raises ValidationError on failure."""
    return schema.model_validate(data)


def _validate_json_schema(data: dict, schema: dict) -> None:
    """Validate dict against JSON Schema (Draft 2020-12). Raises ValidationError."""
    import jsonschema

    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(data)


def _schema_to_repr(schema: type[pydantic.BaseModel] | dict) -> str:
    """Serialise the schema for inclusion in the LLM prompt."""
    if isinstance(schema, dict):
        return json.dumps(schema, ensure_ascii=False)
    # Pydantic model class
    return json.dumps(schema.model_json_schema(), ensure_ascii=False)


async def _call_llm(prompt: str, llm_type: LLMType) -> str:
    """Call the shared LLM service and return the raw content string."""
    from services.llm_service import get_llm_service

    svc = get_llm_service()
    response = await svc.chat(
        messages=[{"role": "user", "content": prompt}],
        llm_type=llm_type,
        structured_output=True,
    )
    if response.error:
        raise ExtractionError(f"LLM call failed: {response.error}")
    return response.content


async def _extract_single(
    text: str,
    schema: type[pydantic.BaseModel] | dict,
    llm_type: LLMType,
    max_retries: int,
) -> pydantic.BaseModel | dict:
    """Run the extraction + validation loop for a single text block.

    On each attempt the full prompt is rebuilt so the model always has the
    schema in view. The validation error from attempt N is prepended in the
    prompt for attempt N+1.
    """
    schema_repr = _schema_to_repr(schema)
    base_prompt = f"{_build_system_prompt(schema_repr)}\n\n" f"Text to extract from:\n\n{text}"
    prompt = base_prompt
    last_error: str = ""

    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            prompt = _build_retry_prompt(base_prompt, last_error)
            logger.debug(
                "structured_ops.extract: retry %d/%d after error: %s",
                attempt,
                max_retries,
                last_error,
            )

        raw = await _call_llm(prompt, llm_type)

        # --- Parse ---
        try:
            data = extract_json_object(raw)
        except json.JSONDecodeError as exc:
            last_error = f"JSONDecodeError: {exc}"
            logger.warning("structured_ops: JSON parse failed (attempt %d): %s", attempt, exc)
            if attempt >= max_retries:
                raise ExtractionError(f"LLM returned non-JSON output after {max_retries} attempts: {exc}") from exc
            continue

        # --- Validate ---
        try:
            if isinstance(schema, dict):
                _validate_json_schema(data, schema)
                return data
            else:
                return _validate_pydantic(data, schema)
        except Exception as exc:
            last_error = str(exc)
            logger.warning("structured_ops: validation failed (attempt %d): %s", attempt, exc)
            if attempt >= max_retries:
                raise ExtractionError(f"Schema validation failed after {max_retries} attempts: {exc}") from exc

    # Should be unreachable — loop always returns or raises above.
    raise ExtractionError("extract: exhausted all attempts without result")  # pragma: no cover


# ---------------------------------------------------------------------------
# Chunk-merge helpers
# ---------------------------------------------------------------------------


def _merge_dicts(base: dict, update: dict) -> dict:
    """Merge *update* into *base* using last-non-null-wins for scalars and
    concatenation for lists.

    Rules (documented in module docstring):
    * Scalar/object fields: value from *update* wins when it is not None / "".
    * List/array fields: concatenated; exact string duplicates are removed.
    """
    result = dict(base)
    for key, value in update.items():
        existing = result.get(key)
        if isinstance(existing, list) and isinstance(value, list):
            # Concatenate lists, removing exact string duplicates.
            seen: set = set()
            merged: list = []
            for item in existing + value:
                dedup_key = item if isinstance(item, str) else id(item)
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    merged.append(item)
            result[key] = merged
        elif value is not None and value != "" and value != []:
            result[key] = value
    return result


def _merge_results(results: list[Any]) -> dict:
    """Merge a list of per-chunk dict results into a single dict."""
    merged: dict = {}
    for r in results:
        chunk_dict = r if isinstance(r, dict) else r.model_dump()
        merged = _merge_dicts(merged, chunk_dict)
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract(
    text: str,
    schema: Union[type[pydantic.BaseModel], dict],
    *,
    llm_type: LLMType = LLMType.EXTRACTION,
    max_retries: int = EXTRACT_MAX_RETRIES,
    chunking: str = "auto",
) -> Union[pydantic.BaseModel, dict]:
    """Extract structured data from *text* conforming to *schema*.

    Args:
        text:        Input text to extract from.
        schema:      Either a ``pydantic.BaseModel`` subclass (returns an
                     instance) or a ``dict`` (JSON Schema — returns a dict).
        llm_type:    LLMType routing key; defaults to ``LLMType.EXTRACTION``.
        max_retries: Maximum LLM call attempts per chunk before raising
                     ``ExtractionError``.  Env override:
                     ``AUTOBOT_EXTRACT_MAX_RETRIES`` (default 3).
        chunking:    ``"auto"`` (default): chunk text when it exceeds
                     ``EXTRACT_CHUNK_THRESHOLD_CHARS`` chars.
                     ``"never"``: always treat the full text as one block.

    Returns:
        A ``pydantic.BaseModel`` instance when *schema* is a model class, or
        a ``dict`` when *schema* is a JSON Schema dict.

    Raises:
        ExtractionError: After all retry attempts are exhausted without a
                         valid result.  Never swallows errors.

    Merge rules (chunked path, dict output):
        * Scalar/object fields: last non-null/non-empty chunk value wins.
        * List/array fields: concatenated; exact string duplicates removed.
    """
    should_chunk = chunking == "auto" and len(text) > EXTRACT_CHUNK_THRESHOLD_CHARS

    if not should_chunk:
        return await _extract_single(text, schema, llm_type, max_retries)

    # --- Chunked path ---
    logger.info(
        "structured_ops.extract: text length %d > threshold %d — chunking",
        len(text),
        EXTRACT_CHUNK_THRESHOLD_CHARS,
    )
    try:
        from utils.semantic_chunker import get_semantic_chunker

        chunker = get_semantic_chunker()
        chunks = await chunker.chunk_text(text)
        chunk_texts = [c.content for c in chunks] if chunks else [text]
    except Exception as exc:
        # Graceful degradation: chunking unavailable, run on full text.
        logger.warning("structured_ops.extract: chunking failed (%s) — using full text", exc)
        chunk_texts = [text]

    if len(chunk_texts) <= 1:
        return await _extract_single(text, schema, llm_type, max_retries)

    logger.info("structured_ops.extract: processing %d chunks", len(chunk_texts))
    results: list[Any] = []
    for i, chunk_text in enumerate(chunk_texts, 1):
        logger.debug("structured_ops.extract: chunk %d/%d", i, len(chunk_texts))
        chunk_result = await _extract_single(chunk_text, schema, llm_type, max_retries)
        results.append(chunk_result)

    # Merge all chunk results into a single output.
    merged = _merge_results(results)

    # If caller passed a Pydantic model, re-validate the merged dict.
    if not isinstance(schema, dict):
        return _validate_pydantic(merged, schema)

    _validate_json_schema(merged, schema)
    return merged
