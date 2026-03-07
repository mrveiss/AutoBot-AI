# Service Message Bus Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a unified inter-service message envelope, cross-service audit trail via Redis Streams, and Redis-persisted workflow state machine with explicit routing.

**Architecture:** Three layers — `ServiceMessage` Pydantic schema in `autobot-shared/`, `ServiceMessageBus` wrapping Redis Streams for cross-service pub/sub, and `WorkflowStateMachine` replacing in-memory workflow state with Redis persistence and `route_next()` routing. Extends existing `RedisEventStreamManager` pattern without modifying it.

**Tech Stack:** Pydantic v2, Redis Streams (via existing `autobot_shared.redis_client`), FastAPI, asyncio

**Issues:** #1377, #1379, #1380

**Design doc:** `docs/plans/2026-03-04-service-message-bus-design.md`

---

## Task 1: ServiceMessage Schema (#1377)

**Files:**
- Create: `autobot-shared/models/__init__.py`
- Create: `autobot-shared/models/service_message.py`
- Create: `autobot-shared/models/service_message_test.py`
- Modify: `autobot-shared/__init__.py`

### Step 1: Create models package

Create `autobot-shared/models/__init__.py` exporting `ServiceMessage`, `ServiceName`, `MessageType`.

### Step 2: Write the failing test

Create `autobot-shared/models/service_message_test.py` with 4 tests:
- `test_service_message_defaults` — msg_id, ts, correlation_id auto-generate
- `test_service_message_explicit_correlation` — explicit correlation_id preserved
- `test_service_message_json_roundtrip` — model_dump_json / model_validate_json
- `test_service_message_meta_field` — nested dict in meta

### Step 3: Run test to verify it fails

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest autobot-shared/models/service_message_test.py -v`
Expected: FAIL with `ModuleNotFoundError`

### Step 4: Write ServiceMessage implementation

Create `autobot-shared/models/service_message.py` — Pydantic BaseModel with:
- `msg_id: str` (default: uuid4)
- `ts: str` (default: UTC ISO 8601)
- `sender: str` (ServiceName Literal for known services)
- `receiver: str`
- `msg_type: str` (MessageType Literal)
- `content: str` (JSON payload or text)
- `correlation_id: str` (default: uuid4, pass existing to chain)
- `meta: Dict[str, Any]` (default: empty dict)

### Step 5: Run tests to verify they pass

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest autobot-shared/models/service_message_test.py -v`
Expected: 4 passed

### Step 6: Update autobot-shared exports

Add `ServiceMessage` to `__all__` and `_LAZY_IMPORTS` in `autobot-shared/__init__.py`.

### Step 7: Commit

```bash
git add autobot-shared/models/ autobot-shared/__init__.py
git commit -m "feat(shared): add ServiceMessage schema for cross-service communication (#1377)"
```

---

## Task 2: ServiceMessageBus (#1379)

**Files:**
- Create: `autobot-shared/message_bus.py`
- Create: `autobot-shared/message_bus_test.py`

### Step 1: Write the failing test

Create `autobot-shared/message_bus_test.py` with mock Redis tests:
- `test_publish_stores_message` — hset + xadd + sadd + publish called
- `test_publish_sets_ttl` — expire called for hash + correlation
- `test_get_message` — retrieves and deserializes
- `test_get_message_not_found` — returns None
- `test_get_correlation_chain` — returns all chained messages sorted

### Step 2: Run test to verify it fails

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest autobot-shared/message_bus_test.py -v`
Expected: FAIL with `ModuleNotFoundError`

### Step 3: Write ServiceMessageBus implementation

Create `autobot-shared/message_bus.py`:
- `ServiceMessageBusConfig` dataclass (stream keys, TTLs)
- `ServiceMessageBus` class:
  - `publish(msg)` — hash + stream + correlation set + pub/sub
  - `get_message(msg_id)` — from hash
  - `get_correlation_chain(correlation_id)` — from correlation set
  - `get_latest(count, sender, receiver, msg_type)` — filtered stream
  - `subscribe(sender, receiver, msg_type)` — async pub/sub iterator
  - `close()` — cleanup
- `get_message_bus()` singleton factory
- Redis database: `logs` (via `get_redis_client`)
- Stream: `autobot:service:messages`, max 50k entries
- Message TTL: 14 days, correlation TTL: 7 days

### Step 4: Run tests to verify they pass

Run: `cd /home/kali/Desktop/AutoBot && python -m pytest autobot-shared/message_bus_test.py -v`
Expected: All passed

### Step 5: Commit

```bash
git add autobot-shared/message_bus.py autobot-shared/message_bus_test.py
git commit -m "feat(shared): add ServiceMessageBus for cross-service audit trail (#1379)"
```

---

## Task 3: WorkflowStateMachine (#1380)

**Files:**
- Create: `autobot-backend/api/workflow_state.py`
- Create: `autobot-backend/api/workflow_state_test.py`

### Step 1: Write the failing test

Create `autobot-backend/api/workflow_state_test.py` with:
- Pure function tests: `route_next()` for each step type + done + custom executor
- `WorkflowState` defaults and JSON roundtrip
- Mock Redis tests for `create`, `get`, `transition`, `complete`, `fail`

### Step 2: Run test to verify it fails

Run: `cd /home/kali/Desktop/AutoBot/autobot-backend && python -m pytest api/workflow_state_test.py -v`
Expected: FAIL with `ModuleNotFoundError`

### Step 3: Write WorkflowStateMachine implementation

Create `autobot-backend/api/workflow_state.py`:
- `WorkflowState` Pydantic model (workflow_id, goal, current_step, active_service, steps_completed, steps_remaining, done, errors, created_at, updated_at, metadata)
- `route_next(state)` — returns service name based on current_step + metadata
- `WorkflowStateMachine` class:
  - `create(workflow_id, goal, steps)` — creates + persists + adds to active set
  - `get(workflow_id)` — retrieves from Redis
  - `transition(workflow_id, new_step, result)` — updates step + persists
  - `complete(workflow_id)` — marks done + removes from active + sets 7d TTL
  - `fail(workflow_id, error)` — marks failed + appends error
  - `list_active()` — returns all active workflows
- `get_workflow_state_machine()` singleton factory
- Redis database: `workflows`
- Key pattern: `autobot:workflow:{workflow_id}`
- Active set: `autobot:workflow:active`

### Step 4: Run tests to verify they pass

Run: `cd /home/kali/Desktop/AutoBot/autobot-backend && python -m pytest api/workflow_state_test.py -v`
Expected: All passed

### Step 5: Commit

```bash
git add autobot-backend/api/workflow_state.py autobot-backend/api/workflow_state_test.py
git commit -m "feat(workflow): add Redis-persisted WorkflowStateMachine with route_next (#1380)"
```

---

## Task 4: Integrate into workflow.py (#1380)

**Files:**
- Modify: `autobot-backend/api/workflow.py`

### Step 1: Add import

Add `from api.workflow_state import get_workflow_state_machine` at top of `workflow.py`.

### Step 2: Update list_active_workflows

Update `list_active_workflows()` (line 375) to query both `WorkflowStateMachine.list_active()` and legacy in-memory dict. Redis results take precedence.

### Step 3: Verify no import errors

Run: `cd /home/kali/Desktop/AutoBot/autobot-backend && python -c "from api.workflow import router; print('OK')"`
Expected: `OK`

### Step 4: Commit

```bash
git add autobot-backend/api/workflow.py
git commit -m "feat(workflow): integrate WorkflowStateMachine into workflow listing (#1380)"
```

---

## Task 5: Final Verification

### Step 1: Run all new tests

```bash
cd /home/kali/Desktop/AutoBot
python -m pytest autobot-shared/models/service_message_test.py autobot-shared/message_bus_test.py -v
cd autobot-backend && python -m pytest api/workflow_state_test.py -v
```

### Step 2: Pre-commit checks

Verify all files pass linting and function length checks.

### Step 3: Update GitHub issues

Comment on #1377, #1379, #1380 with implementation summary. Leave open — full adoption is follow-up.
