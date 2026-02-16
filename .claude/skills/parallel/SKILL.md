---
name: parallel
description: Safely dispatch parallel agents to work on multiple issues simultaneously with worktree isolation
---

# Parallel Agent Dispatch

Orchestrate multiple Claude agents to work on separate GitHub issues simultaneously using isolated git worktrees. Includes permission validation, single-agent testing, and automatic fallback to sequential implementation.

## When to Use This

**Good use cases:**
- Implementing 3-6 independent GitHub issues that don't touch overlapping code
- Bulk fixes across separate modules (e.g., linting violations in different services)
- Parallel feature development where changes are isolated

**Bad use cases:**
- Issues that touch the same files or modules
- Issues with dependencies on each other
- Complex architectural changes requiring coordination
- Single issue that needs focused attention

## Pre-Flight Validation (MANDATORY)

Before dispatching ANY agents:

### 1. Verify Worktree Base Directory

```bash
# Check if worktree base exists
WORKTREE_BASE="../worktrees"
if [[ ! -d "$WORKTREE_BASE" ]]; then
    echo "Creating worktree base directory: $WORKTREE_BASE"
    mkdir -p "$WORKTREE_BASE"
fi

# Verify permissions
if [[ ! -w "$WORKTREE_BASE" ]]; then
    echo "❌ STOP: Worktree base is not writable"
    echo "Fix: chmod 755 $WORKTREE_BASE"
    exit 1
fi

echo "✅ Worktree base ready: $WORKTREE_BASE"
```

### 2. Verify Git Configuration

```bash
# Check git user config (required for commits)
if ! git config user.name >/dev/null || ! git config user.email >/dev/null; then
    echo "❌ STOP: Git user not configured in worktrees"
    echo "Fix: git config --global user.name 'Your Name'"
    echo "     git config --global user.email 'your@email.com'"
    exit 1
fi

echo "✅ Git config ready"
```

### 3. List Target Issues

Ask user to confirm the issues to implement:

```
I'll implement these issues in parallel:
- Issue #123: Add user authentication
- Issue #456: Fix Redis connection pooling
- Issue #789: Update frontend dashboard

Each will work in an isolated worktree. Proceed? (yes/no)
```

Wait for user confirmation before proceeding.

### 4. Verify No File Overlap

```bash
# For each issue, check if they touch overlapping files
# This is a manual check - ask user:

"Do any of these issues modify the same files or modules?
If unsure, I'll test with a single agent first."
```

## Single Agent Test (MANDATORY)

**Never skip this step.** Always test with ONE agent before spawning multiple.

### 5. Create Test Worktree

```bash
TEST_ISSUE="123"  # First issue from the list
WORKTREE_PATH="../worktrees/issue-${TEST_ISSUE}"

# Remove if exists from previous failed attempt
if [[ -d "$WORKTREE_PATH" ]]; then
    git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || rm -rf "$WORKTREE_PATH"
fi

# Create fresh worktree from Dev_new_gui
git worktree add "$WORKTREE_PATH" Dev_new_gui

# Verify creation
if [[ ! -d "$WORKTREE_PATH/.git" ]]; then
    echo "❌ STOP: Worktree creation failed"
    echo "Falling back to sequential implementation"
    exit 1
fi

echo "✅ Test worktree created: $WORKTREE_PATH"
```

### 6. Spawn Single Test Agent

```bash
# Use Task tool with single agent
Task(
    subagent_type="senior-backend-engineer",
    description=f"Test agent for issue #{TEST_ISSUE}",
    prompt=f"""
    You are working in an isolated worktree at: {WORKTREE_PATH}

    Implement GitHub issue #{TEST_ISSUE}:
    1. cd {WORKTREE_PATH}
    2. Verify you can read/write files
    3. Create a feature branch: git checkout -b fix/issue-{TEST_ISSUE}
    4. Make one small change (add a comment to verify write access)
    5. git add . && git commit -m "test: verify worktree works (#{TEST_ISSUE})"
    6. Report success or failure

    If ANY step fails (permission error, git error), report immediately and exit.
    Do NOT continue if errors occur.
    """
)
```

### 7. Evaluate Test Results

Wait for test agent to complete, then:

```bash
# Check if test commit succeeded
cd "$WORKTREE_PATH"
if git log -1 --oneline | grep -q "test: verify worktree"; then
    echo "✅ Test agent succeeded - parallel dispatch is safe"
    PARALLEL_SAFE=true
else
    echo "❌ Test agent failed - falling back to sequential"
    PARALLEL_SAFE=false
fi

# Clean up test worktree
cd - && git worktree remove "$WORKTREE_PATH" --force
```

**If test fails:** Skip to Fallback Sequential Implementation section below.

## Parallel Agent Dispatch

**Only proceed if test agent succeeded.**

### 8. Create Worktrees for All Issues

```bash
ISSUES=(123 456 789)  # From user's list

for ISSUE in "${ISSUES[@]}"; do
    WORKTREE_PATH="../worktrees/issue-${ISSUE}"

    # Clean up if exists
    [[ -d "$WORKTREE_PATH" ]] && git worktree remove "$WORKTREE_PATH" --force 2>/dev/null

    # Create fresh worktree
    git worktree add "$WORKTREE_PATH" Dev_new_gui

    echo "✅ Created worktree for issue #${ISSUE}"
done
```

### 9. Spawn Parallel Agents

**CRITICAL: Spawn all agents in a SINGLE response** to maximize parallelism.

```python
# Use multiple Task() calls in one response
Task(
    subagent_type="senior-backend-engineer",
    description="Implement issue #123",
    prompt="""
    WORKTREE: ../worktrees/issue-123

    Implement GitHub issue #123 in isolation:
    1. cd ../worktrees/issue-123
    2. Create feature branch: git checkout -b fix/issue-123
    3. Implement the full issue following /implement skill workflow
    4. Run tests and verify
    5. Commit with: git commit -m "feat: description (#123)"
    6. Push branch: git push -u origin fix/issue-123
    7. Report: files changed, tests status, branch name

    Timeout: 30 minutes. If blocked, report and exit.
    """
)

Task(
    subagent_type="senior-backend-engineer",
    description="Implement issue #456",
    prompt="""
    WORKTREE: ../worktrees/issue-456

    Implement GitHub issue #456 in isolation:
    [Same instructions as above, but for #456]
    """
)

Task(
    subagent_type="senior-backend-engineer",
    description="Implement issue #789",
    prompt="""
    WORKTREE: ../worktrees/issue-789

    Implement GitHub issue #789 in isolation:
    [Same instructions as above, but for #789]
    """
)
```

### 10. Monitor Agent Progress

While agents run, periodically check status:

```bash
# Check which agents are still running
# (This happens automatically - just be patient)

# Typical runtime: 10-30 minutes per agent depending on complexity
```

### 11. Collect Results

After all agents complete:

```bash
echo "📊 Parallel Agent Results:"
echo "=========================="

ISSUES=(123 456 789)
for ISSUE in "${ISSUES[@]}"; do
    WORKTREE_PATH="../worktrees/issue-${ISSUE}"

    if [[ -d "$WORKTREE_PATH" ]]; then
        cd "$WORKTREE_PATH"

        # Check if branch was created
        BRANCH=$(git branch --show-current)

        # Check if commits were made
        COMMITS=$(git log Dev_new_gui..HEAD --oneline | wc -l)

        # Check if tests passed (look for pytest output in agent logs)

        echo "Issue #${ISSUE}:"
        echo "  Branch: $BRANCH"
        echo "  Commits: $COMMITS"
        echo "  Worktree: $WORKTREE_PATH"
        echo ""

        cd - >/dev/null
    else
        echo "Issue #${ISSUE}: ❌ Worktree not found (agent may have cleaned up)"
    fi
done
```

### 12. Create PRs for Successful Implementations

```bash
for ISSUE in "${ISSUES[@]}"; do
    WORKTREE_PATH="../worktrees/issue-${ISSUE}"

    if [[ -d "$WORKTREE_PATH" ]]; then
        cd "$WORKTREE_PATH"

        # Push branch if not already pushed
        BRANCH=$(git branch --show-current)
        git push -u origin "$BRANCH" 2>/dev/null || echo "Already pushed"

        # Create PR
        gh pr create \
            --base Dev_new_gui \
            --title "$(git log -1 --pretty=%s)" \
            --body "Implements #${ISSUE}

Developed in parallel worktree by automated agent.

🤖 Generated with Claude Code - Parallel Dispatch" || echo "PR may already exist"

        cd - >/dev/null
    fi
done
```

## Fallback: Sequential Implementation

**Use this if:**
- Test agent failed
- Worktree permissions are broken
- User prefers sequential approach
- Issues have file overlap

### 13. Sequential Implementation Pattern

```bash
# Instead of parallel agents, implement one at a time in main repo

ISSUES=(123 456 789)

for ISSUE in "${ISSUES[@]}"; do
    echo "📝 Implementing issue #${ISSUE} sequentially..."

    # Use /implement skill for each issue
    /implement $ISSUE

    # Wait for completion before starting next
    echo "✅ Issue #${ISSUE} complete, moving to next..."
done
```

## Cleanup

### 14. Remove Worktrees After PRs Merged

```bash
# After PRs are merged, clean up worktrees
ISSUES=(123 456 789)

for ISSUE in "${ISSUES[@]}"; do
    WORKTREE_PATH="../worktrees/issue-${ISSUE}"

    if [[ -d "$WORKTREE_PATH" ]]; then
        echo "Removing worktree for issue #${ISSUE}..."
        git worktree remove "$WORKTREE_PATH" --force
    fi
done

echo "✅ All worktrees cleaned up"
```

## Guardrails

**If ANY agent fails:**
- Don't panic - other agents may still succeed
- Check agent logs for specific error
- Common issues: Permission errors, file conflicts, test failures
- Fix the failing issue manually or re-run with /implement

**If multiple agents fail:**
- STOP parallel dispatch
- Check worktree permissions: `ls -la ../worktrees/`
- Check disk space: `df -h`
- Fall back to sequential implementation

**If agents conflict (unlikely but possible):**
- Check for file overlap: `git diff issue-123..issue-456 --name-only`
- Merge conflicts will appear when creating PRs
- Resolve conflicts manually or pick one implementation to prioritize

## Success Criteria

✅ Worktree base directory created and writable
✅ Test agent completed successfully
✅ All parallel agents completed without permission errors
✅ All worktrees have commits on feature branches
✅ Branches pushed to remote
✅ PRs created for each issue
✅ No file conflicts between implementations
✅ Worktrees cleaned up after PRs merged

## Performance Expectations

**Wall-clock time savings:**
- Sequential: 4 issues × 30 min = 120 minutes
- Parallel: max(30, 30, 30, 30) = 30-40 minutes (4x speedup)

**When parallel is NOT faster:**
- Issues are highly coupled (merge conflicts take longer to resolve)
- System resources are constrained (CPU, memory)
- Issues are very quick individually (<5 min each)

## Troubleshooting

**Error: "fatal: cannot create worktree"**
- Fix: `rm -rf ../worktrees/issue-XXX && git worktree prune`

**Error: "permission denied"**
- Fix: `chmod -R 755 ../worktrees/`

**Error: "cannot lock ref"**
- Fix: Another worktree is using that branch - choose different branch name

**Error: "disk quota exceeded"**
- Fix: Clean up old worktrees: `git worktree prune`
- Check space: `du -sh ../worktrees/`
