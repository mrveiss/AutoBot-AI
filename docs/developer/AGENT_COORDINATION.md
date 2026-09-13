# Agent Coordination Doctrine

> Read before adding a claim, a lock, a lease, or any "which agent owns this"
> state. This is a checklist, not a manual — if a rule needs more than two
> lines, the reasoning belongs in the linked issue.

Several agents work one project at once. Coordination is how they avoid
overwriting each other; it is **not** part of the event layer, which names
agent-to-agent coordination semantics as an anti-goal
([`EVENT_STATE_DOCTRINE.md`](EVENT_STATE_DOCTRINE.md)). Semantics live in
`autobot_shared/coordination/`; only the user-visible projection is published.

## Principles

1. **One claim registry.** `autobot_shared/coordination/work_claims.py` is the
   single place a resource scope is claimed. A second claim primitive is never
   the answer to a coordination problem — `services/task_claim.py` already
   exists for task identity, and #15957 decides whether they merge. A third is
   not open for discussion.
2. **Every claim expires.** A lock that can outlive its holder turns one crashed
   agent into a permanently blocked project, which is worse than the collision
   it prevents. TTL plus renew, never an unbounded hold.
3. **A refusal names its holder.** `ClaimConflict` carries agent, task, mode,
   intent and expiry. A bare `False` leaves the loser with nothing to wait for,
   ask, or escalate.
4. **Reentrancy is keyed on `(agent_id, task_id)`.** An agent that deadlocks
   against itself is a defect in the primitive, not in the caller.
5. **Ownership is checked on release and renew.** Releasing another holder's
   claim is refused and logged: it means two agents disagree about who owns the
   work, which is the condition claims exist to surface.
6. **Coordination state is ephemeral by declaration.** `agent_work_claims` names
   Redis as its system of record in `store_authority.py`, with the reason. The
   durable record of work is the a2a `Task`.

## Scope grammar

`<kind>:<segment>/<segment>/...`, kinds `path`, `kb`, `device`, `project`,
`config`. A claim covers its **subtree**, and prefixes are segment-aligned:

- `path:a/b` covers `path:a/b/c.py`
- `path:a/b` does **not** cover `path:a/bc.py`
- `path:a/b` does **not** cover `kb:a/b` — a claim never spans two kinds

There is deliberately no `dir` kind. Two kinds over one namespace would need the
overlap rule to know that `dir` and `file` are the same namespace while `kb` and
`device` are not, and a rule with an exception table is the kind nobody applies
correctly at the next call site.

## Design tests

Any "no" needs a written justification in the issue.

- Can the holder crash without blocking the scope forever?
- Does a refusal tell the loser who holds it and why?
- Can the same `(agent, task)` re-enter its own scope without deadlocking?
- Is the claim's lifetime tied to the work, rather than to a fixed guess?
- Would a second agent see the same answer as the first? (Acquire is one Lua
  script for this reason — read-then-write in Python cannot promise it.)

## Contention: queue, ask, arbitrate

A refusal is the start of a negotiation, not the end of one (#15948).

- **Queue.** A refused agent joins the scope's waitlist. Position is join order,
  and re-joining as the same `(agent_id, task_id)` refreshes in place — a retry
  loop must not push an agent to the back of a queue it is already in.
- **Promotion is an invitation, not a grant.** Nothing computes whether a waiter
  *could* acquire; the waiter is told to retry and calls `try_acquire` itself.
  This is deliberate: that predicate already exists twice (`Scope.overlaps` and
  the acquire Lua) and needed an exhaustive test to keep the two in step. A
  third copy would need pinning to both. It also makes the multi-holder case
  correct for free — a path can carry several SHARED claims, so one release need
  not free it, and a waiter that retries simply fails and keeps its place.
- **Ask.** A requester may ask the holder to release early, on the holder's own
  a2a task channel. No new bus.
- **Silence means hold.** An unanswered yield resolves to a refusal. Treating no
  answer as consent would take a scope from a holder precisely when it is least
  able to object.
- **Arbitrate.** When two contenders must be compared, one pure function decides:
  priority, then who waited longer, then agent id. The last rule is arbitrary and
  that is the point — an arbitrary *stable* rule beats a fair *unstable* one,
  because two callers comparing the same pair must reach the same answer or they
  will both yield and the scope goes to nobody.

**Where each half lives.** The queue and the arbitration are in
`autobot_shared/coordination/claim_waitlist.py`; the notification is in
`autobot-backend/services/claim_yield.py`. The split is not stylistic:
publishing on the a2a channel needs the task manager, and `autobot_shared` must
not import from `autobot-backend`. It also leaves the queue testable with no
task manager and no running backend.

## Unlanded work: interest and stewardship

A claim frees when the task ends. The **change** does not land until its PR
merges, and between those two moments the scope is unclaimed but not safe
(#15987).

- **The branch holds the interest, not the session.** A session is not a durable
  holder — a 2026-09-07 census found 13 of 17 worktrees belonged to sessions that
  were offline or ended, and a session-keyed lock on any of them would have held
  its scope with nobody alive to release it. A branch's end condition, merged or
  closed, is externally observable.
- **A session is the branch's steward, and stewardship transfers.** Handing a
  branch on beats opening a parallel one: one branch carries the file forward,
  one PR touches it, one review sees the whole change.
- **An interest never refuses a claim.** Blocking on an open PR would serialise
  the fleet behind review. `acquire_aware` grants the claim and reports what else
  is in flight, so the second agent finds out before editing rather than at merge.
- **A handoff must be refusable.** One that could not be declined turns the
  batching *default* into a batching *requirement* and overrules the rule that
  independent or different-risk changes get separate PRs.
- **The chain is bounded.** Unbounded handoff recreates, inside one branch, the
  pile of unlanded work the worktree ceiling exists to prevent — and hides it,
  because a growing branch looks like progress.
- **No TTL decides this.** An interest ends when its branch does. `prune` takes
  the live-branch set from a caller with a GitHub client, because this package
  has none and must not grow one.

### Three relationships, three answers

| | Relationship | Answer |
|---|---|---|
| 1 | Disjoint scopes | Independent branches; claims keep them apart |
| 2 | Sequential overlap | Handoff — stewardship of the branch transfers |
| 3 | Interdependent | One branch, worked in turns |

Mode 3 cannot mean two agents editing one branch at once: `git worktree add`
refuses a branch already checked out elsewhere, and agents never share a
worktree. It means **ping-pong stewardship** — the lock alternates — or stacked
branches when the dependency is one-directional. Before entering mode 3, check
whether the dependency is one-directional (sequence it with a `blocked_by` edge)
or whether the two issues should have been one.

## Anti-goals

This layer does **not** provide:

- Distributed transactions, or a substitute for database constraints.
- Enforcement on its own. Layer 1 is advisory by contract; #15950 is what makes
  declared write sites acquire before they write.
- Negotiation. Waitlist, yield and arbitration are #15948.
- A second event bus. The projection of who holds what is #15949, on the
  existing bus and existing channels.

## See also

- [`EVENT_STATE_DOCTRINE.md`](EVENT_STATE_DOCTRINE.md) — why the projection, and
  not the semantics, belongs on the bus
- [`ARCHITECTURE_EXCEPTIONS.md`](ARCHITECTURE_EXCEPTIONS.md) — for a deliberate
  deviation from any rule above
