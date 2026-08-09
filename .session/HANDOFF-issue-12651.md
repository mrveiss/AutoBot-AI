# Handoff: issue-12651

status: complete (design phase only — no code)
pr: (see PR)
gates: docs-only change; no test/lint gates apply
needs_rebase_before_merge: no
worktree: .worktrees/issue-12651  (safe to remove after merge)

## Delivered

`docs/adr/009-canonical-browser-interface.md`, status **Proposed**, following
the ADR-008 precedent set for #12653.

## The finding that matters

**#12651 says two Playwright stacks. There are three**, and the web-search tool
in `chat_workflow/tool_handler.py` already fans out across all of them:

1. `research_browser_manager.py` — in-process Python Playwright
2. `services/playwright_service.py` — HTTP to a Playwright container
3. `api/browser_mcp.py` → `autobot-browser-worker/` — HTTP to the Node worker

None is redundant. MHTML capture and human handoff exist only in (1); stable
element refs and live interaction only in (3); restart-survival only in (2)/(3).
So the ADR wraps them as backends rather than deleting any — deleting two would
lose features the umbrella's own contract forbids losing.

`research_browser_manager.py` has **no** screenshot capability — checked, after
initially assuming it did. The `/screenshot` endpoint in `api/playwright.py`
goes through the container service.

## Security finding — filed as #13204

The SSRF guard is **not uniform**, and the agent-reachable path is the weakest:

| path | guard |
|---|---|
| `content_reach/backends/browser.py` | `ensure_public_url` + `ensure_robots_allowed` |
| `research_browser_manager.py` | DNS-rebind re-check (#13018) |
| `send_to_browser_vm()` | **none** |
| `services/playwright_service.py` | **none** |

`is_url_allowed()` in `api/browser_mcp.py` guards exactly one HTTP endpoint
(`POST /mcp/navigate`) — not the `send_to_browser_vm()` helper the agent tool
path uses — and it is a regex allowlist, so it cannot see where a host
resolves. Evidence: it does not even allowlist the search domain that
`_web_search_via_browser_vm` navigates to, so that path demonstrably never
passes through it.

The ADR puts the guard in the interface so a backend cannot forget it.

## Next step (needs owner acceptance of the ADR first)

Sequencing is in the ADR. Steps 1-2 (interface + capability model, then wrap the
three stacks as backends) are **additive** — no caller changes, safe to land
before deciding on steps 3-6 (repointing `content_reach`, `web_fetch`,
`tool_handler`, `api/playwright`).

Step 5 (repointing `tool_handler`) is the one that closes #13204 on the agent
path, and it **will** start blocking requests those paths accept today. That
needs its own callout in the migration PR.

## Also found

**#12653's ADR already exists** — `docs/adr/008-frontend-shared-code-boundary.md`,
Accepted 2026-07-31. That issue's step 1 is done; only step 2 (de-duplicate
`useVncControls` and Advanced Control per the ADR) remains. Do not re-write it.
