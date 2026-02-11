---
name: implement
description: Complete GitHub issue implementation workflow with built-in guardrails
---

# Implement GitHub Issue

Complete workflow for implementing a GitHub issue from investigation through PR creation, merge, and cleanup.

## Pre-Flight Checks (MANDATORY - run first)

Before making ANY code changes:

1. **Verify branch state:**
   ```bash
   git branch --show-current
   git status
   git stash list
   ```
   - If on wrong branch, STOP and ask user
   - If uncommitted changes exist, STOP and ask user how to handle
   - If stashes exist, STOP and ask user how to handle

2. **Fetch issue details:**
   ```bash
   gh issue view {issue_number}
   ```
   - Verify issue is still open
   - Read full description and acceptance criteria
   - Check for linked PRs or existing branches

3. **Check for existing work:**
   ```bash
   gh pr list | grep {issue_number}
   git branch -a | grep {issue_number}
   ```
   - If PR/branch exists, STOP and ask user

4. **Verify target merge branch:**
   ```bash
   git fetch origin Dev_new_gui
   git log --oneline origin/Dev_new_gui -3
   ```
   - Confirm Dev_new_gui is the target (unless explicitly told otherwise)

## Implementation Phase

5. **Create feature branch:**
   ```bash
   git checkout -b fix/issue-{issue_number} Dev_new_gui
   ```

6. **Search memory for context:**
   - Use `mcp__memory__search_nodes` to find relevant past work
   - Check for related issues or patterns

7. **Create implementation plan:**
   - Break work into 3-10 subtasks
   - Add subtasks as checklist to GitHub issue
   - Identify backend vs frontend work
   - Plan commit checkpoints (every 2-3 logical tasks)

8. **Implement using incremental edits:**
   - Use `Edit` for existing files >50 lines (NOT Write)
   - Focus on one subtask at a time
   - Run relevant tests after each subtask
   - **Commit after completing each logical group (2-3 subtasks)**

   **Commit pattern:**
   ```bash
   git add <files-for-this-group>
   git commit -m "<type>(scope): <description> (#{issue_number})"
   git log -1 --stat  # Verify commit landed
   git diff           # Verify nothing left uncommitted
   ```

9. **For multi-phase work (backend + frontend):**
   - Complete and commit backend FIRST
   - Then start frontend
   - Commit frontend when complete
   - Run full test suite

## Verification Phase

10. **Run tests:**
    ```bash
    # Backend
    python -m pytest {affected_test_files}

    # Frontend (if applicable)
    npm run test {affected_components}
    ```

11. **Pre-commit validation:**
    - Run `git diff --staged` before committing
    - Verify no unintended files are staged
    - If pre-commit hooks fail, fix the issue (don't bypass)

## PR & Merge Phase

12. **Push and create PR:**
    ```bash
    git push -u origin fix/issue-{issue_number}

    gh pr create \
      --base Dev_new_gui \
      --title "fix: <clear title> (#{issue_number})" \
      --body "$(cat <<'EOF'
    ## Summary
    Fixes #{issue_number}

    <1-3 bullet points summarizing changes>

    ## Changes
    - <specific change 1>
    - <specific change 2>

    ## Testing
    - [ ] Backend tests pass
    - [ ] Frontend tests pass (if applicable)
    - [ ] Manual testing completed

    🤖 Generated with Claude Code
    EOF
    )"
    ```

13. **Merge PR:**
    ```bash
    # Verify PR is approved and CI passes
    gh pr merge {pr_number} --squash --delete-branch
    ```

14. **Cleanup:**
    ```bash
    git checkout Dev_new_gui
    git pull origin Dev_new_gui
    git branch -d fix/issue-{issue_number}
    ```

15. **Close issue:**
    ```bash
    gh issue close {issue_number} --comment "Implemented in PR #{pr_number}.

    Changes:
    - <summary of what was done>
    - <acceptance criteria met>

    All tests passing."
    ```

16. **Store in memory:**
    - Use `mcp__memory__create_entities` to record:
      - What was implemented
      - Key technical decisions
      - Patterns used
      - Lessons learned

## Guardrails

**If session is getting long:**
- Commit completed work immediately
- Note what's left in issue comment
- Ask user if should continue or pause

**If implementation is blocked:**
- Document blocker in issue comment
- Ask user how to proceed
- Don't implement workarounds without permission

**If scope expands:**
- Create new issue for additional work
- Ask user if should include in current PR or defer

**If tests fail:**
- Fix failures before creating PR
- Don't skip tests or mark as "will fix later"

## Success Criteria

✅ All code committed with correct issue references
✅ All acceptance criteria verified
✅ Tests passing
✅ PR created and merged to Dev_new_gui
✅ Feature branch deleted
✅ Issue closed with summary
✅ Knowledge stored in memory MCP
