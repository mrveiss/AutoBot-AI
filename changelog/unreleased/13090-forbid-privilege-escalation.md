---
type: security
scope: docs
issue: 13090
pr: 0000
---
New agent-facing rule in `docs/developer/CLAUDE_RULES.md` (and echoed in `CLAUDE_BATCH.md` for dispatched sub-agents): never `sudo`, never run an application service as root, service secrets belong in a tmpdir not a worktree, and leave no root-owned files — filed after an agent escalated to root for a schema dump, got a worse result than the unprivileged run that had already succeeded, and left 147 root-owned files the repo owner had to remove by hand (#12662). A tested `.claude/hooks/block-dangerous-commands.sh` guard is proposed on the issue but not yet landed — hook-script edits are blocked from the same access path used for everything else in this repo, so applying it needs a different route.
