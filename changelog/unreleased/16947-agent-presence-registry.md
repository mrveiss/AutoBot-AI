---
type: feat
scope: backend
issue: 16947
pr: 0
---
`AgentIdentity` (`protocols/agent_communication.py`) gains `kind`, `name` and `tenant_id` -- the shared identity model from #16946, additive and backward-compatible. A new `AgentPresenceRegistry` (`protocols/agent_presence.py`) gives one live, TTL-bounded query across all three internal agent kinds (Company OS, AI-stack, sessions), consolidating the four unconnected "is this agent alive right now" registries (#6828) rather than adding a fifth; pull adapters (`protocols/agent_presence_feeds.py`) feed it from each kind's own authoritative source. External A2A peers are refused at registration -- identity for attribution only, never discoverable (#16946 owner decision 3). A background task (`initialization/agent_presence_sync.py`) now calls the three feed adapters on an interval, and `GET /agents/presence` (`api/agent_presence.py`) reads the registry back, scoped to the caller's own tenant from the verified session context.
