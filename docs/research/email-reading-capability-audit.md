# Email Reading Capability — Audit & Company OS (LLC) Opportunity

**Date:** 2026-08-08
**Question:** Does AutoBot have email *reading* capability? Would the Company OS (LLC)
module benefit from the CEO agent having an email address?
**Method:** audit-first — grep + read the actual modules, verify wiring before claiming
a gap. Every claim below cites a path.

**Tracking umbrella:** [#13707](https://github.com/mrveiss/AutoBot-AI/issues/13707) —
company mailbox for Company OS: inbound email, autonomy-gated, vault-backed.

---

## Tracking issues

Every gap identified below is filed. This table is the map from a finding to the issue that
owns it — and back: each issue cites the section here that produced it.

| Wave | Issue | Gap | Section |
| --- | --- | --- | --- |
| — | [#13707](https://github.com/mrveiss/AutoBot-AI/issues/13707) | **Umbrella** — company mailbox for Company OS | all |
| 0 | [#13588](https://github.com/mrveiss/AutoBot-AI/issues/13588) | Agent seam authorises by tool name, fails open on unknown agent id | 2.2 |
| 0 | [#13250](https://github.com/mrveiss/AutoBot-AI/issues/13250) | Tool approval gated twice by different mechanisms (backend) | 3.1 |
| 0 | [#13421](https://github.com/mrveiss/AutoBot-AI/issues/13421) | Five approval surfaces, three `risk_level` definitions (frontend) | 3.1, 3.3 |
| 1 | [#13708](https://github.com/mrveiss/AutoBot-AI/issues/13708) | Credential redaction is name-keyed, blind to free text | 4.3 |
| 1 | [#13709](https://github.com/mrveiss/AutoBot-AI/issues/13709) | Approval memory scoped per project path | 3.1 |
| 1 | [#13710](https://github.com/mrveiss/AutoBot-AI/issues/13710) | Outlook integration has no API router; duplicate `__all__` entry | 1.3 |
| 2 | [#13712](https://github.com/mrveiss/AutoBot-AI/issues/13712) | No mail connector — email never reaches the knowledge base | 1.5, 3.2 |
| 2 | [#13713](https://github.com/mrveiss/AutoBot-AI/issues/13713) | Orphaned Gmail service cannot run | 1.2, 2.5 |
| 3 | [#13714](https://github.com/mrveiss/AutoBot-AI/issues/13714) | No mailbox GUI | 3.3 |
| 3 | [#13715](https://github.com/mrveiss/AutoBot-AI/issues/13715) | Mail has no autonomy/sign-off model | 3.1 |
| 3 | [#13711](https://github.com/mrveiss/AutoBot-AI/issues/13711) | Agents have no write path to the vault; no provenance | 4.2, 4.4 |
| 4 | [#13716](https://github.com/mrveiss/AutoBot-AI/issues/13716) | Company OS has zero email | 1.6, 2.1 |
| 5 | [#13718](https://github.com/mrveiss/AutoBot-AI/issues/13718) | Agent cannot sign up for services | 3.4, 4.5 |
| — | [#13845](https://github.com/mrveiss/AutoBot-AI/issues/13845) | `CommandRisk` vs `CommandRiskLevel` — same concept, divergent tails | 3.1 |
| — | [#13846](https://github.com/mrveiss/AutoBot-AI/issues/13846) | `SecretType` vs `SecretRequirement` — duplicate taxonomy, no OAuth requirement | 4.2 |

**Critical path:** #13708 → #13712 → #13715 → #13716 → #13718.
Issues #13710 and #13711 have no blockers inside the umbrella and may start at any time.

**Ordering constraint that drives the waves:** a credential copied into the vector store
cannot be revoked, so #13708 ships *before* #13712 — see section 4.3.

---

## Answer in one line

**Outbound email works and is wired. Inbound email reading does not exist as a reachable
capability** — three partial implementations exist, and *none* of them can be called by
anything: one has zero callers and an undeclared dependency, one has no API router, one
is Slack/Teams/Discord only.

---

## Part 1 — What exists today

### 1.1 Outbound SMTP — REAL, WIRED, IN USE

[`autobot-backend/services/notification_service.py`](../../autobot-backend/services/notification_service.py)

- `NotificationChannel.EMAIL` (line 63); `_send_email()` (line 414) using stdlib `smtplib`
  with `MIMEText`, TLS-aware.
- Config via SSOT: `AUTOBOT_SMTP_HOST/PORT/USER/PASSWORD/FROM/TLS`
  (`autobot_shared/ssot_config.py`).
- Genuinely called — not dead: `autobot-backend/celery_app.py`,
  `autobot-backend/orchestration/workflow_executor.py`, `autobot-backend/api/push.py`,
  `autobot-backend/push_notifications/mobile_push.py`,
  `autobot-backend/services/autoresearch/auto_research_agent.py`.
- Sibling channels on the same service: `SLACK`, `WEBHOOK`, `IN_APP`, `TELEGRAM`.

**Verdict: AutoBot can send mail. It cannot receive it.**

### 1.2 Gmail — BUILT, UNREACHABLE (three independent reasons)

[`autobot-backend/operator_dashboard/gmail_service.py`](../../autobot-backend/operator_dashboard/gmail_service.py) — 214 lines,
`class GmailService`, scopes `gmail.readonly` **and** `gmail.send` (lines 32-35).

Three separate things make it non-functional, each sufficient on its own:

1. **Zero callers.** `grep -rn "GmailService\|gmail_service" --include="*.py"` across the
   repo returns nothing outside the file itself.
2. **Undeclared dependency.** It imports `googleapiclient`, `google.oauth2`,
   `google.auth.transport.requests`. No `google-api-python-client` / `google-auth*`
   package appears in *any* requirements file (`requirements.txt`, `requirements-ci.txt`,
   `requirements-dev.txt`, `autobot-backend/requirements.txt`). Importing the module
   raises `ImportError` on a clean install.
3. **Bootstrap script does not exist.** The module docstring says credentials come from
   `scripts/gmail_authorize.py`; `find . -name "gmail_authorize*"` finds no such file.

The directory `autobot-backend/operator_dashboard/` contains **only this one file** — no
`__init__.py`, no router, no tests. It is an orphaned module referencing an external
tracker id (`MVA-2894`) that does not match this repo's issue scheme.

Note the contrast with the canonical pattern: the Google Drive connector
[`knowledge/connectors/gdrive.py`](../../autobot-backend/knowledge/connectors/gdrive.py)
deliberately uses raw `aiohttp` + `autobot_shared.auth.BearerAuth` + the shared HTTP
client — *not* the Google SDK. `gmail_service.py` violates that convention, which is
likely why it never got wired.

### 1.3 Outlook / Microsoft Graph — BUILT, NO API SURFACE

[`autobot-backend/integrations/microsoft365_integration.py`](../../autobot-backend/integrations/microsoft365_integration.py) — 628 lines.
It genuinely implements mail **reading**:

| Action | Line | Graph endpoint |
| --- | --- | --- |
| `list_messages` | 403 | `/me/mailFolders/inbox/messages`, `/me/mailFolders/{id}/messages` |
| `search_messages` | ~418+ | Graph `$search` |
| `list_mail_folders` | ~225 | folder enumeration |
| `create_mail_folder` | ~231 | folder creation |
| `send_email` | 418 | `/me/sendMail` |

Plus calendar (`_list_calendar_events`, `_create_calendar_event`, `_check_availability`)
and Teams actions.

**But there is no way to reach it.** Every other integration family has a matching
router — `api/integration_github.py`, `integration_cloud.py`, `integration_cicd.py`,
`integration_database.py`, `integration_communication.py`, `integration_monitoring.py`,
`integration_project_management.py`, `integration_version_control.py`. There is **no
`api/integration_microsoft365.py`**. The class is imported only by
`integrations/__init__.py` for re-export.

Minor defect spotted while reading: `Microsoft365Integration` is listed **twice** in
`integrations/__init__.py.__all__` (lines 32 and 34).

### 1.4 Communication integration — no email at all

[`autobot-backend/integrations/communication_integration.py`](../../autobot-backend/integrations/communication_integration.py)
defines exactly `SlackIntegration` (47), `TeamsIntegration` (296), `DiscordIntegration`
(444). Despite the name, it carries no mail transport.

### 1.5 Knowledge connectors — no mail connector

`autobot-backend/knowledge/connectors/` ships: `gdrive`, `onedrive`, `confluence`, `jira`,
`notion`, `slack`, `gitlab`, `nextcloud`, `web_crawler`, `file_server`, `database`,
`audio`, `mock`, `external_adapter`. **No IMAP / Gmail / Outlook mail connector.**

Consequence: email content never enters the knowledge base or RAG. The infrastructure a
mail connector would need already exists and is proven — `base.py` (`AbstractConnector`),
`registry.py`, `credential_store.py`, `oauth_flow.py`, `scheduler.py`,
`content_extraction.py` (PDF/DOCX text extraction, which is exactly what mail attachments
need).

### 1.6 Company OS (LLC) — zero email, inbound or outbound

`grep -rn "email\|smtp\|inbox" --include="*.py" autobot-backend/llc/` returns **three
hits, all comments, none functional**:

- `llc/api/replay.py:261-263` — a note that emails are *not* redacted in replay.
- `llc/services/work_item_service.py:384` — `# Review inbox (#10533)` — an in-app queue,
  not mail.

Other relevant facts:

- `llc/notifications/router.py` — `LLCNotificationRouter` is Redis pub-sub → WebSocket
  only. No channel abstraction, no email fan-out.
- `llc/agent_tools.py` — the LLC agent tool surface is exactly **four** tools:
  `create_task`, `update_goal`, `request_approval`, `record_decision` (dispatch at line
  222). No send-mail, no read-mail.
- `llc/models/enums.py:226` — `MembershipRole` = `OWNER, ADMIN, MEMBER, GUEST, LEAD`.
  **There is no CEO role constant.** "CEO" is not a modelled concept in the LLC schema.
- The module is otherwise rich: `companies`, `agents`, `agent_hires`, `work_items`,
  `approvals`, `decisions`, `findings`, `goals`, `boards`, `sprints`, `routines`,
  `budget`, `costs`, `secrets`, `review_gate_policies`.

---

## Part 2 — The "CEO has an email address" proposal

### 2.1 Why it is a genuinely strong fit

The Company OS already has the *back half* of the pipeline built. A findings→work-items
design is specified in
[`docs/superpowers/specs/2026-07-08-companyos-findings-to-workitems-design.md`](../superpowers/specs/2026-07-08-companyos-findings-to-workitems-design.md)
with a phase-3 plan. **Inbound email → triage → work item is the same shape as
finding → work item.** The proposal is not a new subsystem; it is a new *source* feeding
an existing sink.

What a company-addressable mailbox unlocks that nothing else currently does:

- **An external inbound channel.** Today every input to the LLC originates from an
  authenticated user in the GUI or from a webhook (`llc/api/github_webhooks.py`). Email is
  the only universal, zero-onboarding way for an outside party — a customer, a vendor, a
  regulator — to reach the company.
- **Closing the loop on notifications.** `notification_service` already emails *out*.
  Replies to those emails currently vanish. Threading replies back onto the originating
  work item is a small delta with a large usability win.
- **Approvals by reply.** `llc/api/approvals.py` exists; approving from an email reply is
  the single most-requested affordance in this class of product.
- **Document intake.** `connectors/content_extraction.py` already extracts PDF/DOCX text.
  Invoices, contracts and reports arrive by mail; today they must be manually uploaded.

### 2.2 Hidden costs — and one hard sequencing blocker

Visible win: an inbox is "just a connector". Hidden costs are where this proposal is
decided, and one of them is disqualifying **in the current codebase state**.

| Hidden cost | Severity | Detail |
| --- | --- | --- |
| **Prompt injection into an acting agent** | **Blocking** | Email is attacker-authored text. An agent that reads it *and* holds `create_task` / `request_approval` / `record_decision` is a direct injection target. Per the open agent-seam umbrella **#13587/#13588**, the live tool seam authorises by tool *name* only, never by arguments, and `resolve_forbidden_tools` **fails open on an unknown agent id**. Per **#13228**, MCP tool calls bypass canonical RBAC via a default-allow blocklist. The guardrails this feature needs are filed but **not built**. |
| ~~OAuth refresh bug~~ | **CLEARED** | **#13626 has landed** (`cc6760931`) — `_lifetime_seconds()` in `connectors/credential_store.py:352` now preserves the stored lifetime across a refresh that omits `expires_in`. Sibling **#13624** (SSRF: credential headers dropped on cross-origin redirect hops) landed in `c727d704c`. OAuth mail is no longer blocked on connector auth. |
| Spoofing / authenticity | High | Without SPF/DKIM/DMARC verification on ingest, anyone can send mail *as* anyone. An approval-by-reply flow on an unverified sender is an authorisation bypass. |
| Auto-reply / mail loops | Medium | Two systems that auto-acknowledge will loop. Needs `Auto-Submitted` / `List-Id` header suppression and rate limiting. |
| Attachment malware | Medium | `content_extraction.py` parsing untrusted PDFs is a new remote-input attack surface on a parser not currently hardened for hostile input. |
| Deliverability & ops | Medium | A real mailbox means DNS records, reputation, bounce handling, and a domain — ongoing ops load, not a one-time build. |
| Data retention / redaction | Medium | `llc/api/replay.py:261-263` already documents that **emails are not redacted in replay**. Ingesting mail wholesale multiplies that exposure. |

### 2.3 Verdict

**Adopt — with conditions, and not first.**

The capability is real, the fit with Company OS is unusually clean, and most of the
plumbing (connector base, OAuth flow, credential store, scheduler, content extraction,
findings→work-item pipeline) already exists. This is a moderate build, not a large one.

One open, already-filed blocker remains under it:

- **#13588** (agent seam authorises by tool *name*, fails open on unknown agent id) —
  without this, a mail-reading agent holding tool access is an injection hole.

The previously-suspected second blocker has cleared: **#13626 and #13624 both landed**
(commits `cc6760931`, `c727d704c`), so OAuth connector auth is sound.

### 2.4 Recommended sequence

| Wave | Work | Why here |
| --- | --- | --- |
| **0 — prerequisites** | #13626 (OAuth refresh), #13588 (agent-seam by-argument authz) | Already filed, already prioritised first on their umbrellas. Both are directly load-bearing for mail. |
| **1 — read-only ingest** | Mail connector under `knowledge/connectors/` following `AbstractConnector` + raw `aiohttp`/`BearerAuth` (the `gdrive.py` pattern, **not** the Google SDK). Read-only. No agent tool access. | Delivers document/thread search into the KB with no acting-agent exposure. |
| **2 — surface the built code** | Add `api/integration_microsoft365.py` to match the eight sibling routers; fix the duplicate `__all__` entry. | 628 lines of working Outlook mail code become reachable for near-zero cost. |
| **3 — triage → work item** | Inbound thread → LLC work item, reusing the findings→work-items design. Sender verification (SPF/DKIM/DMARC) mandatory. Agent triage runs **read-only** — proposes, never commits. | The actual CEO-inbox value, with the acting-agent risk contained. |
| **4 — reply & approve** | Outbound threading on `notification_service`; approval-by-reply gated on verified sender + `review_gate_policies`. | Highest value, highest risk — last. |

### 2.5 The three orphans — finish, don't discard

Per the standing rule that debris is unfinished work, none of these should be deleted:

- **`operator_dashboard/gmail_service.py`** — its *capability* is wanted. Rewrite onto the
  canonical `AbstractConnector` + `aiohttp`/`BearerAuth` pattern in Wave 1, so the
  undeclared `googleapiclient` dependency disappears rather than getting added. The
  orphan directory then folds into `knowledge/connectors/`.
- **`microsoft365_integration.py`** — complete and working; it only lacks a router
  (Wave 2).
- **The missing `scripts/gmail_authorize.py`** — superseded by the existing
  `connectors/oauth_flow.py` + `credential_store.py`; the fix is to use those, not to
  write the missing script.

---

## Part 3 — Owner requirements (added 2026-08-08)

Four additional requirements. Audit-first result: **three of the four are mostly a reuse
job — the mechanisms already exist and are proven. Only agent self-signup is a true
greenfield gap.**

### 3.1 Autonomy vs sign-off — "same approach as terminal"

**Already exists, and it is better than most products'. Reuse it wholesale; do not build a
second approval system.**

The terminal permission stack, verified by reading:

[`autobot-backend/secure_command_executor.py`](../../autobot-backend/secure_command_executor.py)

- `class CommandRisk` (line 271): `SAFE` / `MODERATE` / `HIGH` / `CRITICAL` / `FORBIDDEN`
  — **five** members, not four. `CRITICAL` sits between `HIGH` and `FORBIDDEN`.
- `class SecurityPolicy` (line 281) — allowlists per risk tier.
- `class SecureCommandExecutor` (line 343) supports **two** permission models, documented
  in its own docstring:
  1. **Risk-based** (default) — assess by risk tier.
  2. **Permission v2** — glob-pattern rules with `ALLOW` / `ASK` / `DENY` / `DEFAULT`.
- Resolution order when v2 is on: **rules (DENY > ASK > ALLOW) → approval memory →
  risk-based fallback**.
- `require_approval_callback` (line 360) is the async human-in-the-loop hook.
- Argument-aware risk elevation (`_check_argument_aware_risk`, line 137) — including
  chained-command handling that takes the **strictest** risk across `cmd1; cmd2`
  sub-commands (#7406, line 205).
- `command_history` for audit.

[`autobot-backend/services/approval_memory.py`](../../autobot-backend/services/approval_memory.py)

- `ApprovalMemoryManager` (line 91), Redis-backed, **per-user per-project scoped**
  (line 17).
- `remember_approval` (244), `check_remembered` (309), `get_project_approvals` (366),
  `clear_project_approvals` (401), `remove_approval` (454), `get_memory_stats` (506).
- `_extract_pattern` (165) generalises a specific command into a reusable pattern — this
  is what makes "remember this decision" work without approving everything.

[`autobot-frontend/src/composables/useCommandApproval.ts`](../../autobot-frontend/src/composables/useCommandApproval.ts)

- `approveCommand(approved, ...)` posting to
  `/agent-terminal/sessions/{id}/approve` with `auto_approve_future` (line 235).
- `rememberForProject` → `permissionStore.storeApproval` (line 286) — "Approval remembered
  for this project".

**The mapping to email is direct** — but it must **reuse** `CommandRisk`, not introduce a
parallel `MailRisk` enum. An earlier draft of this section proposed a new enum; that was
wrong. `CommandRisk` already carries the exact semantics mail needs, and the codebase
already has one unreconciled fork of it (`CommandRiskLevel` in `api/schemas_terminal.py:473`
— `SAFE`/`MODERATE`/`HIGH`/`DANGEROUS`). A third definition would compound that, not solve
it. See the enum-consolidation issue linked in *Tracking issues*.

The tiers below are therefore a **mapping of mail actions onto the existing
`CommandRisk` members**, not a new type:

| `CommandRisk` tier | Email action | Default |
| --- | --- | --- |
| `SAFE` | Read / search / classify / label | Auto |
| `MODERATE` | Reply within an existing thread to a known correspondent | Auto in full-autonomy, ASK in sign-off |
| `HIGH` | New outbound mail to a new external address; attachments out | ASK always by default |
| `CRITICAL` | Bulk send; outbound to a large or undisclosed recipient set | Never auto — explicit per-item sign-off |
| `FORBIDDEN` | Financial instruction, credential disclosure | Never permitted autonomously in any mode |

**Reuse verdict:** the `require_approval_callback` seam, `ApprovalMemoryManager`, and the
`ALLOW/ASK/DENY/DEFAULT` matcher are all domain-agnostic enough to serve mail. The correct
build is to **generalise them out of the terminal-specific module**, not to copy them.
That refactor is the single highest-leverage item in this whole proposal — it also serves
the browser and signup surfaces below.

**Hidden cost:** `approval_memory` is scoped *per project path*. Mail is not
project-scoped, it is company/mailbox-scoped. The scoping key needs generalising
(`project_path` → a generic scope identifier) or mail approvals will collide. This is a
real, small refactor — not a blocker, but it must be done deliberately rather than by
passing a fake project path.

### 3.2 Credentials via unified secrets management

**Already satisfied by the canonical path — provided the mail connector is built as a
connector.** This is the strongest argument for Wave 1 being a `knowledge/connectors/`
module rather than a standalone service.

Canonical stack, verified:

- `autobot-backend/services/secrets_service.py`, `secrets_coordinator.py`
- `autobot-backend/models/secret.py`, `secret_grant.py`, `secret_dependency.py` — grant /
  dependency modelling
- `autobot_shared/secrets_vault.py`, `secrets_envelope.py`, `secret_redaction.py`
- `autobot-backend/llc/api/secrets.py` — per-company `list` / `set` / `get` / **`revoke`**
  with `_check_company_access` (line 79)
- `autobot-frontend/src/views/llc/SecretsView.vue` — the GUI already exists

[`knowledge/connectors/credential_store.py`](../../autobot-backend/knowledge/connectors/credential_store.py)
is the bridge, and it is **not** a parallel crypto path — it takes `secrets_service` in
`__init__` (line 62) and mirrors to the vault via `services/credential_write.py`. It
provides exactly what a mailbox needs: `store` (69), `load` (104), `store_oauth` (189),
`get_access_token` (230), `rotate` (141), `revoke` (173).

**Verdict:** requirement met for free by following the existing connector pattern. It is
also why `operator_dashboard/gmail_service.py` must be rewritten rather than revived — it
reads `gmail_token.json` from disk, bypassing the secrets manager entirely, which violates
the standing credentials rule.

### 3.3 Mailbox GUI — read and compose

**Genuine gap, but the UX pattern already exists twice and should be reused.**

Existing inbox-shaped views:

- [`autobot-frontend/src/views/llc/ApprovalsInbox.vue`](../../autobot-frontend/src/views/llc/ApprovalsInbox.vue)
  — pending/history tabs, filters by type/status/free-text search (lines 33-44), per-item
  approve/deny (line 71-75), status badges, full `$t()` i18n.
- `autobot-frontend/src/views/llc/ReviewInboxView.vue`
- Backend shape to mirror: `llc/api/approvals.py` — `list_pending` (104),
  `decide_approval` (124).

There is **no** mail view: `find autobot-frontend/src autobot-slm-frontend/src -iname
"*mail*"` returns nothing.

What a `MailboxView.vue` needs beyond the ApprovalsInbox pattern:

- Thread/conversation grouping (approvals are flat items; mail is threaded)
- A body renderer with **HTML sanitisation** — untrusted remote HTML, so no raw `v-html`,
  and remote images blocked by default (tracking pixels)
- A compose/reply editor with the risk tier from 3.1 surfaced *before* send
- Attachment handling wired to `content_extraction.py`
- A visible "agent drafted this" state, so an autonomous draft is never mistaken for a
  sent message

**Mandatory per standing rules:** every string via `$t()`, all **11 locales** — no
hardcoded UI strings.

### 3.4 Agent signs up for services, with user permission

**True greenfield gap — nothing like it exists.** `grep -rln
"signup\|register_account\|verification_link\|verify_email"` returns only
`autobot-backend/api/auth.py` and `autobot_shared/user_management/models/user.py`, which
are AutoBot's *own* user registration — unrelated.

The pieces that do exist and would combine:

| Piece | Status | Path |
| --- | --- | --- |
| Browser automation (Playwright) | Exists | `autobot-browser-worker/` — `playwright-server.js`, `session-store.js` |
| Browser GUI | Exists | `autobot-frontend/src/views/BrowserAutomationView.vue` |
| Credential storage for the new account | Exists | secrets stack per 3.2 |
| Approval gate | Exists | per 3.1 |
| Mailbox to receive the verification mail | **Missing** — this proposal | — |

This is the capability that makes the mailbox *strategically* valuable rather than merely
convenient: **an agent without an inbox cannot complete any signup flow**, because
verification is universally email-based. Mail + browser + secrets + approvals together
close the loop: agent requests → user approves → agent registers → verification mail
arrives → browser worker follows the link → resulting credential lands in the secrets
vault under a grant.

**Hidden costs — this one is the highest-risk item in the document:**

| Risk | Detail |
| --- | --- |
| **Terms-of-service** | Many services prohibit automated account creation outright. A blanket capability will get accounts banned; the user, not AutoBot, bears that. Needs a per-service allow decision, not a global toggle. |
| **CAPTCHA / anti-bot** | Signup flows are the most aggressively bot-protected pages on the web. Expect frequent failure; the honest design surfaces "needs a human" rather than attempting to defeat protections. **Do not build CAPTCHA circumvention.** |
| **Financial commitment** | A signup that reaches a paid tier obligates real money. This must be `FORBIDDEN`-tier: explicit per-instance sign-off, never covered by remembered approval or full-autonomy mode. |
| **Identity attribution** | Accounts created under the company address are legally the owner's. Needs an audit trail — which agent, which approval, which run — reusing `llc/api/decisions.py`. |
| **Approval-memory blast radius** | "Remember this approval" is right for `git status`; it is dangerous for "sign up for services". Signup should be **excluded from pattern generalisation** in `_extract_pattern` — approve once means once. |

**Verdict: adopt-with-conditions, last wave, and never under full autonomy.** The
capability is legitimate for an owner-operated platform, but it is the one place where
"full autonomy" should not be an available setting — the user permission gate stays
mandatory regardless of autonomy mode, and per-service rather than global.

### 3.5 Revised wave plan

| Wave | Work | Notes |
| --- | --- | --- |
| **0** | #13588 agent-seam by-argument authz | Only remaining prerequisite; #13626/#13624 have landed |
| **1** | Generalise the approval seam out of `secure_command_executor` / `approval_memory` — scope key `project_path` → generic scope | Highest leverage; serves mail, browser, and signup |
| **2** | Mail connector under `knowledge/connectors/` (read-only, secrets via `ConnectorCredentialStore`) | Requirement 3.2 satisfied by construction |
| **3** | `api/integration_microsoft365.py` router | 628 built lines become reachable |
| **4** | `MailboxView.vue` — read, thread, sanitised render, compose; 11 locales | Requirement 3.3 |
| **5** | Autonomy modes + `MailRisk` tiers wired to the Wave-1 seam | Requirement 3.1 |
| **6** | Inbound thread → work item; approval-by-reply gated on SPF/DKIM/DMARC | Original CEO-inbox value |
| **7** | Agent self-signup: browser + mail + secrets + mandatory per-service approval | Requirement 3.4 — last, never full-autonomy |

---

## Part 4 — Invariant: agent-obtained credentials land in the vault, user-controlled

**Owner requirement (2026-08-08):** *anywhere an agent signs up, all resulting credentials
end up in the secrets vault, controlled by the user.*

Audit result: **the storage-and-control half is genuinely built and good. The
"…and nowhere else" half is not enforceable today** — and the signup flow is the exact
place it breaks.

### 4.1 What already supports the invariant

The vault is not a thin wrapper — it has real ownership, revocation and audit:

[`autobot-backend/models/secret.py`](../../autobot-backend/models/secret.py)

- `owner_id` (79), `org_id` (86), `scope` (107) with `team_ids`, `session_id`,
  `workflow_id`, `shared_with`.
- **Fails closed:** an unknown stored scope degrades to `ScopeLevel.USER` — owner-only
  (line 263). That is the correct default for this invariant.
- `expires_at` (187), `is_active` (192), `version` (168), `sealed_value` envelope (162).

[`autobot-backend/models/secret_grant.py`](../../autobot-backend/models/secret_grant.py)

- Each grant row holds a **per-grantee `wrapped_dek`** (49). The module docstring is
  explicit: *"revoking a share = deleting one; the owner's own access is just the row
  whose…"*. Revocation is **cryptographic, not an advisory ACL flag** — this is what makes
  "controlled by the user" real rather than nominal.

[`autobot-backend/services/secrets_service.py`](../../autobot-backend/services/secrets_service.py)

- `create_secret` (238), `get_secret` (327), `list_secrets` (399), `update_secret` (448),
  `delete_secret` (483), `transfer_secret` (512), `cleanup_chat_secrets` (557).
- **Audit trail exists:** `_audit_action` (604), `get_audit_log` (628), plus
  `_update_access_tracking` (202) recording `accessed_by`.

User-facing control surface already shipped: `autobot-frontend/src/views/llc/SecretsView.vue`
and `llc/api/secrets.py` (`list` / `set` / `get` / `revoke`, gated by
`_check_company_access`).

**Verdict: the "user controls it" requirement is met by existing primitives.** Nothing new
is needed for ownership, revocation, or audit.

### 4.2 Gap 1 — there is no agent *write* path

[`autobot-backend/services/agent_secrets_integration.py`](../../autobot-backend/services/agent_secrets_integration.py)
is **read-only**. Its entire surface is retrieval and configuration:

`get_agent_mapping`, `register_agent_mapping`, `_determine_types_to_fetch`,
`_fetch_and_merge_secrets`, `get_secrets_for_agent`.

There is **no `store_secret_for_agent`**. An agent that completes a signup has no
sanctioned place to deposit the credential it just obtained. Today it would end up in
whatever the agent happened to write — a work item body, a chat message, a log line.

**This is the one concrete thing that must be built for the invariant to hold.**

Design constraints for that write path:

- **Deposit ≠ retrieve.** The agent gets *create* capability; read-back of a stored
  credential in plaintext stays governed by the existing `AgentSecretMapping`. An agent
  that can bank a credential must not automatically be able to exfiltrate it later.
- **`owner_id` is always the human user, never the agent.** Otherwise a decommissioned
  agent orphans the secret and the user's revocation has nothing to revoke.
- **Provenance is mandatory** — see 4.4.

### 4.3 Gap 2 — nothing stops the credential landing *elsewhere as well* (the serious one)

The invariant says *all* credentials end up in the vault. The unstated other half is *and
nowhere else*. That half is currently unenforceable.

[`autobot_shared/secret_redaction.py`](../../autobot_shared/secret_redaction.py) is
**name-keyed, not content-keyed**:

- `is_credential_field(name)` (84) matches on a *field name* against `CREDENTIAL_SUFFIXES`.
- `redact_value(name, value)` (121) only masks when handed a credential-shaped **name**.
- `redact_url_userinfo` (100) does strip passwords from connection strings, and it fails
  closed on unparseable input — good, but still URL-shaped values only.

Its callers are all config/model contexts: `ssot_config.py`, `models/settings.py`,
`pki/config.py`, `config_revision_service.py`, `workflow_secret_service.py`,
`llm_shared/observability/tracing_config.py`.

**It cannot see a credential sitting in free text.** And that is precisely what a signup
produces: *"Your temporary password is X"*, *"Here is your API key: Y"* — in the body of
an email, which under this proposal gets parsed, persisted, indexed into Chroma, embedded,
logged, and replayed.

Two existing facts make this concrete rather than theoretical:

- `llc/api/replay.py:261-263` already documents that **emails are not redacted in replay**,
  noting that email redaction "would require regex patterns not" currently present.
- The Wave-2 mail connector feeds `content_extraction.py` → knowledge base. A credential
  copied into embeddings **cannot be revoked** — deleting the vault row does nothing about
  the vector store copy.

**Required control:** a content-scanning redactor at *mail ingest*, before persistence and
before indexing. This is a new capability, not a reuse of `secret_redaction.py`. The rule
must be: a message that appears to carry a credential is **quarantined — vaulted, then the
body redacted** — never indexed in the clear.

### 4.4 Gap 3 — provenance is not modelled

`Secret` carries `owner_id`, but not *which agent obtained it, under which approval, in
which run, for which service*. `SecretGrant.created_by` (55) is a user FK, not an agent.

Without provenance, "the user controls it" is true but useless — the user sees an
unexplained credential. Needs to land in `extra_data` / `tags`:

`created_by_agent`, `approval_id` (FK to `llc/api/approvals.py`), `run_id`, `service_domain`,
`signup_decision_id` (FK to `llc/api/decisions.py`).

Then `SecretsView.vue` shows an "obtained by agent" badge and the user can trace any
credential back to the approval that authorised it.

### 4.5 The rule set this implies

1. Agent signup credentials are written to the vault **before** the source message is
   persisted or indexed.
2. The source message body is **redacted or quarantined** — never indexed in the clear.
3. `owner_id` is the human user. Always.
4. Agent gets create, not blanket read-back.
5. Every agent-created secret carries provenance and appears in `get_audit_log`.
6. Revocation is the existing grant-deletion path — already cryptographic, already correct.
7. A credential that reached the vector store counts as **leaked, not stored** — treat
   indexing as an irreversible disclosure.

### 4.6 Revised wave plan (supersedes 3.5)

| Wave | Work | Notes |
| --- | --- | --- |
| **0** | #13588 agent-seam by-argument authz | Only remaining prerequisite |
| **1** | Generalise the approval seam out of `secure_command_executor` / `approval_memory` | Serves mail, browser, signup |
| **2** | **Content-scanning credential redactor + quarantine at ingest** | **Moved up** — must exist *before* any mail is indexed (4.3) |
| **3** | Mail connector, read-only, secrets via `ConnectorCredentialStore` | Ingest passes through Wave 2 |
| **4** | `api/integration_microsoft365.py` router | 628 built lines become reachable |
| **5** | `MailboxView.vue` — read, thread, sanitised render, compose; 11 locales | |
| **6** | Autonomy modes + `MailRisk` tiers on the Wave-1 seam | |
| **7** | `store_secret_for_agent` write path + provenance fields (4.2, 4.4) | Prerequisite for signup |
| **8** | Inbound thread → work item; approval-by-reply gated on SPF/DKIM/DMARC | |
| **9** | Agent self-signup — browser + mail + vault deposit + per-service approval | Last; never full-autonomy |

**The ordering change matters:** the redactor moved ahead of the mail connector. Ingesting
mail into the KB before content-scanning exists would copy signup credentials into
embeddings, where revocation cannot reach them.

---

## Files that would change

| Path | Change |
| --- | --- |
| `autobot-backend/knowledge/connectors/mail.py` | **New** — `AbstractConnector` subclass, IMAP + Graph + Gmail REST via `aiohttp`/`BearerAuth` |
| `autobot-backend/knowledge/connectors/registry.py` | Register the mail connector |
| `autobot-backend/api/integration_microsoft365.py` | **New** — router matching the 8 existing `integration_*.py` siblings |
| `autobot-backend/integrations/__init__.py` | Remove duplicate `Microsoft365Integration` in `__all__` (lines 32/34) |
| `autobot-backend/operator_dashboard/gmail_service.py` | Migrate onto the connector pattern; retire the orphan directory |
| `autobot-backend/llc/models/enums.py` | Company-address / mail-identity model (note: no CEO role exists today) |
| `autobot-backend/llc/services/` | Inbound thread → work item, reusing the findings→work-items design |
| `autobot-backend/llc/notifications/router.py` | Email as a routed channel alongside WebSocket |
| `autobot-backend/services/notification_service.py` | Outbound threading headers (`Message-Id` / `In-Reply-To`) for reply correlation |
| `autobot-backend/llc/api/replay.py` | Email redaction — the gap is already documented at lines 261-263 |
| `autobot-backend/secure_command_executor.py` | Extract the `ALLOW/ASK/DENY/DEFAULT` matcher + `require_approval_callback` seam into a domain-agnostic module |
| `autobot-backend/services/approval_memory.py` | Generalise scope key from `project_path` to a generic scope id; exclude signup patterns from `_extract_pattern` |
| `autobot-frontend/src/composables/useCommandApproval.ts` | Generalise into a shared approval composable serving terminal + mail + signup |
| `autobot-frontend/src/views/llc/MailboxView.vue` | **New** — modelled on `ApprovalsInbox.vue`; threads, sanitised body render, compose, 11 locales |
| `autobot-frontend/src/locales/*` | 11 locales for all mailbox strings |
| `autobot-backend/knowledge/connectors/credential_store.py` | Already canonical — mail OAuth secrets route through `store_oauth`/`get_access_token` unchanged |
| `autobot-browser-worker/` | Verification-link following for the signup flow (Wave 7) |
| `autobot-backend/llc/api/decisions.py` | Audit trail for agent-initiated signups — which agent, which approval, which run |
| `autobot-backend/services/agent_secrets_integration.py` | **Add the missing write path** — `store_secret_for_agent`; today the module is read-only (4.2) |
| `autobot_shared/secret_redaction.py` | Companion **content-scanning** redactor — current module is name-keyed and cannot see credentials in free text (4.3) |
| `autobot-backend/knowledge/connectors/content_extraction.py` | Route extracted mail bodies through the content redactor **before** persistence/indexing |
| `autobot-backend/models/secret.py` | Provenance in `extra_data`/`tags`: `created_by_agent`, `approval_id`, `run_id`, `service_domain` (4.4) |
| `autobot-frontend/src/views/llc/SecretsView.vue` | "Obtained by agent" badge + trace back to the authorising approval |

---

## Verification commands used

```bash
grep -rli "imap\|smtp\|email_client\|mailbox" --include="*.py" .     # found notification_service
grep -rl "imaplib\|IMAP\|gmail\|Gmail\|graph.microsoft\|outlook" .   # found the 3 partials
grep -rn "GmailService\|gmail_service" --include="*.py" .            # ZERO callers
find . -name "gmail_authorize*"                                       # does not exist
grep -rin "google" requirements*.txt autobot-backend/requirements.txt # no google SDK declared
ls autobot-backend/api/integration_*.py                               # 8 routers, no microsoft365
grep -rn "email\|smtp\|inbox" --include="*.py" autobot-backend/llc/   # 3 comment-only hits
grep -n "class.*Role" autobot-backend/llc/models/enums.py             # no CEO role
```
