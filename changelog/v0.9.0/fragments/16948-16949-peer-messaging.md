---
type: feat
scope: backend
issue: 16948
pr: 0
---
Agents can now send each other a message through the presence registry (`#16947`) rather than through a human: `protocols/peer_inbox.py` addresses a recipient by its stable presence name and delivers into a per-`(kind, tenant_id, name)` inbox, drained at the real per-agent turn boundary (AI_STACK's `chat_workflow/tool_handler.py::_dispatch_tool_call`, SESSION's `services/agent_terminal/service.py::execute_command`) rather than mid-task, and never across tenants. A peer message carries no approval of its own -- a sensitive tool call it triggers still goes through the ordinary human-approval gate. Presence (`#16947`) also now pushes a one-shot notice (`protocols/idle_notice.py`) the moment a busy peer goes idle, with a bounded timeout (`AUTOBOT_IDLE_NOTICE_TIMEOUT_SECONDS`) instead of forcing a waiter to poll (`#16949`).
