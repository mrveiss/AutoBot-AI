---
type: fix
scope: frontend
issue: 17020
pr: 0
---
`components/terminal/Terminal.vue` opened WebSocket endpoints (`{ws base}/secure/{id}`,
`/terminal/{id}`, `/simple/{id}`) the backend has never served, and was referenced only by its
own Storybook story and an unused barrel export -- `ChatTabContent.vue`, the real terminal mount
point, has used `SSHTerminal.vue` all along. Retired `Terminal.vue` and its story.
`SSHTerminal.vue` was checked by hand and confirmed to already target a route the backend
serves (`/api/terminal/ws/ssh/{host_id}`, `api/terminal.py:863`); added a guard pinning that
match so the two sides can't silently drift apart again.

The other client named in #17020, `useCanvasWebSocket.ts`, needs a backend decision (a
`canvas:{id}` live-event channel does not exist yet -- filed as #17154) and is not part of this
change; #17020 stays open for it.
