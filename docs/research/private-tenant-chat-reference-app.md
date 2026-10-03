---
tags:
  - research
aliases:
  - Private-Tenant Chat Reference App
---

# Source Analysis: A Cloud Vendor's Private-Tenant Chat Reference Application

## What It Is

A first-party reference application published by a major cloud vendor so that an
organisation can stand up its own private ChatGPT-style tenant inside its own
cloud subscription: familiar chat UI, chat-over-your-files, and pluggable calls
out to internal APIs. Next.js 14 App Router with React server components and
server actions, TypeScript, Tailwind + Radix primitives, `valtio` stores on the
client, `zod` for validation, shipped together with infrastructure-as-code
templates and CI workflows so the whole thing provisions and deploys with one
command. Mature by adoption (~1.4k stars, ~1.3k forks, still actively pushed,
MIT) but deliberately shaped as a *template to fork*, not a library to depend
on — the fork:star ratio near 1.0 is the tell.

**The input handed to this research was a fork, and the fork is empty:** 0
commits ahead of upstream, 66 behind, last pushed 2024-09-17, 1 star. It
contributes no original work, so everything below is an analysis of an ~2-year-old
snapshot of the upstream reference application. That is itself the single most
useful datum in the source (see *Hidden metrics*): the distribution model is
"fork and customise", and this is what a fork looks like two years later.

## Architecture & Key Patterns

- **Feature-folder monolith.** `src/features/<feature>/` each owning its own
  `*-service.ts` (server), `*-store.ts` (client), `models.ts` (zod schema +
  type-discriminator constant) and components. No shared "services" layer beyond
  `features/common/services/` which holds one thin factory per managed cloud
  service.
- **Server actions as the only API.** Almost nothing is a REST route. Files open
  with `"use server"; import "server-only";` and export functions the client
  calls directly; the four real HTTP routes exist only for streaming (chat),
  auth, file upload and images.
- **One uniform result envelope.** `ServerActionResponse<T>` =
  `{status:"OK",response:T}` | `{status:"ERROR"|"NOT_FOUND"|"UNAUTHORIZED",errors:[{message}]}`
  (`features/common/server-action-response.ts`). Every service function returns
  it; zod issues are mapped into the same shape. Callers branch on `status`, never
  on exceptions.
- **Single-container, type-discriminated persistence.** One managed document-DB
  container holds chat threads, messages, citations, personas, prompts and
  extensions, separated by a `type` attribute (`CHAT_THREAD`, `MESSAGE`,
  `EXTENSION`, …) and queried with `SELECT * FROM root r WHERE r.type=@type`.
- **Chat mode is selected, not composed.** `chat-api.ts` resolves user, history,
  documents and tools in one `Promise.all`, then picks exactly one of three
  runners — `chat-with-file` (RAG), `multimodal` (image in prompt), `extensions`
  (tool calling) — with documents winning over tools. The modes are mutually
  exclusive.
- **Tools are database rows.** An "extension" is a user- or admin-authored
  record holding a JSON function schema, an HTTP endpoint + method, and a list of
  headers. At chat time `chat-api-dynamic-extensions.ts` turns each row into a
  vendor-SDK runnable tool whose body is a generic `fetch` of that endpoint. The
  SDK's `runTools` drives the tool loop; the app never writes an agent loop.
- **Prompt assembly is string concatenation.** A global default system prompt,
  then the thread's persona text, then each selected extension's free-text
  `executionSteps`, all concatenated into one system message.
- **SSE hand-rolled over the SDK's event stream.** `open-ai-stream.ts` wraps the
  streaming runner in a `ReadableStream`, emitting `event:`/`data:` frames per
  `content` / `functionCall` / `functionCallResult` / `abort` / `error` /
  `finalContent`, and persists messages from inside those same handlers.

## Notable Implementation Details

- **Citations as a markup tag, not a text convention.** The RAG prompt instructs
  the model to end its answer with {% raw %}`{% citation items=[{name,id}] /%}`{% endraw %}; the
  renderer registers `citation` as a Markdoc custom tag
  (`features/ui/markdown/config.tsx`) so the model's own output token stream
  materialises into an interactive component with a slide-out source panel. The
  retrieved chunks were persisted as `CHAT_CITATION` rows first, so the `id` the
  model emits resolves to durable, per-user-scoped content
  (`citation-service.ts` `FindCitationByID` filters on `userId`).
- **Secret values never round-trip.** Extension header values are written to a
  managed vault under the header's own id and replaced in the stored record with
  a literal `**********` mask; on save, a value still equal to the mask is left
  alone (`extension-service.ts` `secureHeaderValues`). The vault read is isolated
  in `FindSecureHeaderValue` with a comment forbidding client use.
- **Short-lived token brokering for speech.** The server action exchanges the
  long-lived speech-service key for a scoped STS token and returns only that plus
  the region, so the browser SDK never sees the key
  (`chat-input/speech/speech-service.ts`).
- **Auth providers self-register from env presence.** Each identity provider is
  pushed into the provider array only if its env vars exist, admin status is
  computed inside the provider's `profile()` callback against a comma-separated
  admin-email list, and a dev-only credentials provider is appended when
  `NODE_ENV === "development"` (`auth-page/auth-api.ts`).
- **User identity is a hash everywhere.** All ownership filters use
  `userHashedId()` rather than an email or subject, so the chat corpus carries no
  directly-identifying key.
- **Documents are OCR'd, not parsed.** Upload goes to the vendor's
  document-extraction service (one generic "read" model), whose paragraph list is joined
  and re-split at 2300 characters with 25% overlap — one path for every format,
  no per-format parser.

## Strengths

- **The result envelope is applied without exception**, which makes every service
  function's failure mode inspectable at the call site and gives the UI one error
  component to render.
- **Deployability is a first-class feature**: IaC templates, a `Deploy to`
  button, a devcontainer, and a documented "you do not need to clone this repo"
  path. The docs are numbered as a sequence and cover identity setup, local runs,
  extensions and every environment variable.
- **Citation provenance is durable and scoped**, not reconstructed from the
  prompt at render time.
- **Extensions require no code or redeploy** — a tool is a form submission, and
  admin-published tools become available to the whole tenant. The `isPublished`
  flag is forced to `false` for non-admins server-side.
- **Ownership checks live in a shared helper** (`EnsureExtensionOperation`,
  `EnsureChatThreadOperation`) that admits either the owner or an admin, rather
  than being re-derived per route.

## Weaknesses / Limitations

- **The extension mechanism is an authenticated-user-driven server-side fetch
  with no egress control.** `executeFunction` in
  `chat-api-dynamic-extensions.ts` calls `fetch(functionModel.endpoint, …)` where
  the endpoint is a value the user typed into a form. No scheme check, no host
  allow-list, no private-range or metadata-endpoint block, no size or timeout
  bound, and the response body is returned into the model's context. Any logged-in
  user can make the server read whatever the server can reach.
- **Query substitution splices model output into the URL unescaped.** For each
  key in the model's `args.query`, the code does
  `functionModel.endpoint.replace(key, value)` — a bare substring replace with no
  URL encoding, whose target is not delimited (so a placeholder name that also
  appears in the host or path rewrites those), and which mutates the shared model
  object so the placeholder is consumed after the first call.
- **A derived user identifier is sent as an `authorization` header** to that
  arbitrary endpoint (`headerItems.push({key:"authorization", value: await
  userHashedId()})`). It both leaks a stable per-user identifier to any host a
  user names and trains downstream internal APIs to treat an unsigned, unscoped
  value as authentication.
- **Two different credential models in one app.** The vault uses workload
  identity (the SDK's ambient-credential chain), while the
  document DB is opened with an account key read from an env var
  (the document-DB factory in `common/services/`) — the highest-privilege secret in the system, in
  plaintext config, for the store that holds every conversation.
- **A new DB client per access.** `HistoryContainer()` constructs a fresh client,
  database and container handle on every call, and it is called several times per
  request. No singleton, no pooling.
- **Admin reporting is an unbounded cross-partition scan** with `OFFSET`/`LIMIT`
  paging over the shared container (`reporting-service.ts`) — cost and latency
  grow with the whole tenant's history, not the page.
- **Zero tests.** A recursive tree search for `test`/`spec` returns an empty set.
  There is no unit, integration or contract test anywhere in the repository.
- **Exceptions are stringified into user-visible errors.** Every catch block
  returns `` `${error}` `` as the message, and the UI renders it — a direct path
  for internal endpoints, resource names and SDK internals to reach the browser.
- **Prompt-injection surface is structural.** User-authored extension
  `executionSteps` are concatenated verbatim into the system message, tool results
  are interpolated into the conversation, and the RAG prompt asks the model to
  honour a citation syntax — with no separation, sanitisation or fencing of any
  untrusted segment.
- **An aborted stream loses the answer.** The `abort` handler closes the
  controller without persisting `lastMessage`, while `error` does persist it —
  so a user who stops generation sees text that will not be in history.
- **No per-user quota, rate limit or cost accounting** in a design whose whole
  premise is many users sharing one tenant's model deployment. The reporting
  feature browses transcripts; it reports no tokens, cost or usage.
- **Model identity is invisible to the request.** Calls pass `model: ""` and rely
  entirely on deployment routing in the client factory, so there is no per-request
  or per-persona model choice, and no fallback if that one deployment is degraded.
- **Mode exclusivity caps capability**: a thread with an uploaded document cannot
  use tools in the same turn, because `chat-api.ts` selects one runner.
- **Fixed-size character chunking** with no token awareness, no sentence or
  structural boundary respect, and no re-ranking after vector search.

## Visible vs Hidden Metrics

**Visible (all self-reported or structural — none independently benchmarked):**

| Claim | Evidence in source |
|---|---|
| Private / isolated tenancy | Architectural: everything deploys into the adopter's own subscription; network isolation is asserted in the README, not demonstrated |
| Deploy in one command | Real — IaC templates + CI workflows + button, and the docs state the repo need not be cloned |
| Breadth of features | Real — files, personas, prompt library, extensions, image in/out, speech in/out, admin reporting, theming, 2 identity providers |
| ~1.4k stars / ~1.3k forks | Real, and the ratio says "template", not "dependency" |
| MIT licence | Real |

**Hidden (what an adopter inherits and nobody advertises):**

- **Seven managed cloud services imported directly into feature code** (document
  DB, vector search, OCR, blob storage, secrets vault, speech, hosted models),
  with no provider interface anywhere. Portability cost is a data-layer rewrite,
  not a config change.
- **Upgrades are merges into a fork you now maintain.** The input to this very
  research is the proof: a fork 66 commits behind and two years dead. Every
  customisation raises the cost of the next upstream pull.
- **Zero tests** — so every one of those merges is validated by hand.
- **An SSRF primitive is a shipped feature**, not a bug to be patched: the
  operator inherits "any authenticated user can direct the server's HTTP client"
  as a design property, and the docs present it as the integration story.
- **No cost governor** in a multi-user deployment billed per token.
- **Operational load the templates do not remove**: identity provider setup,
  admin-email list maintenance, vault role assignment (the docs call out doing
  this by hand for local runs), and one plaintext high-privilege DB key to rotate.
- **Learning curve is the framework's, not the app's** — server actions,
  server-only modules and streaming runners; a contributor unfamiliar with that
  model cannot safely touch the service layer.
- **Failure modes concentrate in the streaming path**, where persistence happens
  inside event handlers: abort loses the message, and any handler that throws
  leaves the thread partially written.

**Weighing.** For the intended adopter — an organisation that wants a private
chat UI inside that one cloud this quarter, and will treat the result as a
product it now owns — the hidden costs are acceptable, because the deliverable
is a starting point and the coupling is to a platform already chosen. For anyone
else the visible win inverts: "deploy in an afternoon" is repaid as a permanent
maintenance fork of an untested codebase whose data layer cannot be moved and
whose extension feature must be re-architected before it faces real users. The
two hidden costs that veto rather than discount are the **untested fork-to-own
distribution model** and the **unguarded outbound fetch** — the first makes every
future upstream security fix a manual merge, and the second guarantees there will
be one.

## Phase 2 — AutoBot Comparison

Scope: the five mechanisms Phase 1 identified as transferable, plus the two the
source is worst at (egress, cost governance), each audited against AutoBot code
before any verdict. Every claim below was read in the file, not inferred.

### What We Already Do Better

**Outbound egress — not close.** The source's extension feature is a bare
`fetch()` on a user-typed endpoint. AutoBot's equivalent is layered:

| Control | AutoBot | Reference work |
|---|---|---|
| Scheme allowlist | `security/ssrf_guard.py:352` — http/https only | none |
| Private / loopback / link-local | `url_safety.py:108-122` — `169.254.169.254` hard-blocked **even when** private egress is enabled | none |
| DNS-rebind defence | `ssrf_guard.py:65` `safe_aiohttp_resolver` — connector bypasses DNS on the actual TCP connect | none |
| Redirects | refused on guarded calls, or re-validated and re-pinned per hop (`ssrf_guard.py:230`) | followed |
| Size / timeout caps | `max_bytes=4MB`, `timeout=15s` (`ssrf_guard.py:305-311`) | none |
| Outbound credential | real per-server secret (`integrations/base.py:137`; `resolve_extra_headers_for_server`) | a hashed user id sent as `authorization` |

28 `guard_egress=` call sites cover exactly the user-influenced families —
integrations base, every knowledge connector, the MCP bridge/transport.

**Mode composition.** The source picks one of RAG / multimodal / tools per turn
(`chat-api.ts` `switch (chatType)`). AutoBot composes all three in one turn:
`chat_workflow/graph.py:1547,1581` puts `perform_knowledge_search` unconditionally
before `generate_response`; `manager.py:2467-2486` threads `image_b64` into the
same iteration that carries `used_knowledge`/`rag_citations`; and
`graph.py:1466-1484` `route_after_generation` branches to tools on what the model
actually returned, rather than on a mode chosen in advance.

**Retrieval quality.** The source does fixed 2300-character chunks and no
re-ranking. AutoBot has a cross-encoder re-ranking stage on by default
(`search_components/agentic_search.py:46` `enable_reranking: bool = True`,
`advanced_rag_optimizer.py:806-810` running rerank as stage 3 after hybrid
retrieval), plus MMR diversity, staleness and recency scoring
(`search_components/reranking.py:125-195`), and two genuinely structure-aware
chunkers (`autobot_shared/doc_chunking.py:98-189` header-then-paragraph with a
token budget; `knowledge/pipeline/extractors/semantic_chunker.py:74-121`
paragraph→sentence with token overlap).

**Tool definition.** The source lets any user author a tool as a row: JSON schema
plus endpoint plus method plus headers, executed by a generic unguarded `fetch`.
AutoBot's analogue is admin-only external MCP servers — router-level
`dependencies=[Depends(check_admin_permission)]` (`api/mcp_external_servers.py:36-39`),
credentials resolved from the vault into request headers
(`services/mcp_server_credentials.py:62`), `owner_id` and an `allowed_roles`
defaulting to `["admin"]` (`services/mcp_external_servers.py:46,64`), and tool
schemas **discovered from the server over the MCP protocol**
(`services/mcp_external_bridge.py:119-182`) rather than hand-authored. That is the
same capability with the SSRF primitive removed: the operator authorises a server,
not a URL. **Verdict on the source's version: rejected-by-hidden-metrics** — the
visible win (any user adds an integration with no redeploy) is inseparable from
the hidden cost (an authenticated-user-controlled server-side fetch), and we
already hold the safe form.

**Admin oversight is authorised more finely.** The source gates admin reporting on
one boolean from a comma-separated email list (`auth-api.ts`, `reporting-service.ts`).
AutoBot scopes it to the caller's own organisation and audit-logs each access
(`api/chat_sessions.py:570-609` `_list_org_sessions`;
`security/session_ownership.py:404` `_is_org_admin_access`, which checks role **and**
matching `org_id` before the enforcement-mode branch).

### What We Can Adopt

**1. Compare-against-the-mask on every secret write — adopt, trivial, and it
fixes a live credential-destruction bug.**
Already-exists audit: no write-path mask comparison exists anywhere. Greps for
`if.*==.*(mask|redact|\*{3,})` and for "leave existing secret / unchanged mask"
phrasing across `autobot-backend/`, `autobot-slm-backend/`, `autobot_shared/`,
`autobot-frontend/src` returned nothing. Masking exists only on **read**
(`autobot-slm-backend/api/llm_config.py:113` `_mask_api_key`).
The source does this in one line (`extension-service.ts` `secureHeaderValues`:
`if (h.value !== KEY_VAULT_MASK)`), and on this one point it is ahead of us.
Visible benefit: a masked value round-tripped by a client is a no-op.
Hidden cost: none — it is a comparison on a path that already exists.
**Effort: trivial.** See finding F1 below for the bug it fixes.
Two AutoBot subsystems already avoid the trap by a better route and are the
pattern to copy: `sso_secrets.py:144-189` **omits** the field rather than masking
it, and `knowledge/connectors/credential_store.py:285-332` merges only supplied
fields. Omission beats masking — prefer it where the response shape allows.

**2. Citation ids that survive to the renderer — adopt, trivial, one chokepoint.**
Already-exists audit: every leg exists separately and the chain is broken in the
middle. Durable per-owner storage is real (`knowledge/facts.py:825` mints
`fact_id`, `:739` uses it as the ChromaDB `doc_id`, `ownership_index.py:79-86`
maps it to an owner). The prompt instruction is real and production-wired
(`services/knowledge/service.py:30-33` `CITATION_INSTRUCTION`, reached from
`chat_workflow/llm_handler.py:945-949`). The break is
`services/knowledge/service.py:405`: `"id": fact.metadata.get("id", f"citation_{i}")`
reads a key **no writer ever sets** — the writer sets `metadata["fact_id"]`
(`facts.py:757`). So citation ids are always the per-call rank.
Visible benefit: a citation the user clicks resolves to a durable record.
Hidden cost: none; the value is already in the same dict.
**Effort: trivial** (one key name), plus a test asserting the id is not `citation_*`.

**3. Citations as parsed markup rather than inert text — adopt-with-conditions,
moderate.** Already-exists audit: we instruct the model to emit `[Source N]`
and then never parse it. `ChatMessages.vue:889-926` `formatMessageContentRaw` is
hand-rolled regex markdown that strips whole-word `THOUGHT|PLANNING|DEBUG|SOURCES`
tags and has no citation branch; no markdown library exists to hang a plugin on
(`marked`/`markdown-it`/`vue-markdown` absent from `package.json`). A sources
panel exists (`CitationsDisplay.vue`) but its `citation-click` is not bound in
the live parent, and the component that does bind it (`MessageItem.vue:130-136`)
has no production caller at all.
Visible benefit: the model's own output becomes interactive provenance.
Hidden cost: adding a markdown-AST dependency to a frontend that deliberately
hand-rolls its renderer, and a new parse surface for model-controlled text —
the tag must be rendered as a component, never as HTML, or it is an XSS sink.
**Condition:** do it on the existing regex renderer with a whitelisted pattern, or
adopt an AST renderer deliberately as its own decision — not as a side effect.
**Effort: moderate.**

**4. Short-lived token brokering — already ours, in the better form.** We do this
for realtime voice as an SDP-answer relay
(`voice_processing/realtime/openai_provider.py:37-143`,
`api/realtime_session.py:105-153`): the provider key never leaves the server and
the browser receives only a session-scoped artefact. TTS/STT are fully
server-side, so there is no key to broker. No adoption needed.

**5. Uniform result envelope — rejected as shaped, but the underlying discipline
is a real gap we have already measured.** The source's `ServerActionResponse<T>`
buys consistency, not shape: FastAPI's status codes are a better contract than a
200-with-a-status-field. What the source genuinely has and we do not is *one*
client contract applied without exception. Ours is measured and ratcheted:
`repo_tests/frontend_api_contract_ratchet_test.py:72-91` pins the main frontend at
8 HTTP-client classes, 17 raw `fetch` call sites, 187 hand-typed `*Response`
interfaces and 562 inline generics (SLM: 1 / 3 / 34 / 87, plus 1 axios holdout),
under #12363, #12420, #14062. Already filed — witness, not a new finding.

### Gaps & Opportunities

Ordered by impact. Each was verified in code by this session, not taken from a
report.

| # | Finding | Evidence | Severity |
|---|---|---|---|
| F1 (#17826) | Saving **any** LLM setting in the SLM admin GUI overwrites every configured provider's real API key in the vault with its masked display string | `llm_config.py:127-142` resolves the real key → `:194-196` masks it → `LLMSettings.vue:70-96` round-trips `{...config}` → `llm_config.py:214-216` `if d.get("api_key")` → `llm_secrets.py:96` `vault_rotate(id, "sk-a...b3f2")`. No mask comparison at any hop | critical — silent credential destruction |
| F2 (#17827) | The LLM's own HTTP tool checks the domain allowlist on the initial URL, then follows redirects anywhere | `api/http_client_mcp.py:666` `is_domain_allowed(request.url)`, then `:588-620` `execute_http_request` calls `session.request(...)` directly on a `tracked_session()`, bypassing `HTTPClientManager.request()` where `guard_egress` and `allow_redirects=False` live; `_build_request_kwargs` sets url/headers/timeout/ssl and **not** `allow_redirects` | high — the source's own hole, narrowed to allowlisted-host redirects |
| F3 (#17828) | Citation ids are always synthetic; the durable `fact_id` is never read | `services/knowledge/service.py:405` vs `knowledge/facts.py:757`. Same key-shape class as closed #16708 — second sighting, one fix | medium |
| F4 (#17828) | `[Source N]` is instructed, never parsed; sources-panel click is a no-op; the component that wires it is unreachable | `ChatMessages.vue:889-926`, `:228-231`; `MessageItem.vue:130-136` with zero importers | medium |
| F5 (#17273, #17829) | A disconnected SSE client orphans the generation — no `finally: graph_task.cancel()`, so the LLM call runs to completion, billed and invisible; and there is no stop control to begin with (`stopGenerating` defined in 11 locales, **0** component references) | `chat_workflow/manager.py:3827` create → `:3845` await, nothing between | medium — cost and correctness |
| F6 (#17830) | `add_document` never chunks, despite the class docstring claiming "Add documents with chunking" / "Automatic chunking and vectorization" — a whole transcript or file becomes **one** embedding | `knowledge/documents.py:30,37` (claim) vs `:42-76` → `:77-92` → `store_fact(content, …)`; 8 production callers incl. `api/transcripts.py:229`, `api/knowledge_maintenance.py:558` | medium — silently degrades retrieval |
| F7 (#16845) | Chat-originated spend carries no `user_id`, so per-user breakdowns miss it and the budget hard-stop cannot fire for chat | `services/llm_service.py:1174` `_track_usage(response, session_id)`; called at `:635,969,989` | witnessed on #16845 |
| F8 (#16845) | Two shared rate limiters declared with **zero** callers | `utils/conversation_rate_limiter.py:360`, `user_management/middleware/rate_limit.py:28` | low |
| F9 (#17576) | **Corrected.** I filed this as "nothing enforces rule 8", having searched `repo_tests/` only. Enforcement does exist — `knowledge/connectors/egress_policy_test.py` with a literal five-file `_GUARDED` population — so the true finding is #17576's: the enforcement cannot see a call site it was not told about. #17831 closed as a duplicate | `http_client_manager.py:229-235`; #17576; default ruling #17233 | low — and my version of it was a shallow search reported as an absence |
| F10 (#17832) | Org-scoped admin conversation review works at the API and has no GUI | `api/chat_sessions.py:378,570`; no frontend caller of `scope=org` outside generated types | low — feature gap |

### Specific Code/Files Affected

- `autobot-slm-backend/api/llm_config.py` (+ `user_management/services/llm_secrets.py`) — skip the write when the submitted value equals the mask; better, follow `sso_secrets.py` and omit the field from the response entirely.
- `autobot-backend/api/http_client_mcp.py` — route `execute_http_request` through `HTTPClientManager.request(..., guard_egress=…)`, or set `allow_redirects=False` and re-validate each hop via `pinned_request_with_redirects`.
- `autobot-backend/services/knowledge/service.py:405` — read `fact_id`.
- `autobot-frontend/src/components/chat/ChatMessages.vue` — parse the citation marker; bind `@citation-click`; then either promote or retire `MessageItem.vue`.
- `autobot-backend/chat_workflow/manager.py:3827-3845` — `try/finally` cancelling `graph_task`; wire a stop control to the already-translated string.
- `autobot-backend/knowledge/documents.py:77-92` — chunk before `store_fact`, reusing `autobot_shared/doc_chunking.py`, or correct the docstring if single-vector is intended.

### Filed

| Issue | Finding | Parent / relation | State |
|---|---|---|---|
| #17826 | F1 — LLM settings save overwrites every provider API key with its mask | sub-issue of #10088 (unify AutoBot secrets) | critical, new |
| #17827 | F2 — LLM HTTP tool follows redirects past the domain allowlist | sub-issue of #13623 (connector/credential/egress hardening); same defect **class** as #16562, cross-linked both ways | high, new |
| #17828 | F3+F4 — provenance chain broken at the id, the renderer and the click | sub-issue of #17537 (KB-as-hub roadmap) | medium, new |
| #17829 | F5b — no stop control exists at all | **rescoped**; `blocked_by` #17273 | medium, new (narrowed) |
| #17830 | F6 — `add_document` never chunks | sub-issue of #17527 (KB intake umbrella) | medium, new |
| #17832 | F10 — org-scoped conversation review has no GUI | standalone; no umbrella fits | low, new |
| ~~#17831~~ | F9 — rule 8 enforcement | **closed as duplicate of #17576**; evidence moved there | duplicate |
| #17273 (comment) | F5a — disconnected client orphans the turn | already filed, child of #17271 | witness |
| #17576 (comment) | F9 — enforcement is a five-file literal | already filed | witness |
| #16845 (comment) | F7+F8 — chat spend unattributed; two zero-caller rate limiters | already filed | witness |

### Dedupe pass

Seven issues were filed; **two were rediscoveries of work already on the backlog**, found only
on a second, wider sweep. Recording the miss rather than quietly fixing it, because the pattern
is the point:

- **#17831 → #17576.** Both concern rule 8's enforcement. Mine searched `repo_tests/` and
  concluded *nothing* enforces it; #17576 had already found the enforcement that exists —
  `knowledge/connectors/egress_policy_test.py`, populated by a literal five-file dict — and
  stated the sharper finding: the enforcement cannot see a call site it was not told about.
  A narrower search produced a *stronger-sounding* and less true claim. Closed as duplicate.
- **#17829 → #17273.** #17273 (child of #17271, filed earlier from a different comparison) has
  the orphaned-graph-task finding with more evidence: it also covers `resume_graph` and the
  missing total timeout on the streaming call. My issue was rescoped down to the one thing
  #17273 does not cover — that no stop control exists — and marked `blocked_by` it.

Both misses came from searching with the vocabulary of the *source* rather than the vocabulary
of our own backlog. The first-pass queries were phrased as `guard_egress ratchet` and
`streaming abort task cancel`; the issues that already existed are titled around *"rule 8's only
enforcement is a five-file literal"* and *"a disconnected client leaves the LangGraph turn
running"*. Searching the symptom found nothing; searching the subsystem found both.

Clusters the surviving issues belong to, for anyone picking this up:

| Cluster | Issues |
|---|---|
| Egress / rule 8 | #13623 (umbrella) · #17827 · #17576 · #17233 · #16562 · #17249 · #13625 |
| Chat turn lifecycle | #17271 (umbrella) · #17273 · #17829 · #16805 |
| KB intake & retrieval quality | #17527 (umbrella) · #17830 · #14480 · #13245 · #17625 |
| Answer provenance | #17537 (roadmap) · #17828 · #17215 |
| Secrets custody | #10088 (umbrella/PRD) · #17826 · #17099 · #16450 · #13051 · #17097 |
| Usage attribution & quota | #16845 · #16951 |

Already filed and witnessed, not re-filed: the API-contract sprawl the source's
uniform envelope would address (#12363, #12420, #14062, ratcheted at
`repo_tests/frontend_api_contract_ratchet_test.py:72-91`), and the citation
key-shape class first fixed in #16708 — F3 is its second sighting at a different
site, so it is one defect with two witnesses, fixed once in #17828.
