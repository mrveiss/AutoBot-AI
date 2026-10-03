---
tags:
  - research
  - architecture
  - security
aliases:
  - Self-Hosted Deployment Control Plane
---

# Source Analysis: a self-hostable deployment control plane

> Phase 1 of a two-phase research run. Source identity (vendor, repository, authors) is
> deliberately absent from this file — see the anonymization rule in the `research` skill.
> Everything below was read read-only over the hosting provider's contents API and raw
> file endpoints; nothing was cloned or executed.

## What It Is

A vendor-built, self-hostable deployment platform — a PaaS control plane that takes a
source (git repo, local folder, or prebuilt artifact), detects the stack, builds a
container or bare release, runs it on loopback only, then writes a reverse-proxy vhost and
issues TLS. Around it sit managed Postgres/MySQL/Mongo/Redis, an SMTP engine, a CDN, a
backup scheduler, and per-project traffic monitoring. It is driven from four surfaces that
share one engine: a desktop app, a web dashboard, a CLI, and a JS/TS SDK — plus a REST API
and an MCP endpoint for agents. TypeScript monorepo (~136 MB checkout), Apache-2.0 for
first-party code, roughly seven months old, and already heavily starred — adoption is
running well ahead of the codebase's age. Self-hosting is unbilled; a managed cloud tier is
the commercial arm.

## Architecture & Key Patterns

- **Monorepo, engine-once / surface-many.** `apps/{api,cli,dashboard,desktop,edge,email,web}`
  over `packages/{core,contracts,adapters,platform,db,sdk,ui,onboarding}`. The deployment
  engine lives in `packages/platform` + `packages/core`; every surface is a thin caller.
  The CLI bundles the API and dashboard, so "install the CLI" and "install the server" are
  one act.
- **A dependency-free contracts package.** `packages/contracts` holds runtime schemas and
  public types with *no* database, HTTP-framework, provider, or app dependencies. Types are
  *inferred from* the runtime schemas, and the same validator runs on both ends — the remote
  SDK checks the response with the identical predicate the server used to compose it.
  Unknown fields are ignored deliberately, for wire compatibility; internal engine arguments
  are excluded from the public contract by construction.
- **Route registry as the single authority for permissions, docs, and agent tools.** One
  HTTP route registry carries a permission tag and an optional `mcp` block per route. MCP
  tools, the API reference, and the permission matrix are all *generated from it* rather
  than maintained alongside it.
- **Two runtime flavors from one binary.** "Compose mode" (Linux + Docker) brings up
  Postgres, Redis, API, dashboard and a host-networked nginx/Lua edge on :80/:443 and hosts
  deployed apps on the same box. "Bare mode" (macOS/Windows/Docker-less Linux) is a single
  process with an embedded database that deploys *outward* over SSH. The desktop app is bare
  mode that only lives while the window is open.
- **Edge counts, control plane collects.** Request measurement happens entirely in the
  nginx `log_by_lua` phase; a scheduled job moves pre-aggregated counters to Postgres every
  30 minutes. A visitor's request never reaches the API or the database.
- **Deploy-then-route ordering.** Routing and TLS are applied *after* the app is up, so a
  DNS or ACME failure surfaces as "action required" instead of failing the deploy or taking
  a running app down.

## Notable Implementation Details

1. **Signed internal call provenance** (`apps/api/src/lib/call-source.ts`). Agent tool calls
   re-enter the app through its own `fetch()` with the caller's bearer token, precisely so
   routing, auth and permissions are not duplicated — which makes an agent-driven write
   indistinguishable from a scripted token write at the middleware layer. Rather than trust
   an `x-...-source` header (forgeable with curl), the dispatcher signs the claim with a
   **nonce generated at boot and never transmitted**: only a request originating inside the
   process can produce it, compared in constant time, and a forged header silently falls
   back to deriving the source from the credential. A second signed claim names *which*
   client (`oauth:<id>` / `pat:<id>`), because "an assistant did this" and "*that* assistant
   did this" are different facts, and only the second tells an operator which connection to
   revoke.
2. **Opt-in agent-tool exposure with capability-aware listing**
   (`apps/api/src/modules/mcp/mcp-tools.ts`). A route becomes an agent tool only if its spec
   declares an `mcp` block — an allowlist, not a filter over everything. Credential and token
   routes can never opt in. `tools/list` is then filtered *per principal*: the caller's role,
   read-only flag, wildcard grants and repo-content tier decide which tools are even visible,
   and each tool carries `readOnlyHint` / `destructiveHint` annotations. Handlers dispatch
   internally, so no business logic is duplicated per tool.
3. **The consent page as the only writer of the authority binding**
   (`apps/api/src/middleware/mcp-consent.ts`). The upstream OAuth library honours its consent
   page only when `prompt=consent` is present *exactly*; standard agent clients omit it, so
   the middleware injects it. The reason is structural: the consent POST is the sole writer of
   the org+scope binding the token check requires, so a token minted on the bypass path has no
   binding and **is denied everything** rather than being over-privileged. The same middleware
   rejects an unrecognised RFC 8707 `resource` with `invalid_target` instead of ignoring it,
   so a client can never end up holding a token it believes is scoped to a server that was
   never authorized.
4. **Documentation derived from the type checker, then guarded in CI** (`scripts/docs-*.mjs`).
   `docs-surface.mjs` instantiates a TypeScript program and walks the *checker* to extract the
   public SDK interface (including resolving overloaded rest-tuple signatures rather than
   documenting a parameter literally named `args`), shells out for real CLI `--help` text, and
   derives the HTTP surface from the route registry. `check-docs.mjs` then validates every MDX
   page, its navigation and links, *and* the generated SDK/CLI/agent-tool references — using
   the website's own MDX parser and heading plugin, resolved through `createRequire`, so CI
   needs no separate parser, global CLI or git binary. Doc *examples* are checked too
   (`check-docs-examples.mjs`, `check-docs-cli.mjs`).
5. **Update prompting is a separate, version-pinned decision** (`release-advisories.json`).
   Shipping a release does not nag anyone: clients fetch this manifest **pinned to the latest
   release tag**, so edits on the default branch are invisible until a version ships. Each
   advisory has two independent knobs — `severity` (how loud the in-app banner is) and
   `announce` (whether a client may *interrupt* the user at all) — plus a semver `affects`
   range, a per-mode filter (desktop / self-hosted / cloud), and an action. Critical
   advisories surface once even when notifications are muted.
6. **Delegated authority without stored secrets** (`packages/core/src/execution-authority.ts`,
   19 lines). A saved/scheduled action persists user id, org id, token *identifier* and kind,
   and its restrictions (org pin, read-only, expiry) — explicitly "never bearer secrets or
   roles". Re-execution re-resolves the live authority instead of replaying a captured one.
7. **Bounded cardinality with disclosed degradation** (`docs/monitoring.md` + the edge Lua
   handler). Per-request work is ~a dozen atomic shared-dict increments, one get and one ring
   buffer write, all in the phase that runs *after* the response is flushed; the thousandth
   request in a minute touches the same keys as the first. Every unbounded dimension is capped
   deliberately — query strings stripped and numeric/UUID path segments collapsed to `:id`
   with a 2000-path/day tail folded into `other`; a fixed 1000-slot request ring with a 1-hour
   TTL; a per-day salted visitor hash in its own 64 MB zone. The part worth copying: when the
   visitor zone evicts, the count *understates*, the status endpoint reports each zone's free
   space, and the UI **marks the figure approximate rather than presenting an eviction
   artifact as a measurement**.
8. **Frozen config snapshots.** The resolved build/run configuration is snapshotted at deploy
   time so a redeploy or rollback re-runs exactly what shipped, rather than re-detecting the
   stack against a moved repo.
9. **Resumable releases.** `scripts/release-resume.ts` and `npm-release-resume.ts` (both with
   unit tests) let a partially-completed multi-artifact release continue instead of restarting.

## Strengths

- **Contract, permission, documentation and agent-tool surfaces all derive from one
  registry.** Drift between them is a compile/CI error, not a discovery.
- **Security reasoning is written down at the point of enforcement.** The most interesting
  comments explain the *attack* ("and so could anyone with curl"), not the mechanism.
- Agent (MCP) integration is treated as a first-class, least-privilege surface — opt-in,
  per-principal filtered, non-forgeably attributed, and audited — rather than a wrapper that
  re-exposes the API.
- Failure ordering is designed for availability: measurement cannot delay a request, and
  edge/TLS problems cannot take down a healthy app.
- Honest operational disclosure: the host-socket privilege, the GPL component, the "not a
  production path" dev installer and the incomplete docs are all stated in the repo.
- Extensive test co-location (`*.test.ts` beside implementation), five CI workflows including
  a dedicated release gate and a scaling e2e suite.

## Weaknesses / Limitations

- **Host-privileged by design.** The API container mounts the host Docker socket, and a
  container→host SSH channel exists for :80/:443 takeover, the mail engine, and host
  terminal/port scans. Documented, but it means a control-plane RCE is a host compromise;
  the raw-compose path silently lacks that channel, producing a class of "works except for
  host operations" failures.
- **No file-size discipline.** `packages/core/src/stacks.ts` is 1,377 lines and
  `audit-taxonomy.ts` 1,173 — more than twice AutoBot's enforced 600-line ceiling. Nothing
  ratchets it down.
- **Decision records live in a 36 KB `TODO.md`**, including an "Open TODO markers in code"
  register and a "Known gaps" section. The gaps being *stated* is a genuine strength; keeping
  them in one growing file rather than as tracked issues means they are neither assignable
  nor closable.
- **The repo doubles as a work journal.** `docs/` carries dated PR reviews, bugfix-batch
  notes and point-in-time audits alongside current architecture docs, so a reader cannot tell
  present doctrine from historical record without checking dates.
- **License hygiene is an open liability for redistributors.** A GPL mail engine is bundled
  into several control-plane distributions *even when mail is never configured*, and the
  licensing inventory records an outstanding upstream-notice review.
- **Two runtime flavors double the behavior matrix** (embedded DB + outward SSH vs
  Postgres/Redis + local hosting), and the split is platform-determined rather than chosen.
- **Young and fast-moving**: a ~132 KB changelog in ~7 months, with multi-node clusters,
  private networking and load-balancing still on the "coming next" list. Docs are
  self-described as actively being filled in.
- Toolchain demands Bun + Node 22; the from-source build is explicitly flagged as unsuitable
  for production.

## Visible vs Hidden Metrics

- **Visible:** very high star/fork counts for a seven-month-old project; a breadth claim
  spanning CI/CD, databases, TLS, CDN, mail, backups and monitoring; "production-ready core";
  Apache-2.0; a ten-language README; and a precise performance claim — **~1.4 µs added per
  request** (~3.1 µs with per-path collection), zero per-request I/O, zero Postgres rows per
  request, ≤1440 rows/domain/day. *Self-reported* — but uniquely, stated with enough method
  (which nginx phase, which key shapes, which zones) to be independently reproduced, which is
  more than most benchmark claims offer. Feature breadth is unverified. Star count measures
  attention, not reliability.
- **Hidden:** the host-socket/SSH privilege an adopter inherits; a GPL component shipped into
  distributions regardless of use; the upgrade treadmill implied by the release cadence; two
  runtime modes to reason about in every support conversation; decision debt parked in a
  monolithic TODO; no size or complexity ratchet, so `stacks.ts`-scale files are the
  trajectory; single-vendor governance with a commercial cloud tier, i.e. the self-hosted
  edition's roadmap is set by someone else's business; and a learning curve that only bites
  at the edge — the Lua handler, ACME behavior, and edge vhost generation are where operators
  will actually get stuck.
- **Weighing:** as a *product to run*, the hidden costs are real but priced honestly and mostly
  accepted knowingly — the host-socket privilege is the single item that should stop anyone
  running it on a shared or untrusted host. As a *source of patterns*, the weighing inverts:
  the patterns worth taking (signed internal call provenance, opt-in agent tools with
  per-principal listing, consent-as-sole-authority-writer, type-checker-derived docs guards,
  the severity/announce split in update prompting, disclosed measurement degradation) are
  small, self-contained and carry almost none of the platform's hidden cost, because none of
  them depend on Docker, the edge, or the monorepo layout. The costs that would veto adoption
  — privilege surface, GPL bundling, runtime duality — attach to the *platform*, not to the
  ideas.

## Second pass — the node-lifecycle layer

Read after the Phase 2 focus was set to *deploying and maintaining nodes* (AutoBot SLM's
scope). These are the source's fleet-management patterns, all in `packages/core` (isomorphic,
dependency-free) or `packages/adapters/src/system` (the SSH/exec layer — SLM's Ansible layer
is the analogue).

### The pattern worth the most: two named probe primitives

`packages/adapters/src/system/probe-exec.ts` exists because the same helper had been written
five times byte-identically, and the traced variant twice with the second missing its
reporting half. The two are kept side by side because *choosing between them is the
load-bearing decision*:

| | Behaviour | For |
|---|---|---|
| `tryExec` | Swallows everything, including a dropped transport. `null` = the command did not complete · `""` = it completed and printed nothing | Probes whose answer is optional — one tier of a fallback ladder, a best-effort rollback — where "couldn't ask" and "asked, got nothing" lead to the same next step |
| `probeExec` | Traces the attempt, **keeps the failure text**, and re-throws a transport drop | Probes that report a verdict to a human: an unreachable host must abort the whole check rather than be recorded per-component as "not installed" |

The comment records the incident that produced it: collapsing the two made a real bug
undiagnosable, because a probe that *failed* and a probe that *answered nothing* both rendered
as the static string "the daemon is not running" — so the daemon's own words ("permission
denied while trying to connect to the Docker daemon socket", "Command timed out after
10000ms") were read off the wire and then **discarded in favour of a guess the reporter had no
way to check**. And the boundary is stated: neither primitive is for a command that *changes*
the box, because "a mutation whose failure is discarded is a silent skip".

This is AutoBot's own measurement doctrine — *a `0` from a failed command is not a measurement*
— implemented as **two typed functions at the exec boundary** rather than as a rule in a
document that a call site can forget to consult.

### Absence as a first-class value

`packages/adapters/src/system/output-exists.ts` returns a probe result where *absence is the
signal*: `checked: false` means the probe could not run (callers "must treat `checked:false` as
'no signal', never as 'missing'"), and `status` / `served` are **absent** rather than `0` /
`false` when there was no HTTP signal at all. The stated failure mode: "a caller that reads
`!served` instead of `served === false` turns 'no signal' into a false alarm."

The same file also makes a *which question is this about* argument: a filesystem check
structurally cannot answer what an HTTP request can — correct files with unreadable modes, a
vhost that was never written, a document root the edge container cannot see — so a probe
meant to predict a 404 has to be an actual request, not a stat.

### `none` and `unknown` are different states with different rules

`packages/core/src/host-profile.ts` is "what one target host IS — the facts, and nothing about
what to do with them": pure unions plus the classification of `/etc/os-release`, with detection
in `system/environment.ts` and the acting commands in `system/environment-ops.ts`. Three things
it does that a fleet manager would want:

- The firewall union separates `none` ("we looked and found no manager", so the rule is raw
  iptables with its caveat) from `unknown` ("we couldn't look" — the API is containerized and
  cannot see the host's package list, so it must offer both forms), and keeps `iptables`
  distinct from both, because rules exist and are enforced by something the platform cannot
  drive, so *a rule we add may not survive a reboot*.
- Distros the platform **refuses to drive are named in the union on purpose**, turning
  "unsupported host" into a specific, actionable sentence with the observed ID quoted back.
- It lives in the isomorphic package specifically so the dashboard and the SSH layer share one
  member list — "what makes exhaustiveness real rather than per-package theatre".

`packages/adapters/src/system/privilege.ts` answers "may I do root-owned work on this host, and
through which executor" once, after three layers had answered it differently and a non-root
host's EACCES was attributed to whichever step happened to surface it first. Two details
transfer directly: the **order** is deliberate — the host verdict is checked *before* privilege,
because privilege is the narrower question and its message shadowed the real one on exactly the
hosts the check exists for (a forced-command image cannot report a uid at all, so it reads as
unprivileged and gets told to "connect as root", the opposite of the fix) — and the branded
type is called `ROOT_CHECKED`, deliberately "checked" rather than "capable", because "a brand
that lies is worse than none: it makes the reader stop checking".

### One failure-shape taxonomy for every reachability check

`packages/core/src/connectivity.ts` is a single dependency-free contract for every "can we
reach / authenticate / use this target" question — SSH servers, backup destinations, cluster
nodes, mail servers — classifying the *shape* of the failure while never opening a connection
itself. `ok` is separate from `code`; `code` distinguishes `unreachable` · `auth_failed` ·
`permission_denied` · `timeout` · `protocol_error` · `misconfigured` · `unknown`; and
`latencyMs` is present only "when measured". The frontend maps copy once per code instead of
per check.

### Degraded capability announced once, with scope

`apps/api/src/lib/host-channel-banner.ts` diagnoses the container→host control channel **at
boot**, classifying the outcome (`unreachable` · `not_configured` · `key_unreadable` ·
`auth_rejected`) and printing three things: what is *unaffected*, the explicit list of
operations *blocked until the channel works*, and the symptom an operator will otherwise see.
It "never throws and never blocks boot". The existence rationale is a fleet-management fact:
the channel's address is host-local, so unlike a published container port it traverses the
host's `filter/INPUT` chain, where a default-deny firewall silently DROPs it — including on
hosts whose firewall changed *under a running install*.

### Update prompting: two questions, two sources, resolved once

`packages/core/src/updates/` + `release-advisories.json`. `resolve.ts` states it plainly —
*"is there something newer to install?"* comes from the release feed (version + a platform
asset), *"may I interrupt the user about it?"* comes from the advisory manifest **and only it**,
and both are folded into one decision that callers act on; "nothing downstream re-fetches the
manifest or re-decides from severity". The resolved `announcement` carries the advisory
author's own title and message, so a caller that prompts "can say WHY without inventing copy".
`advisories.ts` treats the manifest as **untrusted third-party data** — malformed entries are
dropped, not trusted — and normalizes `announce` in exactly one place, which is "the only place
severity is allowed to imply anything about interrupting". Clients read the manifest pinned to
the latest release *tag*, so edits on the default branch cannot nag anyone.

### Retention arithmetic shared so the two sides cannot drift

`packages/core/src/rollback-window.ts` keeps the rollback-window maths in core because the API
enforces it and the dashboard renders and clamps it — "a second hand-written `Math.min(20, …)`
in a settings component is how the two drift". Two details: a **blank string is "not set", not
zero**, because `Number("")` is `0` and one cleared form field would otherwise purge every
restorable release; and `MIN_AUTO_ROLLBACK_WINDOW = 2` keeps rollback existing "whenever we can
measure at all", even on a cramped host. `operation-limits.ts` does the same for exec timeouts,
output byte caps, generated-config size/count caps and a 100-target ceiling on a single deploy
fan-out — "shared bounds used by public schemas and their runtime implementations", so the
schema and the implementation cannot disagree about a limit.

---

## Untrusted-content handling

The repository ships agent-instruction files (an agent-config directory at the root among
them). They were not read, followed, or executed, and nothing in this run acted on fetched
content: no clone, no script execution, no package install. All fetched text was treated as
data. No injected-instruction attempt was observed in the files that were read.

---

# AutoBot Comparison: the reference work → AutoBot SLM (node deploy + maintain)

Phase 2 focus set by the owner: *what can SLM learn — we also deploy nodes and maintain them*.
Scope is `autobot-slm-backend/` (the node lifecycle plane: Ansible playbooks, node/service/
secret/update routes), `autobot-slm-frontend/`, and the shared audit/auth layers it depends on.
Every AutoBot claim below was verified by reading the cited lines, not inferred from a filename.

**Filed from this analysis** — umbrella [#17656](https://github.com/mrveiss/AutoBot-AI/issues/17656), a child of the SLM lifecycle umbrella
[#10016](https://github.com/mrveiss/AutoBot-AI/issues/10016):

| Issue | Finding |
|---|---|
| [#17657](https://github.com/mrveiss/AutoBot-AI/issues/17657) | `rollback_deployment` runs no playbook; the node keeps the software |
| [#17658](https://github.com/mrveiss/AutoBot-AI/issues/17658) | Node operations write no audit row — [#17038](https://github.com/mrveiss/AutoBot-AI/issues/17038)'s paper-trail half unenforced |
| [#17659](https://github.com/mrveiss/AutoBot-AI/issues/17659) | "A node is behind" is the same signal as "interrupt the user" |
| [#17660](https://github.com/mrveiss/AutoBot-AI/issues/17660) | Five sites turn a failed measurement into a real-looking value |
| [#17661](https://github.com/mrveiss/AutoBot-AI/issues/17661) | Maintenance windows and drain are enforced by nothing |
| [#17662](https://github.com/mrveiss/AutoBot-AI/issues/17662) | The agent HTTP bridge forwards `x-internal-api-key`, which mints admin |

Cross-linked onto existing work rather than re-filed: call-site evidence on [#16036](https://github.com/mrveiss/AutoBot-AI/issues/16036)
(sibling — `reboot_strategy` is the same class from another end), the paper-trail gap on
[#17038](https://github.com/mrveiss/AutoBot-AI/issues/17038), three witnesses on the detector-blindness umbrella [#15826](https://github.com/mrveiss/AutoBot-AI/issues/15826), and the
second rollback surface plus the playbook file-size observation on [#17262](https://github.com/mrveiss/AutoBot-AI/issues/17262).

The mapping is close: SLM's Ansible layer is the reference work's `packages/adapters/src/system`
(remote exec on hosts), SLM's node model is its `host-profile` + node rows, and SLM's code-sync
updater is its `updates/` + advisory manifest. Nothing about its Docker/edge/TypeScript stack
needs to come along for the patterns to apply.

## Axis 1 — Who did this to my node? (provenance)

**The reference work's position.** An agent tool call re-enters the app through its own
`fetch()` with the caller's token, so at the middleware layer an agent-driven write and a
scripted token write are *identical* — and rather than trust a header, the dispatcher signs the
source claim with a **boot-generated nonce that is never transmitted**, compared in constant
time, with a forged header falling back to deriving source from the credential
(`apps/api/src/lib/call-source.ts`). A second signed claim names *which* client, because that is
the fact that decides which connection an operator revokes.

**AutoBot's position — verified.** SLM has the tables and the vocabulary and does not write to
them from node operations:

| Finding | Evidence |
|---|---|
| Node operations write no audit row at all. `AuditLogCategory` defines `NODE_MANAGEMENT`, `SERVICE_CONTROL` and `DEPLOYMENT`; **zero non-test writes of any of them exist** | `autobot-slm-backend/models/database.py:696-706` (enum); `grep -rn 'AuditLogCategory\.' --include=*.py` excluding tests → no hits |
| The audit writer that does exist is wired only to auth/SSO/API-key paths, never to node routes | `autobot-slm-backend/api/security.py:60-97` (`create_audit_log`), callers in `api/sso_auth.py`, `api/auth.py`, `services/api_key_audit.py` |
| `NodeEvent`, the one thing node operations *do* write, has **no actor column** | `autobot-slm-backend/models/database.py:226-243` |
| Reboot discards the authenticated user and writes a hardcoded literal actor | `autobot-slm-backend/api/nodes.py:2211-2216` binds `_: Annotated[dict, Depends(get_current_user)]`; `api/nodes.py:2172` writes `{"action": "reboot", "initiated_by": "api"}` — the same string whoever called |
| Same shape for service restart, secret apply, update apply — `current_user` bound to `_`, and `UpdateJob` has no actor column | `api/services.py:554-558`, `api/secrets.py:234-237`, `api/updates.py:906-908`, `models/database.py:317-338` |
| Where an actor *is* captured it is a bare subject string with no actor-*type* field | `api/deployments.py:238,332`, `api/blue_green.py:95,237`, `api/nodes.py:1605` — all `current_user.get("sub"/"username", "unknown")` |
| A scheduled sync leaves no queryable trail distinguishable from anything else | `services/schedule_executor.py:223-275` calls `code_distributor.trigger_node_sync` in-process, writing only `logger.info` |
| **The identity-collapse seam.** A bare shared-secret header mints a synthetic admin *before* any user-JWT check | `autobot-backend/auth_middleware.py:879-880` returns `{"username": "service:slm", "role": "admin", "service": True}` for anyone presenting `X-Internal-API-Key`; SLM's mirror is `services/auth.py:316-354` |
| The generic agent HTTP bridge strips six credential headers and **not** that one | `autobot-backend/api/http_client_mcp.py:107-115` blocks `authorization`, `cookie`, `set-cookie`, `x-api-key`, `x-auth-token`, `x-csrf-token`, `x-xsrf-token`; `x-internal-api-key` appears nowhere in the file |

**Where we are ahead.** No node operation is exposed as an agent tool today — the MCP server
carries only KB/memory/agent tools (`autobot-backend/mcp_server/autobot_server.py:655-859`), and
`reboot`/`apply_secret`/`decommission` are not registered anywhere as tools. So the reference
work's per-principal `tools/list` filtering solves a problem we have not yet created. The
reachable path is the generic bridge, which allowlists destination **domains**
(`http_client_mcp.py:81-97`), not routes or verbs — so the moment an internal host is
allowlisted, every route on it is reachable by any verb, with "destructive" expressed only as
prose in a tool docstring (`http_client_mcp.py:505`).

**Verdict: adopt, in three separable pieces.**

1. *Write the audit rows the enum already promises.* Trivial-to-moderate: the table, the writer
   and the categories exist; node/service/secret/update routes need to call the writer and stop
   binding `current_user` to `_`. This is a defined-but-never-written gap, not a new subsystem.
2. *Add an actor-**type** dimension* (human · schedule · agent · internal-service), not just a
   subject string. Moderate. Without it, "did an agent reboot production or did a person?" is
   unanswerable even once rows exist.
3. *Make the internal-service claim attributable.* The current header is a single shared secret
   that grants admin and is indistinguishable per holder; the reference work's answer (a
   process-local nonce proving *inside this process*, plus a per-client claim) is the right
   shape, but our seam is different — ours is cross-service, so a nonce alone does not transfer.
   The transferable half is the *requirement*: the audit column must record which holder acted,
   and a bridge that forwards credential headers must blocklist this one. **Hidden cost:** adding
   `x-internal-api-key` to `BLOCKED_HEADERS` is a one-line change with a real blast radius — any
   existing internal caller routing through that bridge on purpose would break, so it needs a
   call-site sweep first, not a blind edit.

## Axis 2 — Should this update interrupt anyone? (maintenance)

**The reference work's position.** Two questions, two sources, resolved exactly once:
*is there something newer to install?* → the release feed; *may I interrupt the user about it?*
→ the advisory manifest **and only it** (`packages/core/src/updates/resolve.ts`). The manifest is
parsed as untrusted data with malformed entries dropped, `announce` is normalized in the single
place "severity is allowed to imply anything about interrupting", the resolved announcement
carries the author's own copy so a prompt can say *why* without inventing text
(`updates/advisories.ts`), and clients read it pinned to the latest release **tag** so
default-branch edits cannot nag anyone (`release-advisories.json`).

**AutoBot's position — verified.**

| Finding | Evidence |
|---|---|
| Version discovery is a git commit-hash diff, not a release/semver feed — so there is no artifact on which an advisory *could* be carried | `autobot-slm-backend/services/git_tracker.py:150-213` (`git fetch --prune`, `git rev-parse origin/<branch>` vs local HEAD), persisted at `git_tracker.py:295-317`, polled every 300 s (`git_tracker.py:33,322-364`) |
| "A node is behind" **is** "interrupt the user" — one signal, no severity gate. The only suppressor is a per-version `localStorage` dismissal | `autobot-slm-frontend/src/components/UpdateNotification.vue:29-33` → `shouldShow = !isDismissed && hasOutdatedNodes`; `src/composables/useCodeSync.ts:390-392` → `status.outdated_nodes > 0` |
| A severity concept exists but only for OS packages, and it only filters a list and colours a badge — it never escalates to a different notification | `models/database.py:300` (`low/medium/high/critical`), `api/updates.py:367-378` (`_classify_severity` in practice emits only `security` vs `standard`), consumed at `api/updates.py:682,710-711,745` and `autobot-slm-frontend/src/views/SystemUpdatesTab.vue:187-193` |
| `UpdatePolicy` (manual/security/full) governs what may **auto-apply** per node role — a different axis from whether to notify | `services/manifest_loader.py:207-259`, `api/nodes.py:2674-2716` |
| **Maintenance windows and drain are built and enforced by nothing.** Claim checked by following the chain, not by grepping the routes: `MaintenanceWindow` is referenced **only** by its own model definition and its own CRUD router across `autobot-slm-backend`, `autobot-backend` and `autobot_shared` (non-test, non-migration), so no shared helper can be enforcing it; and `NodeStatus.MAINTENANCE` is read at exactly three sites, all of them drain/undrain/window-activation themselves | `models/database.py:507-510` + `api/maintenance.py` only; `status_enums.py:45`, `api/maintenance.py:398`, `api/nodes.py:2113,2119,2147`; reboot's full chain `api/nodes.py:2211-2239` → `_execute_reboot_playbook` (`:2182-2194`) → `executor.execute_playbook("reboot-node.yml", limit=[node_id])` passes no window or drain state |
| Reboot is fire-on-request: the only gate is "not already offline" | `api/nodes.py:2228-2239` — rejects `NodeStatus.OFFLINE`, then emits the event and runs `reboot-node.yml` |
| The one real gate is inside a playbook, not in policy: `apply-system-updates.yml` reboots only on `/var/run/reboot-required` **and** a caller-supplied `auto_reboot` (default false) | `ansible/apply-system-updates.yml:19,161-164,185-201` |

**Where we are ahead.** Two genuine wins. Our OS-update classification is *measured from the
host* — `check-system-updates.yml:24-67` parses `apt list --upgradable`, separates packages whose
apt line carries `-security`, and queries Ubuntu Pro ESM status — where the reference work has no
equivalent OS-patch plane at all; its advisory severity is hand-authored per release by a human.
And `UpdatePolicy` per node role (`manifest_loader.py:207-259`) is a fleet concept it lacks
entirely: it decides update *prompting*, we decide update *permission*, and permission is the
harder half.

**Verdict: adopt the split, not the manifest.** The transferable idea is one sentence —
*"there is something newer" and "interrupt someone about it" are different facts with different
owners, resolved once, and only one source may answer the second.* Our banner currently derives
the second from the first, which is why a routine fleet drift and an urgent security drift look
identical in the UI.

- **Adopt (moderate):** separate the two signals, and let the already-measured
  `security_update_count` be the thing that raises urgency, since we compute it and then only
  colour a badge with it. No new fetch, no new manifest, no coupling.
- **Adopt-with-conditions (moderate):** wire `maintenance_windows` and `drain` into the reboot
  and update-apply paths. This is a *finish the work* item, not a new feature — the primitives
  exist and enforce nothing, which is worse than absent because the UI implies a control that
  the disruptive path ignores. **Related existing issue: [#16036](https://github.com/mrveiss/AutoBot-AI/issues/16036)**
  (open, `priority: high`) is the same gap from another end — it records that
  `ManifestSystemUpdates.reboot_strategy` is declared per role and never read, because
  `api/updates.py:163,949` hardcodes `auto_reboot: "false"`, and that `services/blue_green.py`
  already implements role borrowing and health-gated rollback which the update path never calls.
  It does **not** cover `MaintenanceWindow` or `NodeStatus.MAINTENANCE`/drain, which are separate
  declared controls with their own missing enforcers — so this belongs as a cross-linked sibling
  plus the call-site evidence on #16036, not as a duplicate of it.
- **Rejected by hidden metrics:** a version-pinned advisory manifest of our own. It presumes a
  tagged-release artifact per version; our updater is a git-commit diff against a configured
  source, so adopting the manifest means first adopting a release-tagging pipeline — a large
  coupling cost to buy a prompting policy we can express with the severity we already compute.
  Revisit only if tagged releases arrive for another reason.

## Axis 3 — Can we reproduce, and can we undo? (deploy pipeline)

**The reference work's position.** Three things hold together: the *resolved* build/run config is
snapshotted at deploy time so a redeploy or rollback re-runs exactly what shipped rather than
re-detecting against a moved repo; the retention arithmetic lives in one isomorphic module so the
API and the dashboard cannot drift (`packages/core/src/rollback-window.ts`); and every host
mutation goes through a **rollback journal** — one file, one rollback implementation, one
boot-recovery path, where a takeover abandoned by the CLI is restored by the API on its next boot
and vice versa (`packages/adapters/src/system/proxy/takeover-journal.ts`). Two details of that
journal are the whole lesson: `completed?: boolean` is set *only* after success, so **its absence
means roll back** rather than "probably fine"; and a container's recorded `restart` policy being
**absent means the policy was never read — not that there wasn't one**, because collapsing a
refused `docker inspect` (`null`) with Docker's own spelling of "no policy" (`""`) via `|| "no"`
made rollback write `--restart=no` over an operator's `always` container, which then never came
back after a reboot.

**AutoBot's position — verified.**

| Finding | Evidence |
|---|---|
| No config snapshot. The `Deployment` row stores role *names*, status, error, raw `playbook_output`, `triggered_by`, `extra_data` — no resolved vars, pins, or inventory values | `autobot-slm-backend/models/database.py:111-136` |
| Inventory is re-rendered from live DB state on every run, into a temp file that is then unlinked | `services/playbook_executor.py:1174` (`select(Node)` → `build_registry_inventory`), deleted at `1381-1385`; `api/nodes.py:1029-1038` builds a throwaway inventory string per provision |
| Secrets are re-fetched fresh per call | `services/playbook_executor.py:1320-1321` (`fetch_deploy_secrets`) |
| **"Rollback" is DB bookkeeping only — it runs no playbook.** It subtracts the deployed role names from `node.roles` and marks the row `ROLLED_BACK`. Whatever was installed on the node stays installed | `services/deployment.py:419-440`, verified: `node.roles = list(current_roles - deployed_roles)`, then `status = ROLLED_BACK`; grepping the whole function for `playbook`/`ansible` → **no hits** |
| Auto-rollback in the reconciler is the same set-difference, also with no playbook | `services/reconciler.py:1546-1571` |
| Retry copies role names only, then re-renders live | `services/deployment.py:445-472` |
| Per-run execution state is an **in-process dict**, self-documented as needing a database. A control-plane restart loses the record of what ran | `api/infrastructure.py:436` — `_executions: dict[str, PlaybookExecution] = {}` under the comment `# In-memory storage for executions (in production, use database)`; `PlaybookExecution` (`api/infrastructure.py:71-81`) holds one status/output for the whole fan-out, no per-host breakdown |
| Post-install failures cannot mark a deployment failed, because they are not part of it. TLS deployment returns `{"success": False}` and never touches `Node.status` or any `Deployment` row | `api/tls.py:966-971`; DB-only cert endpoints `api/nodes.py:2425,2484` mutate only `Certificate.status` |
| There is no `action_required` state. `NodeStatus` and `DeploymentStatus` have no such member; the nearest thing is a string written into `NodeEvent.details` JSON by the reconciler, for auto-remediation exhaustion rather than post-install gaps | `status_enums.py:36-46,49-57`; `services/reconciler.py:785,880,1247,1519` (`"action_required": "manual_review"`) |
| `deploy-dns.yml` has no Python call site at all — operator-run only | searched all non-test `.py` under `autobot-slm-backend`; **NOT DETERMINED** whether it is invoked from anywhere outside the repo |

**Where we are ahead — and it is the sharpest win in the whole comparison.** Our fleet-update
entrypoint is a *canonical redirect with the incident recorded in it*. `ansible/update-all-nodes.yml`
is a 22-line file that does nothing but `import_playbook: playbooks/update-all-nodes.yml`, because
it used to be a stale duplicate that deployed new backend code and restarted the service but
**never ran the migration sequence**, leaving the DB behind the code (#11424, flagged in #9710).
The canonical playbook runs `pg_dump` backup → baseline adoption → `alembic upgrade head`,
fail-closed, *before* restarting the backend. The reference work has no comparable
schema-ordering story anywhere we could find, and its own `probe-exec.ts` header documents the
same disease — a helper written five times, the second traced copy missing its reporting half —
handled reactively rather than by a redirect that makes the duplicate impossible.

Second win: our fleet rollout is *considered*, not accidental. Play 2 runs `serial: 3` with
`any_errors_fatal: true` (`ansible/playbooks/update-all-nodes.yml:762,766`) — deliberately
stopping the rollout rather than limping — with `block`/`rescue` used precisely where one node's
agent failure should *not* abort the fleet (comment at `:1850-1856`). That is a real
blast-radius policy; the reference work's 100-target deploy ceiling
(`MAX_DEPLOY_SERVICE_TARGETS`) is a bound, not a policy.

**Verdict.**

- **Adopt (moderate) — the journal, for host mutations we already make.** Our disruptive paths
  stop and disable things on nodes; nothing records what the prior state was, so nothing can put
  it back, and nothing recovers a run the control plane died in the middle of. The transferable
  core is small: a durable per-run record of *what was changed and how to restore it*, a
  completion marker whose **absence** triggers recovery, and one recovery entrypoint at boot.
  This subsumes the `_executions` in-memory gap rather than competing with it — the same record
  gives per-node results that survive a restart.
- **Adopt-with-conditions (moderate) — snapshot the resolved run.** Store the rendered inventory
  values, role versions and playbook identity on the `Deployment` row. Condition: **secrets must
  not enter the snapshot** — the reference work's `ExecutionAuthority` shows the discipline
  (identifiers and limits, never bearer secrets), and our `fetch_deploy_secrets` re-fetch is
  currently the right behaviour for exactly that reason. Snapshot the *reference*, keep the
  re-fetch.
- **Adopt (trivial, and the most urgent item on this axis) — stop calling it rollback.** A
  DB-only role subtraction named `rollback_deployment`, returning `ROLLED_BACK`, tells an
  operator the node was reverted when the software is still installed and running. This is the
  reference work's own stated principle turned on us: *a brand that lies is worse than none,
  because it makes the reader stop checking.* Either the operation performs an uninstall, or it
  is renamed to what it does (detach / unassign) and the UI says the node still carries the
  software. Renaming is trivial; uninstalling is significant; **doing neither is the current
  state.**
- **Rejected by hidden metrics — the isomorphic shared-arithmetic package.** The reference work
  can put clamping logic in one TypeScript module both ends import; our control plane is Python
  and our dashboard is Vue, so the equivalent is a generated contract, not a shared import. The
  drift risk it addresses is real for us, but the fix belongs to the API-contract generation
  question, not to node lifecycle.

## Axis 4 — Does a failed measurement look like a measurement? (health honesty)

**The reference work's position.** Covered in the second-pass section above: `tryExec` vs
`probeExec` as two deliberately different primitives, `checked: false` and *absent* fields as
"no signal", `none` vs `unknown` as distinct firewall states with different rules, one
`ConnectivityCode` taxonomy across every reachability check, and a boot banner that states what
still works and what is blocked.

**Where AutoBot is already ahead — three places, independently arrived at.**

| Ours | Evidence |
|---|---|
| `_unmonitored()` returns `monitored: False` with **every** reading `None` for "a card sysfs shows but no vendor tool measured" — the reference work's `checked:false` pattern, arguably cleaner because the fields are `None` rather than merely absent | `autobot_shared/gpu_telemetry.py:286-298`; per-field `None` on an unreadable value at `108-113` |
| The frontend **labels** unmonitored/unreadable GPU values instead of rendering them as current | `autobot-slm-frontend/src/components/monitoring/NodeGpuSummary.vue:12,31-55` |
| Defaults lean to "not known yet" rather than "fine": node `status` defaults to `PENDING` not online, `code_status` defaults to `CodeStatus.UNKNOWN`, and `_map_status_from_states` reserves `"unknown"` for "probe got no usable answer" | `models/database.py:63,84`; `slm/agent/health_collector.py:296-330` |
| Cardinality is capped where it matters, including the reference work's own trick — the Prometheus route label uses the matched **template**, never the raw path, with an `"unmatched"` fallback | `middleware/api_request_counter.py:12-16,60-61`; alerts `MAX_ALERTS_RETURNED = 100` (`api/monitoring.py:438,510`); agent event buffer `max_events=500` with pruning (`slm/agent/agent.py:360-384`); journal context capped 5 lines and descriptions `[:500]` (`health_collector.py:358,384-409`) |
| Staleness is recorded **and** surfaced: `last_heartbeat` is stored, exposed, rendered as relative time, and independently drives DEGRADED/OFFLINE on a `heartbeat_interval * unhealthy_threshold` cutoff | `services/reconciler.py:1685,1763,575-627,475,590-595`; `autobot-slm-frontend/src/views/FleetOverview.vue:389,748`; `components/monitoring/NodeMetricsGrid.vue:64-72,173-174` |
| Write amplification is already flat: one `nodes` row updated **in place** per heartbeat, one `services` row upserted per discovered unit, events appended only on status *change* — no per-sample row. Time series live in Prometheus (15 d, 512 MB cap), not Postgres | `services/reconciler.py:1666-1699,1768-1811,1813-1886,1724-1738`; `autobot-monitoring/prometheus.yml:38-42`; `docker-compose.yml:745-756` |

That last row matters for the weighing: the reference work's headline "zero DB writes per request"
design is one we **already have** on the node plane, reached independently. Its monitoring doc is
worth reading for how it *states* the cost, not for the architecture.

**Where we collapse a failed measurement into a real-looking value — four sites.**

| Site | What it does | Why it reads as a measurement |
|---|---|---|
| `autobot_shared/gpu_telemetry.py:136-140` | `power.draw`, `clocks.current.graphics`, `clocks.current.memory` pass through `or 0.0` / `or 0`, and the docstring **documents** the collapse | An unreadable power draw becomes `0.0 W` — indistinguishable from an idle GPU. In the same file that gets `monitored: False` right |
| `slm/agent/health_collector.py:188-196` | `check_port` returns bare `False` on any exception | "Port closed" and "could not ask" are the same value, with no reason preserved anywhere |
| `slm/agent/health_collector.py:183-186` | `check_service` returns `{"active": False, "status": "timeout"}` / `"health check failed"` | Partially honest — the *reason* survives in `status`, but a caller reading `active` alone sees a cleanly inactive service. This is exactly the reference work's warning about reading `!served` instead of `served === false` |
| `models/database.py:72-74` | `cpu_percent`, `memory_percent`, `disk_percent` default to `0.0` | A node that has never heartbeated reads as 0% load rather than unknown |
| `api/health.py:86-95` | On a DB exception, `nodes_online = 0` and `nodes_total = 0`, with `db_status = "unhealthy"` set separately | Anything charting the counts sees a real-looking `0 / 0` fleet; the disclaimer is in a different field |

Plus one retention gap: `node_events` has **no automatic pruning** — only manual endpoints
(`api/errors.py:833-857`, `api/monitoring.py:513-531`), with no scheduler found calling either
(**NOT DETERMINED** whether an external cron does).

**Verdict: adopt the two-primitive discipline, narrowly.** Not as a doctrine document — we
already have one, and these five sites exist anyway. As **typed probe helpers at the agent's exec
boundary**, so a call site has to choose between "couldn't ask" and "asked, got nothing" the way
the reference work's callers do. Effort: moderate, and it is mostly the four call-site fixes plus
a shared result shape; the honest version of `check_port` is a tri-state, not a bool. **Hidden
cost, stated plainly:** every consumer of these values has to be updated in the same change, or a
`None` where a `0.0` used to be will render as a blank tile or crash a chart — so this is one PR
per probe surface with its frontend consumers, not a sweep. **The GPU site is the cheapest and
highest-value start**, because the correct pattern already exists eleven lines away in the same
file.

## The pattern behind three of these findings

Three of this audit's findings are the same defect class, and naming it is more useful than the
three separately: **a declared vocabulary with no consumer** — each side internally consistent, so
no test can see the gap.

| Declared | Consumer that was never written |
|---|---|
| `AuditLogCategory.NODE_MANAGEMENT` · `SERVICE_CONTROL` · `DEPLOYMENT` (`models/database.py:696-706`) | No non-test writer of any of the three exists |
| `MaintenanceWindow` (`models/database.py:507-510`) + `POST /{node_id}/drain` (`api/nodes.py:2092-2122`) | No enforcer outside its own CRUD router; the disruptive paths never consult it |
| `UpdateInfo.severity` (`models/database.py:300`), computed from real host measurement (`api/updates.py:367-378`) | Nothing escalates on it — it filters a list and colours a badge (`api/updates.py:682,710-711,745`) |

[#16036](https://github.com/mrveiss/AutoBot-AI/issues/16036) independently records a fourth in the
same plane, in almost the same words: `reboot_strategy` "is **never read by the update path** — it
is dead declaration". The class is already tracked repo-wide under the detector-blindness umbrella
[#15826](https://github.com/mrveiss/AutoBot-AI/issues/15826); these are witnesses to it, so they
raise its priority rather than its count.

What the reference work does differently is structural rather than diligent, and that is the part
worth taking: its declarations *are* the producers. Agent tools are **generated from** the route
registry, so a route cannot declare an `mcp` block that nothing exposes; the API reference is
**derived from** the TypeScript checker, so a documented method that does not exist is a CI
failure; `advisories.ts` normalizes `announce` in the one place "severity is allowed to imply
anything about interrupting", so a severity that escalates nothing cannot exist. A vocabulary that
generates its consumer cannot drift from it.

## Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-slm-backend/api/nodes.py` (`:2172`, `:2211-2216`, `:2092-2122`, `:2228-2239`) | Stop discarding `current_user`; write a real audit row instead of `initiated_by: "api"`; gate reboot on maintenance window / drain state |
| `autobot-slm-backend/api/services.py:554-558`, `api/secrets.py:234-237`, `api/updates.py:906-908` | Same: capture the actor, write the audit row the category enum already defines |
| `autobot-slm-backend/api/security.py:60-97` + `models/database.py:696-706` | Add an actor-**type** dimension (human · schedule · agent · internal-service) alongside the subject |
| `autobot-backend/api/http_client_mcp.py:107-115` | Add `x-internal-api-key` to `BLOCKED_HEADERS` — after a call-site sweep, since some internal caller may rely on forwarding it |
| `autobot-slm-backend/services/deployment.py:419-472` + `services/reconciler.py:1546-1571` | Either make rollback uninstall, or rename it to what it does and say so in the UI |
| `autobot-slm-backend/models/database.py:111-136` | Snapshot columns for the resolved run (inventory values, role versions, playbook identity) — references only, never secret values |
| `autobot-slm-backend/api/infrastructure.py:71-81,436` | Move `_executions` to a durable table with per-node rows; fold in a completion marker whose absence drives recovery |
| `autobot-slm-backend/services/playbook_executor.py` | Write the host-mutation journal entries; one recovery entrypoint at boot |
| `autobot_shared/gpu_telemetry.py:136-140` | Drop `or 0.0` / `or 0`; `None` means unread — the `_unmonitored` pattern in the same file is the model |
| `autobot-slm-backend/slm/agent/health_collector.py:183-196` | Tri-state probe results; `check_port` must be able to say "could not ask" |
| `autobot-slm-backend/api/health.py:86-95` | Report unknown counts as unknown, not `0` |
| `autobot-slm-backend/models/database.py:72-74` | Nullable metric columns, so "never measured" is not `0.0` |
| `autobot-slm-frontend/src/components/UpdateNotification.vue:29-33`, `composables/useCodeSync.ts:390-392` | Separate "a node is behind" from "interrupt someone"; let the already-computed `security_update_count` raise urgency |

## One thing we should not repeat from our own criticism

This study faulted the reference work for having no file-size discipline (a 3,302-line
`nginx.ts`, a 1,377-line `stacks.ts`). Our own fleet-update playbook is **2,260 lines / 102 KB**
(`autobot-slm-backend/ansible/playbooks/update-all-nodes.yml`), and the 600-line `MAX_LINES`
ratchet only covers `.py` (plus `.sh`, since #17353). The Ansible plane has the same disease we
named in theirs; the ratchet simply cannot see it. Counted across the tree: **17 YAML files over
600 lines, 33,996 lines in them**, 7 of them Ansible. Filed as **#17675**.
