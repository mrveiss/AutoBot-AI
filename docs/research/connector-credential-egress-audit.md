# Audit: connector, credential and egress layer

**Date:** 2026-08-05
**Scope:** `knowledge/connectors/`, `integrations/`, `autobot_shared/security/ssrf_guard.py`,
`autobot_shared/url_safety.py`, and the agent tool surface.
**Method:** review of an external connector-gateway implementation covering the same problem
domain (credential custody, provider egress, agent-facing action catalog), then a line-by-line
comparison against our own. Every finding below cites a file that was read.
**Filed as:** umbrella #13623, children #13624-#13632.

---

## Summary

The secrets layer underneath is mature and no changes are proposed to it. The findings are all in
the **connector shim on top of it**, plus the egress guard's redirect handling.

Two are live bugs that fail silently in production. Two are fail-open guards. Five are structural
gaps. One is a decision for the owner.

---

## Reference patterns considered

The external implementation solves the same problem at roughly 100x our provider count. Four of its
design choices are transferable; one is not, and the reasoning for rejecting it is recorded because
it is the kind of idea that gets re-proposed.

| Pattern | Verdict for us |
|---|---|
| Strip credential-bearing headers on cross-origin redirect hops, using an explicit header allowlist rather than a name pattern | **Adopt** — #13624 |
| Deployment-gated private-network opt-in: permit RFC-1918 targets for an operator-configured instance host while hard-blocking reserved/loopback/link-local/metadata in both states, and never applying the opt-in to user-supplied URLs | **Adopt** — #13625 |
| Separate the operator-owned OAuth *app* config from the user-owned *credential*, resolving app config at refresh time rather than copying it into each credential | **Adopt** — #13630 |
| Compute declared-vs-executable capability flags on every catalog response, derived from real handler resolution | **Adopt** — #13631 |
| Policy decisions that return the matched rule and its source layer, for allows as well as denials | **Fold into #13588/#13592**, not a new mechanism |
| Progressive tool discovery — a handful of search/read/execute tools fronting a very large action catalog instead of one tool per action | **Rejected at our scale** — see below |

### Why progressive tool discovery is rejected

It is the most elegant idea in the reference implementation, and it is correct there: a catalog of
~10,000 actions cannot be expressed as tool definitions in any context window, so discovery has to
become a search.

We have roughly 40 tools. [`tools/tool_registry.py:849-894`](../../autobot-backend/tools/tool_registry.py#L849-L894)
returns a flat list of ~25 registry tools plus `BROWSER_TOOL_NAMES`;
[`chat_workflow/tool_handler.py:495`](../../autobot-backend/chat_workflow/tool_handler.py#L495)
holds a static `_BUILTIN_TOOL_SCHEMAS`; the MCP manifest
([`mcp/autobot_server.py:560-570`](../../autobot-backend/mcp/autobot_server.py#L560-L570)) returns
all tools filtered by token scope. The whole manifest fits in context with room to spare.

Adopting search-then-execute would buy nothing and cost an extra LLM round trip before every tool
use, a search index to keep in sync with the registry, a second discovery protocol alongside the
existing manifest, and a new failure mode: the search misses a tool and the agent cannot know what
it did not see.

**Revisit trigger:** if `services/mcp_bridge_workers` starts federating third-party MCP servers and
the aggregate tool count crosses a few hundred, this becomes the right design. Record the trigger;
do not build ahead of it.

Related observation: [`get_compressed_descriptions()`](../../autobot-backend/tools/tool_registry.py#L827)
spends an LLM call per tool to shrink descriptions we can afford to send verbatim. If manifest size
is a real cost today, that is the thing to re-measure — not a retrieval layer.

---

## Findings

### Live bugs

**1. An OAuth refresh response without `expires_in` permanently disables refresh** (#13626)

[`credential_store.py:272`](../../autobot-backend/knowledge/connectors/credential_store.py#L272)
overwrites `access_token_expires_at` from the refresh response.
[`_expiry_iso`](../../autobot-backend/knowledge/connectors/credential_store.py#L324) returns `None`
when `expires_in` is absent — which RFC 6749 §5.1 permits, and several providers do — and
[`_access_token_expired`](../../autobot-backend/knowledge/connectors/credential_store.py#L338)
treats a missing expiry as non-expiring. The credential is then never refreshed again. It keeps
working until the access token actually lapses, at which point every sync fails with a provider 401
and no self-healing path.

The failure is silent and delayed: it surfaces hours or days after the refresh that caused it, with
nothing in the logs pointing back at it.

The fix is not "carry the old expiry forward" — a refresh only runs once that timestamp is already
past, so the credential would look permanently expired and refresh on every call. Persist the
last-reported **lifetime** and recompute `now + lifetime` when a refresh response omits it.

**2. Concurrent `get_access_token` calls both refresh** (#13627)

[`credential_store.py:230-288`](../../autobot-backend/knowledge/connectors/credential_store.py#L230-L288)
is read → refresh → write with no lock, transaction, or compare-and-swap. The code already notes at
line 274 that some providers rotate the refresh token on each use — exactly the case this races on.
Two callers refresh with the same token, the provider rotates twice, and the last writer wins; if
the stored token is not the provider's currently-valid one, the next refresh fails permanently.
Some providers treat reuse of a rotated refresh token as a breach signal and revoke the entire
grant family (OAuth 2.0 Security BCP §4.14.2).

A scheduled connector sync overlapping a user-triggered one is ordinary operation, not an edge case.

### Fail-open guards

**3. Owner check skips rather than denies on a missing owner** (#13628)

All three ownership guards — [`load()`:135](../../autobot-backend/knowledge/connectors/credential_store.py#L135),
[`rotate()`:155](../../autobot-backend/knowledge/connectors/credential_store.py#L155),
[`get_access_token()`:252](../../autobot-backend/knowledge/connectors/credential_store.py#L252) —
use `if stored_owner and stored_owner != owner_id`. An empty `created_by` skips the comparison
entirely. This is the only per-user boundary on a decrypted connector credential.

The OAuth path's `str(user.get("user_id") or "system")` fallback
([`knowledge_connector_oauth.py:106`](../../autobot-backend/api/knowledge_connector_oauth.py#L106))
avoids empty owners but collapses distinct users into one shared owner instead — a second, milder
problem on the same line.

**4. `rotate()` decrypts without attribution** (#13628)

[`credential_store.py:148-151`](../../autobot-backend/knowledge/connectors/credential_store.py#L148-L151)
omits `accessed_by`, which [`secrets_service.py:360`](../../autobot-backend/services/secrets_service.py#L360)
uses to drive access tracking. Rotation is the most privileged read path and the only one that
leaves no attributed audit record. The caller has `owner_id` in hand.

### Egress

**5. Cross-origin redirect replays the caller's credential headers** (#13624)

[`ssrf_guard.py:132-187`](../../autobot_shared/security/ssrf_guard.py#L132-L187) re-resolves and
re-pins each hop — good, and stronger than the reference implementation on rebinding — but passes
the caller's `headers` unchanged to every hop while `current_url` is reassigned (line 170 vs 185).
A 302 to a foreign **public** origin is followed with the original `Authorization` attached. The
per-hop pinning stops private-address redirects; it does nothing about this.

Reachable: this function exists specifically for `web_fetch` and `media/link/pipeline` (#13019),
which run on the agent path over content the agent does not control.

**6. Six connectors with user-configured hosts never touch the guard** (#13625)

| connector | config key | concat site |
|---|---|---|
| `knowledge/connectors/confluence.py:92` | `base_url` | `:225` |
| `knowledge/connectors/jira.py:100` | `base_url` | `:240` |
| `knowledge/connectors/gitlab.py:134` | `gitlab_url` | `:135` |
| `knowledge/connectors/gitlab.py:486` (Gitea) | `gitea_url` | `:487` |
| `knowledge/connectors/nextcloud.py:94` | `nextcloud_url` | `:113` |
| `integrations/base.py:125-149` | per-integration | bare `aiohttp.ClientSession` per request |

Grepped all six for `is_public_url|ssrf_guard|pinned_connector`: zero hits.

**Not a duplicate of #13204**, which is scoped to the four browser execution paths and never
mentions connectors or integrations.

The likely reason it was never guarded: a self-hosted Confluence/GitLab/Nextcloud legitimately
lives on a private network, so `is_public_url` as-is would break the feature it protects. The
deployment-gated opt-in pattern resolves that. The delta we need is in
[`url_safety.py:88-96`](../../autobot_shared/url_safety.py#L88-L96), which collapses private /
loopback / link-local / multicast / reserved into a single boolean — "private" has to become
separable so it can be selectively permitted while the rest stays hard-blocked.

### Structural gaps

**7. Credentials carry no account identity** (#13629)

Grepped `credential_store.py` for `profile|account_id|granted_scope`: zero hits. The stored OAuth
bundle holds tokens, client credentials, the token URL, and a raw scope string — nothing
identifying the account. A user with two Slack workspaces connected cannot tell which one an agent
will act as, and a re-auth against a *different* account is silent. This matters more for us than
for a single-operator gateway, because we have per-user RBAC and multiple users' credentials in one
store.

**8. The OAuth app client secret is duplicated into every user's credential bundle** (#13630)

[`_oauth_bundle`:312-313](../../autobot-backend/knowledge/connectors/credential_store.py#L312-L313)
copies `client_id`/`client_secret` — operator-owned, one per provider — into every per-user
credential secret so refresh can run without re-reading provider config. Rotating the app secret
would therefore require rewriting every user's stored credential, and no code path does that: a
rotation would silently strand every existing connection.
[`oauth_flow.py:96`](../../autobot-backend/knowledge/connectors/oauth_flow.py#L96)
already resolves app credentials from settings, so refresh could resolve at use time instead.

**9. `OAuthProvider` is thinner than real providers require** (#13630)

[`oauth_flow.py:39-50`](../../autobot-backend/knowledge/connectors/oauth_flow.py#L39-L50) has six
fields. Deviations that currently have nowhere to go except a per-provider code branch: a separate
refresh URL, token-endpoint auth method (basic vs post vs none), form-vs-JSON token requests,
per-grant-type parameter renames, non-standard response envelopes, a comma scope separator, and
extra operator-supplied config fields required before authorization can start. Cheap as declarative
fields now; expensive to retrofit after `if provider == "x"` branches accumulate.

**10. No declared-vs-executable capability flags** (#13631)

[`registry.py:187`](../../autobot-backend/knowledge/connectors/registry.py#L187) `list_types()`,
[`registry.py:254`](../../autobot-backend/knowledge/connectors/registry.py#L254) `health_check_all()`,
and [`integrations/base.py:103`](../../autobot-backend/integrations/base.py#L103)
`get_available_actions()` — none distinguishes a declared capability from a runnable one. Our
current answer is retrospective (`dead-code-audit`, `claims-audit`, periodic campaigns); #13227's
findings include three declared-but-unwired MCP features, all found after they shipped.

Implementation constraint: the flags must derive from real handler resolution. A hardcoded
`executable: True` converts an audit-findable gap into an audit-proof one.

**11. Two connector families model one concept** (#13632 — owner decision)

Slack, Notion and GitHub each exist in **both** `knowledge/connectors/` and `integrations/`, with
separate base classes, registries, credential handling, and egress paths. This is why finding 6 has
to fix egress in two places. Three options are laid out in the issue; option 2 (unify the seams,
keep both base classes) is recommended as the cheapest that removes the security-relevant
duplication without foreclosing full convergence later.

---

### Platform rule: credentials always go through the canonical secrets manager (#13643)

Owner directive, 2026-08-05: **anywhere credentials or connectors are used, use the canonical
secrets manager as the single platform** — one framework for passing credentials to modules, agents
and users in a safe, controlled manner. Not merely "encrypted at rest": a credential must be
*referenced*, *granted*, *audited*, and *revocable*, never handed across a module boundary as a bare
value.

Audit result — `integrations/` violates this completely:

`rg -l 'secrets_service|SecretsService|credential_store' autobot-backend/integrations/` returns
**zero hits**. [`IntegrationConfig`](../../autobot-backend/integrations/base.py#L38-L51) holds
`api_key` / `api_secret` / `token` / `password` as plain `str` fields, each described as
`"(stored encrypted)"` — a claim nothing in the package implements. The value is used directly at
[`base.py:135-136`](../../autobot-backend/integrations/base.py#L135-L136).

Credentials arrive as plaintext from four upstreams, none of them the store: HTTP request bodies
(`api/integration_cloud.py:244`, `integration_cicd.py:304`, `integration_database.py:82`),
`ssot_config` (`integrations/capability_registry.py:115`), the LLC `external_pm_config` blob via a
separate `encrypt_field`/`decrypt_field` path (`llc/api/companies.py:658,693` →
`llc/sync/outbound_sync.py:176`), and `agent_loop/slack_hook.py:75`.

Because integrations hold **values** rather than **references**, no platform guarantee applies: no
grant (possession is authorization), no audit (`accessed_by` never set), no revocation handle, no
rotation, and no `secret_dependencies` edge — so #10088 Task 8.3's rotation impact analysis has a
permanent blind spot exactly where third-party credentials live.

Two adjacent partial violations: `api/user_provider_credentials.py:94,183` borrows
`SecretsService`'s **cipher only** and writes its own row, inheriting the encryption but none of the
audit/expiry/grant machinery; and operator OAuth **app** credentials resolve from `config.auth.*`
rather than the System vault ([`oauth_flow.py:96-109`](../../autobot-backend/knowledge/connectors/oauth_flow.py#L96-L109)),
which is the upstream of #13630.

Filed as **#13643**, cross-linked to #10088 Task 5.

## What we already do better

Recorded so none of these get "fixed" toward the reference implementation.

1. **DNS-rebind defence is real, not advisory.**
   [`safe_aiohttp_resolver`](../../autobot_shared/security/ssrf_guard.py#L65-L104) pins the socket
   to a pre-verified IP with `use_dns_cache=False`, and `pinned_request_with_redirects` builds a
   fresh pinned connector per hop. The reference implementation cannot do this at all — connection
   pinning is not expressible over the fetch API it is built on, so its DNS check loses to a
   low-TTL attacker. Ours does not.
2. **Fail-closed DNS.** [`is_public_url`](../../autobot_shared/url_safety.py#L143-L145) returns
   `False` on any resolution failure. The reference falls through to the transport so unreachable
   hosts surface a natural network error — friendlier, weaker.
3. **Auth is a different class of system.** The reference is admin token plus runtime tokens,
   single operator, no multi-user RBAC. We have full user management, SSO/SCIM, per-user RBAC,
   run-JWT scopes mapped to tool prefixes
   ([`autobot_server.py:72-79`](../../autobot-backend/mcp/autobot_server.py#L72-L79)), pre-auth
   throttling per client IP plus an endpoint-wide ceiling (#13268), constant-time comparison, and a
   no-default-credential policy that fails fatally rather than authenticating everyone (#13266).
4. **The secrets layer is mature.** `models/secret.py` carries owner, org, scope, team ids,
   `shared_with`, envelope `sealed_value`, `version`, `expires_at`, `is_active`, with a separate
   grant model, credential isolation formalised in ADR-007, and the #10088 unification running as a
   proper expand/contract cutover behind two independent read/write flags. No changes proposed.
5. **Connector depth beats connector breadth.** `AbstractConnector`
   ([`base.py:63`](../../autobot-backend/knowledge/connectors/base.py#L63)) gives every connector
   incremental sync, Redis checkpointing, change detection, retry with backoff, bounded concurrency,
   and stored-config version migration — with per-connector tests. Twelve connectors that resync
   correctly are worth more to a KB-ingesting system than a thousand untested ones.

---

## Filed

Umbrella **#13623**.

| # | Issue |
|---|---|
| #13624 | security(ssrf): cross-origin redirect replays the caller `Authorization` header |
| #13625 | security(connectors): six connectors bypass the SSRF guard; needs private-network opt-in |
| #13626 | bug(oauth): refresh without `expires_in` permanently disables refresh |
| #13627 | bug(oauth): concurrent `get_access_token` loses a rotating refresh token |
| #13628 | security(secrets): owner check fails open; `rotate()` has no audit attribution |
| #13629 | feat(connectors): credentials carry no account identity |
| #13630 | canonical(oauth): app client secret duplicated per user; `OAuthProvider` too thin |
| #13631 | feat(connectors): no declared-vs-executable capability flags |
| #13632 | canonical(connectors): two connector families — owner decision needed |

## Sequencing

1. **#13626** — live, silent, delayed production failure. First.
2. **#13624** — trivial, closes a credential leak on the agent path.
3. **#13627** — live race with permanent-disconnect potential.
4. **#13628** — two small hardening fixes in one file.
5. **#13625** — moderate, six call sites plus the `_ip_is_public` split.
6. **#13629**, **#13630**, **#13631** — capability work.
7. **#13632** — owner decision, blocks nothing.

Policy-audit-trail work folds into #13588/#13592 rather than being filed separately.

## Deliberately not proposed — do not re-file

- Progressive tool discovery (reasoning above; revisit trigger recorded).
- Mass provider onboarding / a provider-catalog generator. The reference ships its very large
  provider set with no provider-level regression tests in its open repository, by explicit policy.
- Adopting an external gateway as a runtime dependency: a second gateway process, credential store,
  and policy model is a net loss for a system that needs roughly a dozen integrations.
