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

import logging
from typing import Any, Union

import pydantic

from autobot_shared.env_utils import env_int
from llm_shared.types import LLMType
from llm_shared.validated_llm import (
    ValidatedLLMError,
    complete_validated,
    llm_service_completer,
    schema_repr,
    validate_against,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level env-configurable constants (never hard-coded)
# ---------------------------------------------------------------------------

#: Maximum number of LLM call attempts before raising ExtractionError.
EXTRACT_MAX_RETRIES: int = env_int("AUTOBOT_EXTRACT_MAX_RETRIES", 3)

#: Inputs larger than this many characters trigger auto-chunking.
EXTRACT_CHUNK_THRESHOLD_CHARS: int = env_int("AUTOBOT_EXTRACT_CHUNK_THRESHOLD", 8000)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


#: The original name (#11520) of ``validated_llm.ValidatedLLMError`` -- the
#: same class, not a subclass, so ``except ExtractionError`` at the three
#: production callers keeps catching what it always caught after #17307 moved
#: the retry-and-validate loop out of this module.
ExtractionError = ValidatedLLMError


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


# Schema serialisation, validation, the retry prompt and the loop itself all
# live in ``llm_shared.validated_llm`` (#17307) -- extraction is one of its
# callers, the judges and the decision seam are the others.
_schema_to_repr = schema_repr


async def _extract_single(
    text: str,
    schema: type[pydantic.BaseModel] | dict,
    llm_type: LLMType,
    max_retries: int,
    llm_service: Any = None,
) -> pydantic.BaseModel | dict:
    """Extract one text block through the shared retry-and-validate loop.

    The prompt shape is unchanged: the schema and the text ride in one user
    message, which is what the extraction callers and their tests expect. What
    changed with #17307 is that the loop, the schema serialisation and the
    retry text are no longer this module's own copy -- and that the schema now
    also travels to the provider as ``json_schema`` (#17305), so a provider
    with native schema mode constrains the reply before the retry is needed.
    """
    user_prompt = f"{_build_system_prompt(schema_repr(schema))}\n\nText to extract from:\n\n{text}"
    return await complete_validated(
        "",
        user_prompt,
        schema,
        completer=llm_service_completer(schema, llm_type=llm_type, llm_service=llm_service),
        max_retries=max_retries,
        label="structured_ops.extract",
    )


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
    llm_service: Any = None,
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
        llm_service: Optional pre-configured LLM interface (``LLMService.chat``
                     signature).  Callers with per-agent SSOT routing must pass
                     their own interface; defaults to the shared singleton.

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
        return await _extract_single(text, schema, llm_type, max_retries, llm_service)

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
        return await _extract_single(text, schema, llm_type, max_retries, llm_service)

    logger.info("structured_ops.extract: processing %d chunks", len(chunk_texts))
    results: list[Any] = []
    for i, chunk_text in enumerate(chunk_texts, 1):
        logger.debug("structured_ops.extract: chunk %d/%d", i, len(chunk_texts))
        chunk_result = await _extract_single(chunk_text, schema, llm_type, max_retries, llm_service)
        results.append(chunk_result)

    # Merge all chunk results into a single output.
    merged = _merge_results(results)

    # If caller passed a Pydantic model, re-validate the merged dict.
    # Wrapped so the public ExtractionError-only contract holds even when the
    # merged result fails validation (#11520 review B1).
    # `validate_against` returns the merged dict unchanged for a JSON Schema
    # and a model instance for a Pydantic schema, so there is nothing to fall
    # through to -- the previous trailing `return merged` was unreachable once
    # the two validators became one call (#17307).
    try:
        return validate_against(merged, schema)
    except Exception as exc:
        raise ExtractionError(f"Merged chunk result failed schema validation: {exc}") from exc
