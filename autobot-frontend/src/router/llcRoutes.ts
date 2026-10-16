// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Company-scoped Company OS routes: the children of /llc/companies/:companyId
 * (GH#8248 backlog/sprint/kanban, GH#8249/GH#8550 modules, #18391 agent ledger).
 * Split out of router/index.ts, which is over the 600-line limit, as the place
 * company views are added; index.ts keeps the parent record and its guard.
 */
import type { RouteRecordRaw } from 'vue-router'
import WorkflowBuilderView from '@/views/WorkflowBuilderView.vue'

export const llcCompanyChildren: RouteRecordRaw[] = [
  { path: '', redirect: { name: 'llc-backlog' } },
  {
    path: 'backlog',
    name: 'llc-backlog',
    component: () => import('@/views/llc/BacklogView.vue'),
    meta: { title: 'Backlog', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'boards/:boardId/sprint',
    name: 'llc-sprint-board',
    component: () => import('@/views/llc/SprintBoardView.vue'),
    meta: { title: 'Sprint Board', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'boards/:boardId/kanban',
    name: 'llc-kanban-board',
    component: () => import('@/views/llc/KanbanBoardView.vue'),
    meta: { title: 'Kanban Board', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'timeline',
    name: 'llc-timeline',
    component: () => import('@/views/llc/GanttTimelineView.vue'),
    meta: { title: 'Timeline', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'boards',
    name: 'llc-boards',
    component: () => import('@/views/llc/BoardsView.vue'),
    meta: { title: 'Boards', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'reviews',
    name: 'llc-reviews',
    component: () => import('@/views/llc/ReviewInboxView.vue'),
    meta: { title: 'My Reviews', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'portfolios',
    name: 'llc-portfolios',
    component: () => import('@/views/llc/PortfolioBrowserView.vue'),
    meta: { title: 'Portfolios', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'portfolios/:portfolioId/programs',
    name: 'llc-programs',
    component: () => import('@/views/llc/ProgramBrowserView.vue'),
    meta: { title: 'Programs', requiresAuth: true, hideInNav: true },
  },
  {
    path: 'programs/:programId/projects',
    name: 'llc-projects',
    component: () => import('@/views/llc/ProjectBrowserView.vue'),
    meta: { title: 'Projects', requiresAuth: true, hideInNav: true },
  },
  { path: 'approvals', name: 'llc-approvals', component: () => import('@/views/llc/ApprovalsInbox.vue'), props: true, meta: { title: 'Approvals Inbox', requiresAuth: true } },
  { path: 'costs', name: 'llc-costs', component: () => import('@/views/llc/CostDashboard.vue'), props: true, meta: { title: 'Cost Dashboard', requiresAuth: true } },
  { path: 'heartbeat', name: 'llc-heartbeat', component: () => import('@/views/llc/HeartbeatMonitor.vue'), props: true, meta: { title: 'Heartbeat Monitor', requiresAuth: true } },
  // #18391: Overview > Agent ledger -- read-only, company-scoped by the backend.
  { path: 'ledger', name: 'llc-ledger', component: () => import('@/views/llc/AgentLedgerView.vue'), meta: { title: 'Agent ledger', requiresAuth: true } },
  { path: 'routines', name: 'llc-routines', component: () => import('@/views/llc/RoutinesView.vue'), props: true, meta: { title: 'Routines', requiresAuth: true } },
  { path: 'ceo-chat', name: 'llc-ceo-chat', component: () => import('@/views/llc/CeoChatView.vue'), props: true, meta: { title: 'CEO Chat', requiresAuth: true } },
  { path: 'activity', name: 'llc-activity', component: () => import('@/views/llc/ActivityFeedView.vue'), props: true, meta: { title: 'Activity', requiresAuth: true } },
  { path: 'roles', name: 'llc-roles', component: () => import('@/views/llc/RolesView.vue'), props: true, meta: { title: 'Roles', requiresAuth: true } },
  { path: 'members', name: 'llc-members', component: () => import('@/views/llc/MembersView.vue'), props: true, meta: { title: 'Members', requiresAuth: true } },
  { path: 'portability', name: 'llc-company-portability', component: () => import('@/views/llc/CompanyPortabilityView.vue'), props: true, meta: { title: 'Portability', requiresAuth: true } },
  { path: 'secrets', name: 'llc-company-secrets', component: () => import('@/views/llc/SecretsView.vue'), props: true, meta: { title: 'Secrets', requiresAuth: true } },
  // GH#10750 (B3): in-layout variants of the formerly top-level dashboard/
  // goals/org-chart views so the LlcSidebar stays mounted on navigation.
  // The views resolve the active company from :companyId via
  // useLlcCompanyContext (param -> ?company= fallback for back-compat).
  { path: 'dashboard', name: 'llc-company-dashboard', component: () => import('@/views/llc/CompanyDashboard.vue'), props: true, meta: { title: 'Company Dashboard', requiresAuth: true } },
  { path: 'goals', name: 'llc-company-goals', component: () => import('@/views/llc/GoalTree.vue'), props: true, meta: { title: 'Goal Tree', requiresAuth: true } },
  { path: 'org-chart', name: 'llc-company-org-chart', component: () => import('@/views/llc/OrgChart.vue'), props: true, meta: { title: 'Org Chart', requiresAuth: true } },
  // GH#13939: the automation module, moved here from /automation/*. Route
  // names are preserved so deep links and the builder's own active-state
  // checks keep working. Child routes render inside WorkflowBuilderView's
  // <router-view /> (#2368); ':section' is rendered inline via
  // route.params.section (GH#8750).
  {
    path: 'automation',
    name: 'llc-company-automation',
    component: WorkflowBuilderView,
    // #16901: no longer hidden — it has a Company OS sidebar entry now.
    meta: { title: 'Workflow Automation', requiresAuth: true },
    children: [
      {
        // Named so vue-router does not warn about an unnamed empty-path
        // child under a named parent.
        path: '',
        name: 'llc-company-automation-index',
        redirect: (to) => `/llc/companies/${to.params.companyId}/automation/overview`
      },
      {
        path: 'browser-automation',
        name: 'browser-automation',
        component: () => import('@/views/BrowserAutomationView.vue'),
        meta: {
          title: 'Browser Automation',
          icon: 'fas fa-globe',
          description: 'Control browser workers and automate web tasks',
          requiresAuth: true
        }
      },
      // Issue #9890: Vision Automation panel — dedicated component route
      {
        path: 'vision-automation',
        name: 'vision-automation',
        component: () => import('@/views/VisionAutomationView.vue'),
        meta: {
          title: 'Vision Automation',
          description: 'Screen analysis, element detection, OCR, and automation opportunities',
          requiresAuth: true
        }
      },
      {
        path: ':section',
        name: 'automation-section',
        component: { render: () => null },
        meta: {
          sectionRoute: true,
          requiresAuth: true
        }
      }
    ]
  },
]
