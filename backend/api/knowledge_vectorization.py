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

from backend.type_defs.common import Metadata
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from backend.background_vectorization import get_background_vectorizer
from backend.knowledge_factory import get_or_create_knowledge_base
from src.exceptions import InternalError
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge_vectorization"])


# ===== HELPER FUNCTIONS FOR BATCH VECTORIZATION STATUS =====


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
    return hashlib.md5(ids_str.encode()).hexdigest()


async def _check_vectorization_batch_internal(
    kb_instance, fact_ids: List[str], include_dimensions: bool = False
) -> Metadata:
    """
    Internal helper to check vectorization status for multiple facts using Redis pipeline.

    Args:
        kb_instance: KnowledgeBase instance
        fact_ids: List of fact IDs to check
        include_dimensions: Whether to include vector dimensions in response

    Returns:
        Dict with statuses and summary statistics
    """
    start_time = time.time()

    # Build vector keys
    vector_keys = [f"llama_index/vector_{fact_id}" for fact_id in fact_ids]

    # Use Redis pipeline for batch EXISTS checks (single roundtrip)
    try:
        pipeline = kb_instance.redis_client.pipeline()
        for vector_key in vector_keys:
            pipeline.exists(vector_key)

        # Execute pipeline (wrap in to_thread to avoid blocking event loop)
        results = await asyncio.to_thread(pipeline.execute)

        # Build status map
        statuses = {}
        vectorized_count = 0

        for i, fact_id in enumerate(fact_ids):
            exists = bool(results[i])

            if exists:
                vectorized_count += 1
                status_entry = {"vectorized": True}

                # Optionally include dimensions
                if include_dimensions:
                    # Get embedding dimensions from knowledge base config
                    # Default to 768 for nomic-embed-text
                    dimensions = getattr(kb_instance, "embedding_dimensions", 768)
                    status_entry["dimensions"] = dimensions

                statuses[fact_id] = status_entry
            else:
                statuses[fact_id] = {"vectorized": False}

        # Calculate summary statistics
        total_checked = len(fact_ids)
        not_vectorized_count = total_checked - vectorized_count
        vectorization_percentage = (
            (vectorized_count / total_checked * 100) if total_checked > 0 else 0.0
        )

        check_time_ms = (time.time() - start_time) * 1000

        return {
            "statuses": statuses,
            "summary": {
                "total_checked": total_checked,
                "vectorized": vectorized_count,
                "not_vectorized": not_vectorized_count,
                "vectorization_percentage": round(vectorization_percentage, 2),
            },
            "check_time_ms": round(check_time_ms, 2),
        }

    except Exception as e:
        logger.error(f"Error checking vectorization batch: {e}")
        raise


# ===== ENDPOINTS =====


@router.post("/vectorization_status")
async def check_vectorization_status_batch(request: dict, req: Request):
    """
    Check vectorization status for multiple facts in a single efficient batch operation.

    This endpoint uses Redis pipeline for optimal performance, checking 100-1000 facts
    with a single Redis roundtrip. Results are cached with TTL to reduce Redis load.

    Args:
        request: {
            "fact_ids": ["id1", "id2", ...],  # Required: List of fact IDs to check
            "include_dimensions": bool,        # Optional: Include vector dimensions
                                               # (default: false)
            "use_cache": bool                  # Optional: Use cached results (default: true)
        }

    Returns:
        {
            "statuses": {
                "fact-id-1": {"vectorized": true, "dimensions": 768},
                "fact-id-2": {"vectorized": false}
            },
            "summary": {
                "total_checked": 1000,
                "vectorized": 750,
                "not_vectorized": 250,
                "vectorization_percentage": 75.0
            },
            "cached": false,
            "check_time_ms": 45.2
        }

    Performance:
        - Batch size: Up to 1000 facts per request
        - Single Redis roundtrip using pipeline
        - Cache TTL: 60 seconds (configurable)
        - Typical response time: <50ms for 1000 facts
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        raise InternalError(
            "Knowledge base not initialized - please check logs for errors"
        )

    # Extract parameters
    fact_ids = request.get("fact_ids", [])
    include_dimensions = request.get("include_dimensions", False)
    use_cache = request.get("use_cache", True)

    # Validate input
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

    # Generate cache key
    cache_key = f"cache:vectorization_status:{_generate_cache_key(fact_ids)}"
    cached_result = None

    # Try cache if enabled
    if use_cache:
        try:
            cached_json = kb_to_use.redis_client.get(cache_key)
            if cached_json:
                cached_result = json.loads(cached_json)
                cached_result["cached"] = True
                logger.debug(
                    f"Cache hit for vectorization status ({len(fact_ids)} facts)"
                )
                return cached_result
        except Exception as cache_err:
            logger.debug(f"Cache read failed (continuing without cache): {cache_err}")

    # Cache miss - perform batch check
    logger.info(
        f"Checking vectorization status for {len(fact_ids)} facts (batch operation)"
    )

    result = await _check_vectorization_batch_internal(
        kb_to_use, fact_ids, include_dimensions
    )

    result["cached"] = False

    # Cache the result (TTL: 60 seconds)
    if use_cache:
        try:
            kb_to_use.redis_client.setex(
                cache_key, 60, json.dumps(result)  # 60 second TTL
            )
            logger.debug(f"Cached vectorization status for {len(fact_ids)} facts")
        except Exception as cache_err:
            logger.warning(f"Failed to cache vectorization status: {cache_err}")

    return result


@router.post("/vectorize_facts")
async def vectorize_existing_facts(
    req: Request,
    batch_size: int = 50,
    batch_delay: float = 0.5,
    skip_existing: bool = True,
):
    """
    Generate vector embeddings for facts in Redis using batched processing.

    Args:
        batch_size: Number of facts to process per batch (default: 50)
        batch_delay: Delay in seconds between batches (default: 0.5)
        skip_existing: Skip facts that already have vectors (default: True)

    This prevents resource lockup by processing facts in manageable batches
    and can be run periodically to vectorize new facts.
    """
    kb = await get_or_create_knowledge_base(req.app)

    if not kb:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Get all fact keys from Redis
    fact_keys = await kb._scan_redis_keys_async("fact:*")

    if not fact_keys:
        return {
            "status": "success",
            "message": "No facts found to vectorize",
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

    logger.info(
        f"Starting batched vectorization of {len(fact_keys)} facts "
        f"(batch_size={batch_size}, delay={batch_delay}s)"
    )

    success_count = 0
    failed_count = 0
    skipped_count = 0
    processed_facts = []

    total_batches = (len(fact_keys) + batch_size - 1) // batch_size

    # Process in batches
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(fact_keys))
        batch = fact_keys[start_idx:end_idx]

        logger.info(
            f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} facts)"
        )

        for fact_key in batch:
            try:
                # Get fact data
                fact_data = await kb.aioredis_client.hgetall(fact_key)

                if not fact_data:
                    logger.warning(f"No data found for fact key: {fact_key}")
                    failed_count += 1
                    continue

                # Extract content and metadata (handle both bytes and string keys from Redis)
                content_raw = fact_data.get("content") or fact_data.get(b"content", b"")
                content = (
                    content_raw.decode("utf-8")
                    if isinstance(content_raw, bytes)
                    else str(content_raw) if content_raw else ""
                )

                metadata_str = fact_data.get("metadata") or fact_data.get(
                    b"metadata", b"{}"
                ),
                metadata = json.loads(
                    metadata_str.decode("utf-8")
                    if isinstance(metadata_str, bytes)
                    else metadata_str
                )

                # Extract fact ID from key (fact:uuid)
                fact_id = fact_key.split(":")[-1] if ":" in fact_key else fact_key

                # Check if already vectorized by checking vector_indexed status
                if skip_existing:
                    # Check if this fact is already in the vector index
                    vector_key = f"llama_index/vector_{fact_id}"
                    has_vector = await kb.aioredis_client.exists(vector_key)
                    if has_vector:
                        skipped_count += 1
                        continue

                # Vectorize existing fact without duplication
                result = await kb.vectorize_existing_fact(
                    fact_id=fact_id, content=content, metadata=metadata
                )

                if result.get("status") == "success" and result.get("vector_indexed"):
                    success_count += 1
                    processed_facts.append({"fact_id": fact_id, "status": "vectorized"})
                else:
                    failed_count += 1
                    logger.warning(
                        f"Failed to vectorize fact {fact_id}: {result.get('message')}"
                    )

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing fact {fact_key}: {e}")

        # Delay between batches to prevent resource exhaustion
        if batch_num < total_batches - 1:
            await asyncio.sleep(batch_delay)

    # KnowledgeBaseV2 automatically indexes during add_document - no rebuild needed
    logger.info("Batched vectorization complete - index updated automatically")

    return {
        "status": "success",
        "message": (
            f"Vectorization complete: {success_count} successful, "
            f"{failed_count} failed, {skipped_count} skipped"
        ),
        "processed": len(fact_keys),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "batches": total_batches,
        "details": processed_facts[:10],  # Return first 10 for reference
    }


# ===== INDIVIDUAL DOCUMENT VECTORIZATION =====


async def _vectorize_fact_background(
    kb_instance, fact_id: str, job_id: str, force: bool = False
):
    """
    Background task to vectorize a single fact and track progress in Redis.

    Args:
        kb_instance: KnowledgeBase instance
        fact_id: ID of fact to vectorize
        job_id: Job tracking ID
        force: Force re-vectorization even if already vectorized
    """
    try:
        # Update job status to processing
        job_data = {
            "job_id": job_id,
            "fact_id": fact_id,
            "status": "processing",
            "progress": 10,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "error": None,
            "result": None,
        }
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)  # 1 hour TTL
        )
        logger.info(f"Started vectorization job {job_id} for fact {fact_id}")

        # Get fact data from Redis - facts are stored as individual hashes with key "fact:{uuid}"
        fact_key = f"fact:{fact_id}"
        fact_hash = kb_instance.redis_client.hgetall(fact_key)

        if not fact_hash:
            raise ValueError(f"Fact {fact_id} not found in knowledge base")

        # Extract content and metadata from hash
        content = (
            fact_hash.get("content", "")
            if isinstance(fact_hash.get("content"), str)
            else fact_hash.get("content", b"").decode("utf-8")
        ),
        metadata_str = fact_hash.get("metadata", "{}")
        metadata = (
            json.loads(metadata_str)
            if isinstance(metadata_str, str)
            else json.loads(metadata_str.decode("utf-8"))
        )

        # Update progress
        job_data["progress"] = 30
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )

        # Check if already vectorized (unless force=True)
        if not force:
            vector_key = f"llama_index/vector_{fact_id}"
            if kb_instance.redis_client.exists(vector_key):
                logger.info(
                    f"Fact {fact_id} already vectorized, skipping (use force=true to re-vectorize)"
                )
                job_data["status"] = "completed"
                job_data["progress"] = 100
                job_data["completed_at"] = datetime.now().isoformat()
                job_data["result"] = {
                    "status": "skipped",
                    "message": "Fact already vectorized",
                    "fact_id": fact_id,
                    "vector_indexed": True,
                }
                kb_instance.redis_client.setex(
                    f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
                )
                return

        # Update progress
        job_data["progress"] = 50
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )

        # Vectorize the fact
        result = await kb_instance.vectorize_existing_fact(
            fact_id=fact_id, content=content, metadata=metadata
        )

        # Update job with result
        job_data["progress"] = 90
        job_data["result"] = result

        if result.get("status") == "success" and result.get("vector_indexed"):
            job_data["status"] = "completed"
            job_data["progress"] = 100
            logger.info(f"Successfully vectorized fact {fact_id} in job {job_id}")
        else:
            job_data["status"] = "failed"
            job_data["error"] = result.get("message", "Unknown error")
            logger.error(
                f"Failed to vectorize fact {fact_id} in job {job_id}: {job_data['error']}"
            )

        job_data["completed_at"] = datetime.now().isoformat()
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"Error in vectorization job {job_id} for fact {fact_id}: {error_msg}"
        )

        # Update job with error
        job_data = {
            "job_id": job_id,
            "fact_id": fact_id,
            "status": "failed",
            "progress": 0,
            "started_at": job_data.get("started_at", datetime.now().isoformat()),
            "completed_at": datetime.now().isoformat(),
            "error": error_msg,
            "result": None,
        }
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )


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

    Args:
        fact_id: ID of the fact to vectorize
        force: Force re-vectorization even if already vectorized (default: False)

    Returns:
        Job tracking information with job_id for status monitoring
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Check if fact exists - facts are stored as individual Redis hashes with key "fact:{uuid}"
    fact_key = f"fact:{fact_id}"
    fact_data = kb.redis_client.hgetall(fact_key)
    if not fact_data:
        raise HTTPException(
            status_code=404, detail=f"Fact {fact_id} not found in knowledge base"
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Create initial job record
    job_data = {
        "job_id": job_id,
        "fact_id": fact_id,
        "status": "pending",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
    }

    kb.redis_client.setex(
        f"vectorization_job:{job_id}", 3600, json.dumps(job_data)  # 1 hour TTL
    )

    # Add background task
    background_tasks.add_task(_vectorize_fact_background, kb, fact_id, job_id, force)

    logger.info(
        f"Created vectorization job {job_id} for fact {fact_id} (force={force})"
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
    job_json = kb.redis_client.get(f"vectorization_job:{job_id}")

    if not job_json:
        raise HTTPException(
            status_code=404, detail=f"Vectorization job {job_id} not found"
        )

    job_data = json.loads(job_json)

    return {"status": "success", "job": job_data}


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

    # Use SCAN to iterate through keys efficiently (non-blocking)
    failed_jobs = []
    cursor = 0

    while True:
        cursor, keys = kb.redis_client.scan(
            cursor, match="vectorization_job:*", count=100
        )

        # Use pipeline for batch operations
        if keys:
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            results = pipe.execute()

            for job_json in results:
                if job_json:
                    job_data = json.loads(job_json)
                    if job_data.get("status") == "failed":
                        failed_jobs.append(job_data)

        if cursor == 0:
            break

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

    Args:
        job_id: ID of the failed job to retry
        force: Force re-vectorization even if already vectorized

    Returns:
        New job tracking information
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Get old job data
    old_job_json = kb.redis_client.get(f"vectorization_job:{job_id}")

    if not old_job_json:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    old_job_data = json.loads(old_job_json)
    fact_id = old_job_data.get("fact_id")

    if not fact_id:
        raise HTTPException(status_code=400, detail="Job does not contain fact_id")

    # Create new job
    new_job_id = str(uuid.uuid4())
    job_data = {
        "job_id": new_job_id,
        "fact_id": fact_id,
        "status": "pending",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
        "retry_of": job_id,  # Track that this is a retry
    }

    kb.redis_client.setex(f"vectorization_job:{new_job_id}", 3600, json.dumps(job_data))

    # Add background task
    background_tasks.add_task(
        _vectorize_fact_background, kb, fact_id, new_job_id, force
    )

    logger.info(f"Retrying vectorization job {job_id} as {new_job_id}")

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
    deleted = kb.redis_client.delete(f"vectorization_job:{job_id}")

    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    logger.info(f"Deleted vectorization job {job_id}")

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

    # Use SCAN to iterate through keys efficiently (non-blocking)
    deleted_count = 0
    cursor = 0

    while True:
        cursor, keys = kb.redis_client.scan(
            cursor, match="vectorization_job:*", count=100
        )

        # Use pipeline for batch operations
        if keys:
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            results = pipe.execute()

            # Collect failed job keys
            failed_keys = []
            for key, job_json in zip(keys, results):
                if job_json:
                    job_data = json.loads(job_json)
                    if job_data.get("status") == "failed":
                        failed_keys.append(key)

            # Delete failed jobs in batch
            if failed_keys:
                kb.redis_client.delete(*failed_keys)
                deleted_count += len(failed_keys)

        if cursor == 0:
            break

    logger.info(f"Cleared {deleted_count} failed vectorization jobs")

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
