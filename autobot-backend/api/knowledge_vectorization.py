# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base Vectorization API endpoints for vector embedding management."""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime
from typing import List

from background_vectorization import get_background_vectorizer
from exceptions import InternalError
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from knowledge_factory import get_or_create_knowledge_base
from redis.exceptions import RedisError
from type_defs.common import Metadata

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge_vectorization"])


# ===== HELPER FUNCTIONS FOR BATCH VECTORIZATION STATUS =====


async def _execute_pipeline_exists_check(kb_instance, vector_keys: List[str]) -> list:
    """
    Execute Redis pipeline for batch EXISTS checks.

    Args:
        kb_instance: KnowledgeBase instance with redis_client
        vector_keys: List of vector keys to check for existence

    Returns:
        List of boolean results indicating existence. Issue #620.
    """
    pipeline = kb_instance.redis_client.pipeline()
    for vector_key in vector_keys:
        pipeline.exists(vector_key)
    return await asyncio.to_thread(pipeline.execute)


def _build_status_map(
    fact_ids: List[str],
    exists_results: list,
    include_dimensions: bool,
    kb_instance,
) -> tuple:
    """
    Build status map from existence check results.

    Args:
        fact_ids: List of fact IDs checked
        exists_results: Pipeline results for EXISTS checks
        include_dimensions: Whether to include vector dimensions
        kb_instance: KnowledgeBase instance for dimension lookup

    Returns:
        Tuple of (statuses dict, vectorized_count). Issue #620.
    """
    statuses = {}
    vectorized_count = 0

    for i, fact_id in enumerate(fact_ids):
        exists = bool(exists_results[i])

        if exists:
            vectorized_count += 1
            status_entry = {"vectorized": True}

            if include_dimensions:
                dimensions = getattr(kb_instance, "embedding_dimensions", 768)
                status_entry["dimensions"] = dimensions

            statuses[fact_id] = status_entry
        else:
            statuses[fact_id] = {"vectorized": False}

    return statuses, vectorized_count


def _calculate_vectorization_summary(total_checked: int, vectorized_count: int) -> dict:
    """
    Calculate summary statistics for vectorization status.

    Args:
        total_checked: Total number of facts checked
        vectorized_count: Number of facts that are vectorized

    Returns:
        Summary statistics dictionary. Issue #620.
    """
    not_vectorized_count = total_checked - vectorized_count
    vectorization_percentage = (
        (vectorized_count / total_checked * 100) if total_checked > 0 else 0.0
    )

    return {
        "total_checked": total_checked,
        "vectorized": vectorized_count,
        "not_vectorized": not_vectorized_count,
        "vectorization_percentage": round(vectorization_percentage, 2),
    }


def _generate_cache_key(fact_ids: List[str]) -> str:
    """
    Generate deterministic cache key for a list of fact IDs.

    Args:
        fact_ids: List of fact IDs to check

    Returns:
        MD5 hash of sorted fact IDs
    """
    sorted_ids = sorted(fact_ids)
    ids_str = ",".join(sorted_ids)
    return hashlib.md5(ids_str.encode(), usedforsecurity=False).hexdigest()


async def _check_vectorization_batch_internal(
    kb_instance, fact_ids: List[str], include_dimensions: bool = False
) -> Metadata:
    """
    Internal helper to check vectorization status for multiple facts using Redis pipeline.

    Issue #620: Refactored to use extracted helper methods.

    Args:
        kb_instance: KnowledgeBase instance
        fact_ids: List of fact IDs to check
        include_dimensions: Whether to include vector dimensions in response

    Returns:
        Dict with statuses and summary statistics
    """
    start_time = time.time()
    vector_keys = [f"llama_index/vector_{fact_id}" for fact_id in fact_ids]

    try:
        # Execute pipeline EXISTS checks (Issue #620: uses helper)
        results = await _execute_pipeline_exists_check(kb_instance, vector_keys)

        # Build status map (Issue #620: uses helper)
        statuses, vectorized_count = _build_status_map(
            fact_ids, results, include_dimensions, kb_instance
        )

        # Calculate summary (Issue #620: uses helper)
        summary = _calculate_vectorization_summary(len(fact_ids), vectorized_count)
        check_time_ms = (time.time() - start_time) * 1000

        return {
            "statuses": statuses,
            "summary": summary,
            "check_time_ms": round(check_time_ms, 2),
        }

    except Exception as e:
        logger.error("Error checking vectorization batch: %s", e)
        raise


# ===== ENDPOINTS =====


def _validate_vectorization_request(fact_ids: List[str]) -> dict:
    """
    Validate vectorization status request parameters.

    Issue #281: Extracted helper for input validation.

    Args:
        fact_ids: List of fact IDs to check

    Returns:
        Empty dict if valid, or early return response if no facts provided

    Raises:
        ValueError: If too many fact IDs provided
    """
    if not fact_ids:
        return {
            "statuses": {},
            "summary": {
                "total_checked": 0,
                "vectorized": 0,
                "not_vectorized": 0,
                "vectorization_percentage": 0.0,
            },
            "cached": False,
            "check_time_ms": 0.0,
            "message": "No fact IDs provided",
        }

    if len(fact_ids) > 1000:
        raise ValueError(
            f"Too many fact IDs ({len(fact_ids)}). Maximum 1000 per request."
        )

    return {}


async def _get_cached_vectorization_status(
    kb_instance, cache_key: str, fact_count: int
) -> dict:
    """
    Try to get cached vectorization status result.

    Issue #281: Extracted helper for cache retrieval.

    Args:
        kb_instance: KnowledgeBase instance
        cache_key: Redis cache key
        fact_count: Number of facts being checked (for logging)

    Returns:
        Cached result dict if found, None otherwise
    """
    try:
        cached_json = await asyncio.to_thread(kb_instance.redis_client.get, cache_key)
        if cached_json:
            json_str = (
                cached_json.decode("utf-8")
                if isinstance(cached_json, bytes)
                else cached_json
            )
            cached_result = json.loads(json_str)
            cached_result["cached"] = True
            logger.debug("Cache hit for vectorization status (%s facts)", fact_count)
            return cached_result
    except Exception as cache_err:
        logger.debug("Cache read failed (continuing without cache): %s", cache_err)

    return None


async def _cache_vectorization_result(
    kb_instance, cache_key: str, result: dict, fact_count: int
) -> None:
    """
    Cache vectorization status result.

    Issue #281: Extracted helper for cache storage.

    Args:
        kb_instance: KnowledgeBase instance
        cache_key: Redis cache key
        result: Result to cache
        fact_count: Number of facts (for logging)
    """
    try:
        # Issue #361 - avoid blocking
        await asyncio.to_thread(
            kb_instance.redis_client.setex,
            cache_key,
            60,
            json.dumps(result),  # 60 second TTL
        )
        logger.debug("Cached vectorization status for %s facts", fact_count)
    except Exception as cache_err:
        logger.warning("Failed to cache vectorization status: %s", cache_err)


async def _perform_uncached_batch_check(
    kb_instance,
    fact_ids: List[str],
    include_dimensions: bool,
    cache_key: str,
    use_cache: bool,
) -> dict:
    """
    Perform batch check and optionally cache result.

    Args:
        kb_instance: KnowledgeBase instance
        fact_ids: List of fact IDs to check
        include_dimensions: Whether to include vector dimensions
        cache_key: Redis cache key
        use_cache: Whether to cache the result

    Returns:
        Batch check result dict. Issue #620.
    """
    logger.info(
        "Checking vectorization status for %d facts (batch operation)", len(fact_ids)
    )

    result = await _check_vectorization_batch_internal(
        kb_instance, fact_ids, include_dimensions
    )
    result["cached"] = False

    if use_cache:
        await _cache_vectorization_result(kb_instance, cache_key, result, len(fact_ids))

    return result


@router.post("/vectorization_status")
async def check_vectorization_status_batch(request: dict, req: Request):
    """
    Check vectorization status for multiple facts in a single efficient batch operation.

    Issue #620: Uses extracted helper methods for validation, caching, and batch processing.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        raise InternalError(
            "Knowledge base not initialized - please check logs for errors"
        )

    fact_ids = request.get("fact_ids", [])
    include_dimensions = request.get("include_dimensions", False)
    use_cache = request.get("use_cache", True)

    early_return = _validate_vectorization_request(fact_ids)
    if early_return:
        return early_return

    cache_key = f"cache:vectorization_status:{_generate_cache_key(fact_ids)}"

    if use_cache:
        cached_result = await _get_cached_vectorization_status(
            kb_to_use, cache_key, len(fact_ids)
        )
        if cached_result:
            return cached_result

    return await _perform_uncached_batch_check(
        kb_to_use, fact_ids, include_dimensions, cache_key, use_cache
    )


def _extract_fact_content(fact_data: dict) -> str:
    """Extract content from fact data, handling both bytes and string keys."""
    content_raw = fact_data.get("content") or fact_data.get(b"content", b"")
    if isinstance(content_raw, bytes):
        return content_raw.decode("utf-8")
    return str(content_raw) if content_raw else ""


def _extract_fact_metadata(fact_data: dict) -> dict:
    """Extract metadata from fact data, handling both bytes and string keys."""
    metadata_str = fact_data.get("metadata") or fact_data.get(b"metadata", b"{}")
    if isinstance(metadata_str, bytes):
        return json.loads(metadata_str.decode("utf-8"))
    return json.loads(metadata_str)


async def _fetch_batch_data(kb, batch: List[str], skip_existing: bool) -> tuple:
    """
    Fetch batch fact data and vector existence status.

    Returns:
        Tuple of (all_fact_data, fact_ids, vector_exists_map)
    """
    # Batch fetch all fact data using pipeline - eliminates N+1 queries
    async with kb.aioredis_client.pipeline() as pipe:
        for fact_key in batch:
            await pipe.hgetall(fact_key)
        all_fact_data = await pipe.execute()

    # Extract fact IDs
    fact_ids = [
        fact_key.split(":")[-1] if ":" in fact_key else fact_key for fact_key in batch
    ]

    # If skip_existing, also batch check vector existence
    vector_exists = {}
    if skip_existing:
        async with kb.aioredis_client.pipeline() as pipe:
            for fact_id in fact_ids:
                await pipe.exists(f"llama_index/vector_{fact_id}")
            exists_results = await pipe.execute()
            vector_exists = dict(zip(fact_ids, exists_results))

    return all_fact_data, fact_ids, vector_exists


async def _process_single_fact(
    kb,
    fact_key: str,
    fact_data: dict,
    fact_id: str,
    skip_existing: bool,
    vector_exists: dict,
) -> tuple:
    """
    Process a single fact for vectorization.

    Returns:
        Tuple of (success: bool, skipped: bool, result_entry: dict or None)
    """
    if not fact_data:
        logger.warning("No data found for fact key: %s", fact_key)
        return False, False, None

    # Check if already vectorized
    if skip_existing and vector_exists.get(fact_id):
        return False, True, None

    # Issue #552: vectorize_existing_fact() only takes fact_id
    # The method retrieves content/metadata internally via _get_fact_for_vectorization
    result = await kb.vectorize_existing_fact(fact_id=fact_id)

    if result.get("status") == "success" and result.get("vector_indexed"):
        return True, False, {"fact_id": fact_id, "status": "vectorized"}

    logger.warning("Failed to vectorize fact %s: %s", fact_id, result.get("message"))
    return False, False, None


async def _process_single_fact_safe(
    kb,
    fact_key: str,
    fact_data: dict,
    fact_id: str,
    skip_existing: bool,
    vector_exists: dict,
) -> tuple:
    """Process a single fact with exception handling. (Issue #315 - extracted)"""
    try:
        return await _process_single_fact(
            kb, fact_key, fact_data, fact_id, skip_existing, vector_exists
        )
    except Exception as e:
        logger.error("Error processing fact %s: %s", fact_key, e)
        return False, False, None


async def _process_batch(
    kb, batch: list, batch_num: int, total_batches: int, skip_existing: bool
) -> tuple:
    """
    Process a single batch of facts for vectorization (Issue #486: extracted).

    Returns:
        Tuple of (success_count, failed_count, skipped_count, processed_facts)
    """
    success_count = 0
    failed_count = 0
    skipped_count = 0
    processed_facts = []

    logger.info(
        "Processing batch %d/%d (%d facts)", batch_num + 1, total_batches, len(batch)
    )

    try:
        all_fact_data, fact_ids, vector_exists = await _fetch_batch_data(
            kb, batch, skip_existing
        )
    except RedisError as e:
        logger.error("Redis error in batch %d: %s", batch_num + 1, e)
        return 0, len(batch), 0, []

    for fact_key, fact_data, fact_id in zip(batch, all_fact_data, fact_ids):
        success, skipped, result_entry = await _process_single_fact_safe(
            kb, fact_key, fact_data, fact_id, skip_existing, vector_exists
        )
        if success:
            success_count += 1
            if result_entry:
                processed_facts.append(result_entry)
        elif skipped:
            skipped_count += 1
        else:
            failed_count += 1

    return success_count, failed_count, skipped_count, processed_facts


async def _process_all_batches(
    kb, fact_keys: list, batch_size: int, batch_delay: float, skip_existing: bool
) -> tuple:
    """
    Process all batches of facts for vectorization (Issue #486: extracted).

    Returns:
        Tuple of (total_success, total_failed, total_skipped, all_processed_facts, total_batches)
    """
    total_success = 0
    total_failed = 0
    total_skipped = 0
    all_processed_facts = []

    total_batches = (len(fact_keys) + batch_size - 1) // batch_size

    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(fact_keys))
        batch = fact_keys[start_idx:end_idx]

        success, failed, skipped, processed = await _process_batch(
            kb, batch, batch_num, total_batches, skip_existing
        )
        total_success += success
        total_failed += failed
        total_skipped += skipped
        all_processed_facts.extend(processed)

        if batch_num < total_batches - 1:
            await asyncio.sleep(batch_delay)

    return (
        total_success,
        total_failed,
        total_skipped,
        all_processed_facts,
        total_batches,
    )


def _build_empty_vectorization_response() -> dict:
    """
    Build response for when no facts are found to vectorize.

    Returns:
        Empty vectorization response dict. Issue #620.
    """
    return {
        "status": "success",
        "message": "No facts found to vectorize",
        "processed": 0,
        "success": 0,
        "failed": 0,
        "skipped": 0,
    }


def _build_vectorization_response(
    fact_count: int,
    success: int,
    failed: int,
    skipped: int,
    total_batches: int,
    processed_facts: list,
) -> dict:
    """
    Build response for completed vectorization.

    Args:
        fact_count: Total facts processed
        success: Successful vectorizations
        failed: Failed vectorizations
        skipped: Skipped facts (already vectorized)
        total_batches: Number of batches processed
        processed_facts: List of processed fact details

    Returns:
        Vectorization response dict. Issue #620.
    """
    return {
        "status": "success",
        "message": f"Vectorization complete: {success} successful, {failed} failed, {skipped} skipped",
        "processed": fact_count,
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "batches": total_batches,
        "details": processed_facts[:10],
    }


@router.post("/vectorize_facts")
async def vectorize_existing_facts(
    req: Request,
    batch_size: int = 50,
    batch_delay: float = 0.5,
    skip_existing: bool = True,
):
    """
    Generate vector embeddings for facts in Redis.

    Issue #620: Refactored to use extracted helper methods.

    Args:
        batch_size: Number of facts to process per batch (default: 50)
        batch_delay: Delay in seconds between batches (default: 0.5)
        skip_existing: Skip facts that already have vectors (default: True)
    """
    kb = await get_or_create_knowledge_base(req.app)

    if not kb:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    fact_keys = await kb._scan_redis_keys_async("fact:*")

    if not fact_keys:
        return _build_empty_vectorization_response()

    logger.info(
        "Starting batched vectorization of %d facts (batch_size=%d, delay=%ss)",
        len(fact_keys),
        batch_size,
        batch_delay,
    )

    (
        success,
        failed,
        skipped,
        processed_facts,
        total_batches,
    ) = await _process_all_batches(
        kb, fact_keys, batch_size, batch_delay, skip_existing
    )

    logger.info("Batched vectorization complete - index updated automatically")

    return _build_vectorization_response(
        len(fact_keys), success, failed, skipped, total_batches, processed_facts
    )


# ===== INDIVIDUAL DOCUMENT VECTORIZATION =====


async def _update_job_status(kb_instance, job_id: str, job_data: Metadata) -> None:
    """
    Update job status in Redis with 1-hour TTL.

    Issue #281: Extracted helper for job status updates.

    Args:
        kb_instance: KnowledgeBase instance with redis_client
        job_id: Job tracking ID
        job_data: Job data dictionary to store
    """
    # Issue #361 - avoid blocking
    await asyncio.to_thread(
        kb_instance.redis_client.setex,
        f"vectorization_job:{job_id}",
        3600,  # 1 hour TTL
        json.dumps(job_data),
    )


async def _get_fact_content(kb_instance, fact_id: str) -> tuple:
    """
    Retrieve fact content and metadata from Redis.

    Issue #281: Extracted helper for fact retrieval.

    Args:
        kb_instance: KnowledgeBase instance
        fact_id: ID of fact to retrieve

    Returns:
        Tuple of (content, metadata)

    Raises:
        ValueError: If fact not found
    """
    fact_key = f"fact:{fact_id}"
    # Issue #361 - avoid blocking
    fact_hash = await asyncio.to_thread(kb_instance.redis_client.hgetall, fact_key)

    if not fact_hash:
        raise ValueError(f"Fact {fact_id} not found in knowledge base")

    # Extract content
    content = (
        fact_hash.get("content", "")
        if isinstance(fact_hash.get("content"), str)
        else fact_hash.get("content", b"").decode("utf-8")
    )

    # Extract metadata
    metadata_str = fact_hash.get("metadata", "{}")
    metadata = (
        json.loads(metadata_str)
        if isinstance(metadata_str, str)
        else json.loads(metadata_str.decode("utf-8"))
    )

    return content, metadata


async def _check_already_vectorized(kb_instance, fact_id: str) -> bool:
    """
    Check if fact is already vectorized.

    Issue #281: Extracted helper for vectorization check.

    Args:
        kb_instance: KnowledgeBase instance
        fact_id: ID of fact to check

    Returns:
        True if already vectorized, False otherwise
    """
    vector_key = f"llama_index/vector_{fact_id}"
    # Issue #361 - avoid blocking
    return await asyncio.to_thread(kb_instance.redis_client.exists, vector_key)


def _create_initial_job_data(job_id: str, fact_id: str) -> Metadata:
    """
    Create initial job data structure.

    Issue #281: Extracted helper for job initialization.

    Args:
        job_id: Job tracking ID
        fact_id: Fact ID being processed

    Returns:
        Initial job data dictionary
    """
    return {
        "job_id": job_id,
        "fact_id": fact_id,
        "status": "processing",
        "progress": 10,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
    }


async def _fetch_existing_job(kb_instance, job_id: str) -> tuple:
    """
    Fetch existing job data from Redis.

    Args:
        kb_instance: KnowledgeBase instance
        job_id: Job ID to fetch

    Returns:
        Tuple of (job_data dict, fact_id). Issue #620.

    Raises:
        HTTPException: If job not found or missing fact_id
    """
    job_json = await asyncio.to_thread(
        kb_instance.redis_client.get, f"vectorization_job:{job_id}"
    )

    if not job_json:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job_data = json.loads(job_json)
    fact_id = job_data.get("fact_id")

    if not fact_id:
        raise HTTPException(status_code=400, detail="Job does not contain fact_id")

    return job_data, fact_id


def _create_retry_job_data(
    new_job_id: str, fact_id: str, original_job_id: str
) -> Metadata:
    """
    Create job data structure for a retry job.

    Args:
        new_job_id: New job tracking ID
        fact_id: Fact ID to vectorize
        original_job_id: ID of the original failed job

    Returns:
        Retry job data dictionary. Issue #620.
    """
    return {
        "job_id": new_job_id,
        "fact_id": fact_id,
        "status": "pending",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
        "retry_of": original_job_id,
    }


async def _store_and_start_retry_job(
    kb_instance,
    new_job_id: str,
    job_data: dict,
    fact_id: str,
    background_tasks: BackgroundTasks,
    force: bool,
) -> None:
    """
    Store retry job in Redis and start background vectorization.

    Args:
        kb_instance: KnowledgeBase instance
        new_job_id: New job ID
        job_data: Job data to store
        fact_id: Fact ID to vectorize
        background_tasks: FastAPI background tasks
        force: Force re-vectorization flag. Issue #620.
    """
    await asyncio.to_thread(
        kb_instance.redis_client.setex,
        f"vectorization_job:{new_job_id}",
        3600,
        json.dumps(job_data),
    )

    background_tasks.add_task(
        _vectorize_fact_background, kb_instance, fact_id, new_job_id, force
    )


async def _validate_fact_exists(kb_instance, fact_id: str) -> None:
    """
    Validate that a fact exists in Redis.

    Args:
        kb_instance: KnowledgeBase instance
        fact_id: Fact ID to validate

    Raises:
        HTTPException: If fact not found. Issue #620.
    """
    fact_key = f"fact:{fact_id}"
    fact_data = await asyncio.to_thread(kb_instance.redis_client.hgetall, fact_key)
    if not fact_data:
        raise HTTPException(
            status_code=404, detail=f"Fact {fact_id} not found in knowledge base"
        )


def _create_pending_job_data(job_id: str, fact_id: str) -> Metadata:
    """
    Create pending job data structure for individual vectorization.

    Args:
        job_id: Job tracking ID
        fact_id: Fact ID to vectorize

    Returns:
        Pending job data dictionary. Issue #620.
    """
    return {
        "job_id": job_id,
        "fact_id": fact_id,
        "status": "pending",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
    }


async def _store_and_start_job(
    kb_instance,
    job_id: str,
    job_data: dict,
    fact_id: str,
    background_tasks: BackgroundTasks,
    force: bool,
) -> None:
    """
    Store job in Redis and start background vectorization.

    Args:
        kb_instance: KnowledgeBase instance
        job_id: Job ID
        job_data: Job data to store
        fact_id: Fact ID to vectorize
        background_tasks: FastAPI background tasks
        force: Force re-vectorization flag. Issue #620.
    """
    await asyncio.to_thread(
        kb_instance.redis_client.setex,
        f"vectorization_job:{job_id}",
        3600,
        json.dumps(job_data),
    )

    background_tasks.add_task(
        _vectorize_fact_background, kb_instance, fact_id, job_id, force
    )


async def _handle_already_vectorized(
    kb_instance, job_id: str, job_data: dict, fact_id: str
) -> None:
    """
    Handle case where fact is already vectorized.

    Issue #665: Extracted helper for already-vectorized case.

    Args:
        kb_instance: KnowledgeBase instance
        job_id: Job tracking ID
        job_data: Job data to update
        fact_id: Fact ID
    """
    logger.info(
        f"Fact {fact_id} already vectorized, skipping (use force=true to re-vectorize)"
    )
    job_data.update(
        {
            "status": "completed",
            "progress": 100,
            "completed_at": datetime.now().isoformat(),
            "result": {
                "status": "skipped",
                "message": "Fact already vectorized",
                "fact_id": fact_id,
                "vector_indexed": True,
            },
        }
    )
    await _update_job_status(kb_instance, job_id, job_data)


async def _perform_vectorization(
    kb_instance, fact_id: str, job_id: str, job_data: dict
) -> None:
    """
    Perform the actual vectorization and update job status.

    Issue #665: Extracted helper for vectorization execution.

    Args:
        kb_instance: KnowledgeBase instance
        fact_id: Fact ID to vectorize
        job_id: Job tracking ID
        job_data: Job data to update
    """
    # Debug: Log KB state before vectorization
    logger.debug(
        f"KB state before vectorization: initialized={getattr(kb_instance, 'initialized', 'N/A')}, "
        f"vector_store={kb_instance.vector_store is not None}, "
        f"llama_index_configured={getattr(kb_instance, 'llama_index_configured', 'N/A')}"
    )

    # Issue #552: vectorize_existing_fact() only takes fact_id
    # The method retrieves content/metadata internally via _get_fact_for_vectorization
    result = await kb_instance.vectorize_existing_fact(fact_id=fact_id)

    # Update job with result
    job_data["progress"] = 90
    job_data["result"] = result

    if result.get("status") == "success" and result.get("vector_indexed"):
        job_data["status"] = "completed"
        job_data["progress"] = 100
        logger.info("Successfully vectorized fact %s in job %s", fact_id, job_id)
    else:
        job_data["status"] = "failed"
        job_data["error"] = result.get("message", "Unknown error")
        logger.error(
            f"Failed to vectorize fact {fact_id} in job {job_id}: {job_data['error']}"
        )

    job_data["completed_at"] = datetime.now().isoformat()
    await _update_job_status(kb_instance, job_id, job_data)


async def _vectorize_fact_background(
    kb_instance, fact_id: str, job_id: str, force: bool = False
):
    """
    Background task to vectorize a single fact and track progress in Redis.

    Issue #665: Refactored from 95 lines to use additional extracted helpers.

    Args:
        kb_instance: KnowledgeBase instance
        fact_id: ID of fact to vectorize
        job_id: Job tracking ID
        force: Force re-vectorization even if already vectorized
    """
    job_data = _create_initial_job_data(job_id, fact_id)

    try:
        # Initialize job status
        await _update_job_status(kb_instance, job_id, job_data)
        logger.info("Started vectorization job %s for fact %s", job_id, fact_id)

        # Get fact content (Issue #281: uses helper)
        content, metadata = await _get_fact_content(kb_instance, fact_id)

        # Update progress to 30%
        job_data["progress"] = 30
        await _update_job_status(kb_instance, job_id, job_data)

        # Check if already vectorized (Issue #665: uses helper)
        if not force and await _check_already_vectorized(kb_instance, fact_id):
            await _handle_already_vectorized(kb_instance, job_id, job_data, fact_id)
            return

        # Update progress to 50%
        job_data["progress"] = 50
        await _update_job_status(kb_instance, job_id, job_data)

        # Perform vectorization (Issue #665: uses helper)
        await _perform_vectorization(kb_instance, fact_id, job_id, job_data)

    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"Error in vectorization job {job_id} for fact {fact_id}: {error_msg}"
        )

        # Update job with error
        job_data.update(
            {
                "status": "failed",
                "progress": 0,
                "completed_at": datetime.now().isoformat(),
                "error": error_msg,
                "result": None,
            }
        )
        await _update_job_status(kb_instance, job_id, job_data)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="vectorize_individual_fact",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/vectorize_fact/{fact_id}")
async def vectorize_individual_fact(
    fact_id: str, req: Request, background_tasks: BackgroundTasks, force: bool = False
):
    """
    Vectorize a single fact by ID with progress tracking.

    Issue #620: Refactored to use extracted helper methods.

    Args:
        fact_id: ID of the fact to vectorize
        force: Force re-vectorization even if already vectorized (default: False)

    Returns:
        Job tracking information with job_id for status monitoring
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Validate fact exists (Issue #620: uses helper)
    await _validate_fact_exists(kb, fact_id)

    # Create and store job (Issue #620: uses helpers)
    job_id = str(uuid.uuid4())
    job_data = _create_pending_job_data(job_id, fact_id)

    await _store_and_start_job(kb, job_id, job_data, fact_id, background_tasks, force)

    logger.info(
        "Created vectorization job %s for fact %s (force=%s)", job_id, fact_id, force
    )

    return {
        "status": "success",
        "message": "Vectorization job started",
        "job_id": job_id,
        "fact_id": fact_id,
        "force": force,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vectorization_job_status",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/vectorize_job/{job_id}")
async def get_vectorization_job_status(job_id: str, req: Request):
    """
    Get the status of a vectorization job.

    Args:
        job_id: Job tracking ID

    Returns:
        Job status information including progress and result
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Get job data from Redis
    # Issue #361 - avoid blocking
    job_json = await asyncio.to_thread(
        kb.redis_client.get, f"vectorization_job:{job_id}"
    )

    if not job_json:
        raise HTTPException(
            status_code=404, detail=f"Vectorization job {job_id} not found"
        )

    job_data = json.loads(job_json)

    return {"status": "success", "job": job_data}


def _filter_failed_jobs(results: list) -> List[dict]:
    """Filter and parse failed jobs from Redis results."""
    failed_jobs = []
    for job_json in results:
        if not job_json:
            continue
        job_data = json.loads(job_json)
        if job_data.get("status") == "failed":
            failed_jobs.append(job_data)
    return failed_jobs


def _collect_failed_keys(keys: list, results: list) -> List[str]:
    """Collect keys of failed jobs from Redis results."""
    failed_keys = []
    for key, job_json in zip(keys, results):
        if not job_json:
            continue
        job_data = json.loads(job_json)
        if job_data.get("status") == "failed":
            failed_keys.append(key)
    return failed_keys


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_failed_vectorization_jobs",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/vectorize_jobs/failed")
async def get_failed_vectorization_jobs(req: Request):
    """
    Get all failed vectorization jobs from Redis.

    Returns:
        List of failed jobs with their error details
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Use SCAN to iterate through keys efficiently
    # Issue #361 - avoid blocking - wrap all Redis ops in helper
    def _scan_failed_jobs():
        failed_jobs = []
        cursor = 0
        while True:
            cursor, keys = kb.redis_client.scan(
                cursor, match="vectorization_job:*", count=100
            )

            if not keys:
                if cursor == 0:
                    break
                continue

            # Use pipeline for batch operations
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            results = pipe.execute()

            # Filter failed jobs (extracted helper reduces nesting)
            failed_jobs.extend(_filter_failed_jobs(results))

            if cursor == 0:
                break
        return failed_jobs

    failed_jobs = await asyncio.to_thread(_scan_failed_jobs)

    return {
        "status": "success",
        "failed_jobs": failed_jobs,
        "total_failed": len(failed_jobs),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="retry_vectorization_job",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/vectorize_jobs/{job_id}/retry")
async def retry_vectorization_job(
    job_id: str, req: Request, background_tasks: BackgroundTasks, force: bool = False
):
    """
    Retry a failed vectorization job.

    Issue #620: Refactored to use extracted helper methods.

    Args:
        job_id: ID of the failed job to retry
        force: Force re-vectorization even if already vectorized

    Returns:
        New job tracking information
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Fetch original job data (Issue #620: uses helper)
    _, fact_id = await _fetch_existing_job(kb, job_id)

    # Create and store retry job (Issue #620: uses helpers)
    new_job_id = str(uuid.uuid4())
    job_data = _create_retry_job_data(new_job_id, fact_id, job_id)

    await _store_and_start_retry_job(
        kb, new_job_id, job_data, fact_id, background_tasks, force
    )

    logger.info("Retrying vectorization job %s as %s", job_id, new_job_id)

    return {
        "status": "success",
        "message": "Retry job started",
        "new_job_id": new_job_id,
        "fact_id": fact_id,
        "original_job_id": job_id,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_vectorization_job",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/vectorize_jobs/{job_id}")
async def delete_vectorization_job(job_id: str, req: Request):
    """
    Delete a vectorization job record from Redis.

    Args:
        job_id: ID of the job to delete

    Returns:
        Deletion confirmation
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Delete job from Redis
    # Issue #361 - avoid blocking
    deleted = await asyncio.to_thread(
        kb.redis_client.delete, f"vectorization_job:{job_id}"
    )

    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    logger.info("Deleted vectorization job %s", job_id)

    return {
        "status": "success",
        "message": f"Job {job_id} deleted",
        "job_id": job_id,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_failed_vectorization_jobs",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/vectorize_jobs/failed/clear")
async def clear_failed_vectorization_jobs(req: Request):
    """
    Clear all failed vectorization jobs from Redis.

    Returns:
        Number of jobs cleared
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Issue #361 - avoid blocking - wrap all Redis ops in helper
    def _clear_failed_jobs():
        deleted_count = 0
        cursor = 0
        while True:
            cursor, keys = kb.redis_client.scan(
                cursor, match="vectorization_job:*", count=100
            )

            if not keys:
                if cursor == 0:
                    break
                continue

            # Use pipeline for batch operations
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            results = pipe.execute()

            # Collect failed job keys (using extracted helper)
            failed_keys = _collect_failed_keys(keys, results)

            # Delete failed jobs in batch
            if failed_keys:
                kb.redis_client.delete(*failed_keys)
                deleted_count += len(failed_keys)

            if cursor == 0:
                break
        return deleted_count

    deleted_count = await asyncio.to_thread(_clear_failed_jobs)

    logger.info("Cleared %s failed vectorization jobs", deleted_count)

    return {
        "status": "success",
        "message": f"Cleared {deleted_count} failed jobs",
        "deleted_count": deleted_count,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_background_vectorization",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/vectorize_facts/background")
async def start_background_vectorization(
    req: Request, background_tasks: BackgroundTasks
):
    """
    Start background vectorization of all pending facts.
    Returns immediately while vectorization runs in the background.
    """
    kb = await get_or_create_knowledge_base(req.app)
    if not kb:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    vectorizer = get_background_vectorizer()

    # Add vectorization to background tasks
    background_tasks.add_task(vectorizer.vectorize_pending_facts, kb)

    return {
        "status": "started",
        "message": "Background vectorization started",
        "last_run": vectorizer.last_run.isoformat() if vectorizer.last_run else None,
        "is_running": vectorizer.is_running,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vectorization_status",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/vectorize_facts/status")
async def get_vectorization_status(req: Request):
    """Get the status of background vectorization"""
    vectorizer = get_background_vectorizer()

    return {
        "is_running": vectorizer.is_running,
        "last_run": vectorizer.last_run.isoformat() if vectorizer.last_run else None,
        "check_interval": vectorizer.check_interval,
        "batch_size": vectorizer.batch_size,
    }
