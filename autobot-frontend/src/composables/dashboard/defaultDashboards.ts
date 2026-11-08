// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Home dashboard defaults and new-dashboard templates (#18242). Pure data, no Vue.
 * Titles and names are i18n KEYS, stored as such on the server and translated at render,
 * so a stored default follows the reader's language; a title the user types stays as typed.
 */
import {
  i18nRef,
  spanFromLegacyWidth,
  type DashboardLayout,
  type DashboardWidget,
} from './dashboardLayoutModel'
import type { IconName } from '@/components/ui/Icon.vue'

export const DEFAULT_DASHBOARD_ID = 'default'

function widget(
  id: string,
  type: string,
  title: string,
  legacyWidth: number,
  height: number,
  props: Record<string, unknown> = {},
): DashboardWidget {
  return { id, type, title, span: spanFromLegacyWidth(legacyWidth), height, props }
}

export function defaultHomeWidgets(): DashboardWidget[] {
  return [
    widget('widget-1', 'system', i18nRef('views.customDashboard.widgetSystemMonitor'), 1, 350),
    widget('widget-2', 'heatmap', i18nRef('views.customDashboard.widgetHeatmap'), 2, 300, { height: 300 }),
    widget('widget-3', 'agents', i18nRef('views.customDashboard.widgetAgents'), 2, 400, { height: 400 }),
  ]
}

export function defaultHomeLayout(): DashboardLayout {
  const now = Date.now()
  return {
    dashboards: [
      { id: DEFAULT_DASHBOARD_ID, name: i18nRef('views.customDashboard.mainDashboard'), widgets: defaultHomeWidgets(), createdAt: now, updatedAt: now },
    ],
    activeId: DEFAULT_DASHBOARD_ID,
  }
}

export function templateWidgets(template: string): DashboardWidget[] {
  switch (template) {
    case 'monitoring':
      return [
        widget('w1', 'system', i18nRef('views.customDashboard.widgetSystemMonitor'), 1, 350),
        widget('w2', 'heatmap', i18nRef('views.customDashboard.widgetCpuHeatmap'), 2, 300, { height: 300, metric: 'cpu' }),
      ]
    case 'agents':
      return [widget('w1', 'agents', i18nRef('views.customDashboard.widgetAgents'), 3, 450, { height: 450 })]
    case 'workflows':
      return [widget('w1', 'workflow', i18nRef('views.customDashboard.widgetWorkflow'), 3, 500, { height: 500 })]
    default:
      return []
  }
}

/** A widget kind the palette offers; names and descriptions are i18n keys. */
export interface WidgetDefinitionSpec {
  type: string
  nameKey: string
  descriptionKey: string
  icon: IconName
  defaultSpan: DashboardWidget['span']
  defaultHeight: number
  defaultProps: Record<string, unknown>
}

const K = 'views.customDashboard.'

export const WIDGET_DEFINITIONS: WidgetDefinitionSpec[] = [
  { type: 'heatmap', nameKey: `${K}widgetHeatmap`, descriptionKey: `${K}widgetHeatmapDesc`, icon: 'th-large', defaultSpan: 8, defaultHeight: 300, defaultProps: { height: 300, metric: 'cpu' } },
  { type: 'workflow', nameKey: `${K}widgetWorkflow`, descriptionKey: `${K}widgetWorkflowDesc`, icon: 'project-diagram', defaultSpan: 8, defaultHeight: 400, defaultProps: { height: 400 } },
  { type: 'agents', nameKey: `${K}widgetAgents`, descriptionKey: `${K}widgetAgentsDesc`, icon: 'robot', defaultSpan: 8, defaultHeight: 400, defaultProps: { height: 400 } },
  { type: 'architecture', nameKey: `${K}widgetArchitecture`, descriptionKey: `${K}widgetArchitectureDesc`, icon: 'sitemap', defaultSpan: 12, defaultHeight: 500, defaultProps: { height: 500 } },
]
