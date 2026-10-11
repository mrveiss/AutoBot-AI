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
Logo · Home · Chat · Knowledge · Company OS · Analytics (`adv`), then an outlined **SLM Admin ↗**
link (`adv`) and an icon cluster on the right: Plugins · Secrets (key) · Preferences ·
**UI-mode toggle** · Admin panel (shield) · Profile settings. Every icon has an `aria-label` and a
tooltip. Active item: `--nav-on-bw` underline in `--accent`. Overflow collapses into the existing
`NavOverflowMenu`. Agents is reached from its own pages' sub-navigation, not the top bar.
Reference: any app screen (e.g. `Chat`); `ComponentsNavigation` for states.

### 4.2 Minimal / Full interface mode
- Root attribute `data-ui="minimal|full"`; CSS hides `.adv` in Minimal (`tokens.css`).
- **Toggle** is a button in the nav icon cluster, just before the Admin icon. Label "Minimal",
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
first item of the **Danger Zone** card in Admin → Advanced control. Reference: `Chat`,
`AdminAdvancedControl`.

## 5. Screen → view map

Route/view as found on `main` at 940da29. **New** = no view exists yet; confirm the backend before
building UI for it.

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
| Chat | `/chat` | `ChatView` → `components/chat/ChatInterface.vue` |
| Desktop | `/chat/novnc` (`/desktop` redirects) | `ChatInterface.vue` (noVNC tab) |
| Canvas | `/canvas` | `views/CanvasView.vue` |
| Knowledge | `/knowledge/browser` | `components/knowledge/KnowledgeBrowser.vue` |
| KnowledgeGraph | `/knowledge/graph` | `components/knowledge/KnowledgeGraphView.vue` |
| KnowledgeVectorStore | `/knowledge/vector-store` | (route `knowledge-vector-store`, #8999) |
| KnowledgeHealth | `/knowledge/health` | `components/knowledge/KnowledgeHealth.vue` |
| KnowledgeResearch | `/knowledge/research` | `components/knowledge/KnowledgeResearchTabs.vue` |
| KnowledgeMcpResources | `/knowledge/mcp-resources` | `components/knowledge/McpResourceBrowser.vue` |
| KnowledgeSystemDocs | `/knowledge/system-docs` | `components/knowledge/KnowledgeSystemDocs.vue` |
| KnowledgeManage | `/knowledge/manage` | `components/knowledge/KnowledgeEntries.vue` |
| KnowledgeEntities | `/knowledge/entities` | `components/knowledge/EntityGraphManager.vue` |
| Documents | `/documents` redirects to `/knowledge/browser` | AI documents view inside Knowledge |
| TranscriberProjects / Project / Transcript | `/knowledge/transcriber/…` | `views/transcriber/ProjectsView.vue`, `ProjectDetailView.vue`, `TranscriptView.vue` |
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
| OrgChart | `…/org-chart` | `views/llc/OrgChart.vue` |
| Members / Roles | `…/members`, `…/roles` | `views/llc/MembersView.vue`, `RolesView.vue` |
| Approvals | `…/approvals` | `views/llc/ApprovalsInbox.vue` |
| Costs | `…/costs` | `views/llc/CostDashboard.vue` |
| HeartbeatMonitor | `…/heartbeat` | `views/llc/HeartbeatMonitor.vue` |
| Routines | `…/routines` | `views/llc/RoutinesView.vue` |
| CeoChat | `…/ceo-chat` | `views/llc/CeoChatView.vue` |
| Activity | `…/activity` | `views/llc/ActivityFeedView.vue` |
| Portability | `…/portability` | `views/llc/CompanyPortabilityView.vue` |
| CompanySecrets | `…/secrets` | `views/llc/SecretsView.vue` |
| AutomationOverview / Automation / Templates / Runner / History | `…/automation/:section` | `WorkflowBuilderView` |
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
| Operations | `/analytics/operations` | `views/OperationsView.vue` |
| ErrorMonitoring | `/analytics/errors` | `views/ErrorMonitoringView.vue` |
| FailureAnalysis | `/analytics/diagnostics` | `views/FailureAnalysisDashboard.vue` |
| Plugins / Marketplace | `/plugins`, `/plugins/marketplace` | `views/PluginsView.vue`, `MarketplaceView.vue` |
| Secrets / SecretsApiKeys / SecretsAudit | `/secrets`, `/secrets/llm-keys`, `/secrets/audit-log` | `components/security/SecretsManager.vue` + child routes |
| Preferences | `/preferences` | `views/SettingsView.vue` |
| LlmConfig | SLM `admin/llm` | `autobot-slm-frontend` (`/llm-config` in the user frontend redirects) |
| ThemeManager | SLM — **new** | SLM admin screen for installed themes (#10472) |
| AdminUsers | `/admin/users` | `views/AdminUsersView.vue` |
| AdminSandbox | `/admin/sandbox` | `views/AdminSandboxView.vue` |
| AdminAdvancedControl | `/admin/advanced-control` | `views/AdvancedControlView.vue` |
| AdminBudgetPolicies | `/admin/budget-policies` | `views/BudgetPolicies.vue` |
| AdminProviderFallback | `/admin/provider-fallback` | `views/ProviderFallbackView.vue` |
| AdminPricing | `/admin/pricing` | `views/AdminPricingView.vue` |
| AdminMcpServers | `/admin/mcp-servers` | `views/AdminMcpServersView.vue` |
| AdminPermissionScopes | `/admin/permission-scopes` | `views/AdminPermissionScopesView.vue` (empty state today) |
| AuditLogs | `/analytics/audit` | `views/AuditLogsView.vue` |
| SystemHealth | `/admin/system-health` | `views/SystemHealthView.vue` |
| Experiments | `/experiments` | `views/ExperimentDashboard.vue` |
| Benchmark | `/analytics/benchmark` | `views/BenchmarkView.vue` |
| Evolution | `/analytics/evolution` | `views/EvolutionView.vue` |
| DevSpeedup | `/analytics/dev-tools` | (moved there by #902) |
| SignUp, ForgotPassword, TwoFactor, AcceptInvite | — **new** | confirm auth backend support first |
| AccountSecurity, AccountNotifications, AccountApiKeys, AccountIntegrations | — **new** | account area linked from Profile settings |
| HelpCenter, SearchResults | — **new** | — |
| FileBrowser, Mailbox | patterns | build as reusable components; there is no mailbox UI today |

## 6. Known gaps found while mocking up

- Several strings shown in the mockups have no `en.json` key yet — add i18n keys as screens are built.
- `/llm-config`, `/desktop` and `/documents` are redirects, not screens.
- Admin → Permission scopes is an empty state on `main`.
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
5. **Section by section** — Chat (incl. System Control move to Advanced control), Knowledge,
   Company OS pages + Automation, Agents, Analytics, Settings, Admin, SLM.
6. **New screens** — account area, auth flows, help, search, mailbox — each only after its backend
   is confirmed.

## Related

- #14779 — shared interaction primitives (Tooltip, Popover, DropdownMenu, Tabs, …)
- #17571 — design system not declared canonical
- #17560 — independent colour-mapping functions, not theme-aware
- #18161 — density never scales spacing; ember palette applied to every theme
- #10472 — runtime installed-theme delivery
- [`TECHNICAL_PRECISION_THEME.md`](TECHNICAL_PRECISION_THEME.md) — the previous theme direction
