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
  active: (route: RouteLike) => boolean
}

/** The icon of each item, by id (the view draws it in SectionNav's icon slot). */
export const KNOWLEDGE_NAV_ICONS: Record<string, IconName> = {
  browser: 'folder', graph: 'project-diagram', vectorStore: 'cube', research: 'search', mcpResources: 'file-alt',
  systemDocs: 'bookmark', transcriber: 'microphone', manage: 'list', entities: 'user', health: 'heartbeat', webResearch: 'globe',
}

const byName = (name: string) => (r: { name?: unknown }) => r.name === name
const byPrefix = (prefix: string) => (r: { path: string }) => r.path.startsWith(prefix)

type SectionId = 'browse' | 'manage' | 'research'
type BareDef = Omit<NavDef, 'label' | 'aria'>
type RouteLike = { name?: unknown; path: string; query: Record<string, unknown> }

const researchTab = (onWebTools: boolean) => (r: RouteLike) => (r.query.tab === WEB_TOOLS_TAB) === onWebTools

const browseDefs = (): BareDef[] => [
  { id: 'browser', to: '/knowledge/browser', active: byName('knowledge-browser') },
  { id: 'graph', to: '/knowledge/graph', active: byPrefix('/knowledge/graph') },
  { id: 'vectorStore', to: '/knowledge/vector-store', active: byName('knowledge-vector-store') },
  { id: 'research', to: '/knowledge/research', active: (r) => r.name === 'knowledge-research' && researchTab(false)(r) },
  { id: 'mcpResources', to: '/knowledge/mcp-resources', active: byName('knowledge-mcp-resources') },
  { id: 'systemDocs', to: '/knowledge/system-docs', active: byName('knowledge-system-docs') },
  { id: 'transcriber', to: '/knowledge/transcriber', active: byPrefix('/knowledge/transcriber') },
]

const manageDefs = (): BareDef[] => [
  { id: 'manage', to: '/knowledge/manage', active: byName('knowledge-manage') },
  { id: 'entities', to: '/knowledge/entities', active: byName('knowledge-entities') },
  { id: 'health', to: '/knowledge/health', active: byName('knowledge-health') },
]

const researchDefs = (): BareDef[] => [
  {
    id: 'webResearch', to: `/knowledge/research?tab=${WEB_TOOLS_TAB}`,
    active: (r) => r.name === 'knowledge-research' && researchTab(true)(r),
  },
]

/** The items, section by section; labels are looked up by the caller. */
function definitions(): Record<SectionId, BareDef[]> {
  return { browse: browseDefs(), manage: manageDefs(), research: researchDefs() }
}

type Translate = (key: string) => string

/** Visible label of each item, by id. */
function labelMap(t: Translate): Record<string, string> {
  return {
    browser: t('knowledge.views.browser'), graph: t('knowledge.views.graph'), vectorStore: t('knowledge.views.vectorStore'),
    research: t('knowledge.views.research'), mcpResources: t('knowledge.views.mcpResources'), systemDocs: t('knowledge.views.systemDocs'),
    transcriber: t('nav.transcriber'), manage: t('knowledge.views.manage'), entities: t('knowledge.views.entities'),
    health: t('knowledge.views.health'), webResearch: t('knowledge.views.webResearch'),
  }
}

/** Accessible name of each item, by id. */
function ariaMap(t: Translate): Record<string, string> {
  return {
    browser: t('knowledge.views.browserAriaLabel'), graph: t('knowledge.views.graphAriaLabel'),
    vectorStore: t('knowledge.views.vectorStoreAriaLabel'), research: t('knowledge.views.researchAriaLabel'),
    mcpResources: t('knowledge.views.mcpResourcesAriaLabel'), systemDocs: t('knowledge.views.systemDocsAriaLabel'),
    transcriber: t('knowledge.views.transcriberAriaLabel'), manage: t('knowledge.views.manageAriaLabel'),
    entities: t('knowledge.views.entitiesAriaLabel'), health: t('knowledge.views.healthAriaLabel'),
    webResearch: t('knowledge.views.webResearchAriaLabel'),
  }
}

/** Every item with its label and accessible name filled in. */
function labelled(defs: Record<SectionId, BareDef[]>, t: Translate): NavDef[] {
  const labels = labelMap(t)
  const arias = ariaMap(t)
  return Object.values(defs).flat().map((d) => ({ ...d, label: labels[d.id] ?? d.id, aria: arias[d.id] ?? '' }))
}

export function useKnowledgeSectionNav(isAdmin: ComputedRef<boolean> | { value: boolean }) {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const defs = definitions()
  const metaOf = (d: BareDef) => router.resolve(d.to).meta

  const all = computed<NavDef[]>(() => labelled(defs, t).filter((d) => !metaOf(d).admin || isAdmin.value))

  const toItem = (d: NavDef): SectionNavItem => ({
    id: d.id, label: d.label, to: d.to, ariaLabel: d.aria, adv: !!metaOf(d).adv, active: d.active(route),
  })

  const section = (id: SectionId, heading: string, adv = false): SectionNavSection => ({
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
