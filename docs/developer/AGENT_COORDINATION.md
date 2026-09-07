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
