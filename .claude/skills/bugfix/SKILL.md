---
name: bugfix
description: Autonomous test-driven bug fixing with iterative fix-verify loops
---

# Autonomous Bug-Fixing Pipeline

Systematically debug and fix issues using a test-driven loop: analyze error → hypothesize root cause → implement minimal fix → verify → repeat until all tests pass.

## When to Use This

**Good use cases:**
- Failing test suite (unit, integration, E2E)
- Reproducible runtime errors with clear error messages
- Regression bugs caught by CI/CD
- 500 errors with stack traces in logs
- Performance degradations with measurable metrics

**Bad use cases:**
- Intermittent/flaky failures (need manual investigation first)
- Issues without clear reproduction steps
- Architectural problems requiring design decisions
- Security vulnerabilities requiring user approval

## Input Requirements

You must provide ONE of:
1. **GitHub issue URL or number** - e.g., `/bugfix 123` or `/bugfix https://github.com/mrveiss/AutoBot-AI/issues/123`
2. **Error log or stack trace** - paste directly
3. **Failing test command** - e.g., `pytest tests/test_redis.py::test_connection`

## Autonomous Fix Loop

**Maximum 5 iterations.** If not fixed after 5 attempts, stop and escalate to user.

### Iteration N (repeat until tests pass)

#### Step 1: Run Tests & Capture Failure

```bash
# For Python backend
python -m pytest tests/ -x -v --tb=short 2>&1 | tee /tmp/test_output.txt

# For TypeScript frontend
cd autobot-user-frontend && npm test 2>&1 | tee /tmp/test_output.txt

# For specific test file
python -m pytest tests/test_specific.py -v --tb=long 2>&1 | tee /tmp/test_output.txt
```

**Capture:**
- Which test(s) failed
- Error message and type
- Stack trace (full traceback)
- Line numbers where failure occurred

#### Step 2: Analyze Failure & Form Hypothesis

**Read the error output carefully:**

```
FAILED tests/redis_test.py::test_connection - ConnectionRefusedError: [Errno 111] Connection refused
  File "/opt/autobot/autobot_shared/redis_client.py", line 45, in get_redis_client
    client = redis.Redis(host=host, port=port)
```

**Form a 1-2 sentence hypothesis:**

Example hypotheses:
- "Redis host is hardcoded to 'localhost' instead of using SSOT config"
- "Database migration for column 'user_id' hasn't been applied"
- "Frontend API client is calling old /api/v1/ instead of /api/v2/"
- "Async function not being awaited in sync context"
- "Import path still uses old 'from src.' instead of colocated structure"

**State your hypothesis in this format:**
```
🔍 Iteration N Hypothesis:
[Your 1-2 sentence hypothesis]

Root cause: [specific file:line]
Expected fix: [what needs to change]
```

#### Step 3: Investigate Root Cause

**Read relevant source files:**

```bash
# Read the file mentioned in stack trace
Read: /opt/autobot/autobot_shared/redis_client.py

# Search for related code
Grep: "redis.Redis" in autobot-shared/
Glob: "**/*redis*.py"

# Check recent changes
git log --oneline -10 -- path/to/file.py
```

**Verify your hypothesis:**
- Does the code match what you expected?
- Are there related issues in nearby code?
- Was this broken by a recent change?

#### Step 4: Implement Minimal Fix

**CRITICAL: Make the SMALLEST possible change to fix the specific failure.**

❌ **Do NOT:**
- Refactor surrounding code
- Add new features or "improvements"
- Fix unrelated issues
- Add extensive error handling "just in case"
- Reorganize imports or file structure

✅ **DO:**
- Fix ONLY the specific issue causing the test failure
- Use existing patterns from the codebase
- Follow CLAUDE.md guidelines (SSOT config, no hardcoding, etc.)
- Preserve existing functionality

**Example fixes:**

```python
# WRONG: Over-engineered fix
def get_redis_client():
    try:
        config = load_config_with_fallback()
        if config.redis.host:
            host = config.redis.host
        else:
            host = os.getenv("REDIS_HOST", "localhost")
    except Exception as e:
        logger.error(f"Config error: {e}")
        host = "localhost"
    # ... 20 more lines

# RIGHT: Minimal fix
def get_redis_client():
    from autobot_shared.ssot_config import config
    return redis.Redis(host=config.redis.host, port=config.redis.port)
```

**Use Edit tool for existing files:**

```python
Edit(
    file_path="autobot_shared/redis_client.py",
    old_string='client = redis.Redis(host="localhost", port=6379)',
    new_string='client = redis.Redis(host=config.redis.host, port=config.redis.port)'
)
```

#### Step 5: Re-run Tests

```bash
# Run the SAME test command as Step 1
python -m pytest tests/ -x -v --tb=short 2>&1 | tee /tmp/test_output.txt
```

**Analyze results:**

**If tests PASS:** → Go to Step 6 (Commit)

**If tests FAIL with SAME error:**
- Your fix didn't address the root cause
- Re-read error message carefully
- Form a NEW hypothesis
- Loop back to Step 2 (Iteration N+1)

**If tests FAIL with DIFFERENT error:**
- Good! You fixed the original issue
- But introduced a new issue or uncovered another bug
- Form hypothesis for the NEW error
- Loop back to Step 2 (Iteration N+1)

#### Step 6: Commit the Fix (only when tests pass)

```bash
git add <files-you-changed>

git commit -m "fix: <concise description of what was broken> (#issue-number)

Root cause: <1 sentence explaining the bug>
Fix: <1 sentence explaining the solution>

- Fixed: <specific error that was happening>
- Changed: <what you modified>
- Tests: <which tests now pass>

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# Verify commit
git log -1 --stat
git diff  # Should be empty
```

## After Fix Loop Completes

### Success Path (tests pass within 5 iterations)

**Report to user:**

```
✅ Bug fixed successfully in N iterations

Root Cause:
[1-2 sentence explanation of what was actually broken]

Fix Applied:
[1-2 sentence explanation of what you changed]

Files Changed:
- path/to/file1.py (+3, -1)
- path/to/file2.py (+5, -2)

Iterations Needed: N of 5

Test Results:
✅ All tests passing
✅ No new failures introduced
✅ Changes committed

Next Steps:
- Review the commit if needed
- Push the branch: git push origin <branch>
- Create PR or merge to Dev_new_gui
```

### Failure Path (5 iterations exhausted, tests still failing)

**Report to user:**

```
❌ Unable to fix bug automatically after 5 iterations

Current Status:
[What error is still happening]

Hypotheses Tried:
1. [First hypothesis] - Result: [what happened]
2. [Second hypothesis] - Result: [what happened]
...
5. [Fifth hypothesis] - Result: [what happened]

Remaining Issue:
[What's still broken and why it's complex]

Recommendation:
This bug requires manual investigation because:
- [Reason 1: e.g., "Root cause spans multiple files"]
- [Reason 2: e.g., "Architecture decision needed"]
- [Reason 3: e.g., "Test failures are intermittent"]

Files to Investigate:
- path/to/file1.py:45 (where error originates)
- path/to/file2.py:120 (related code)

Suggested Next Steps:
1. [Specific action user should take]
2. [Another specific action]
```

## Deployment Verification (if applicable)

**If the bug was discovered in production:**

After tests pass locally, verify the fix works on remote server:

```bash
# Deploy using /deploy skill
/deploy main

# Verify the original error is gone
ssh autobot@172.16.168.20 "journalctl -u autobot-backend --since '1 hour ago' | grep 'ConnectionRefusedError' || echo 'Error is gone'"

# Hit the affected endpoint
curl -s http://172.16.168.20:8001/api/health | jq

# Check for new errors
ssh autobot@172.16.168.20 "journalctl -u autobot-backend --since '1 minute ago' | grep -i error || echo 'No new errors'"
```

## Guardrails

**If you notice related bugs during fixing:**
- Create separate GitHub issues for them
- Do NOT fix them in this iteration
- Stay focused on the single failing test

**If the fix requires architectural changes:**
- STOP after iteration 2
- Explain why architecture decision is needed
- Ask user how to proceed

**If tests are flaky (pass/fail randomly):**
- STOP after iteration 1
- Report that tests are flaky
- Recommend investigating test stability first

**If multiple unrelated tests are failing:**
- Pick the FIRST failure only
- Fix it completely
- Then run this skill again for the next failure

## Success Criteria

✅ All tests passing (or at least the originally failing test)
✅ No new test failures introduced
✅ Fix is minimal (no refactoring, no feature additions)
✅ Root cause identified and documented
✅ Changes committed with clear message
✅ Deployment verified (if production bug)

## Common Bug Patterns & Quick Fixes

**Pattern: Hardcoded IP/config**
- Search for: Hardcoded IPs, ports, passwords
- Fix: Use `from autobot_shared.ssot_config import config`

**Pattern: Stale import paths**
- Search for: `from src.` imports
- Fix: Use colocated imports (file next to file)

**Pattern: Missing database migration**
- Run: `alembic upgrade head`
- Check: `alembic current`

**Pattern: Async/await mismatch**
- Error: "coroutine was never awaited"
- Fix: Add `await` or use `asyncio.run()`

**Pattern: Missing dependency**
- Error: "ModuleNotFoundError"
- Fix: Check if package is in requirements.txt and installed in venv

**Pattern: Wrong endpoint URL**
- Search for: Old API paths (`/api/v1/`, `/api/control/`)
- Fix: Update to current API paths

## Performance Tracking

Track your bugfix pipeline performance:

```
Session Stats:
- Bugs fixed: N
- Average iterations per bug: M
- Success rate: X%
- Most common root causes: [list]
```

Store in memory MCP after each session.

## Example Session

```
User: /bugfix 845

[Iteration 1]
🔍 Hypothesis: Redis connection using hardcoded localhost instead of SSOT config
Root cause: autobot_shared/redis_client.py:45
Expected fix: Import and use config.redis.host

[Implements minimal fix]
[Re-runs tests]

❌ FAILED - Different error now: "redis.exceptions.AuthenticationError"

[Iteration 2]
🔍 Hypothesis: Redis password not being passed to connection
Root cause: Same file, missing password parameter
Expected fix: Add password=config.redis.password

[Implements fix]
[Re-runs tests]

✅ PASSED - All tests passing

✅ Bug fixed successfully in 2 iterations

Root Cause:
Redis client was using hardcoded localhost and missing password parameter

Fix Applied:
Updated redis_client.py to use SSOT config for host, port, and password

Files Changed:
- autobot_shared/redis_client.py (+2, -1)

Iterations Needed: 2 of 5
```
