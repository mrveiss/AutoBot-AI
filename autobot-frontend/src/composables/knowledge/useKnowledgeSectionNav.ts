// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The Knowledge sub-navigation (#18244, Refined UI): one typed list in the mockup's order.
 * Whether an item is advanced (`meta.adv`, hidden in Minimal mode by the shared `.adv` rule)
 * and admin-only (`meta.admin`, #16666) is read from its route, so the router is the one
 * place that says so; the active item is derived from the route.
 *
 * Transcriber and Health stay until their new homes exist (owner decision D1); Health is
 * advanced-only. `onAdvancedArea` says the open page is an advanced one, so the shell can show
 * the "advanced area" notice when Minimal mode is on.
 */
import { computed, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { SectionNavSection, SectionNavItem } from '@autobot/ui'
import type { IconName } from '@/components/ui/Icon.vue'

const WEB_TOOLS_TAB = 'webTools'

interface NavDef {
  id: string
  to: string
  label: string
  aria: string
  /** True when the current route belongs to this item. */
  active: (route: { name?: unknown; path: string; query: Record<string, unknown> }) => boolean
}

/** The icon of each item, by id (the view draws it in SectionNav's icon slot). */
export const KNOWLEDGE_NAV_ICONS: Record<string, IconName> = {
  browser: 'folder', graph: 'project-diagram', vectorStore: 'cube', research: 'search', mcpResources: 'file-alt',
  systemDocs: 'bookmark', transcriber: 'microphone', manage: 'list', entities: 'user', health: 'heartbeat', webResearch: 'globe',
}

const byName = (name: string) => (r: { name?: unknown }) => r.name === name
const byPrefix = (prefix: string) => (r: { path: string }) => r.path.startsWith(prefix)

/** The items, section by section; labels are looked up by the caller. */
function definitions(): Record<'browse' | 'manage' | 'research', Omit<NavDef, 'label' | 'aria'>[]> {
  const base = {
    browse: [
      { id: 'browser', to: '/knowledge/browser', active: byName('knowledge-browser') },
      { id: 'graph', to: '/knowledge/graph', active: byPrefix('/knowledge/graph') },
      { id: 'vectorStore', to: '/knowledge/vector-store', active: byName('knowledge-vector-store') },
      {
        id: 'research', to: '/knowledge/research',
        active: (r: { name?: unknown; query: Record<string, unknown> }) => r.name === 'knowledge-research' && r.query.tab !== WEB_TOOLS_TAB,
      },
      { id: 'mcpResources', to: '/knowledge/mcp-resources', active: byName('knowledge-mcp-resources') },
      { id: 'systemDocs', to: '/knowledge/system-docs', active: byName('knowledge-system-docs') },
      { id: 'transcriber', to: '/knowledge/transcriber', active: byPrefix('/knowledge/transcriber') },
    ],
    manage: [
      { id: 'manage', to: '/knowledge/manage', active: byName('knowledge-manage') },
      { id: 'entities', to: '/knowledge/entities', active: byName('knowledge-entities') },
      { id: 'health', to: '/knowledge/health', active: byName('knowledge-health') },
    ],
    research: [
      {
        id: 'webResearch', to: `/knowledge/research?tab=${WEB_TOOLS_TAB}`,
        active: (r: { name?: unknown; query: Record<string, unknown> }) => r.name === 'knowledge-research' && r.query.tab === WEB_TOOLS_TAB,
      },
    ],
  }
  return base as Record<'browse' | 'manage' | 'research', Omit<NavDef, 'label' | 'aria'>[]>
}

export function useKnowledgeSectionNav(isAdmin: ComputedRef<boolean> | { value: boolean }) {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()

  const label = (id: string) =>
    ({
      browser: t('knowledge.views.browser'), graph: t('knowledge.views.graph'), vectorStore: t('knowledge.views.vectorStore'),
      research: t('knowledge.views.research'), mcpResources: t('knowledge.views.mcpResources'), systemDocs: t('knowledge.views.systemDocs'),
      transcriber: t('nav.transcriber'), manage: t('knowledge.views.manage'), entities: t('knowledge.views.entities'),
      health: t('knowledge.views.health'), webResearch: t('knowledge.views.webResearch'),
    })[id] ?? id

  const aria = (id: string) =>
    ({
      browser: t('knowledge.views.browserAriaLabel'), graph: t('knowledge.views.graphAriaLabel'),
      vectorStore: t('knowledge.views.vectorStoreAriaLabel'), research: t('knowledge.views.researchAriaLabel'),
      mcpResources: t('knowledge.views.mcpResourcesAriaLabel'), systemDocs: t('knowledge.views.systemDocsAriaLabel'),
      transcriber: t('knowledge.views.transcriberAriaLabel'), manage: t('knowledge.views.manageAriaLabel'),
      entities: t('knowledge.views.entitiesAriaLabel'), health: t('knowledge.views.healthAriaLabel'),
      webResearch: t('knowledge.views.webResearchAriaLabel'),
    })[id]

  const defs = definitions()
  const metaOf = (d: NavDef) => router.resolve(d.to).meta
  const visible = (d: NavDef) => !metaOf(d).admin || isAdmin.value
  const all = computed<NavDef[]>(() =>
    Object.values(defs).flat().map((d) => ({ ...d, label: label(d.id), aria: aria(d.id) ?? '' })).filter(visible),
  )

  const toItem = (d: NavDef): SectionNavItem => ({
    id: d.id, label: d.label, to: d.to, ariaLabel: d.aria, adv: !!metaOf(d).adv, active: d.active(route),
  })

  const section = (id: keyof typeof defs, heading: string, adv = false): SectionNavSection => ({
    id, label: heading, adv,
    items: all.value.filter((d) => defs[id].some((x) => x.id === d.id)).map(toItem),
  })

  const sections = computed<SectionNavSection[]>(() => [
    section('browse', t('knowledge.views.browse')),
    section('manage', t('knowledge.views.manage')),
    section('research', t('knowledge.views.research'), true),
  ])

  /** The open page is an advanced one: a matched route (a graph child inherits its parent's) is `meta.adv`. */
  const onAdvancedArea = computed(() => route.matched.some((r) => r.meta.adv))

  return { sections, onAdvancedArea }
}
