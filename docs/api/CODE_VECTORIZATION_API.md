# Code Vectorization API Specification
**Version**: 1.0
**Date**: 2025-10-25
**Base URL**: `https://172.16.168.20:8443/api/analytics/code`

---

## Overview

The Code Vectorization API provides endpoints for semantic code analysis, duplicate detection, and code quality insights. All endpoints follow RESTful conventions and return JSON responses.

### Authentication
- Uses existing AutoBot authentication mechanisms
- API key required for all endpoints
- Rate limiting: 100 requests/minute for vectorization, 1000 requests/minute for searches

### Common Response Format
```json
{
    "status": "success|error",
    "data": {},
    "message": "Optional message",
    "timestamp": "2025-10-25T12:00:00Z"
}
```

---

## Endpoints

### 1. Vectorization Operations

#### POST `/vectorize`
Trigger code vectorization for the codebase.

**Request Body:**
```json
{
    "target_path": "/home/kali/Desktop/AutoBot",
    "incremental": true,
    "force_reindex": false,
    "languages": ["python", "javascript", "vue"],
    "embedding_model": "codebert-base",
    "chunk_strategy": "function"
}
```

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `target_path` | string | No | Project root | Path to analyze |
| `incremental` | boolean | No | true | Only process changed files |
| `force_reindex` | boolean | No | false | Force complete re-indexing |
| `languages` | array | No | All supported | Languages to process |
| `embedding_model` | string | No | codebert-base | Model to use for embeddings |
| `chunk_strategy` | string | No | function | How to chunk code (function/class/sliding_window) |

**Response:**
```json
{
    "status": "success",
    "data": {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "in_progress",
        "estimated_time_seconds": 120,
        "total_files": 450,
        "websocket_url": "wss://172.16.168.20:8443/ws/vectorization/550e8400-e29b-41d4-a716-446655440000"
    }
}
```

**Status Codes:**
- `202 Accepted`: Vectorization job started
- `400 Bad Request`: Invalid parameters
- `503 Service Unavailable`: Vectorization service unavailable

---

#### GET `/vectorize/status/{job_id}`
Get status of a vectorization job.

**Path Parameters:**
- `job_id`: UUID of the vectorization job

**Response:**
```json
{
    "status": "success",
    "data": {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "completed",
        "progress": {
            "files_processed": 450,
            "total_files": 450,
            "functions_embedded": 2340,
            "classes_embedded": 156,
            "modules_embedded": 450,
            "errors": [
                {
                    "file": "test_broken.py",
                    "error": "SyntaxError: invalid syntax"
                }
            ]
        },
        "duration_seconds": 115.4,
        "started_at": "2025-10-25T12:00:00Z",
        "completed_at": "2025-10-25T12:01:55Z",
        "result_summary": {
            "total_embeddings": 2946,
            "storage_size_mb": 245.6,
            "average_embedding_time_ms": 45,
            "model_used": "codebert-base",
            "dimensions": 768
        }
    }
}
```

---

#### DELETE `/vectorize/cancel/{job_id}`
Cancel a running vectorization job.

**Response:**
```json
{
    "status": "success",
    "data": {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "cancelled_at": "2025-10-25T12:00:30Z",
        "files_processed": 230
    }
}
```

---

### 2. Duplicate Detection

#### GET `/duplicates`
Find duplicate or near-duplicate code.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `similarity_threshold` | float | No | 0.85 | Minimum similarity (0-1) |
| `min_lines` | int | No | 10 | Minimum lines to consider |
| `max_lines` | int | No | 500 | Maximum lines to consider |
| `languages` | string | No | all | Comma-separated languages |
| `exclude_paths` | string | No | tests/,__pycache__/ | Paths to exclude |
| `exclude_tests` | boolean | No | true | Exclude test files |
| `group_by` | string | No | semantic | Grouping strategy (semantic/exact/structural) |
| `limit` | int | No | 100 | Max duplicate groups to return |

**Response:**
```json
{
    "status": "success",
    "data": {
        "duplicate_groups": [
            {
                "group_id": "dup_001",
                "pattern_name": "Redis connection with timeout",
                "pattern_type": "error_handling",
                "similarity_score": 0.92,
                "total_instances": 3,
                "total_lines": 145,
                "instances": [
                    {
                        "file": "autobot-user-backend/api/chat.py",
                        "function": "get_redis_connection",
                        "class": null,
                        "lines": "45-67",
                        "line_count": 22,
                        "snippet": "async def get_redis_connection():\n    try:\n        ...",
                        "complexity": {
                            "cyclomatic": 5,
                            "cognitive": 7
                        },
                        "last_modified": "2025-10-20T14:30:00Z"
                    },
                    {
                        "file": "autobot-user-backend/api/files.py",
                        "function": "init_redis",
                        "class": "FileManager",
                        "lines": "123-145",
                        "line_count": 22,
                        "snippet": "async def init_redis(self):\n    try:\n        ...",
                        "complexity": {
                            "cyclomatic": 6,
                            "cognitive": 8
                        },
                        "last_modified": "2025-10-18T10:15:00Z"
                    }
                ],
                "refactoring_suggestion": {
                    "action": "extract_to_utility",
                    "description": "Extract common Redis connection logic to a shared utility",
                    "target_location": "backend/utils/redis_helper.py",
                    "suggested_name": "create_redis_connection",
                    "estimated_loc_reduction": 44,
                    "difficulty": "low",
                    "priority": "high",
                    "benefits": [
                        "Reduce code duplication by 44 lines",
                        "Centralize Redis connection logic",
                        "Easier to maintain and update"
                    ]
                }
            }
        ],
        "summary": {
            "total_duplicate_groups": 23,
            "total_duplicate_instances": 67,
            "total_duplicate_lines": 1456,
            "potential_loc_reduction": 890,
            "duplication_percentage": 12.5,
            "highest_duplication_file": "autobot-user-backend/api/chat.py",
            "most_common_patterns": [
                "error_handling",
                "redis_connection",
                "api_response_formatting"
            ]
        },
        "recommendations": {
            "high_priority": 5,
            "medium_priority": 12,
            "low_priority": 6
        }
    }
}
```

---

### 3. Similarity Search

#### POST `/similarity-search`
Find code similar to a query.

**Request Body:**
```json
{
    "query_type": "code",
    "query": "async def process_message(self, message: str) -> Dict[str, Any]:",
    "top_k": 10,
    "filters": {
        "file_type": "python",
        "exclude_paths": ["tests/", "archives/"],
        "min_similarity": 0.7,
        "has_docstring": true,
        "complexity_max": 20
    },
    "include_explanation": true
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query_type` | string | Yes | Type of query (code/natural_language/function_signature) |
| `query` | string | Yes | The search query |
| `top_k` | int | No | Number of results to return (default: 10) |
| `filters` | object | No | Filtering criteria |
| `include_explanation` | boolean | No | Include similarity explanation (default: false) |

**Response:**
```json
{
    "status": "success",
    "data": {
        "query": "async def process_message(self, message: str) -> Dict[str, Any]:",
        "results": [
            {
                "rank": 1,
                "similarity_score": 0.94,
                "file": "backend/services/chat_service.py",
                "function": "handle_message",
                "class": "ChatHandler",
                "lines": "234-267",
                "signature": "async def handle_message(self, msg: str) -> Dict[str, Any]:",
                "snippet": "async def handle_message(self, msg: str) -> Dict[str, Any]:\n    \"\"\"Process incoming message.\"\"\"\n    ...",
                "metadata": {
                    "complexity": 8,
                    "has_docstring": true,
                    "has_type_hints": true,
                    "test_coverage": 0.85
                },
                "explanation": {
                    "why_similar": "Same async pattern, similar parameter types, identical return type",
                    "key_matches": ["async", "self", "str parameter", "Dict return"],
                    "semantic_similarity": "Both handle message processing asynchronously"
                }
            }
        ],
        "search_metadata": {
            "embedding_model": "codebert-base",
            "search_time_ms": 234,
            "total_candidates": 2340,
            "filtered_candidates": 450
        }
    }
}
```

---

### 4. Reuse Opportunities

#### GET `/reuse-opportunities`
Identify code that could be refactored for reuse.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `min_occurrences` | int | No | 3 | Minimum pattern occurrences |
| `scope` | string | No | project | Analysis scope (project/directory/module) |
| `path` | string | No | / | Path to analyze (if scope is directory) |

**Response:**
```json
{
    "status": "success",
    "data": {
        "opportunities": [
            {
                "opportunity_id": "reuse_001",
                "pattern": "Redis connection initialization",
                "pattern_type": "infrastructure",
                "occurrences": 12,
                "confidence": 0.95,
                "files_affected": [
                    "autobot-user-backend/api/chat.py",
                    "autobot-user-backend/api/files.py",
                    "autobot-user-backend/api/terminal.py"
                ],
                "current_metrics": {
                    "total_loc": 340,
                    "average_complexity": 6.5,
                    "maintenance_burden": "high"
                },
                "suggested_refactoring": {
                    "utility_name": "RedisConnectionManager",
                    "suggested_location": "backend/utils/redis_manager.py",
                    "template_code": "class RedisConnectionManager:\n    ...",
                    "estimated_metrics": {
                        "new_loc": 60,
                        "loc_reduction": 280,
                        "complexity_reduction": 4.2
                    }
                },
                "priority": "high",
                "effort": "low",
                "roi_score": 8.5,
                "benefits": [
                    "82% code reduction",
                    "Single point of configuration",
                    "Easier testing",
                    "Consistent error handling"
                ]
            }
        ],
        "summary": {
            "total_opportunities": 15,
            "high_priority": 5,
            "total_potential_loc_reduction": 1250,
            "estimated_effort_hours": 16,
            "roi_analysis": {
                "immediate_benefits": "25% reduction in maintenance time",
                "long_term_benefits": "Improved code quality and consistency"
            }
        }
    }
}
```

---

### 5. Code Quality Insights

#### GET `/quality-insights`
Get code quality metrics and insights.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `scope` | string | No | project | Scope (project/directory/file) |
| `path` | string | No | / | Path to analyze |
| `metrics` | string | No | all | Comma-separated metrics to include |

**Response:**
```json
{
    "status": "success",
    "data": {
        "scope": "project",
        "path": "/",
        "insights": {
            "complexity_analysis": {
                "average_cyclomatic_complexity": 4.2,
                "max_cyclomatic_complexity": 25,
                "complexity_hotspots": [
                    {
                        "file": "autobot-user-backend/api/chat.py",
                        "function": "process_complex_request",
                        "complexity": 25,
                        "recommendation": "Break into 3-4 smaller functions",
                        "estimated_improvement": 60
                    }
                ],
                "distribution": {
                    "low": 234,
                    "medium": 45,
                    "high": 12,
                    "very_high": 3
                }
            },
            "duplication_analysis": {
                "duplication_percentage": 12.5,
                "total_duplicate_lines": 1456,
                "most_duplicated_patterns": [
                    {
                        "pattern": "error_handling",
                        "occurrences": 45,
                        "lines_wasted": 540
                    }
                ]
            },
            "maintainability_analysis": {
                "average_maintainability_index": 72,
                "files_below_threshold": 15,
                "top_issues": [
                    {
                        "file": "backend/services/agent_service.py",
                        "maintainability_index": 45,
                        "issues": ["long_functions", "deep_nesting", "no_docstrings"]
                    }
                ]
            },
            "code_smells": {
                "total_smells": 67,
                "by_type": {
                    "long_function": 23,
                    "duplicate_code": 15,
                    "complex_conditional": 12,
                    "deep_nesting": 8,
                    "god_class": 3
                }
            }
        },
        "overall_health": {
            "score": 72,
            "grade": "B",
            "trend": "improving",
            "comparison_to_baseline": "+5"
        },
        "recommendations": [
            {
                "priority": "high",
                "category": "duplication",
                "action": "Extract common error handling patterns",
                "impact": "Reduce codebase by 500+ lines",
                "effort": "4 hours"
            },
            {
                "priority": "medium",
                "category": "complexity",
                "action": "Refactor 5 high-complexity functions",
                "impact": "Improve maintainability by 15%",
                "effort": "8 hours"
            }
        ],
        "metadata": {
            "analysis_timestamp": "2025-10-25T12:00:00Z",
            "files_analyzed": 450,
            "total_loc": 45678,
            "analysis_duration_ms": 3456
        }
    }
}
```

---

### 6. File Vectorization

#### POST `/vectorize/file`
Vectorize a single file (useful for real-time updates).

**Request Body:**
```json
{
    "file_path": "autobot-user-backend/api/new_feature.py",
    "force": false
}
```

**Response:**
```json
{
    "status": "success",
    "data": {
        "file": "autobot-user-backend/api/new_feature.py",
        "embeddings_created": 12,
        "functions_processed": 8,
        "classes_processed": 2,
        "modules_processed": 1,
        "processing_time_ms": 234
    }
}
```

---

### 7. Cache Management

#### DELETE `/cache/clear`
Clear vectorization cache.

**Query Parameters:**
- `scope`: Cache scope (all/embeddings/similarities/metadata)

**Response:**
```json
{
    "status": "success",
    "data": {
        "cleared_items": 4567,
        "freed_memory_mb": 123.4
    }
}
```

---

#### GET `/cache/stats`
Get cache statistics.

**Response:**
```json
{
    "status": "success",
    "data": {
        "embedding_cache": {
            "size_mb": 45.6,
            "entries": 2340,
            "hit_rate": 0.85,
            "avg_age_hours": 12.3
        },
        "similarity_cache": {
            "size_mb": 12.3,
            "entries": 456,
            "hit_rate": 0.92,
            "avg_age_hours": 2.1
        }
    }
}
```

---

## WebSocket API

### Vectorization Progress

**Endpoint:** `wss://172.16.168.20:8443/ws/vectorization/{job_id}`

**Message Types:**

#### Progress Update
```json
{
    "type": "progress",
    "data": {
        "current_file": "autobot-user-backend/api/chat.py",
        "files_processed": 123,
        "total_files": 450,
        "percentage": 27.3,
        "current_operation": "embedding_generation",
        "embeddings_created": 567,
        "estimated_time_remaining": 85
    }
}
```

#### Error Notification
```json
{
    "type": "error",
    "data": {
        "file": "backend/broken_file.py",
        "error": "SyntaxError: invalid syntax",
        "action": "skipped"
    }
}
```

#### Completion
```json
{
    "type": "completed",
    "data": {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "success",
        "summary": {
            "files_processed": 450,
            "embeddings_created": 2340,
            "errors": 3,
            "duration_seconds": 115.4
        }
    }
}
```

---

## Error Responses

All error responses follow this format:

```json
{
    "status": "error",
    "error": {
        "code": "VECTORIZATION_FAILED",
        "message": "Failed to vectorize codebase",
        "details": "ChromaDB connection timeout",
        "timestamp": "2025-10-25T12:00:00Z"
    }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_PARAMETERS` | 400 | Invalid request parameters |
| `FILE_NOT_FOUND` | 404 | Requested file not found |
| `VECTORIZATION_IN_PROGRESS` | 409 | Another vectorization job is running |
| `EMBEDDING_MODEL_ERROR` | 500 | Embedding model failed |
| `CHROMADB_ERROR` | 503 | ChromaDB connection error |
| `TIMEOUT_ERROR` | 504 | Operation timed out |

---

## Rate Limiting

| Endpoint Type | Limit | Window |
|--------------|-------|--------|
| Vectorization | 10 | 1 hour |
| Similarity Search | 1000 | 1 minute |
| Duplicate Detection | 100 | 1 minute |
| Quality Insights | 100 | 1 minute |
| Cache Operations | 50 | 1 minute |

Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Request limit
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: UTC timestamp when limit resets

---

## Pagination

For endpoints returning large result sets:

**Request Parameters:**
- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 20, max: 100)

**Response Headers:**
- `X-Total-Count`: Total number of items
- `X-Page`: Current page
- `X-Per-Page`: Items per page
- `Link`: RFC 5988 links (first, prev, next, last)
