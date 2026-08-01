# API Response Pattern Migration Guide

**Date**: 2025-01-09
**Status**: ⚠️ SUPERSEDED (2026-07-27, issue #12753) — see below

## Superseded notice

This guide originally documented `autobot-backend/utils/api_responses.py`, a
standardized-response utility that was never adopted by any production
endpoint (zero call sites outside its own test suite, confirmed 2026-07-27).

Fork-convergence issue [#12753](https://github.com/mrveiss/AutoBot-AI/issues/12753)
retired `api_responses.py`. Its unique capabilities (`bad_request`/`conflict`
convenience helpers, the `raise_*` HTTPException-compatible helpers, and
`**kwargs` passthrough for extra top-level fields) were folded into the
already-canonical `autobot-backend/utils/response_builder.py` — the module
actually used in production (`autobot-backend/api/sandbox.py`).

Use `utils.response_builder` going forward:

```python
from utils.response_builder import success_response, error_response, paginated_response

return success_response(data=result, message="Operation completed")
return error_response("Invalid input", status_code=400, error_code="VALIDATION_ERROR")
return paginated_response(items=workflows, total=150, page=2, page_size=20)
```

Function name mapping (`api_responses.py` → `response_builder.py`):

| Old (`api_responses.py`, removed) | New (`response_builder.py`) |
|---|---|
| `success_response()` | `success_response()` (unchanged) |
| `error_response(message, status_code=500, ...)` | `error_response(error, status_code=400, ...)` — note default status differs, always pass `status_code` explicitly |
| `paginated_response()` | `paginated_response()` — pagination keys are `total`/`has_prev` (not `total_items`/`has_previous`) |
| `not_found()` | `not_found_response()` |
| `bad_request()` | `bad_request_response()` |
| `unauthorized()` | `unauthorized_response()` |
| `forbidden()` | `forbidden_response()` |
| `internal_error()` | `server_error_response()` |
| `conflict()` | `conflict_response()` |
| `service_unavailable()` | `service_unavailable_response()` |
| `raise_not_found()` / `raise_bad_request()` / `raise_unauthorized()` / `raise_forbidden()` / `raise_internal_error()` / `raise_conflict()` | Same names, `from utils.response_builder import raise_not_found, ...` |
| `StandardResponse` / `ErrorResponse` / `PaginatedResponse` (Pydantic models, no callers) | Not carried over — use `autobot-backend/api/schemas_common.py` (`DataResponse`, `SuccessMessageResponse`, `SuccessDataResponse`) for typed `response_model=` declarations; see the Response Schema Selection Guide below. |

**Note**: `response_builder.py`'s `success_response`/`error_response`/
`paginated_response` **always** emit the full envelope
(`data`/`message`/`error`/`error_code`/`timestamp`, null-filled where unset) —
unlike the retired `api_responses.py`, which conditionally omitted
`message`/`data`. This was already response_builder's documented behavior
before #12753 and did not change.

Full function reference and usage examples: see the docstring in
`autobot-backend/utils/response_builder.py`.

---

## Response Schema Selection Guide

*Added 2026-04-26 — addresses the root cause of the #5843 → #5896 → #5904 runtime-500
cascade where developers defaulted to `response_model=DataResponse` for all endpoints
without guidance. (#5914)*

### Decision Tree

```
New endpoint — which response_model to use?
│
├── Returns streaming / binary / SSE / WebSocket?
│   └─► response_model=None
│       FastAPI MUST NOT validate streaming or binary responses.
│       Also use None for file downloads (FileResponse) and plain-text
│       status pages.
│
├── Returns JSONResponse / Response / StreamingResponse / FileResponse
│   directly (not a plain dict or Pydantic model)?
│   └─► response_model=None
│       FastAPI skips model validation when the return value is already
│       a Response subclass. Annotating with a schema is misleading and
│       adds no enforcement — use None to be explicit.
│
├── Uses create_success_response() exclusively?
│   └─► response_model=DataResponse
│       DataResponse requires success: bool (no default).
│       create_success_response() always sets it. Any endpoint that does
│       NOT call create_success_response() on every return path will
│       produce a runtime HTTP 500 (see #5843 / #5896 / #5904).
│       The tools/lint/check_response_models.py pre-commit hook enforces
│       this invariant. (#5913)
│
├── Always returns {success: bool, message: str} with no extra fields?
│   └─► response_model=SuccessMessageResponse
│       Imported from autobot-backend/api/schemas_common.py.
│       Use for simple acknowledge / toggle / clear endpoints where no
│       payload beyond success+message is needed.
│
├── Returns {success: bool, message: str, <domain-key>: ...}?
│   ├── The extra data has no fixed schema (generic dict / list)?
│   │   └─► response_model=SuccessDataResponse
│   │       Provides success + message + data: Any.
│   │
│   └── The extra fields have a specific shape (known keys + types)?
│       └─► Define a named schema in schemas_common.py
│           class MyDomainResponse(SuccessMessageResponse):
│               field_one: str
│               field_two: int
│           Inheriting from SuccessMessageResponse avoids redeclaring
│           success and message.  After #5799, place domain schemas in
│           per-domain files instead of schemas_common.py.
│
└── Returns a fully custom shape (no success/message convention)?
    └─► Define a standalone Pydantic BaseModel in schemas_common.py
        (or domain schema file after #5799) and use that directly.
        Preferred for domain-rich responses where success/message
        semantics don't apply (e.g. query results, config snapshots).
```

### Quick Reference

| Situation | response_model |
|-----------|---------------|
| Streaming / SSE / WebSocket | `None` |
| Binary / file download | `None` |
| Returns `JSONResponse` / `Response` directly | `None` |
| Uses `create_success_response()` | `DataResponse` |
| Simple OK/fail, no payload | `SuccessMessageResponse` |
| Success + generic extra data dict | `SuccessDataResponse` |
| Success + typed domain fields | `class X(SuccessMessageResponse): ...` |
| Domain-specific shape, no success convention | Custom `BaseModel` |

### Common Mistakes

**❌ Defaulting to DataResponse for everything**

```python
# WRONG — runtime HTTP 500 if function returns a plain dict
@router.post("/stop", response_model=DataResponse)
async def stop():
    return {"stopped": True}   # missing 'success' key → ValidationError
```

**✅ Use SuccessMessageResponse for simple acknowledgements**

```python
@router.post("/stop", response_model=SuccessMessageResponse)
async def stop():
    return {"success": True, "message": "Stopped"}
```

**❌ Annotating streaming responses with a schema**

```python
# WRONG — FastAPI will attempt to validate the StreamingResponse body
@router.get("/stream", response_model=DataResponse)
async def stream():
    return StreamingResponse(generate())
```

**✅ Use None for streaming**

```python
@router.get("/stream", response_model=None)
async def stream():
    return StreamingResponse(generate())
```

### Enforcement

The `tools/lint/check_response_models.py` pre-commit hook (added in #5913) blocks any
`response_model=DataResponse` endpoint whose body does not call
`create_success_response()`, return a dict literal with a `'success'` key, or return a
bypass response type.  This prevents a recurrence of the #5843/5896/5904 runtime-500
cascade at the point of commit rather than at runtime in production.
