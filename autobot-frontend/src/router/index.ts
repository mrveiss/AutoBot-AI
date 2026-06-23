// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Vue Router Configuration
 *
 * Issue #729: Layer separation - autobot-vue is now business-only.
 * Infrastructure routes moved to slm-admin.
 *
 * Routes available:
 * - /chat - AI Assistant (includes chat terminal with agent access)
 * - /knowledge - Knowledge Base
 * - /automation - Workflow Builder
 * - /analytics - Codebase & Business Analytics
 * - /secrets - Secrets Manager (user credentials for chat/agent)
 *
 * For infrastructure operations use slm-admin:
 * - /tools - Developer Tools (standalone terminal, file browser)
 * - /monitoring - System Monitoring
 * - /settings - Settings (infrastructure/admin settings)
 * - /infrastructure - Infrastructure Manager
 * - /tls-certificates - TLS Certificates
 */

import { createRouter, createWebHistory, type RouteLocationNormalized, type RouteRecordRaw } from 'vue-router'
import { useAppStore } from '@/stores/useAppStore'
import { useUserStore } from '@/stores/useUserStore'
import { setupAsyncComponentErrorHandler } from '@/utils/asyncComponentHelpers'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl, getSLMAdminUrl } from '@/config/ssot-config'
import { llcCompanyParamGuard } from './llcGuards'

const logger = createLogger('Router');

// Initialize global async component error handler
setupAsyncComponentErrorHandler()

// Views (Page-level components) - Use direct imports for simple containers to avoid circular dependencies
import ChatView from '@/views/ChatView.vue'
import KnowledgeView from '@/views/KnowledgeView.vue'
import WorkflowBuilderView from '@/views/WorkflowBuilderView.vue'
import AnalyticsView from '@/views/AnalyticsView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import PermissionDeniedView from '@/views/PermissionDeniedView.vue'
import AboutView from '@/views/AboutView.vue'
import OnboardingWizard from '@/views/OnboardingWizard.vue'

// Route configuration - Issue #729: Business-only routes, infrastructure moved to slm-admin
// Exported (#6499) so `nav-items-coverage.test.ts` can verify every top-level
// `requiresAuth: true` route has a matching entry in `@/config/navItems`.
export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/home'
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/components/auth/LoginForm.vue'),
    meta: {
      title: 'Login',
      hideInNav: true,
      requiresAuth: false,
      isPublic: true
    }
  },
  // GH#8996: public shared conversation view (no auth required)
  {
    path: '/shared/:token',
    name: 'shared-chat',
    component: () => import('@/views/SharedChatView.vue'),
    meta: {
      title: 'Shared Conversation',
      hideInNav: true,
      hideFooter: true,
      requiresAuth: false,
      isPublic: true
    }
  },
  {
    path: '/dashboard',
    redirect: '/home'
  },
  // Issue #5061: First-run onboarding wizard
  {
    path: '/onboarding',
    name: 'onboarding',
    component: OnboardingWizard,
    meta: {
      title: 'Setup',
      hideInNav: true,
      hideFooter: true,
      requiresAuth: true
    }
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatView,
    meta: {
      title: 'AI Assistant',
      icon: 'fas fa-robot',
      description: 'Chat with AI assistant',
      requiresAuth: true,
      hideFooter: true
    },
    children: [
      {
        path: '',
        name: 'chat-default',
        component: () => import('@/components/chat/ChatInterface.vue')
      },
      {
        path: 'terminal',
        name: 'chat-terminal',
        component: () => import('@/components/chat/ChatInterface.vue'),
        meta: { chatTab: 'terminal', requiresAuth: true, title: 'Chat — Terminal' }
      },
      {
        path: 'novnc',
        name: 'chat-novnc',
        component: () => import('@/components/chat/ChatInterface.vue'),
        meta: { chatTab: 'novnc', requiresAuth: true, title: 'Chat — Remote Desktop' }
      },
      {
        path: ':sessionId',
        name: 'chat-session',
        component: () => import('@/components/chat/ChatInterface.vue'),
        props: true,
        meta: {
          title: 'Chat Session',
          parent: 'chat'
        }
      }
    ]
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: KnowledgeView,
    meta: {
      title: 'Knowledge Base',
      icon: 'fas fa-database',
      description: 'Manage knowledge and documents',
      requiresAuth: true
    },
    children: [
      {
        path: '',
        name: 'knowledge-default',
        redirect: '/knowledge/search'
      },
      {
        path: 'search',
        name: 'knowledge-search',
        component: () => import('@/components/knowledge/KnowledgeSearch.vue'),
        meta: {
          title: 'Search Knowledge',
          parent: 'knowledge'
        }
      },
      {
        path: 'categories',
        name: 'knowledge-categories',
        component: () => import('@/components/knowledge/KnowledgeBrowser.vue'),
        meta: {
          title: 'Browse Knowledge',
          parent: 'knowledge'
        }
      },
      {
        path: 'upload',
        redirect: '/knowledge/manage'
      },
      {
        path: 'manage',
        name: 'knowledge-manage',
        component: () => import('@/components/knowledge/KnowledgeEntries.vue'),
        meta: {
          title: 'Manage Knowledge',
          parent: 'knowledge'
        }
      },
      {
        path: 'verification',
        name: 'knowledge-verification',
        component: () => import('@/components/knowledge/KnowledgeVerificationQueue.vue'),
        meta: {
          title: 'Source Verification',
          parent: 'knowledge'
        }
      },
      {
        // Issue #1256: Observable Research Panel — live browser collaboration
        path: 'research',
        name: 'knowledge-research',
        component: () => import('@/components/knowledge/KnowledgeResearchPanel.vue'),
        meta: {
          title: 'Research',
          parent: 'knowledge'
        }
      },
      {
        // MVA-2167: MCP Resource Browser
        path: 'mcp-resources',
        name: 'knowledge-mcp-resources',
        component: () => import('@/components/knowledge/McpResourceBrowser.vue'),
        meta: {
          title: 'MCP Resources',
          parent: 'knowledge'
        }
      },
      {
        // #8999: ChromaDB / vector-store explorer — browse collections,
        // inspect documents, run similarity search (backend: api/knowledge_chroma.py)
        path: 'vector-store',
        name: 'knowledge-vector-store',
        component: () => import('@/components/knowledge/ChromaDBExplorer.vue'),
        meta: {
          title: 'Vector Store',
          parent: 'knowledge'
        }
      },
      {
        path: 'connectors',
        name: 'knowledge-connectors',
        component: () => import('@/components/knowledge/connectors/ConnectorManager.vue'),
        meta: {
          title: 'Source Connectors',
          parent: 'knowledge'
        }
      },
      {
        path: 'stats',
        name: 'knowledge-stats',
        component: () => import('@/components/knowledge/KnowledgeStats.vue'),
        meta: {
          title: 'Statistics',
          parent: 'knowledge'
        }
      },
      {
        // Issue #3850: web research settings UI
        path: 'web-research-settings',
        name: 'knowledge-web-research-settings',
        component: () => import('@/components/knowledge/WebResearchSettings.vue'),
        meta: {
          title: 'Web Research Settings',
          parent: 'knowledge'
        }
      },
      {
        // MVA-344: 4-tab web research panel (Fetch Page / Crawl Site / Find Pages / Get Data)
        path: 'web-research',
        name: 'knowledge-web-research',
        component: () => import('@/components/knowledge/WebResearchPanel.vue'),
        meta: {
          title: 'Web Research',
          parent: 'knowledge'
        }
      },
      {
        path: 'manpages',
        redirect: () => ({
          path: '/knowledge/categories',
          query: { view: 'system' }
        })
      },
      {
        path: 'system-knowledge',
        redirect: () => ({
          path: '/knowledge/categories',
          query: { view: 'system' }
        })
      },
      {
        path: 'browser/user',
        redirect: '/knowledge/categories'
      },
      {
        path: 'browser/autobot',
        redirect: '/knowledge/categories'
      },
      {
        path: 'graph',
        name: 'knowledge-graph',
        component: () => import('@/components/knowledge/KnowledgeGraphView.vue'),
        meta: {
          title: 'Knowledge Graph',
          parent: 'knowledge'
        },
        children: [
          {
            // Issue #759: Knowledge Graph Pipeline
            path: 'pipeline',
            name: 'knowledge-graph-pipeline',
            component: () => import('@/components/knowledge/pipeline/PipelineRunner.vue'),
            meta: {
              title: 'Pipeline Runner',
              parent: 'knowledge'
            }
          },
          {
            path: 'entities',
            name: 'knowledge-graph-entities',
            component: () => import('@/components/knowledge/graph/KnowledgeGraphExplorer.vue'),
            meta: {
              title: 'Entity Explorer',
              parent: 'knowledge'
            }
          },
          {
            path: 'timeline',
            name: 'knowledge-graph-timeline',
            component: () => import('@/components/knowledge/temporal/TimelinePage.vue'),
            meta: {
              title: 'Event Timeline',
              parent: 'knowledge'
            }
          },
          {
            path: 'summaries',
            name: 'knowledge-graph-summaries',
            component: () => import('@/components/knowledge/summaries/SummariesPage.vue'),
            meta: {
              title: 'Summary Search',
              parent: 'knowledge'
            }
          }
        ]
      },
      {
        // Issue #586: Entity Extraction & Graph RAG Manager
        path: 'entities',
        name: 'knowledge-entities',
        component: () => import('@/components/knowledge/EntityGraphManager.vue'),
        meta: {
          title: 'Entity Graph Manager',
          parent: 'knowledge'
        }
      },
      {
        path: 'maintenance',
        name: 'knowledge-maintenance',
        component: () => import('@/components/knowledge/KnowledgeMaintenance.vue'),
        meta: {
          title: 'Knowledge Maintenance',
          parent: 'knowledge'
        }
      },
      {
        path: 'watch-folders',
        name: 'knowledge-watch-folders',
        component: () => import('@/views/knowledge/WatchFoldersView.vue'),
        meta: {
          title: 'Watch Folders',
          parent: 'knowledge'
        }
      }
    ]
  },
  {
    path: '/automation',
    name: 'automation',
    component: WorkflowBuilderView,
    meta: {
      title: 'Workflow Automation',
      icon: 'fas fa-project-diagram',
      description: 'Visual workflow builder and automation (Issue #585)',
      requiresAuth: true
    },
    // Child routes render inside WorkflowBuilderView's <router-view /> (#2368)
    children: [
      {
        path: '',
        redirect: '/automation/overview'
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
      // GH#8750: URL-routed sections — rendered inline in WorkflowBuilderView via route.params.section
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
  // Redirect old path (#2367)
  {
    path: '/browser-automation',
    redirect: '/automation/browser-automation'
  },
  {
    path: '/analytics',
    name: 'analytics',
    component: AnalyticsView,
    meta: {
      title: 'Analytics',
      icon: 'fas fa-chart-pie',
      description: 'Codebase analytics and business intelligence',
      requiresAuth: true
    },
    children: [
      {
        path: '',
        name: 'analytics-default',
        redirect: '/analytics/codebase'
      },
      {
        path: 'codebase',
        name: 'analytics-codebase',
        component: () => import('@/components/analytics/CodebaseAnalyticsLanding.vue'),
        meta: {
          title: 'Codebase Analytics',
          parent: 'analytics'
        }
      },
      {
        path: 'codebase/:sourceId',
        name: 'analytics-codebase-project',
        component: () => import('@/components/analytics/CodebaseAnalytics.vue'),
        meta: {
          title: 'Codebase Analytics',
          parent: 'analytics'
        },
        children: [
          {
            path: 'code-quality',
            name: 'analytics-codebase-code-quality',
            component: () => import('@/components/analytics/CodeQualityDashboard.vue'),
            meta: {
              title: 'Code Quality',
              parent: 'analytics'
            }
          },
          {
            path: 'code-review',
            name: 'analytics-codebase-code-review',
            component: () => import('@/components/analytics/CodeReviewDashboard.vue'),
            meta: {
              title: 'Code Review',
              parent: 'analytics'
            }
          },
          {
            path: 'evolution',
            name: 'analytics-codebase-evolution',
            component: () => import('@/views/EvolutionView.vue'),
            meta: {
              title: 'Code Evolution',
              parent: 'analytics'
            }
          },
          {
            path: 'code-generation',
            name: 'analytics-codebase-code-generation',
            component: () => import('@/components/analytics/CodeGenerationDashboard.vue'),
            meta: {
              title: 'Code Generation',
              parent: 'analytics'
            }
          }
        ]
      },
      {
        path: 'bi',
        name: 'analytics-bi',
        component: () => import('@/views/BusinessIntelligenceView.vue'),
        meta: {
          title: 'Business Intelligence',
          parent: 'analytics'
        }
      },
      {
        path: 'security',
        name: 'analytics-security',
        component: () => import('@/components/security/ThreatIntelligenceDashboard.vue'),
        meta: {
          title: 'Security Analytics',
          parent: 'analytics'
        }
      },
      {
        path: 'security/settings',
        name: 'analytics-security-settings',
        component: () => import('@/components/security/ThreatIntelligenceSettings.vue'),
        meta: {
          title: 'Threat Intelligence Settings',
          parent: 'analytics'
        }
      },
      {
        path: 'audit',
        name: 'analytics-audit',
        component: () => import('@/views/AuditLogsView.vue'),
        meta: {
          title: 'Audit Logs',
          parent: 'analytics',
          icon: 'fas fa-shield-halved',
          description: 'Security audit logging and monitoring (Issue #578)',
          requiresAuth: true
        }
      },
      {
        // Issue #902: Dev Tools moved from standalone /dev-speedup into /analytics/dev-tools
        path: 'dev-tools',
        name: 'analytics-dev-tools',
        component: () => import('@/views/DevSpeedupView.vue'),
        meta: {
          title: 'Dev Tools',
          parent: 'analytics'
        }
      },
      // bug-prediction route removed — functionality in CodebaseBugPredictionPanel
      // code-intelligence route removed — functionality in CodebaseIntelligenceScoresPanel
      // evolution, code-generation, code-quality, code-review moved under codebase/:sourceId (Issue #3436)
      {
        path: 'conversation-flow',
        name: 'analytics-conversation-flow',
        component: () => import('@/components/analytics/ConversationFlowDashboard.vue'),
        meta: {
          title: 'Conversation Flow',
          parent: 'analytics'
        }
      },
      {
        path: 'llm-patterns',
        name: 'analytics-llm-patterns',
        component: () => import('@/components/analytics/LLMPatternDashboard.vue'),
        meta: {
          title: 'LLM Patterns',
          parent: 'analytics'
        }
      },
      // Issue #9024: LLM model-comparison / benchmark dashboard
      {
        path: 'benchmark',
        name: 'analytics-benchmark',
        component: () => import('@/views/BenchmarkView.vue'),
        meta: {
          title: 'Model Benchmark',
          parent: 'analytics'
        }
      },
      {
        path: 'log-patterns',
        name: 'analytics-log-patterns',
        component: () => import('@/components/analytics/LogPatternDashboard.vue'),
        meta: {
          title: 'Log Patterns',
          parent: 'analytics'
        }
      },
      {
        path: 'performance',
        name: 'analytics-performance',
        component: () => import('@/components/analytics/PerformanceAnalysisDashboard.vue'),
        meta: {
          title: 'Performance Analysis',
          parent: 'analytics'
        }
      },
      {
        path: 'precommit-hooks',
        name: 'analytics-precommit-hooks',
        component: () => import('@/components/analytics/PrecommitHookDashboard.vue'),
        meta: {
          title: 'Pre-commit Hooks',
          parent: 'analytics'
        }
      },
      {
        path: 'technical-debt',
        name: 'analytics-technical-debt',
        component: () => import('@/components/analytics/TechnicalDebtDashboard.vue'),
        meta: {
          title: 'Technical Debt',
          parent: 'analytics'
        }
      },
      // Issue #4465: Usage & Costs moved under analytics
      {
        path: 'usage',
        name: 'analytics-usage',
        component: () => import('@/views/UsageView.vue'),
        meta: {
          title: 'Usage & Costs',
          parent: 'analytics'
        }
      },
      // Issue #4270: Operations moved under analytics (long-running background tasks monitor)
      {
        path: 'operations',
        name: 'analytics-operations',
        component: () => import('@/views/OperationsView.vue'),
        meta: {
          title: 'Operations',
          parent: 'analytics'
        }
      },
      // Issue #9891: Error monitoring dashboard wired to /api/errors/* endpoints
      {
        path: 'errors',
        name: 'analytics-errors',
        component: () => import('@/views/ErrorMonitoringView.vue'),
        meta: {
          title: 'Error Monitoring',
          parent: 'analytics'
        }
      },
      // Issue #9892: Failure Analysis — causal inference engine diagnostics UI
      {
        path: 'diagnostics',
        name: 'analytics-diagnostics',
        component: () => import('@/views/FailureAnalysisDashboard.vue'),
        meta: {
          title: 'Failure Analysis',
          parent: 'analytics'
        }
      },
    ]
  },
  // Issue #753: User preferences (appearance, font size, colors, etc.)
  {
    path: '/preferences',
    name: 'preferences',
    component: () => import('@/views/SettingsView.vue'),
    meta: {
      title: 'Preferences',
      icon: 'fas fa-sliders-h',
      description: 'Customize your AutoBot experience',
      requiresAuth: true,
      hideInNav: true,
    }
  },
  // Issue #4492: Home serves custom dashboard — renamed from /custom-dashboard
  {
    path: '/home',
    name: 'home',
    component: () => import('@/views/CustomDashboard.vue'),
    meta: {
      title: 'Home',
      icon: 'fas fa-home',
      description: 'Home dashboard',
      requiresAuth: true
    }
  },
  // Issue #4185: Wire AboutView
  {
    path: '/about',
    name: 'about',
    component: AboutView,
    meta: {
      title: 'About',
      icon: 'fas fa-info-circle',
      description: 'About AutoBot',
      requiresAuth: true
    }
  },
  // Issue #901: Component Showcase - Technical Precision Design System
  {
    path: '/components',
    name: 'components',
    component: () => import('@/views/ComponentShowcaseView.vue'),
    meta: {
      title: 'Component Showcase',
      icon: 'fas fa-palette',
      description: 'Technical Precision component library',
      hideInNav: true, // Issue #2071: Dev-only component showcase, hidden from navigation
      requiresAuth: false
    }
  },
  // Issue #897: LLM Configuration Panel — moved to SLM admin settings (#2371)
  // Redirect for backwards compatibility
  {
    path: '/llm-config',
    name: 'llm-config',
    redirect: '/',
    meta: { title: 'LLM Configuration' }
  },
  // Issue #4270: Operations moved under /analytics/operations
  { path: '/operations', redirect: '/analytics/operations' },
  // Issue #6634: Tabbed /agents shell — Registry, Activity, Heartbeat as
  // sibling tabs under a shared AgentsLayout. Each retains its own URL so
  // existing nav-item links and bookmarks still work.
  {
    path: '/agents',
    component: () => import('@/views/AgentsLayout.vue'),
    meta: {
      title: 'Agents',
      requiresAuth: true,
    },
    children: [
      { path: '', redirect: '/agents/registry' },
      // Issue #4703: Wire AgentRegistryView into router (#1794, #1822)
      {
        path: 'registry',
        name: 'agent-registry',
        component: () => import('@/views/AgentRegistryView.vue'),
        meta: {
          title: 'Agent Registry',
          icon: 'fas fa-robot',
          description: 'Browse backend and specialized agents, and manage agent settings',
          requiresAuth: true,
        },
      },
      // Issue #1521: Agent Heartbeat Panel — real-time agent run status
      {
        path: 'heartbeat',
        name: 'agent-heartbeat',
        component: () => import('@/components/agents/HeartbeatPanel.vue'),
        meta: {
          title: 'Agent Heartbeat',
          icon: 'fas fa-heartbeat',
          description: 'Monitor agent heartbeat and real-time run status',
          requiresAuth: true,
        },
      },
      // Issue #5071: per-agent diary with background append and runtime discovery
      {
        path: 'activity',
        name: 'agent-activity',
        component: () => import('@/views/AgentActivity.vue'),
        meta: {
          title: 'Agent Activity',
          icon: 'fas fa-journal-whills',
          description: 'Per-agent diary — recent entries and cross-session journal',
          requiresAuth: true,
        },
      },
    ],
  },
  // Issue #899: Code Intelligence — merged into /analytics/codebase
  {
    path: '/code-intelligence',
    redirect: '/analytics/codebase'
  },
  // Issue #902: Dev Tools moved into /analytics/dev-tools tab
  // Issue #3245: AI Document editor — persistent editable AI output documents
  {
    path: '/documents',
    name: 'documents',
    component: () => import('@/views/DocumentsView.vue'),
    meta: {
      title: 'AI Documents',
      icon: 'fas fa-file-alt',
      description: 'View and edit AI-generated documents saved from chat',
      requiresAuth: true,
    },
    children: [
      {
        path: ':docId',
        name: 'document-detail',
        component: () => import('@/views/DocumentsView.vue'),
        props: true,
        meta: {
          title: 'AI Document',
          parent: 'documents',
        },
      },
    ],
  },
  // MVA-360: Live Canvas — route always registered (preserves bookmarks/direct nav);
  // nav item gated by VITE_FEATURE_CANVAS via navItems.ts (GH#8758)
  {
    path: '/canvas',
    name: 'canvas',
    component: () => import('@/views/CanvasView.vue'),
    meta: {
      title: 'Canvas',
      requiresAuth: true,
      hideInNav: true,
    },
  },
  // Issue #3201: AutoResearch Experiment Dashboard
  {
    path: '/experiments',
    name: 'experiments',
    component: () => import('@/views/ExperimentDashboard.vue'),
    meta: {
      title: 'Experiments',
      icon: 'BeakerIcon',
      description: 'AutoResearch experiment dashboard',
      requiresAuth: true,
      hideInNav: true,
    },
  },
  // Issue #6590: Virtual LLM API Keys admin view
  {
    path: '/admin/llm-keys',
    name: 'llm-api-keys',
    component: () => import('@/views/LLMApiKeysView.vue'),
    meta: {
      title: 'LLM API Keys',
      description: 'Manage virtual LLM API keys with per-key budgets',
      requiresAuth: true,
      admin: true,
      hideInNav: true,
    },
  },
  // MVA-2999: LLM Providers & Fallback Status admin view
  {
    path: '/admin/llm-providers',
    name: 'llm-providers',
    component: () => import('@/views/LLMProvidersView.vue'),
    meta: {
      title: 'LLM Providers',
      description: 'View LLM provider fallback chains and active fallback status',
      requiresAuth: true,
      admin: true,
      // hideInNav (GH#9627 drive-by): admin views live in adminMenuItems, not main nav
      hideInNav: true,
    },
  },
  // Issue #1801: Admin User Management
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/views/AdminUsersView.vue'),
    meta: {
      title: 'User Management',
      icon: 'fas fa-users',
      description: 'Manage users, roles, and account status',
      requiresAuth: true,
      admin: true,
    },
  },
  // Issue #7773: Sandbox file inspector — wires useFileSandbox() into admin UI
  {
    path: '/admin/sandbox',
    name: 'admin-sandbox',
    component: () => import('@/views/AdminSandboxView.vue'),
    meta: {
      title: 'Sandbox Inspector',
      description: 'Browse code-execution sandbox files',
      requiresAuth: true,
      admin: true,
      hideInNav: true,
    },
  },
  // Issue #7513: Host inventory admin view
  {
    path: '/admin/hosts',
    name: 'admin-hosts',
    component: () => import('@/views/Admin/HostsView.vue'),
    meta: {
      title: 'Host Inventory',
      description: 'Manage multi-host role deployment',
      requiresAuth: true,
      admin: true,
      hideInNav: true,
    },
  },
  // GH#8996: Admin cross-user view of all active shared chat links (AC4)
  {
    path: '/admin/shared-links',
    name: 'admin-shared-links',
    component: () => import('@/views/Admin/SharedLinksAdminView.vue'),
    meta: {
      title: 'Shared Chat Links',
      description: 'View all active shared chat links across users',
      requiresAuth: true,
      admin: true,
      hideInNav: true,
    },
  },
  // GH#6470: Budget policy management (admin-only)
  {
    path: '/admin/budget-policies',
    name: 'budget-policies',
    component: () => import('@/views/BudgetPolicies.vue'),
    meta: {
      title: 'Budget Policies',
      description: 'Manage agent spend thresholds and auto-pause rules',
      requiresAuth: true,
      admin: true,
      hideInNav: true,
    },
  },
  // /desktop removed from nav — noVNC is accessible via the Chat tab's noVNC tab.
  // Redirect any bookmarked /desktop URLs to /chat.
  { path: '/desktop', redirect: '/chat' },
  // Issue #4977: Standalone noVNC view at /slm/tools/novnc (driven by HostSelector)
  {
    path: '/slm/tools/novnc',
    name: 'SlmNoVnc',
    component: () => import('@/views/SlmNoVncView.vue'),
    meta: {
      title: 'Remote Desktop',
      requiresAuth: true,
      hideFooter: true,
    },
  },
  // Issue #10472: Admin theme-package management under the /slm route group.
  // Upload/list/uninstall theme zips; install is admin-gated server-side.
  {
    path: '/slm/themes',
    name: 'slm-themes',
    component: () => import('@/views/slm/ThemeManagerView.vue'),
    meta: {
      title: 'Theme Manager',
      requiresAuth: true,
      // Admin-only operator view, reached via /slm — not in the primary nav rail.
      hideInNav: true,
    },
  },
  // Issue #3502: Custom Dashboard renamed to /home (see home route above)

  // Issue #729: Infrastructure routes redirected to slm-admin
  // These routes are kept as redirects for backwards compatibility
  {
    path: '/tools',
    redirect: () => {
      // Redirect to SLM Admin Tools
      window.location.href = `${getSLMAdminUrl()}/#/tools`
      return '/chat' // Fallback
    }
  },
  {
    path: '/tools/:pathMatch(.*)*',
    redirect: () => {
      window.location.href = `${getSLMAdminUrl()}/#/tools`
      return '/chat'
    }
  },
  {
    path: '/monitoring',
    redirect: () => {
      window.location.href = `${getSLMAdminUrl()}/#/monitoring`
      return '/chat'
    }
  },
  {
    path: '/monitoring/:pathMatch(.*)*',
    redirect: () => {
      window.location.href = `${getSLMAdminUrl()}/#/monitoring`
      return '/chat'
    }
  },
  {
    path: '/settings',
    redirect: () => {
      window.location.href = `${getSLMAdminUrl()}/#/settings`
      return '/chat'
    }
  },
  {
    path: '/settings/:pathMatch(.*)*',
    redirect: () => {
      window.location.href = `${getSLMAdminUrl()}/#/settings`
      return '/chat'
    }
  },
  {
    path: '/infrastructure',
    redirect: () => {
      window.location.href = `${getSLMAdminUrl()}/#/`
      return '/chat'
    }
  },
  {
    path: '/tls-certificates',
    redirect: () => {
      window.location.href = `${getSLMAdminUrl()}/#/security`
      return '/chat'
    }
  },
  // Issue #929: Plugin Manager UI
  {
    path: '/plugins',
    name: 'plugins',
    component: () => import('@/views/PluginsView.vue'),
    meta: {
      title: 'Plugin Manager',
      icon: 'fas fa-puzzle-piece',
      description: 'Browse, install, and manage AutoBot plugins',
      requiresAuth: true,
      hideInNav: true,
    },
    children: [
      // Issue #1803: Marketplace as sub-route of plugins
      {
        path: 'marketplace',
        name: 'plugins-marketplace',
        component: () => import('@/views/MarketplaceView.vue'),
        meta: {
          title: 'Marketplace',
          parent: 'plugins',
          requiresAuth: true
        }
      }
    ]
  },
  // Issue #1803: /marketplace redirects to /plugins/marketplace for backwards compatibility
  {
    path: '/marketplace',
    redirect: '/plugins/marketplace'
  },
  // GH#8250: LLC Company Portability — export template/snapshot, import preview + execute
  {
    path: '/llc/portability',
    name: 'llc-portability',
    component: () => import('@/views/llc/CompanyPortabilityView.vue'),
    meta: { title: 'Company Portability', requiresAuth: true, hideInNav: true },
  },
  // Issue #729: Secrets stays in autobot-vue - user functionality for chat/agent credentials
  {
    path: '/secrets',
    name: 'secrets',
    component: () => import('@/views/SecretsView.vue'),
    meta: {
      title: 'Secrets Manager',
      icon: 'fas fa-key',
      description: 'Manage API keys and secrets for chat and agent access',
      requiresAuth: true,
      hideInNav: true,
    },
    children: [
      {
        path: '',
        name: 'secrets-manager',
        component: () => import('@/components/security/SecretsManager.vue'),
        meta: {
          title: 'Secrets Manager',
          hideInNav: true
        }
      }
    ]
  },
  // Issue #8247: LLC Phase 6 — Company Dashboard, Org Chart, Goal Tree, Sub-Company Tree
  // GH#9627: Company selector — entry point for the Company OS nav item
  {
    path: '/llc/select-company',
    name: 'llc-company-select',
    component: () => import('@/views/llc/CompanySelectorView.vue'),
    meta: { title: 'Select Company', requiresAuth: true, llcScope: true },
  },
  {
    path: '/llc/dashboard',
    name: 'llc-dashboard',
    component: () => import('@/views/llc/CompanyDashboard.vue'),
    // hideInNav (GH#9627): reached from the company selector / LLC sidebar
    meta: { title: 'Company Dashboard', requiresAuth: true, llcScope: true, hideInNav: true },
  },
  {
    path: '/llc/org-chart',
    name: 'llc-org-chart',
    component: () => import('@/views/llc/OrgChart.vue'),
    meta: { title: 'Org Chart', requiresAuth: true, llcScope: true, hideInNav: true },
  },
  {
    path: '/llc/goals',
    name: 'llc-goals',
    component: () => import('@/views/llc/GoalTree.vue'),
    meta: { title: 'Goal Tree', requiresAuth: true, llcScope: true, hideInNav: true },
  },
  {
    path: '/llc/companies',
    name: 'llc-companies',
    component: () => import('@/views/llc/SubCompanyTree.vue'),
    meta: { title: 'Company Hierarchy', requiresAuth: true, llcScope: true, hideInNav: true },
  },
  // GH#9164: Company Creation Wizard with Template Browser
  {
    path: '/llc/companies/create',
    name: 'llc-company-create',
    component: () => import('@/views/llc/CompanyCreationWizard.vue'),
    meta: { title: 'Create Company', requiresAuth: true, llcScope: true, hideInNav: true, hideFooter: true },
  },
  // Issue #4465: Usage moved under /analytics/usage
  { path: '/usage', redirect: '/analytics/usage' },
  {
    path: '/permission-denied',
    name: 'permission-denied',
    component: PermissionDeniedView,
    meta: {
      title: 'Permission Denied',
      hideInNav: true,
      requiresAuth: false,
      isPublic: true
    }
  },
  // GH#9627: company-scoped LLC routes share the LlcCompanyLayout (contextual
  // sidebar) and the llcCompanyParamGuard (missing companyId → selector).
  // Children: GH#8248 (backlog/sprint/kanban) + GH#8249/GH#8550 (modules).
  {
    path: '/llc/companies/:companyId',
    component: () => import('@/views/llc/LlcCompanyLayout.vue'),
    beforeEnter: llcCompanyParamGuard,
    meta: { requiresAuth: true, llcScope: true, hideInNav: true },
    children: [
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
      { path: 'ceo-chat', name: 'llc-ceo-chat', component: () => import('@/views/llc/CeoChatView.vue'), props: true, meta: { title: 'CEO Chat', requiresAuth: true } },
    ],
  },
  // Issue #9044: Transcriber — audio/video transcription module
  {
    path: '/transcriber',
    component: () => import('@/views/transcriber/TranscriberLayout.vue'),
    meta: { requiresAuth: true, title: 'Transcriber' },
    children: [
      {
        path: '',
        name: 'transcriber-projects',
        component: () => import('@/views/transcriber/ProjectsView.vue'),
        meta: { title: 'Projects' },
      },
      {
        path: 'projects/:projectId',
        name: 'transcriber-project-detail',
        component: () => import('@/views/transcriber/ProjectDetailView.vue'),
        meta: { title: 'Project' },
      },
      {
        path: 'projects/:projectId/recordings/:recordingId',
        name: 'transcriber-transcript',
        component: () => import('@/views/transcriber/TranscriptView.vue'),
        meta: { title: 'Transcript' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: NotFoundView,
    meta: {
      title: 'Page Not Found',
      hideInNav: true
    }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // Restore scroll position when navigating back
    if (savedPosition) {
      return savedPosition
    }
    // Scroll to top for new pages
    if (to.hash) {
      return { el: to.hash, behavior: 'smooth' }
    }
    return { top: 0, behavior: 'smooth' }
  }
})

// Enhanced error handling for routing failures
router.onError((error) => {
  logger.error('Navigation error:', error)

  // Handle chunk loading failures with enhanced error recovery
  if (error.message.includes('Loading chunk') ||
      error.message.includes('Loading CSS chunk') ||
      error.message.includes('ChunkLoadError')) {

    logger.warn('Chunk loading failed, attempting recovery...', {
      error: error.message,
      url: window.location.href,
      timestamp: new Date().toISOString()
    })

    // Track chunk loading failures
    if (window.rum) {
      window.rum.trackError('router_chunk_load_failed', {
        message: error.message,
        stack: error.stack,
        url: window.location.href,
        userAgent: navigator.userAgent,
        timestamp: new Date().toISOString()
      })
    }

    // Enhanced recovery strategy
    const handleChunkError = () => {
      const reloadAttempted = sessionStorage.getItem('chunk-reload-attempted')
      const reloadCount = parseInt(sessionStorage.getItem('chunk-reload-count') || '0', 10)

      if (!reloadAttempted && reloadCount < 2) {
        // First attempt: Try page reload
        sessionStorage.setItem('chunk-reload-attempted', 'true')
        sessionStorage.setItem('chunk-reload-count', (reloadCount + 1).toString())

        logger.debug('Attempting page reload for chunk recovery...')

        // Clear service worker cache if available
        if ('serviceWorker' in navigator) {
          navigator.serviceWorker.getRegistrations().then(registrations => {
            registrations.forEach(registration => registration.unregister())
          }).finally(() => {
            window.location.reload()
          })
        } else {
          window.location.reload()
        }
      } else {
        // Fallback: Navigate to safe route
        logger.debug('Max reload attempts reached, navigating to fallback route...')
        sessionStorage.removeItem('chunk-reload-attempted')
        sessionStorage.removeItem('chunk-reload-count')

        router.push('/chat').catch((fallbackError) => {
          logger.error('Failed to navigate to fallback route, hard redirect:', fallbackError)
          window.location.href = '/chat'
        })
      }
    }

    handleChunkError()
  } else {
    // Handle other router errors
    logger.error('Non-chunk error occurred:', error)

    if (window.rum) {
      window.rum.trackError('router_navigation_error', {
        message: error.message,
        stack: error.stack,
        url: window.location.href
      })
    }
  }
})

// Global navigation guards with enhanced error handling
// Issue #2676: Migrated from next() callback to return-value pattern (vue-router v5)
router.beforeEach(async (to, from) => {
  try {
    const appStore = useAppStore()
    const userStore = useUserStore()

    logger.debug('Navigating to:', to.path)
    logger.debug('Route matched:', to.matched.length > 0)

    // Clear chunk reload flags on successful navigation
    if (to.matched.length > 0) {
      sessionStorage.removeItem('chunk-reload-attempted')
      sessionStorage.removeItem('chunk-reload-count')
    }

    // Initialize user store from storage if not already done
    if (!userStore.isAuthenticated) {
      userStore.initializeFromStorage()
    }

    // Check authentication requirements
    const requiresAuth = to.matched.some(record => record.meta.requiresAuth === true)

    // If route requires auth and user not authenticated, try backend check first
    // This handles single_user mode where backend auto-authenticates
    if (requiresAuth && !userStore.isAuthenticated) {
      logger.debug('Route requires auth, checking backend for auto-auth (single_user mode)')
      const backendAuthenticated = await userStore.checkAuthFromBackend()
      if (backendAuthenticated) {
        logger.debug('Backend auto-authenticated user (single_user mode)')
        // Continue to route - user is now authenticated
        return
      }
    }

    if (requiresAuth && !userStore.isAuthenticated) {
      logger.debug('Authentication required, redirecting to login')

      // Track authentication redirect
      if (window.rum) {
        window.rum.trackUserInteraction('auth_redirect', null, {
          from: from.path,
          to: to.path,
          reason: 'authentication_required'
        })
      }

      // Redirect to login (no redirect param -- clean URL)
      return { name: 'login' }
    }

    // Block admin-only routes for non-admin users
    const requiresAdmin = to.matched.some(record => record.meta.admin === true)
    if (requiresAdmin && userStore.isAuthenticated && !userStore.isAdmin) {
      logger.debug('Admin route blocked for non-admin user, redirecting to home')
      return { path: '/home' }
    }

    // If user is authenticated and trying to access login page, redirect to home
    if (to.name === 'login' && userStore.isAuthenticated) {
      logger.debug('User already authenticated, redirecting to home')
      return { path: '/home' }
    }

    // Onboarding redirect (#6452) — first-login users with no preset applied get
    // routed to /onboarding. Skip for: the onboarding route itself, public routes,
    // and unauthenticated traffic (already handled above).
    // sessionStorage cache avoids hitting /api/onboarding/status on every nav —
    // one fetch per browser session is enough; OnboardingWizard clears it on
    // successful preset apply so the next nav re-checks.
    if (
      userStore.isAuthenticated &&
      requiresAuth &&
      to.path !== '/onboarding' &&
      !to.matched.some(record => record.meta.isPublic === true)
    ) {
      let presetApplied = sessionStorage.getItem('onboarding_preset_applied')
      if (presetApplied === null) {
        try {
          const resp = await fetch(`${getBackendUrl()}/api/onboarding/status`, {
            credentials: 'include',
            headers: { Accept: 'application/json' },
          })
          if (resp.ok) {
            const data = await resp.json()
            presetApplied = data?.preset_applied ? '1' : '0'
            sessionStorage.setItem('onboarding_preset_applied', presetApplied)
          } else {
            // Fail-open on non-2xx — don't trap users in onboarding.
            presetApplied = '1'
          }
        } catch (statusErr) {
          // Fail-open on network error — don't trap users in onboarding.
          logger.debug('Onboarding status check failed, continuing:', statusErr)
          presetApplied = '1'
        }
      }
      if (presetApplied === '0') {
        logger.debug('Onboarding not complete — redirecting to /onboarding')
        return { path: '/onboarding' }
      }
    }

    // Check for expired tokens
    if (userStore.isAuthenticated && userStore.isTokenExpired) {
      logger.debug('Token expired, logging out user')
      userStore.logout()

      // If the route requires auth, redirect to login
      if (requiresAuth) {
        return { name: 'login' }
      }
    }

    // Update document title
    if (to.meta.title) {
      document.title = `${to.meta.title} - AutoBot Pro`
    }

    // Update active tab in store (with null safety)
    // Issue #729: Updated valid tabs for business-only routes
    if (to.name && typeof to.name === 'string' && appStore && typeof appStore.updateRoute === 'function') {
      const tabName = to.name.split('-')[0] // Extract main section
      const validTabs = ['chat', 'knowledge', 'automation', 'analytics'] as const
      type ValidTab = typeof validTabs[number]

      if ((validTabs as readonly string[]).includes(tabName)) {
        appStore.updateRoute(tabName as ValidTab)
      }
    }

    // Track navigation attempt
    if (window.rum) {
      window.rum.trackUserInteraction('route_navigation_start', null, {
        from: from.path,
        to: to.path,
        routeName: to.name?.toString(),
        authenticated: userStore.isAuthenticated,
        requiresAuth: requiresAuth
      })
    }

    // Continue navigation (returning undefined allows navigation to proceed)

  } catch (error: unknown) {
    logger.error('Navigation guard error:', error)

    // Issue #156 Fix: Type guard for error handling
    const errorMessage = error instanceof Error ? error.message : String(error)
    const errorStack = error instanceof Error ? error.stack : undefined

    if (window.rum) {
      window.rum.trackError('navigation_guard_error', {
        message: errorMessage,
        stack: errorStack,
        from: from.path,
        to: to.path
      })
    }

    // Even on error, continue navigation to prevent blocking
    // (returning undefined allows navigation to proceed)
  }
})

router.afterEach((to, from) => {
  // Track successful page views for analytics
  if (window.rum) {
    window.rum.trackUserInteraction('page_view', null, {
      page: to.path,
      title: to.meta.title,
      from: from.path,
      routeName: to.name?.toString()
    })
  }

  // Log successful navigation
  logger.debug('Successfully navigated to:', to.path)
})

// Route helper functions
export const getMainRoutes = () => {
  return routes.filter(route =>
    !route.meta?.hideInNav &&
    route.path !== '/' &&
    !route.path.includes('*') &&
    !route.redirect // Issue #729: Exclude redirect routes
  )
}

export const getBreadcrumbs = (route: RouteLocationNormalized) => {
  const breadcrumbs = []

  if (route.meta?.parent) {
    const parentRoute = routes.find(r => r.name === route.meta.parent)
    if (parentRoute) {
      breadcrumbs.push({
        name: parentRoute.meta?.title,
        path: parentRoute.path
      })
    }
  }

  breadcrumbs.push({
    name: route.meta?.title || route.name,
    path: route.path
  })

  return breadcrumbs
}

export default router
