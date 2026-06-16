# Handoff: issue-10008
status: complete
pr: DEFERRED — open PR queue at 6 (project limit 5); branch ready + mergeable
base_at_push: origin/Dev_new_gui (rebased clean; three-dot diff = 6 files only)
gates: tests=PASS (ai_stack_client_gate_test 4/4) flake8=0 byte-compile=PASS
needs_rebase_before_merge: no (rebased onto latest at push; re-check if base moves)
remaining:
  - Open the PR once open-PR count < 5:
    gh pr create --base Dev_new_gui --head issue-10008 \
      --title "consolidation: promote AIStackClient.connection_status to ConnectionStatus enum (#10008)"
  - PR body headings required: Thinking Path · What Changed · Verification · Model Used
blocked_on: PR-queue limit only (no technical blocker)
worktree: .worktrees/issue-10008  (safe to remove after merge)

## What landed on the branch
- autobot_shared/status_enums.py — new `ConnectionStatus(str, Enum)` {UNKNOWN, CONNECTED, ERROR, DISABLED} + __all__
- autobot-backend/constants/status_enums.py — re-export shim updated (canonical import path)
- autobot-backend/services/ai_stack_client.py — connection_status typed + all 6 assignments/compares use enum
- autobot-backend/initialization/endpoints.py — _ai_stack_status reads via enum (str-subclass back-compat kept)
- autobot-backend/initialization/ai_stack_init.py — 3 sibling status writes routed through ConnectionStatus.value
- autobot-backend/services/ai_stack_client_gate_test.py — asserts enum identity + str back-compat

## Scope notes
- `(str, Enum)` chosen over `enum.StrEnum`: local/CI Python is 3.10 (StrEnum is 3.11+);
  matches the existing `AgentLifecycleStatus(str, Enum)` precedent in the same file;
  preserves all `== "connected"` comparisons and JSON serialization.
- Deliberately NOT touched (distinct vocabularies — avoid wrong abstraction):
  `ai_stack_agents` ready/partial, and health_check()'s "status" payload (healthy/unhealthy/disabled).
