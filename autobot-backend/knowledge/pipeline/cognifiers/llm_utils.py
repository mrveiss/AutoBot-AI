# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared LLM utilities for ECL pipeline cognifiers.

Issue #1074: Extract duplicated parse/build helpers from cognifiers (ARCH-3/4).
Issue #10598: Shared multi-chunk batching helper — pack K chunks into one LLM
call keyed by chunk index, with per-chunk fallback (generalizes #10647).
"""

import json
import os
from typing import Any, Awaitable, Callable, Dict, List, TypeVar

from autobot_shared.logging_manager import get_logger
from knowledge.pipeline.models.entity import Entity

logger = get_logger(__name__)

_R = TypeVar("_R")

# Batched extraction packs K chunks into one call, so the response is ~K× larger
# than a single-chunk reply. Scale ``max_tokens`` with the batch size (capped) so
# the batched output isn't truncated mid-response — truncation drops trailing
# chunk indices, which per-chunk fallback then has to recover (#11012).
_BATCH_MAX_TOKENS_PER_CHUNK = int(os.environ.get("AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_PER_CHUNK", "1024"))
_BATCH_MAX_TOKENS_CAP = int(os.environ.get("AUTOBOT_COGNIFIER_BATCH_MAX_TOKENS_CAP", "8192"))


def parse_llm_json_response(
    content: str,
    *,
    fallback_dict: bool = False,
    strict: bool = False,
) -> List[Dict[str, Any]] | Dict[str, Any]:
    """Parse LLM response as JSON, handling markdown code fences.

    Args:
        content: Raw LLM response text.
        fallback_dict: If True, return a dict fallback on parse failure
                       (used by summarizer). Otherwise return empty list.
        strict: If True, re-raise ``json.JSONDecodeError`` instead of
                returning an empty fallback — callers that must not swallow
                parse failures (e.g. cognifier extractors) use this so
                malformed LLM responses surface as errors (#10645).

    Returns:
        Parsed JSON (list or dict depending on LLM output).
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        if "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
        if strict:
            raise
        logger.warning("Could not parse LLM response as JSON")
        if fallback_dict:
            return {"summary": content, "key_topics": [], "key_entities": []}
        return []


def build_entity_map(
    entities: List[Entity],
    *,
    include_canonical: bool = True,
) -> Dict[str, Entity]:
    """Build name-to-entity lookup mapping.

    Args:
        entities: Entity list to index.
        include_canonical: Also index by canonical_name (relationship
                          extractor needs this; summarizer does not).

    Returns:
        Mapping of lowercase name -> Entity.
    """
    entity_map: Dict[str, Entity] = {}
    for entity in entities:
        entity_map[entity.name.lower()] = entity
        if include_canonical:
            entity_map[entity.canonical_name] = entity
    return entity_map


def build_indexed_chunk_blocks(contents: List[str], max_chars: int) -> str:
    """Render chunk texts as ``Chunk N:`` blocks for an index-keyed batch prompt.

    Args:
        contents: Per-chunk text, in order.
        max_chars: Truncate each chunk to this many characters (0 = no limit).

    Returns:
        Newline-separated ``Chunk i:\\n<text>`` blocks.
    """
    parts = []
    for i, text in enumerate(contents):
        body = text[:max_chars] if max_chars and max_chars > 0 else text
        parts.append(f"Chunk {i}:\n{body}")
    return "\n\n".join(parts)


def parse_indexed_batch_response(content: str, n_chunks: int) -> Dict[int, List[Any]]:
    """Parse an index-keyed batch response into ``{chunk_index: [raw items]}``.

    Raises ``ValueError`` on a non-object response or one whose keys are disjoint
    from the chunk indices, so the caller can fall back to per-chunk extraction
    (mirrors ``FactExtractor._extract_batched`` #10647). A single-object value is
    coerced to a one-element list.

    Indices whose key is **absent** from the response are OMITTED from the result
    (distinct from a present-but-empty ``[]``), so the caller can recover only the
    dropped chunks via per-chunk fallback — a partial/truncated batch response no
    longer silently yields zero items for the missing chunks (#11012).
    """
    parsed = parse_llm_json_response(content)
    if not isinstance(parsed, dict):
        raise ValueError("batched response was not a JSON object")
    if {str(i) for i in range(n_chunks)}.isdisjoint(parsed.keys()):
        raise ValueError("batched response keys do not match chunk indices")
    result: Dict[int, List[Any]] = {}
    for i in range(n_chunks):
        key = str(i)
        if key not in parsed:
            continue  # missing — omit so the caller falls back for this chunk only
        raw = parsed[key]
        if isinstance(raw, dict):
            result[i] = [raw]
        elif isinstance(raw, list):
            result[i] = raw
        else:
            result[i] = []  # present but null/scalar → explicitly empty, no fallback
    return result


async def batched_chunk_extract(
    chunks: List[Any],
    *,
    llm: Any,
    batch_prompt_template: str,
    llm_type: str,
    max_chunk_chars: int,
    convert: Callable[[List[Any], Any], List[_R]],
    extract_one: Callable[[Any], Awaitable[List[_R]]],
    content_of: Callable[[Any], str] = lambda c: c.content,
) -> List[_R]:
    """Extract items from many chunks in ONE structured LLM call (#10598).

    Sends all ``chunks`` in a single index-keyed prompt, parses results back per
    chunk, and calls ``convert(raw_items, chunk)`` to build domain objects while
    preserving per-chunk mapping and order. On any structural failure (non-object
    response, disjoint keys, or exception) it falls back to ``extract_one(chunk)``
    per chunk so correctness never regresses. A single-chunk batch skips batching.

    Args:
        chunks: The chunk objects to process.
        llm: LLM service exposing ``async chat(messages, *, llm_type, structured_output)``.
        batch_prompt_template: Prompt with a ``{chunks}`` placeholder.
        llm_type: Cheap task tier passed through to the LLM (e.g. ``"extraction"``).
        max_chunk_chars: Per-chunk truncation for the batched prompt (0 = no limit).
        convert: ``(raw_items, chunk) -> [domain objects]``.
        extract_one: Per-chunk async fallback returning domain objects.
        content_of: Extract the text of a chunk (default ``chunk.content``).

    Returns:
        Flattened list of extracted items across all chunks, in chunk order.
    """
    if not chunks:
        return []
    if len(chunks) == 1:
        return await extract_one(chunks[0])
    try:
        blocks = build_indexed_chunk_blocks([content_of(c) for c in chunks], max_chunk_chars)
        prompt = batch_prompt_template.format(chunks=blocks)
        batch_max_tokens = min(_BATCH_MAX_TOKENS_PER_CHUNK * len(chunks), _BATCH_MAX_TOKENS_CAP)
        response = await llm.chat(
            [{"role": "user", "content": prompt}],
            llm_type=llm_type,
            structured_output=True,
            max_tokens=batch_max_tokens,
        )
        by_index = parse_indexed_batch_response(response.content, len(chunks))
    except Exception as exc:
        logger.warning("Batched extraction failed (%s); falling back to per-chunk", exc)
        results: List[_R] = []
        for chunk in chunks:
            results.extend(await extract_one(chunk))
        return results
    items: List[_R] = []
    for i, chunk in enumerate(chunks):
        if i in by_index:
            items.extend(convert(by_index[i], chunk))
        else:
            # Missing from a partial/truncated batch response — recover this chunk
            # via per-chunk extraction so no chunk is silently dropped (#11012).
            items.extend(await extract_one(chunk))
    return items
