# Week 1 Implementation - Quick Start Guide

**Use this when agent session resets (after 7pm)**

---

## ✅ Pre-Flight Checklist

### System Status
- [x] Backend running: http://172.16.168.20:8001
- [x] Frontend running: http://172.16.168.21:5173
- [x] Redis running: 172.16.168.23:6379
- [x] All VMs accessible
- [x] Implementation guide created: `planning/tasks/week-1-database-initialization-detailed-guide.md`
- [x] Memory MCP entities created
- [x] TODO list updated

### Documentation Ready
- [x] 5-week master plan: `planning/tasks/backend-vulnerabilities-implementation-plan.md`
- [x] Week 1 detailed guide: `planning/tasks/week-1-database-initialization-detailed-guide.md`
- [x] Status tracker: `planning/BACKEND_VULNERABILITIES_FIX_STATUS.md`
- [x] Architecture analysis: `docs/architecture/BACKEND_CRITICAL_ISSUES_ARCHITECTURAL_ANALYSIS.md`

---

## 🚀 Launch Commands (Copy-Paste Ready)

### Step 1: Launch Database Engineer Agent

```
Task(
    subagent_type="database-engineer",
    description="Database schema initialization",
    prompt="""**WEEK 1 - TASKS 1.1, 1.2, 1.3: Database Schema Initialization**

**Read the complete implementation guide:**
File: /home/kali/Desktop/AutoBot/planning/tasks/week-1-database-initialization-detailed-guide.md

**Your Tasks:**

1. **Task 1.1: Schema Initialization Method (4 hours)**
   - Add `initialize()` method to `ConversationFileManager` class
   - Implement idempotent schema initialization
   - See guide for complete code

2. **Task 1.2: Schema Versioning System (6 hours)**
   - Implement `_get_schema_version()`
   - Implement `_set_schema_version()`
   - Implement `_apply_schema()`
   - Implement `_apply_migrations()`
   - Implement `_verify_schema_integrity()`
   - See guide for complete implementations

3. **Task 1.3: Health Check Integration (3 hours)**
   - Update health check endpoint in `autobot-user-backend/api/system.py`
   - Report database status and schema version
   - See guide for complete code

**Files to Modify:**
- `src/conversation_file_manager.py` - Add all initialization methods
- `autobot-user-backend/api/system.py` - Update health check endpoint

**Success Criteria:**
- All 5 required tables created automatically
- Schema version tracked in database
- Health check reports DB status
- Idempotent execution (safe to run multiple times)

**Reference Guide:** /home/kali/Desktop/AutoBot/planning/tasks/week-1-database-initialization-detailed-guide.md
"""
)
```

### Step 2: Launch Backend Engineer Agent

```
Task(
    subagent_type="senior-backend-engineer",
    description="Backend startup integration",
    prompt="""**WEEK 1 - TASK 1.4: Backend Startup Integration**

**Read the complete implementation guide:**
File: /home/kali/Desktop/AutoBot/planning/tasks/week-1-database-initialization-detailed-guide.md

**Your Task:**

Integrate database initialization into backend startup sequence in `backend/app_factory.py`.

**Implementation:**

Add startup event handler that:
1. Calls `await app.state.conversation_file_manager.initialize()`
2. Handles initialization errors (prevents startup if DB init fails)
3. Logs initialization progress
4. Verifies database is ready before serving requests

**Two Options:**

Option 1: Lifespan manager (preferred)
Option 2: @app.on_event("startup") decorator

See guide for complete implementations of both options.

**Files to Modify:**
- `backend/app_factory.py` - Add startup initialization

**Success Criteria:**
- Database initialization called during backend startup
- Backend refuses to start if DB init fails
- Clear startup progress logging
- Health check accessible after startup

**Reference Guide:** /home/kali/Desktop/AutoBot/planning/tasks/week-1-database-initialization-detailed-guide.md
"""
)
```

### Step 3: Launch Testing Engineer Agent

```
Task(
    subagent_type="testing-engineer",
    description="Database initialization tests",
    prompt="""**WEEK 1 - TASKS 1.5, 1.6: Comprehensive Testing**

**Read the complete implementation guide:**
File: /home/kali/Desktop/AutoBot/planning/tasks/week-1-database-initialization-detailed-guide.md

**Your Tasks:**

1. **Task 1.5: Unit Tests (4 hours)**
   - Create `tests/unit/test_conversation_file_manager.py`
   - Implement 6+ test cases covering all scenarios
   - See guide for complete test implementations

2. **Task 1.6: Distributed Integration Tests (3 hours)**
   - Create `tests/distributed/test_db_initialization.py`
   - Test cross-VM scenarios (NPU Worker, Browser, Frontend)
   - Test concurrent initialization safety
   - See guide for complete test implementations

**Test Cases Required:**

Unit Tests:
- test_first_time_initialization
- test_idempotent_initialization
- test_schema_version_tracking
- test_integrity_verification_passes
- test_integrity_verification_fails_missing_table
- test_schema_migration_framework

Integration Tests:
- test_fresh_vm_deployment
- test_npu_worker_file_upload
- test_browser_screenshot_save
- test_frontend_file_upload
- test_concurrent_initialization_safe

**Coverage Target:** 100% for initialization code

**Reference Guide:** /home/kali/Desktop/AutoBot/planning/tasks/week-1-database-initialization-detailed-guide.md
"""
)
```

---

## 📋 Execution Checklist

When launching agents:

1. **Launch All 3 Agents in Single Message** (parallel execution)
   - Copy all 3 Task() calls above
   - Send in single message to maximize parallelism

2. **Monitor Progress**
   - Check Memory MCP for agent updates
   - Track TODO list changes
   - Watch for agent completion reports

3. **Agent Completion Verification**
   - Database engineer completes Tasks 1.1, 1.2, 1.3
   - Backend engineer completes Task 1.4
   - Testing engineer completes Tasks 1.5, 1.6

4. **Code Review** (After all agents complete)
   - Launch `code-reviewer` agent
   - Verify all implementations
   - Check test coverage reports

5. **Testing Validation**
   - Run unit tests: `pytest tests/unit/test_conversation_file_manager.py -v`
   - Run integration tests: `pytest tests/distributed/test_db_initialization.py -v -m integration`
   - Verify 100% coverage for initialization code

6. **Week 1 Completion**
   - Update Memory MCP observations
   - Mark Week 1 as completed in TODO list
   - Update status tracker
   - Prepare Week 2 launch

---

## 🎯 Success Criteria Verification

After implementation, verify these criteria:

### Database Initialization
- [ ] `ConversationFileManager.initialize()` method exists
- [ ] Schema loaded from `database/schemas/conversation_files_schema.sql`
- [ ] All 5 tables created: conversation_files, file_metadata, session_file_associations, file_access_log, file_cleanup_queue
- [ ] Schema version table created and populated
- [ ] Idempotent execution (can call multiple times safely)

### Backend Integration
- [ ] `backend/app_factory.py` calls initialization during startup
- [ ] Backend refuses to start if initialization fails
- [ ] Startup logs show initialization progress
- [ ] Health check endpoint reports database status

### Testing Coverage
- [ ] Unit tests created in `tests/unit/test_conversation_file_manager.py`
- [ ] Integration tests created in `tests/distributed/test_db_initialization.py`
- [ ] All tests passing
- [ ] 100% code coverage for initialization code

### Operational Verification
- [ ] Fresh deployment scenario tested
- [ ] Existing deployment scenario tested
- [ ] All 6 VMs can perform file operations
- [ ] Health check accessible: `curl http://172.16.168.20:8001/api/health`

---

## 🔍 Quick Verification Commands

After implementation, run these to verify success:

```bash
# 1. Test fresh database initialization
rm -f /home/kali/Desktop/AutoBot/data/conversation_files.db
bash run_autobot.sh --restart
# Check logs for "Database initialized with schema version 1.0.0"

# 2. Verify all tables created
sqlite3 /home/kali/Desktop/AutoBot/data/conversation_files.db ".tables"
# Should show: conversation_files, file_access_log, file_cleanup_queue, file_metadata, schema_version, session_file_associations

# 3. Check schema version
sqlite3 /home/kali/Desktop/AutoBot/data/conversation_files.db "SELECT * FROM schema_version;"
# Should show: 1.0.0

# 4. Test health check
curl http://172.16.168.20:8001/api/health
# Should show database status as "healthy"

# 5. Run unit tests
pytest tests/unit/test_conversation_file_manager.py -v --cov=src.conversation_file_manager

# 6. Run integration tests
pytest tests/distributed/test_db_initialization.py -v -m integration

# 7. Test file upload (end-to-end)
curl -X POST http://172.16.168.20:8001/api/files/conversation/upload \
  -F "file=@test.txt" \
  -F "session_id=test-session"
```

---

## 📊 Expected Timeline

**Total Time:** 22 hours (5 days with parallel execution)

- **Days 1-2:** Implementation (agents working)
  - Database engineer: Tasks 1.1, 1.2, 1.3 (13 hours)
  - Backend engineer: Task 1.4 (2 hours) - can start after 1.1
  - Testing engineer: Tasks 1.5, 1.6 (7 hours) - can start after 1.2

- **Day 3:** Code review and validation
  - Code review by code-reviewer agent
  - Run comprehensive test suite
  - Fix any issues identified

- **Day 4:** Staging deployment
  - Deploy to staging environment
  - Test fresh deployment scenario
  - Verify all success criteria

- **Day 5:** Production deployment
  - Deploy during maintenance window
  - Monitor initialization logs
  - Verify all 6 VMs operational

---

## 🚨 Troubleshooting

### If agents fail to launch:
- Check agent session limit status
- Retry at 7pm or later
- Verify system requirements met

### If implementation has errors:
- Check detailed guide for correct implementations
- Verify all imports added
- Ensure async/await patterns correct
- Review agent error messages

### If tests fail:
- Check database file permissions
- Verify schema file exists at correct path
- Ensure Redis is running (for integration tests)
- Review test output for specific failures

---

## 📁 Key Files Reference

**Implementation Guides:**
- Master plan: `planning/tasks/backend-vulnerabilities-implementation-plan.md`
- Week 1 guide: `planning/tasks/week-1-database-initialization-detailed-guide.md`
- Status tracker: `planning/BACKEND_VULNERABILITIES_FIX_STATUS.md`
- This quick-start: `planning/WEEK_1_QUICK_START.md`

**Files to Modify:**
- `src/conversation_file_manager.py` - Database initialization
- `backend/app_factory.py` - Startup integration
- `autobot-user-backend/api/system.py` - Health check
- `tests/unit/test_conversation_file_manager.py` - Unit tests (NEW)
- `tests/distributed/test_db_initialization.py` - Integration tests (NEW)

**Schema Files:**
- `database/schemas/conversation_files_schema.sql` - Database schema

---

**Ready to proceed when agent session resets at 7pm.**

**Next command:** Copy and paste all 3 Task() calls above into a single message to launch agents in parallel.
