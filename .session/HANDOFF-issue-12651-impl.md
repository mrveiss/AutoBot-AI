# Handoff: issue-12651-impl

status: complete (ADR-009 phases 1-2 only, per owner scope)
gates: 30 tests PASS (15 registry + 15 conformance) · isort/black/flake8 PASS · bandit 0 issues
worktree: .worktrees/issue-12651-impl  (safe to remove after merge)

## Delivered — additive only

**Phase 1** `autobot_shared/browser/` — `Capability`, frozen request/result
dataclasses, `BrowserBackend` Protocol, capability dispatch with probe-based
fallback, and the DNS-resolving URL guard enforced **before** any backend sees
a request.

**Phase 2** `autobot-backend/browser_backends/` — the three stacks wrapped:
`in_process` (research_browser_manager), `worker` (browser_mcp), `container`
(playwright_service).

**Nothing is repointed.** No caller changed; `register_all()` is opt-in.

## Two traps

1. **Backends must NOT move to `autobot_shared`.** They wrap this app's
   transports; shared code importing `research_browser_manager` /
   `services.playwright_service` / `api.browser_mcp` is the inverted dependency
   #13201 had to design around. `autobot_shared/browser/registry_test.py`
   asserts this by AST — if you see that test fail, do not "fix" it by
   loosening the assertion.
2. **`Capability` is `(str, Enum)`, not `StrEnum`.** `autobot_shared` targets
   3.14 where `StrEnum` exists, but this dev box is 3.10 — `StrEnum` makes the
   whole module unimportable locally, so nothing can be verified before CI.
   `status_enums.AgentLifecycleStatus` uses the same `(str, Enum)` shape.

## What is deliberately NOT done — steps 3-6

ADR-009's caller migration (`content_reach`, `web_fetch`, `tool_handler`,
`api/playwright`) is **out of scope** by owner decision (2026-08-01), because
step 5 is a behaviour change: enforcing the guard starts blocking internal
URLs that `send_to_browser_vm` accepts today.

**Consequence: #13204 stays OPEN.** The interface closes it structurally only
once callers route through it. Do not close #13204 on this PR.

**#12651's "Done when" says "callers use it"** — which phases 1-2 do not
satisfy. Either reword that AC or file a follow-up for steps 3-6 before
closing #12651.
