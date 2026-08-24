---
name: debug-autobot
description: Debug any AutoBot failure across the full stack — dispatches parallel investigators per layer (Vue, FastAPI, Redis, ChromaDB, NPU, Browser, AI Stack), then synthesises their reports into a single root cause. Use for any bug whose layer is unknown, any cross-layer symptom, or when a fix in one layer did not hold.
---

# /debug-autobot - Complete AutoBot Stack Debugging

Investigates bugs across AutoBot's distributed architecture using parallel specialized agents.

## AutoBot Architecture

```
┌─────────────┐
│  Frontend   │ Vue 3 (autobot-user-frontend/)
│  :5173      │
└──────┬──────┘
       ↓ HTTP/WS
┌─────────────┐
│  Backend    │ FastAPI :8001 (autobot-user-backend/)
│  Main       │
└──┬───┬───┬──┘
   │   │   │
   ↓   ↓   ↓
┌─────┐ ┌──────┐ ┌──────────┐
│Redis│ │Chroma│ │NPU Worker│
│:6379│ │ DB   │ │:8081     │
└─────┘ └──────┘ └──────────┘
   ↓
┌──────────┐ ┌──────────┐
│Browser   │ │AI Stack  │
│Worker    │ │:8080     │
│:3000     │ │          │
└──────────┘ └──────────┘
```

## Usage

```bash
/debug-autobot "<symptom>" [--layers <specific layers>]

# Full stack investigation
/debug-autobot "Chat responses are slow"

# Specific layers only
/debug-autobot "NPU inference failing" --layers npu,backend,redis
```

## Investigation Agents

### Agent 1: Frontend (Vue)
**Investigates:**
- Component state/props
- API calls (fetch/axios)
- WebSocket connections
- Browser console errors
- Network tab inspection
- Vue DevTools data

**Common Issues:**
- API endpoint URLs wrong
- WebSocket not connecting
- State not updating
- CORS errors
- Missing error handling

---

### Agent 2: Backend (FastAPI)
**Investigates:**
- API endpoint logic
- Request/response handling
- Authentication/RBAC
- Async operations
- Error handling
- Logging output

**Common Issues:**
- Unhandled exceptions
- Wrong HTTP status codes
- Missing CORS headers
- Async/await issues
- Database connection errors

---

### Agent 3: Redis Stack
**Investigates:**
- Connection status
- Key/value data
- Session storage
- Cache hit/miss rates
- Memory usage
- Slow queries

**Commands:**
```bash
redis-cli -h 172.16.168.23 ping
redis-cli -h 172.16.168.23 info
redis-cli -h 172.16.168.23 keys "*"
redis-cli -h 172.16.168.23 monitor  # Real-time
```

**Common Issues:**
- Connection timeout
- Key expiration too aggressive
- Memory full (maxmemory reached)
- Wrong database selected
- Serialization errors

---

### Agent 4: ChromaDB (Vector Store)
**Investigates:**
- Collection existence
- Embedding dimensions
- Query performance
- Document retrieval
- Similarity search results

**Common Issues:**
- Collection not found
- Embedding dimension mismatch
- Empty results
- Slow queries
- Out of memory

---

### Agent 5: NPU Worker (OpenVINO)
**Investigates:**
- Model loading
- Inference requests
- Queue depth
- NPU utilization
- Model caching

**Health Check:**
```bash
curl http://172.16.168.22:8081/health
```

**Common Issues:**
- Model not loaded
- NPU driver issues
- Queue overflow
- Memory allocation failed
- Wrong model format

---

### Agent 6: Browser Worker (Playwright)
**Investigates:**
- Browser instances
- Automation scripts
- Page load times
- Screenshot generation
- Network requests

**Health Check:**
```bash
curl http://172.16.168.25:3000/health
```

**Common Issues:**
- Browser timeout
- Too many instances
- Page not loading
- Element not found
- Screenshot fails

---

### Agent 7: AI Stack (LLM Services)
**Investigates:**
- LLM API calls
- Token usage
- Response generation
- Prompt formatting
- API rate limits

**Health Check:**
```bash
curl http://172.16.168.24:8080/health
```

**Common Issues:**
- API key invalid
- Rate limit exceeded
- Prompt too long
- Response truncated
- Timeout waiting for completion

---

## Workflow

### 1. Triage: Identify Affected Layers

```bash
# Quick health checks
curl http://localhost:8001/api/health          # Backend
redis-cli -h 172.16.168.23 ping                # Redis
curl http://172.16.168.22:8081/health          # NPU
curl http://172.16.168.25:3000/health          # Browser
curl http://172.16.168.24:8080/health          # AI Stack
```

### 2. Launch Parallel Agents (Affected Layers Only)

**Example: "Chat responses are slow"**

Likely layers: Frontend → Backend → Redis → AI Stack

```python
# Launch 4 parallel investigators
agents = [
    Task(subagent_type="frontend-engineer", ...),  # Check WebSocket, loading states
    Task(subagent_type="senior-backend-engineer", ...),  # Check API performance, async handling
    Task(subagent_type="database-engineer", ...),  # Check Redis latency, caching
    Task(subagent_type="ai-ml-engineer", ...),  # Check LLM API response times
]
```

### 3. Investigation Reports

Each agent provides:

```markdown
## [Layer] Report

**Status:** ✅ Healthy / ⚠️ Degraded / ❌ Failed

**Performance Metrics:**
- Response time: XXms
- Throughput: XX req/s
- Error rate: X%

**Findings:**
1. [What's working correctly]
2. [What's suspicious]
3. [What's definitely broken]

**Root Cause Assessment:**
- Confidence: High/Medium/Low
- Evidence: [Logs, metrics, tests]

**Proposed Fix:**
[If issue is in this layer]
```

### 4. Cross-Layer Analysis

**Common patterns:**

```
Slow responses:
Frontend (200ms) → Backend (1000ms) → Redis (50ms) → AI Stack (5000ms)
                                                        ↑ BOTTLENECK

Authentication fails:
Frontend → Backend → Redis ← User session expired
                      ↑ ROOT CAUSE

NPU inference timeout:
Backend → NPU Worker ← Model not loaded
           ↑ ROOT CAUSE
```

### 5. Create Fix Issue & Implement

```bash
gh issue create --title "Fix: <root cause>" \
  --body "**Symptom:** <original bug>

**Investigation:** Parallel debugging across 4 layers

**Root Cause:** <identified cause with evidence>

**Affected Layer:** <specific component>

**Fix Approach:** <proposed solution>"

/implement <issue-number>
```

## Example: Real AutoBot Bug

### Symptom
"Knowledge retrieval returns empty results even though documents exist"

### Investigation (Parallel)

**Agent: Frontend**
- ✅ Search query is sent correctly
- ✅ API call to /api/knowledge/search
- ✅ No console errors

**Agent: Backend**
```python
# autobot-user-backend/api/knowledge.py
@app.get("/api/knowledge/search")
async def search_knowledge(query: str):
    results = await chromadb_client.query(
        collection_name="documents",
        query_texts=[query],
        n_results=10
    )
    return results  # Returns empty array
```
- ⚠️ ChromaDB query returns empty
- ⚠️ No error handling

**Agent: ChromaDB**
```bash
$ redis-cli -h 172.16.168.23
> KEYS chroma:*
(empty list or set)
```
- ❌ **ROOT CAUSE**: ChromaDB collection "documents" doesn't exist!
- No documents were ever indexed

**Agent: Redis**
- ✅ Redis is healthy
- ✅ Connection working
- ⚠️ No ChromaDB keys found

### Root Cause
**ChromaDB collection was never initialized.** Documents exist in filesystem but weren't indexed.

### Fix
```bash
# Create issue
gh issue create --title "Fix: Initialize ChromaDB collection on startup"

# Implement
/implement <issue>
```

## Multi-Layer Debugging Patterns

| Bug Type | Layers to Check | Typical Root Cause |
|----------|----------------|-------------------|
| **Slow responses** | All layers | AI Stack (LLM latency), NPU (queue depth) |
| **Empty results** | Backend → DB → ChromaDB | Collection empty, wrong query |
| **Authentication fails** | Frontend → Backend → Redis | Session expired, token invalid |
| **NPU errors** | Backend → NPU | Model not loaded, wrong format |
| **Browser automation fails** | Backend → Browser Worker | Timeout, element not found |
| **WebSocket disconnect** | Frontend → Backend | Connection timeout, CORS |

## Success Criteria

- [ ] Symptom clearly described
- [ ] Affected layers identified
- [ ] Parallel agents launched for each layer
- [ ] Each agent completed investigation
- [ ] Reports collected and analyzed
- [ ] Single root cause identified with evidence
- [ ] Fix approach determined
- [ ] Issue created and linked
- [ ] Fix implemented and verified across layers

## Red Flags

- Investigating too many layers (scope creep)
- Agents proposing fixes before root cause found
- No performance metrics collected
- Assuming issue without evidence
- Not testing cross-layer interactions

---

# Synthesis protocol

Carried from the former `debug-stack` skill — the agent-dispatch half above is AutoBot-specific,
this half is how their reports get turned into a root cause.

### 1. Symptom Description

User provides:
- **What's broken:** "Login fails"
- **Expected behavior:** "Should authenticate user"
- **Actual behavior:** "Returns 'Invalid credentials'"
- **Reproduction steps:** "1) Go to /login 2) Enter valid credentials 3) Click submit"

### 3. Collect Investigation Reports

**After all agents complete (5-10 minutes):**

```markdown
## Investigation Summary

### Frontend Report (Agent F)
**Findings:**
- Login form sends POST to /api/auth/login
- Password is sent in plaintext (expected for HTTPS)
- Request format: { "username": "...", "password": "..." }
- No client-side hashing

**Suspicious:**
- None - frontend looks correct

**Root Cause:** NOT in frontend

---

### Backend Report (Agent B)
**Findings:**
- Endpoint: /api/auth/login receives credentials
- Uses bcrypt.checkpw() for password verification
- Retrieves user from database by username
- Error message "Invalid credentials" returned for failed check

**Suspicious:**
- bcrypt.checkpw() returns False even for correct password
- Password hash format in database: $2b$12$...
- Code uses bcrypt.hashpw() for registration

**Root Cause Candidate:**
Password hashing rounds mismatch?
Registration uses 12 rounds, but maybe login expects different format?

**Next Layer:** Check database password hashes

---

### Database Report (Agent D)
**Findings:**
- Users table has password_hash column (VARCHAR(255))
- Test user password hash: $2a$10$... (NOTE: $2a not $2b!)
- Hash was created with older bcrypt version

**Suspicious:**
- Hash prefix is $2a (bcrypt version 2a)
- Backend code expects $2b (bcrypt version 2b)
- Incompatibility between hash versions

**Root Cause:** **DATABASE - Password hashes use old bcrypt version**

Data sample:
```
username: testuser
password_hash: $2a$10$E9F8...  ← OLD VERSION
created_at: 2024-01-15
```
```

### 4. Root Cause Analysis (You Coordinate)

Based on all three reports:

```
ROOT CAUSE: Bcrypt version mismatch
- Database has $2a hashes (old version)
- Backend bcrypt.checkpw() expects $2b (new version)
- Python bcrypt library was upgraded but existing hashes not migrated

SOLUTION OPTIONS:
1. Migrate all password hashes to $2b (requires password reset or migration script)
2. Update backend to accept both $2a and $2b versions
3. Add hash format detection and handle both

RECOMMENDED: Option 2 (backward compatible)
```

## Investigation Report Template

Each agent reports:

```markdown
## [Layer] Investigation Report

**Status:** ✅ Complete / ⚠️ Needs More Info / ❌ Blocked

**Findings:**
1. [What you found]
2. [What you verified]
3. [What you tested]

**Suspicious Items:**
- [Anything unusual]
- [Potential issues]

**Root Cause Assessment:**
- **Is issue in this layer?** YES/NO/MAYBE
- **Confidence:** High/Medium/Low
- **Evidence:** [Why you think so]

**Recommendations:**
- [If issue is here: proposed fix]
- [If not here: which layer to check next]

**Code Snippets:**
```[language]
[Relevant code with line numbers]
```

**Logs/Output:**
```
[Relevant logs, queries, or output]
```
```

## Common Full-Stack Bug Patterns

| Symptom | Frontend Issue | Backend Issue | Database Issue |
|---------|---------------|---------------|----------------|
| **Authentication fails** | Wrong credentials sent | Password comparison broken | Hash format wrong |
| **Data not displaying** | Fetch call broken | API returns wrong data | Query returns empty |
| **Slow performance** | Too many re-renders | N+1 queries | Missing indexes |
| **404 errors** | Wrong route | Endpoint doesn't exist | - |
| **500 errors** | - | Unhandled exception | Connection timeout |
| **Stale data** | Not refetching | Caching too aggressive | Replication lag |

## Red Flags (STOP if you see these)

- Agents investigating wrong components (frontend agent looking at database)
- Agents not sharing context (each assumes different user/test case)
- Agents proposing fixes without identifying root cause
- Multiple "root causes" identified (should be ONE)
- No clear evidence for suspected root cause

## Success Criteria

- [ ] All three layers investigated in parallel
- [ ] Each agent provided detailed report
- [ ] Reports collected and analyzed
- [ ] Single root cause identified with evidence
- [ ] Fix approach determined
- [ ] GitHub issue created for fix
- [ ] Fix implemented and verified

