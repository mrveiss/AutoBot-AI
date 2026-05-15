# AutoBot API Versioning Strategy

This document defines the API versioning strategy, stability guarantees, and deprecation policy for the AutoBot public API.

---

## Versioning Scheme

AutoBot uses **URL path versioning** for its public API:

```
https://<autobot-host>:8443/api/v1/chat
https://<autobot-host>:8443/api/v1/knowledge_base/query
https://<autobot-host>:8443/api/v1/agent/goal
```

The version identifier (`v1`, `v2`, etc.) is the first path segment after `/api/`.

### Why URL Path Versioning

- Explicit and visible in every request
- Easy to route at the load balancer / reverse proxy level
- Simple to test with curl and browser
- No ambiguity about which version is being called

### Current State

| Path | Status | Description |
|------|--------|-------------|
| `/api/...` | Internal | Current unversioned endpoints (internal use) |
| `/api/v1/...` | Planned | First stable public API release |

The `/api/v1/` prefix will be a gateway layer that maps to the existing internal endpoints. Internal endpoints will continue to work without the version prefix for backward compatibility.

---

## Stability Guarantees

### Stable (v1+)

Endpoints under a versioned path (`/api/v1/`) have the following guarantees:

1. **No breaking changes** within a major version
2. **Additive changes only** -- new fields in responses, new optional parameters, new endpoints
3. **Minimum 12-month support** after a new major version is released
4. **Deprecation warnings** at least 6 months before removal

### What Counts as a Breaking Change

The following are considered breaking changes and will only occur in a new major version:

- Removing an endpoint
- Removing a field from a response
- Changing a field's type in a response
- Making a previously optional request parameter required
- Changing the URL path of an endpoint
- Changing authentication requirements
- Changing error response format
- Reducing rate limits below documented minimums

### What Is NOT a Breaking Change

The following may happen within a major version:

- Adding new fields to response objects
- Adding new optional request parameters
- Adding new endpoints
- Adding new enum values to existing fields
- Increasing rate limits
- Improving error messages (while keeping the error code stable)
- Fixing bugs that caused incorrect responses

---

## Deprecation Policy

### Deprecation Lifecycle

```
Active  -->  Deprecated  -->  Sunset  -->  Removed
 (v1)        (v1 + notice)   (v1 off)     (v1 gone)
              6 months min    3 months     after sunset
```

### Step 1: Deprecation Notice

When an endpoint or version is deprecated:

1. Response headers include a `Deprecation` header:
   ```
   Deprecation: true
   Sunset: Sat, 01 Mar 2027 00:00:00 GMT
   Link: <https://docs.autobot.dev/api/v2/migration>; rel="successor-version"
   ```

2. The endpoint continues to work normally
3. Documentation is updated with deprecation notice
4. Changelog and release notes announce the deprecation

### Step 2: Sunset Period

During the sunset period:

1. The deprecated endpoint still works but returns warning headers
2. Usage metrics are monitored to identify remaining consumers
3. SDK packages emit deprecation warnings in logs
4. Migration guides are available

### Step 3: Removal

After the sunset date:

1. The endpoint returns HTTP 410 Gone:
   ```json
   {
     "error": "endpoint_removed",
     "message": "This endpoint was removed on 2027-03-01. Use /api/v2/chat instead.",
     "migration_guide": "https://docs.autobot.dev/api/v2/migration"
   }
   ```
2. After 3 additional months, the endpoint returns HTTP 404

---

## Version Negotiation

### Explicit Version (Recommended)

Include the version in the URL path:

```
GET /api/v1/llm/models
```

### Default Version

Requests to the unversioned path (`/api/...`) hit the internal API directly. This path is not covered by stability guarantees and may change without notice. External developers should always use versioned paths.

---

## Migration Between Versions

When a new major version is released, a migration guide will be published at:

```
docs/api/migration-v1-to-v2.md
```

Migration guides will include:

1. **Summary of breaking changes** with before/after examples
2. **Automated migration tools** where feasible (SDK version bumps)
3. **Compatibility shims** for common patterns
4. **Timeline** with key dates

### SDK Version Mapping

| API Version | Python SDK | TypeScript SDK |
|-------------|------------|----------------|
| v1 | autobot-sdk 1.x | @autobot/sdk 1.x |
| v2 (future) | autobot-sdk 2.x | @autobot/sdk 2.x |

---

## Changelog

API changes are tracked in the main project changelog (`CHANGELOG.md`) and in a dedicated API changelog:

```
docs/api/CHANGELOG.md
```

Each entry includes:

- **Date** of the change
- **Type**: Added, Changed, Deprecated, Removed, Fixed
- **Endpoint(s)** affected
- **Description** of the change
- **Migration notes** if applicable

---

## Headers Reference

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <token>` or `Bearer <api-key>` |
| `Content-Type` | Yes (POST/PUT) | `application/json` or `multipart/form-data` |
| `Accept` | No | `application/json` (default) or `text/event-stream` |
| `X-Request-ID` | No | Client-generated request ID for tracing |

### Response Headers

| Header | Description |
|--------|-------------|
| `X-Request-ID` | Echo of client request ID, or server-generated |
| `X-RateLimit-Limit` | Rate limit ceiling |
| `X-RateLimit-Remaining` | Remaining requests in window |
| `X-RateLimit-Reset` | Window reset time (Unix timestamp) |
| `Deprecation` | Present if endpoint is deprecated |
| `Sunset` | Date when deprecated endpoint will be removed |
