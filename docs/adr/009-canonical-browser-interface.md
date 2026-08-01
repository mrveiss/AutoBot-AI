# ADR-009: One Canonical Browser Interface, With Execution Backends Behind It

## Status

**Status**: Proposed

## Date

**Date**: 2026-08-01

## Context

Issue #12651 (under umbrella #12645, and named in #12756 as "the backbone of
one Browser") asks for a single canonical browser interface, with in-process
and Docker execution as strategies behind it rather than two independent
stacks.

**The issue undercounts the problem. There are three execution stacks, not
two**, and a single tool call already fans out across all three.

| stack | where | process model |
|---|---|---|
| **In-process Playwright** | `autobot-backend/research_browser_manager.py` (704 L) | Python Playwright inside the backend process; one `ResearchBrowserSession` per conversation |
| **Docker/remote render** | `autobot-backend/services/playwright_service.py` (464 L) | HTTP to a Playwright container (`/test-frontend`, `/search` endpoints) |
| **Live browser worker** | `autobot-backend/api/browser_mcp.py` → `autobot-browser-worker/` (Node) | HTTP to a long-lived Node/Playwright worker; one `BrowserContext` per chat `session_id` |

The web-search tool in `chat_workflow/tool_handler.py` walks all three in one
fallback chain:

```text
_execute_web_search
  └─ _web_search_via_playwright
       └─ _web_search_structured_entries
            ├─ registry providers (SearXNG #9022 / Brave #9023)
            └─ services.playwright_service.search_web_embedded   ← stack 2
  └─ _web_search_final_fallback
       └─ _web_search_via_browser_vm
            └─ api.browser_mcp.send_to_browser_vm                ← stack 3

content_reach/backends/browser.py
  └─ research_browser_manager.get_research_browser_manager()     ← stack 1
```

Each stack was built for a real need, and none is redundant:

- the **in-process** one owns interactive research sessions — MHTML capture,
  "interaction required" detection, human-in-the-loop waiting;
- the **Docker** one exists so a JS-render fallback does not put Playwright in
  the backend's own process (`web_fetch/fetcher.py` uses it that way);
- the **worker** one owns the live, per-conversation browser the user can watch
  and take over.

So the goal is *not* to delete two of them. It is to stop them being reachable
as three unrelated APIs with three different sets of guarantees.

### What the divergence already costs

**1. The SSRF guard is not uniform — and the agent-reachable path is the
weakest.** Filed as #13204.

| path | URL guard |
|---|---|
| `content_reach/backends/browser.py` | `ensure_public_url` + `ensure_robots_allowed` |
| `research_browser_manager.py` | DNS-rebind re-check after navigation (#13018) |
| `send_to_browser_vm()` | **none** |
| `services/playwright_service.py` | **none** |

`api/browser_mcp.py` does have `is_url_allowed()`, but it guards exactly one
HTTP endpoint (`POST /mcp/navigate`), not the `send_to_browser_vm()` helper the
agent tool path actually uses — and it is a regex allowlist over the URL
string, so it cannot see where a host resolves.

This is the clearest argument for the interface: a guard belongs at one
chokepoint, not re-added to three call sites that have already drifted.

**2. Capability gaps are invisible to callers.** A caller picking a stack
inherits whatever that stack happens to support:

| capability | in-process | Docker | worker |
|---|---|---|---|
| navigate + extract text | yes | via `/search`, `/test-frontend` only | yes |
| screenshot | **no** | `capture_screenshot` (posts to `/test-frontend`) | yes |
| stable indexed element refs | no | no | yes (`element-index.js`) |
| click / fill / select | no | no | yes |
| MHTML capture | yes | no | no |
| interaction-required detection + human handoff | yes | no | no |
| per-conversation isolation | per conversation | none (stateless) | per `session_id` |
| survives backend restart | no | yes | yes |

**3. Fallback logic is hand-rolled per caller.** `tool_handler.py` encodes its
own cascade, and comments there (#7478) show it has already been debugged for
re-issuing a call to a stack it had just determined unavailable. That policy
should live in one place.

## Decision

Introduce **one canonical browser interface in `autobot_shared`**, with the
three existing stacks as **execution backends** behind it. Callers state
*what* they need; the interface picks *where* it runs.

### The interface

```python
# autobot_shared/browser/base.py
class BrowserBackend(Protocol):
    name: str
    capabilities: frozenset[Capability]

    async def probe(self) -> bool: ...
    async def navigate(self, req: NavigateRequest) -> PageResult: ...
    async def extract(self, req: ExtractRequest) -> ContentResult: ...
    async def screenshot(self, req: ScreenshotRequest) -> ImageResult: ...
    async def act(self, req: ActionRequest) -> ActionResult: ...   # click/fill/select
    async def release(self, session: SessionHandle) -> None: ...
```

Backends declare capabilities rather than implementing everything:

```python
class Capability(StrEnum):
    NAVIGATE = "navigate"
    EXTRACT = "extract"
    SCREENSHOT = "screenshot"
    INTERACT = "interact"          # click/fill/select, needs element refs
    ELEMENT_REFS = "element_refs"
    MHTML = "mhtml"
    HUMAN_HANDOFF = "human_handoff"
    PERSISTENT_SESSION = "persistent_session"
```

A caller asks for capabilities, not a stack:

```python
browser = await get_browser(requires={Capability.NAVIGATE, Capability.EXTRACT},
                            session_id=conversation_id)
result = await browser.navigate(NavigateRequest(url=url))
```

`get_browser` resolves against a **declared preference order per capability
set**, skipping backends that fail `probe()`. That replaces every hand-rolled
cascade, including `tool_handler.py`'s.

### Non-negotiable: the guard lives in the interface

`ensure_public_url` (DNS-resolving) runs in the interface's `navigate`/`extract`
entry points, **before** dispatch to any backend. A backend never receives an
unvalidated URL, so a new backend cannot forget the guard. This closes #13204
by construction rather than by three separate patches.

### What each existing stack becomes

| stack | becomes | keeps |
|---|---|---|
| `research_browser_manager.py` | `InProcessBackend` | MHTML, human handoff, per-conversation sessions |
| `services/playwright_service.py` | `ContainerBackend` | stateless render/screenshot, survives backend restart |
| `api/browser_mcp.py` + browser worker | `WorkerBackend` | element refs, interaction, live per-`session_id` context |

None is deleted. Each is wrapped, its callers repointed at the interface, and
its module reduced to the backend implementation.

### Alternatives Considered

1. **Pick one stack, delete the other two.**
   - Pros: the least code at the end; one thing to reason about.
   - Cons: rejected on evidence. Each stack holds capabilities the others lack
     (MHTML and human handoff only in-process; element refs and live
     interaction only in the worker; restart-survival only out-of-process).
     Collapsing onto any one loses features the umbrella's own contract
     forbids losing.

2. **Keep the stacks, add a thin façade that just re-exports them.**
   - Pros: smallest diff; no behaviour risk.
   - Cons: does not fix anything. Callers still choose a stack, the guard is
     still per-stack, and #13204 stays open. A façade that does not own
     dispatch and validation is documentation, not architecture.

3. **Make the Node browser worker the single backend for everything.**
   - Pros: richest feature set (element refs, interaction, per-session
     contexts); already out-of-process.
   - Cons: pushes Python-side capabilities (MHTML capture, the research
     session's interaction-required detection) into a Node service that would
     have to reimplement them; makes every content fetch depend on the worker
     being up, where today `web_fetch` deliberately has a container fallback.
     Worth revisiting *after* the interface exists, as a backend-selection
     policy change rather than an architecture change.

4. **Adopt PinchTab as the control plane.**
   - Already rejected in #12756: Go vs Python, and it would be a second
     control plane rather than one. Its patterns are mined instead.

## Consequences

### Positive

- One place to enforce the URL guard — closes #13204 structurally, and any
  future backend inherits it.
- Capability gaps become explicit and queryable instead of discovered by a
  caller getting a worse result from the stack it happened to pick.
- Fallback policy is declared once; `tool_handler.py` loses its hand-rolled
  cascade and the bug class that came with it (#7478).
- The #12756 children (#12757 IDPI sanitisation, #12758 progressive
  disclosure, #12759 persistent profiles, #12760 audit surface, #12761
  pooling) each get one place to land rather than three.

### Negative

- A dispatch layer is a new indirection; a caller reading `get_browser(...)`
  cannot see which stack ran without checking capabilities and probe results.
  Mitigated by putting the resolved backend name in the result object and in
  the log line.
- Migration touches live paths — `chat_workflow/tool_handler.py`,
  `web_fetch/fetcher.py`, `content_reach/backends/browser.py`, `api/playwright.py`.
  Sequenced below so no step changes behaviour and structure at once.
- Adding the DNS-resolving guard to `send_to_browser_vm` and
  `playwright_service` **will** block requests those paths accept today.
  That is the point, but it is a behaviour change and needs its own callout in
  the migration PR.

### Neutral

- The interface lives in `autobot_shared/browser/`, so the SLM backend could
  consume it later. Nothing in this ADR requires it to.

## Implementation Notes

Sequenced so each step is separately reviewable and reversible:

1. **Interface + capability model, no callers.** `autobot_shared/browser/`
   with the protocol, request/result types, `Capability`, and the guard in the
   entry points. Tests only.
2. **Wrap the three stacks as backends.** No caller changes; each backend is
   tested against the same conformance suite for the capabilities it declares.
3. **Repoint `content_reach/backends/browser.py`** — the smallest caller, and
   already guarded, so a regression is easy to see.
4. **Repoint `web_fetch/fetcher.py`'s render fallback.**
5. **Repoint `chat_workflow/tool_handler.py`**, deleting the hand-rolled
   cascade. This is the step that closes the #13204 gap on the agent path;
   ship it with the behaviour-change callout.
6. **Repoint `api/playwright.py`**, and retire `is_url_allowed`'s regex
   allowlist in favour of the shared guard plus an explicit internal-host
   exception list.

Steps 1–2 are additive and safe to land ahead of any decision on 3–6.

### Key Files

- `autobot-backend/research_browser_manager.py` — in-process stack; becomes `InProcessBackend`
- `autobot-backend/services/playwright_service.py` — container stack; becomes `ContainerBackend`
- `autobot-backend/api/browser_mcp.py` — worker transport; becomes `WorkerBackend`
- `autobot-backend/chat_workflow/tool_handler.py` — hand-rolled cascade to be replaced
- `autobot-backend/content_reach/backends/browser.py` — first caller to migrate
- `autobot-backend/web_fetch/fetcher.py` — render fallback caller
- `autobot_shared/url_safety.py` — the guard the interface enforces

### Code Examples

```python
# Before — the caller picks a stack, and inherits its guarantees.
from services.playwright_service import search_web_embedded
result = await search_web_embedded(query, max_results=5)
if not result.get("success"):
    from api.browser_mcp import send_to_browser_vm      # unguarded
    await send_to_browser_vm("navigate", {"url": search_url}, session_id=sid)

# After — the caller states requirements; dispatch and guard are the
# interface's job.
browser = await get_browser(
    requires={Capability.NAVIGATE, Capability.EXTRACT},
    session_id=conversation_id,
)
page = await browser.navigate(NavigateRequest(url=search_url))
```

## Related ADRs

- [ADR-008](008-frontend-shared-code-boundary.md) — the same
  "one canonical implementation, explicit boundary" question for the two SPAs
  (#12653, umbrella #12645)

## Related Issues

- #12651 — this ADR's issue
- #12756 — epic: one canonical AutoBot browser (names #12651 as its backbone)
- #13204 — SSRF guard not uniform across browser paths (closed structurally by this design)
- #12757 / #12758 / #12759 / #12760 / #12761 — #12756 children that land on this interface
- #13018 — the DNS-rebind fix this design generalises to every path

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
