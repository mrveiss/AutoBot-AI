---
name: drain
description: Pick and solve the backlog issues that need no decision. Use when asked to work the backlog, drain issues, "solve what you can", run the loop autonomously, or whenever a loop tick has no assigned issue. Selects work; delegates execution to batch-implement.
---

# /drain — spend the loop's attention on what it can actually finish

The loop's scarce resource is **attention**, not filing capacity. Picking the
oldest open issue blindly burns a tick whenever it turns out to need an answer
only the owner can give. This selects work that is finishable now.

Selection only. Execution belongs to `batch-implement`; PR mechanics to
`ci-pipelining.md`. Do not reimplement either here.

## 1. Drain the PR queue first

In-flight PRs before new work, every time:

```bash
gh pr list --state open --json number,title --jq '.[]|"\(.number) \(.title)"'
~/.claude/scripts/backlog-governor.sh status     # advisory signal only
```

Sweep → review → merge green → close with evidence → remove worktree/branch.
A merged PR closes an issue; a new issue closes nothing. If PRs are stacked up,
draining them IS the tick.

## 2. Select

```bash
~/.claude/scripts/backlog-next.py -n 10 --why
```

Ranks problems → enhancements → features, FIFO within each. Judged from issue
content, not labels — labels do not carry this signal (1 of 400 open issues
carries `needs-decision`). An issue is excluded when it is an umbrella, requests
a decision, has an open `depends on #N` blocker, or states no acceptance
criteria.

Take the head of the list that does not collide with an in-flight PR's files.
Skipping for collision is a deferral, not a reorder.

## 3. Confirm readiness before starting

The picker is a heuristic. Read the issue and abandon it if:

- the acceptance criteria are not actually checkable
- it needs a product or architecture call
- delivering it means choosing between two reasonable designs

Put it back with a `needs-decision` label and options + a recommendation posted
on the issue, then take the next candidate **in the same tick**. Never end a
tick because one issue turned out to be decision-gated.

## 4. Execute

Hand the chosen numbers to `batch-implement`, which owns worktree → implement →
review → merge → close → cleanup.

## Hard rules

- **Never file issues as busywork.** Filing is never blocked, but a filed issue
  is not progress. If nothing is solvable, say so and stop — do not manufacture
  backlog to look busy.
- **Discovered problems still get filed** (that rule is absolute), just never as
  a substitute for solving something.
- **A decision-gated issue is posted and skipped, never waited on.**
- **Evidence before done** — `batch-implement` and the closure gate own this;
  do not claim a close without the verifying output.
