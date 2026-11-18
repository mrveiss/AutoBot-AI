---
tags: [type/architecture, status/current]
date: 2026-10-11
issue: 18223
---

# Refined UI redesign — implementation handoff

**Issue:** #18223 · **Mockups:** [`mockups/refined-ui/`](mockups/refined-ui/) · **Tokens:** [`mockups/refined-ui/tokens.css`](mockups/refined-ui/tokens.css)

This is the spec a Claude Code session works from when implementing the redesign. It covers
what the design is, where each screen lands in `autobot-frontend`, the behaviours shared by every
screen, and the order to build it in. The mockups are the visual reference; this doc is the
contract. Where the two disagree, ask — do not guess.

## 1. What the design is

- **Style "Refined":** corporate, flat, line-icon illustration style. IBM Plex Sans for UI, IBM Plex
  Mono for data, paths, IDs and numbers.
- **No shadows anywhere** — not on cards, buttons, menus or dialogs. Separation is borders
  (`--border`, `--line`, width `--bw`) and the two surfaces (`--surface`, `--surface2`).
- **Main navigation is a horizontal top bar** (it saves vertical space). Sections with sub-pages add
  a left sub-sidebar (`--subnav-w` 220px).
- **Automation lives inside Company OS**, not as a top-level section.
- **Four themes:** Light (default), Dark, High contrast (accessibility — 2px borders, bordered
  pills), Monochrome (very corporate). Chosen in **Profile settings → Appearance**, never in the nav.
- **SLM frontend always uses its own teal scheme** plus a dark identity bar, in every theme, so a
  user can always tell SLM from the user frontend.
- **Two interface modes:** Full (everything) and Minimal (advanced features hidden) — see §4.2.

## 2. How to read the mockups

`screens/*.dc.html` are design-canvas source files. They are **not runnable on their own** — they
load a canvas runtime (`support.js`) that is not part of this repo. Read them as annotated HTML:

| In the mockup | Means |
|---|---|
| `.th` wrapper with `data-theme` / `data-ui` | the app root (`<html>`) attributes — see `tokens.css` header |
| `{{hole}}` text and `sc-for` / `sc-if` | template bindings and loops — equivalent of Vue `{{ }}`, `v-for`, `v-if` |
| `<script type="text/x-dc">` class with `renderVals()` | the screen's view-model; state names map to Pinia/composable state |
| class `adv` | hidden in Minimal mode |
| `data-tip="…"` (+ `data-tip-pos`) | tooltip text and placement |
| `.card`, `.ch`, `.row`, `.btn`, `.btn.pri`, `.pill.ok/warn/bad/idle/info`, `.seg`, `.dot` | the component vocabulary documented on the `Components*` screens |

`canvas.json` lists every screen with its section and title. Example IPs and hostnames in the
mockups use reserved documentation ranges (`192.0.2.x`, `*.example`) — they are placeholders.

The `Components*`, `DesignSystem`, `FileBrowser`, `Mailbox` and `ComponentsUiModes` screens are the
design-system reference: tokens and states, grid/table/form tokens, charts, form controls, data
table, dialogs, overlays, tooltips, command menu, navigation, layout, chat primitives, and the two
patterns. Build shared primitives from these, not from individual app screens.

## 3. Tokens — where they go

`tokens.css` holds every value: four colour themes, the SLM scheme, layout grid, table, form,
widget-span and tooltip tokens. The app already has a token pipeline; extend it, do not fork it:

- **Values** → `autobot-frontend/src/assets/css/design-tokens.css` (the SSOT) and per-theme files
  under `src/assets/css/themes/` (use `_template.css` as the pattern). Map Refined names onto the
  existing `--color-*` names where one exists (e.g. `--surface` → background tokens, `--primary` →
  `--color-primary`) and add the rest. Record the mapping in the PR.
- **Tailwind** → expose new tokens through the `@theme` block in `src/assets/tailwind.css`, and list
  blessed names in `src/design-system/tokens.ts` (it catalogues names, not values).
- **Theme switching** → `src/composables/useTheme.ts` currently supports `dark | light | system`.
  Add `contrast` and `mono`. The attribute stays `data-theme` on `<html>`
  (`useUserStore.ts` already applies it).
- **Themes deployed via SLM** → these are the runtime installed themes from #10472
  (`useThemeVariant.ts` + `useThemeRegistry`). The four built-ins ship with the app; anything extra
  arrives that way. The SLM **Themes** screen (`ThemeManager`) is the admin side of it.
- **Retire** the hard-wired ember red/orange accent as a default for every theme — see #18161.

## 4. Shared behaviours (build once, used everywhere)

### 4.1 Top navigation
Logo · Home · Chat · Knowledge · Company OS · Analytics (`adv`), then an icon cluster on the
right: Secrets (key) · Preferences (a **cogwheel** — the old rays icon read as a light/dark switch; use the same cog for every "settings" control) · **UI-mode toggle** · Platform admin (shield, "Platform admin —
opens the SLM console ↗") · Profile settings. Plugins lives in the SLM console nav, not the user
top nav. Every icon has an `aria-label` and a tooltip. Active item: `--nav-on-bw` underline in `--accent`. Overflow collapses into the existing
`NavOverflowMenu`. Agents is reached from its own pages' sub-navigation, not the top bar.
Reference: any app screen (e.g. `Chat`); `ComponentsNavigation` for states.

### 4.2 Minimal / Full interface mode
- Root attribute `data-ui="minimal|full"`; CSS hides `.adv` in Minimal (`tokens.css`).
- **Toggle** is a button in the nav icon cluster, just before the Platform admin icon. Label "Minimal",
  `aria-pressed` reflects state, pressed style = `--surface2` fill + `--accent` border.
  A visually hidden `aria-live` region announces the change.
- **Preference:** Profile settings → *Preferred mode* (Minimal / Full cards) plus *Start in*
  (Last used / Minimal / Full).
- Persist per user (server-side preference); the mockups use `localStorage` keys
  `autobot-ui-mode` and `autobot-ui-start` only as stand-ins.
- Minimal screens show a one-line note "Showing essentials · Show all features" (`.only-min`).
- What is `adv` on each screen is marked in the mockups. Reference: `ComponentsUiModes`, `Chat`.

### 4.3 Theme preference
Profile settings → Appearance: four theme cards with live preview; selection applies immediately
and persists per user. Reference: `Preferences`.

### 4.4 Dashboard widgets — movable and resizable
Home (`HomeCustom`, `Main`) and Company OS (`CompanyOS`) have a **Customize layout** mode: drag to
move, resize by width span (`--widget-s/m/l/full` = 4/6/8/12 of 12 columns) and height, reset to
default. Persist per user and per page (mockups use `autobot-layout-<page>` as a stand-in).
**Not designed yet:** keyboard move/resize — the mockups are pointer-only. It is required for
accessibility; agree the key bindings before building.

### 4.5 Tooltips
Every icon-only button and every abbreviation or metric label has one (about 2,300 in the
mockups). Behaviour: 500ms show delay, 100ms hide delay, 8px offset, 280px max width, shows on
keyboard focus as well as hover, hidden on touch, no animation under reduced motion.
`tokens.css` contains a CSS-only reference; the app should use the shared **Tooltip primitive**
from #14779 with the same tokens. Inside scrollable tables, header tooltips open downwards.
Reference: `ComponentsTooltips`.

### 4.6 Tables
Real `<table>` with `th scope`, never div grids for data. Tokens `--tbl-*`. Numbers right-aligned
mono with `tabular-nums`; only message/description columns wrap; wrap in an `overflow-x:auto`
container. Wide data tables take the full content width — do not put a table with more than three
columns into a half-width card. Reference: `ComponentsGrid` §tables, `ComponentsTable`,
`AnalyticsCodebaseOverview`.

### 4.7 System Control moves out of Chat
The System Control widget (status + Reload System) is removed from the Chat sidebar and becomes the
first item of the **Danger Zone** card in SLM console → Advanced control. Reference: `Chat`,
`AdminAdvancedControl`.

## 5. Screen → view map

Route/view as found on `main` at 940da29. **New** = no view exists yet; confirm the backend before
building UI for it.

Page groups on the canvas (130 screens; the 131st file, `screens/CompanyOSRefined.dc.html`, is not placed on the canvas): Entry & Home 8 · Chat & Workspace 3 · Knowledge 9 ·
Company OS 40 (includes BusinessIntelligence, the Transcriber screens and Handbook) · Automation 8 · Agents 3 ·
Analytics 6 · Settings 2 (Secrets, Preferences) · **SLM console (server-wide) 25** · Auth & Account
10 · Components 16. The SLM console group holds Operations, ErrorMonitoring, FailureAnalysis,
Plugins, Marketplace, SecretsApiKeys, SecretsAudit, LlmConfig, ThemeManager, the Admin* screens,
AuditLogs, SystemHealth, **KnowledgeHealth**, **SlmAgentLedger**, Experiments, Benchmark, Evolution
and DevSpeedup.

**Company OS model (owner, 2026-10-11 — #18390).** Like a film script: people and agents are the
actors, they hold **roles**, roles perform **workflows**, workflows are made of **processes**. A
workflow belongs to one role, starts on a trigger (manual, schedule, email received, work item
status change, webhook, file added to folder, another process's result) and joins processes with
typed transitions (on success, on failure with optional retries, if/else, after timeout). A process
is reusable across workflows, has one owner role, may require skills, and may also run alone on a
routine as its owner role. Roles hold **skills** and **meta skills** (a reusable graph of processes
with no trigger, called by workflows as one step). `OrgChart`, `ProcessCanvas`,
`ProcessCanvasTable`, `Roles` and `Routines` follow this model; build to #18390 once its open
decisions are made.

**Three lines for AI (owner, 2026-10-12 — #18430).** Every tool action, process and meta skill is
*Autonomous*, *AI drafts, a person sends* (waits in Approvals) or *AI never touches*. Unset = the
middle line; agents never change a line; changing one is an approval. A process shows its effective
line (strictest of its own and its tool actions'). Setting up an automation is **four moves** —
connect, set the line, give the job, wire the trigger — `AutomationSetup`.

**Handbook (#18431).** An employee handbook that onboards people and agents: company chapters plus a
generated page for every role, workflow, process and meta skill, an onboarding path per role, and
need-to-know scoping per reader. `Handbook`.

**Schedules (#18432).** One clickable schedule picker (Routines, workflow Schedule trigger, automation
setup); lists show a plain-language summary; storage is translated in the background to standard
cron, an RFC 5545 calendar rule, or a one-off run. The routes below are the current user-frontend
routes; the group says where the mockup now puts the screen. For the 25 SLM-console screens the Route
column gives the route in `autobot-slm-frontend` on `main` (`router/index.ts`, `router/monitoringRoutes.ts`)
or **new**; "moving from" is the user-frontend path being retired, and "closest today" is a route
that exists but does not serve the screen.

| Mockup | Route | View / component |
|---|---|---|
| Login | `/login` | `components/auth/LoginForm.vue` |
| Onboarding | `/onboarding` | `OnboardingWizard` |
| Main | `/home` | concept for the agent dashboard — variant of `views/CustomDashboard.vue` |
| HomeCustom | `/home` | `views/CustomDashboard.vue` |
| About | `/about` | `AboutView` |
| SharedChat | `/shared/:token` | `views/SharedChatView.vue` |
| NotFound | catch-all | `views/NotFoundView.vue` |
| PermissionDenied | `/permission-denied` | (route exists) |
| Chat | `/chat` | `ChatView` → `components/chat/ChatInterface.vue` — tabs Chat · Files · Terminal · Browser · Remote desktop (`ChatTabs`, `ChatTabContent`); right panels Session files (`ChatFilePanel`) and Voice chat (`VoiceConversationPanel`), one at a time |
| Desktop | `/chat/novnc` (`/desktop` redirects) | `ChatInterface.vue` (noVNC tab) |
| Canvas | `/canvas` | `views/CanvasView.vue` |
| Knowledge | `/knowledge/browser` | `components/knowledge/KnowledgeBrowser.vue` |
| KnowledgeGraph | `/knowledge/graph` | `components/knowledge/KnowledgeGraphView.vue` |
| KnowledgeVectorStore | `/knowledge/vector-store` | (route `knowledge-vector-store`, #8999) |
| KnowledgeHealth | `/knowledge/health` → **SLM** Monitoring › Knowledge base (admin only) — SLM route **new** (closest today: `/monitoring/admin`) | `components/knowledge/KnowledgeHealth.vue` — moves to `autobot-slm-frontend`, install-wide |
| KnowledgeResearch | `/knowledge/research` | `components/knowledge/KnowledgeResearchTabs.vue` |
| KnowledgeMcpResources | `/knowledge/mcp-resources` | `components/knowledge/McpResourceBrowser.vue` |
| KnowledgeSystemDocs | `/knowledge/system-docs` | `components/knowledge/KnowledgeSystemDocs.vue` |
| KnowledgeManage | `/knowledge/manage` | `components/knowledge/KnowledgeEntries.vue` — upload takes audio/video too: transcribed by Transcriber, transcript added as text (#17527) |
| KnowledgeEntities | `/knowledge/entities` | `components/knowledge/EntityGraphManager.vue` |
| Documents | `/documents` redirects to `/knowledge/browser` | AI documents view inside Knowledge |
| TranscriberProjects / Project / Transcript | `/knowledge/transcriber/…` → **Company OS** › Work › Transcriber | `views/transcriber/ProjectsView.vue`, `ProjectDetailView.vue`, `TranscriptView.vue` — watch folders start a workflow; transcripts can be added to Knowledge |
| CompanySelector | `/llc/select-company` | `views/llc/CompanySelectorView.vue` |
| CompanyCreate | `/llc/companies/create` | `views/llc/CompanyCreationWizard.vue` |
| CompanyOS | `/llc/companies/:id/dashboard` | `views/llc/CompanyDashboard.vue` |
| Backlog | `…/backlog` | `views/llc/BacklogView.vue` |
| Boards | `…/boards`, `…/boards/:id/kanban` | `views/llc/BoardsView.vue`, `KanbanBoardView.vue` |
| SprintBoard | `…/boards/:id/sprint` | `views/llc/SprintBoardView.vue` |
| Timeline | `…/timeline` | `views/llc/GanttTimelineView.vue` |
| Portfolios | `…/portfolios`, `…/portfolios/:id/programs` | `views/llc/PortfolioBrowserView.vue`, `ProgramBrowserView.vue` |
| Projects | `…/programs/:id/projects` | `views/llc/ProjectBrowserView.vue` |
| WorkItem | — | work-item detail (drawer/page) — confirm where it opens today |
| ReviewInbox | `…/reviews` | `views/llc/ReviewInboxView.vue` |
| Goals | `…/goals` | `views/llc/GoalTree.vue` |
| OrgChart | `…/org-chart` | `views/llc/OrgChart.vue` — roles with holders, skills, workflows, processes, routines (#18390) |
| ProcessCanvas / ProcessCanvasTable | — **new** | workflow graph editor, process library, meta skills, transitions (#18390) |
| Teams | — **new** | teams inside a company |
| MyPlace | — **new** | a member's own landing page in the company |
| ProjectDetail | — **new** | project page opened from Projects |
| EntityLifecycle | — pattern | edit / archive / delete for Company OS entities |
| RunSupervision | — **new** | live heartbeat runs |
| OperationHistory | — **new** | company operation log |
| AgentLedger | — **new** | who is working on what, per company (#18391) |
| ApprovalReview | — **new** | single approval opened from Approvals |
| CompanyMailbox | — **new** | company mailboxes |
| CompanySettings | — **new** | company-wide settings |
| Members / Roles | `…/members`, `…/roles` | `views/llc/MembersView.vue`, `RolesView.vue` |
| Approvals | `…/approvals` | `views/llc/ApprovalsInbox.vue` |
| Costs | `…/costs` | `views/llc/CostDashboard.vue` |
| HeartbeatMonitor | `…/heartbeat` | `views/llc/HeartbeatMonitor.vue` |
| Routines | `…/routines` | `views/llc/RoutinesView.vue` — schedule picker replaces cron entry (#18432); each routine runs a process as its owner role |
| Handbook | — **new** | company handbook, generated role/workflow/process pages, onboarding, need-to-know (#18431) |
| CeoChat | `…/ceo-chat` | `views/llc/CeoChatView.vue` |
| Activity | `…/activity` | `views/llc/ActivityFeedView.vue` |
| Portability | `…/portability` | `views/llc/CompanyPortabilityView.vue` |
| CompanySecrets | `…/secrets` | `views/llc/CompanySecretsView.vue` |
| AutomationOverview / Automation / Templates / Runner / History | `…/automation/:section` | `WorkflowBuilderView` |
| AutomationSetup | — **new** | four-move setup: connect, set the line per tool action, give the job, wire the trigger (#18430) |
| BrowserAutomation | `…/automation/browser-automation` | (child route) |
| VisionAutomation | `…/automation/vision-automation` | `views/VisionAutomationView.vue` |
| Agents | `/agents/registry` | `views/AgentRegistryView.vue` |
| AgentActivity / AgentHeartbeat | `/agents/activity`, `/agents/heartbeat` | (child routes of `views/AgentsLayout.vue`) |
| Analytics | `/analytics/codebase` | `components/analytics/CodebaseAnalyticsLanding.vue` |
| AnalyticsCodebaseOverview | `/analytics/codebase/:sourceId` | `components/analytics/CodebaseAnalytics.vue` and its section components |
| AnalyticsCodebase | `/analytics/code-quality` | `components/analytics/CodeQualityDashboard.vue` |
| AnalyticsCodeReview | `/analytics/code-review` | `components/analytics/CodeReviewDashboard.vue` |
| AnalyticsCodeGeneration | `/analytics/code-generation` | `components/analytics/CodeGenerationDashboard.vue` |
| BusinessIntelligence | `/analytics/bi` | `views/BusinessIntelligenceView.vue` |
| Usage | `/analytics/usage` | `views/UsageView.vue` |
| Operations | SLM — **new** (closest today: `/monitoring/system`); moving from `/analytics/operations` | `views/OperationsView.vue` |
| ErrorMonitoring | SLM `/monitoring/errors`; moving from `/analytics/errors` | `views/ErrorMonitoringView.vue` → `autobot-slm-frontend` `views/monitoring/ErrorMonitor.vue` |
| FailureAnalysis | SLM — **new** (closest today: `/monitoring/errors`); moving from `/analytics/diagnostics` | `views/FailureAnalysisDashboard.vue` |
| Plugins / Marketplace | SLM — **new**; moving from `/plugins`, `/plugins/marketplace` | `views/PluginsView.vue`, `MarketplaceView.vue` |
| Secrets / SecretsApiKeys / SecretsAudit | SLM — **new** (closest today: `/settings/admin/secrets`, system secrets only; there is no `/secrets` route in the SLM); moving from `/secrets`, `/secrets/llm-keys`, `/secrets/audit-log` | `components/security/SecretsManager.vue` + child routes |
| Preferences | `/preferences` | `views/SettingsView.vue` |
| LlmConfig | SLM `/settings/admin/llm` | `autobot-slm-frontend` (`/llm-config` in the user frontend redirects) |
| ThemeManager | SLM — **new** | SLM admin screen for installed themes (#10472) |
| AdminUsers | SLM `/settings/admin/users`; moving from `/admin/users` | `views/AdminUsersView.vue` → SLM `views/settings/admin/UserManagementSettings.vue` |
| AdminSandbox | SLM — **new**; moving from `/admin/sandbox` | `views/AdminSandboxView.vue` |
| AdminAdvancedControl | SLM `/tools/advanced-control`; moving from `/admin/advanced-control` | `views/AdvancedControlView.vue` → SLM `views/tools/admin/AdvancedControlTool.vue` |
| AdminBudgetPolicies | SLM — **new** (closest today: `/settings/admin/budget-audit`, read-only audit); moving from `/admin/budget-policies` | `views/BudgetPolicies.vue` |
| AdminProviderFallback | SLM `/settings/admin/llm-fallbacks`; moving from `/admin/provider-fallback` | `views/ProviderFallbackView.vue` → SLM `views/settings/admin/LLMFallbacksView.vue` |
| AdminPricing | SLM — **new**; moving from `/admin/pricing` | `views/AdminPricingView.vue` |
| AdminMcpServers | SLM — **new** (closest today: `/tools/mcp`, the MCP Registry); moving from `/admin/mcp-servers` | `views/AdminMcpServersView.vue` |
| AdminPermissionScopes | SLM — **new**; moving from `/admin/permission-scopes` | `views/AdminPermissionScopesView.vue` (empty state today) |
| AuditLogs | SLM `/security/audit` (Audit Logs tab); moving from `/analytics/audit` | `views/AuditLogsView.vue` → SLM `views/SecurityView.vue` |
| SystemHealth | SLM — **new** (closest today: `/monitoring/system`); moving from `/admin/system-health` | `views/SystemHealthView.vue` |
| SlmAgentLedger | SLM `/monitoring/agent-ledger` (admin only, #18391) | install-wide agent ledger: presence, claims, contention, dev-loop history — SLM `views/monitoring/AgentLedgerMonitor.vue` |
| Experiments | SLM — **new**; moving from `/experiments` | `views/ExperimentDashboard.vue` |
| Benchmark | SLM — **new**; moving from `/analytics/benchmark` | `views/BenchmarkView.vue` |
| Evolution | SLM — **new**; moving from `/analytics/evolution` | `views/EvolutionView.vue` |
| DevSpeedup | SLM — **new**; moving from `/analytics/dev-tools` | (moved there by #902) |
| SignUp, ForgotPassword, TwoFactor, AcceptInvite | — **new** | confirm auth backend support first |
| AccountSecurity, AccountNotifications, AccountApiKeys, AccountIntegrations | — **new** | account area linked from Profile settings |
| HelpCenter, SearchResults | — **new** | — |
| FileBrowser, Mailbox | patterns | build as reusable components; there is no mailbox UI today |

## 6. Known gaps found while mocking up

- Several strings shown in the mockups have no `en.json` key yet — add i18n keys as screens are built.
- `/llm-config`, `/desktop` and `/documents` are redirects, not screens.
- SLM console → Permission scopes is an empty state on `main`.
- No mailbox, sign-up, password-reset, two-factor or invite UI exists.
- Mockup tooltip text includes a few **keyboard shortcuts that the app does not have** (e.g.
  Ctrl+S, Ctrl+Enter, Ctrl+L, F11, Shift+F10). Implement the shortcut or drop it from the tooltip —
  never ship a tooltip that names a shortcut that does nothing.
- Some example figures in tooltips are illustrative. Tooltip copy that states a fact about the
  system must be checked against the code when the screen is built.

## 7. Build order

Each step is one PR-sized scope. A session should take one step, not the whole list.

1. **Tokens and themes** — fold `tokens.css` into `design-tokens.css` / `themes/`, add `contrast`
   and `mono` to `useTheme`, SLM scheme in `autobot-slm-frontend`. No visual regressions in the
   current views beyond the palette change.
2. **Shell** — top nav + icon cluster, UI-mode toggle and preference, Profile settings appearance
   and preferred-mode sections.
3. **Shared primitives** — buttons, pills, cards, tables, form controls, dialogs, overlays,
   tooltip (#14779), command menu — from the `Components*` screens.
4. **Home and Company OS dashboards** — including move/resize widgets.
5. **Section by section** — Chat (incl. System Control move to Advanced control), Knowledge
   (without Health and Transcriber; with audio/video upload), Company OS pages + Automation +
   Transcriber, Agents, Analytics, Settings, SLM console (now including Knowledge base health and
   Agent ledger).
6. **New screens** — account area, auth flows, help, search, mailbox, and the Company OS screens
   marked **new** in §5 — each only after its backend is confirmed. The role → workflow → process
   screens wait for #18390; the agent ledger screens for #18391's read APIs; the AI lines and
   automation setup for #18430 (one enforcement point with the approval policies, #17463); the
   handbook for #18431; the schedule picker for #18432's scheduler support.

## Related

- #14779 — shared interaction primitives (Tooltip, Popover, DropdownMenu, Tabs, …)
- #17571 — design system not declared canonical
- #17560 — independent colour-mapping functions, not theme-aware
- #18161 — density never scales spacing; ember palette applied to every theme
- #10472 — runtime installed-theme delivery
- [`TECHNICAL_PRECISION_THEME.md`](TECHNICAL_PRECISION_THEME.md) — the previous theme direction
