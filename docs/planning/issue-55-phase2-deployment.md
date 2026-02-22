# Issue #55: Phase 2 Deployment Instructions

**Date**: 2025-01-24
**Status**: Ready for Deployment

---

## Deployment Requirements

Phase 2 implementation is complete and tested, but requires backend restart to activate new endpoints.

### New Endpoints to be Activated

1. **POST /api/entities/extract** - Extract entities from single conversation
2. **POST /api/entities/extract-batch** - Batch extraction from multiple conversations
3. **GET /api/entities/extract/health** - Entity extraction service health check
4. **GET /api/graph-rag/search** - Graph-aware RAG search (from Phase 1)

### Deployment Steps

```bash
# 1. Ensure all changes are committed
git status

# 2. Restart backend to load new routers
bash run_autobot.sh --restart

# 3. Wait for backend initialization (Phase 1 + Phase 2 services)
# Expected log messages:
# ✅ [ 87%] Graph-RAG: Graph-aware RAG service initialized successfully
# ✅ [ 88%] Entity Extractor: Entity extractor initialized successfully

# 4. Verify new endpoints are available
curl https://172.16.168.20:8443/api/entities/extract/health

# Expected response:
# {
#   "status": "healthy",
#   "components": {
#     "entity_extractor": "healthy",
#     "knowledge_extraction_agent": "healthy",
#     "memory_graph": "healthy"
#   },
#   "timestamp": "2025-01-24T..."
# }
```

### Verification Test

```bash
# Test entity extraction with sample conversation
curl -X POST https://172.16.168.20:8443/api/entities/extract \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "test-123",
    "messages": [
      {"role": "user", "content": "Redis is timing out"},
      {"role": "assistant", "content": "Fixed by increasing timeout to 30s"}
    ]
  }'

# Expected response:
# {
#   "success": true,
#   "conversation_id": "test-123",
#   "facts_analyzed": <number>,
#   "entities_created": <number>,
#   "relations_created": <number>,
#   "processing_time": <seconds>,
#   "errors": [],
#   "request_id": "<uuid>"
# }
```

### Troubleshooting

**If endpoints not available after restart:**
1. Check backend logs: `tail -f logs/backend.log`
2. Look for Phase 2 initialization messages (87-88%)
3. Verify no import errors for entity_extraction or graph_rag modules

**If entity extractor fails to initialize:**
1. Verify memory_graph initialized successfully (85%)
2. Check KnowledgeExtractionAgent dependencies
3. Review error messages in startup logs

---

## Production Readiness Checklist

- ✅ Unit tests passing (15/15)
- ✅ Error boundaries implemented
- ✅ Graceful degradation configured
- ✅ UTF-8 encoding compliance
- ✅ Dependency injection setup
- ✅ Performance metrics tracking
- ✅ API documentation in OpenAPI spec
- ⏳ Backend restart required
- ⏳ Endpoint verification pending

---

## Rollback Plan

If deployment issues occur:

```bash
# 1. Stop backend
bash run_autobot.sh --stop

# 2. Revert changes
git revert HEAD  # Or specific commit

# 3. Restart backend
bash run_autobot.sh --dev

# 4. Verify core services still working
curl https://172.16.168.20:8443/api/health
```

The new routers are optional - if they fail to load, backend continues with core functionality.
