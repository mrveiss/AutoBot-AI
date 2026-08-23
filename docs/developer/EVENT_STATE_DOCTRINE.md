# Event & State Doctrine

> Read before adding an event type, a WebSocket route, an event bus, or a new
> piece of session state. This is a checklist, not a manual — if a rule needs
> more than two lines, the reasoning belongs in the linked issue.

The event/state layer carries what the user sees happening: chat turns,
workflow progress, agent steps, approvals, worker health. AutoBot is **one host
with many clients** — several tabs, several devices, several users on a shared
session — so "it works on my screen" is not the bar.

## Principles

1. **One bus.** `events/bus.py` is the single publish entry point.
   `PersistStrategy` is the durability knob. A second bus is never the answer to
   a delivery problem — three parallel systems is the state this codebase was
   already in once, and callers had to publish twice to reach everyone.
2. **State over notification.** If a user-visible fact is only ever an ephemeral
   notification, a client that was disconnected can never learn it. Durable,
   user-visible truth must be recoverable from state or from a replayable
   stream.
3. **The backend is the authority.** The server sequences events and resolves
   conflicts. A client may render optimistically, but it is never the source of
   truth — two clients that each own the truth cannot converge, by construction.
4. **Delivery and persistence are separate concerns.** Persisting inside a
   delivery callback means nothing is recorded when nobody is watching. Publish
   persists; delivery is what happens next, to however many clients are
   attached (#14814).
5. **Channels, not routes.** New event types extend the channel grammar in
   `live_event_manager.py`. They do not add a WebSocket endpoint. Routing is
   `(type, channel)` — uniform, so a client, a proxy, or a test can dispatch
   without per-message knowledge.
6. **Additive and capability-gated.** A smaller or older client should keep
   working. Prefer optional fields and negotiated capabilities over changes that
   force every consumer to upgrade at once.

## Design tests

Ask these before adding to this layer. Any "no" needs a written justification in
the issue.

- Can a minimal client ignore this and still render a coherent session?
- Is the durable, user-visible result represented in **state**, rather than only
  in an ephemeral notification?
- Does the backend remain the authority for sequencing and conflict resolution?
- Does this fit an existing channel, or does it genuinely need a new one?
- Can clients discover support through a capability rather than a version check?
- If a client is offline when this fires, can it find out afterwards?
- Does a second connected client see the same thing as the first?

## Anti-goals

This layer does **not** define:

- How agents reason, plan, or manage context. That is the agent loop's concern.
- A model provider, router, or credential flow.
- A universal backend tool registry or tool schema.
- A required UI layout or client framework.
- Agent-to-agent coordination semantics.
- Binary or high-volume streams. VNC framebuffers, audio, terminal PTY bytes and
  log tails stay on their own sockets — multiplexing them onto a JSON event
  channel serves neither well.

## Rules with teeth

| Rule | Why it exists |
|---|---|
| Never hold a broadcast callback as a scalar | A single slot means last-writer-wins and one disconnect silences everyone (#14814) |
| Never derive a sequence number from process memory | It resets on restart and diverges across workers; a marker clients trust but which restarts is worse than no marker (#14817) |
| Never return an incomplete history as if it were complete | "You missed nothing" and "I cannot tell you what you missed" must not both be an empty list (#14818) |
| Never make persistence a side effect of delivery | Zero clients connected must still record the event (#14814) |
| Fail closed on channel authorization | An unknown or unowned resource is a denial, not an absence of restriction (#14819) |

## See also

- [`docs/research/agent-host-and-agent-client-protocols.md`](../research/agent-host-and-agent-client-protocols.md)
  — the audit that produced these rules, and the external protocols they draw on
  (Microsoft's Agent Host Protocol; Zed/JetBrains' Agent Client Protocol).
- [`CLAUDE_RULES.md`](CLAUDE_RULES.md) — the general engineering rules this
  refines for one layer.
