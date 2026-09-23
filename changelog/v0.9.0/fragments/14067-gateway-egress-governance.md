---
type: security
scope: gateway
issue: 14067
pr: 14261
---
Outbound Gateway sends now pass an egress governance stage that records every agent-authored message and, when armed, requires approval before the message reaches a channel adapter.
