// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #21037: every knowledge view that renders a fact title shows a man-page fact
 * as "<command>, section <N>: <name>". Each payload below has the shape the
 * backend sends to that view, so a call site reading a field the backend never
 * fills would render the raw "man gettext(1)" and fail here.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import TreeNodeComponent from '../TreeNodeComponent.vue'
import KnowledgeContentViewer from '../KnowledgeContentViewer.vue'
import KBSearchResultPanel from '../KBSearchResultPanel.vue'
import KnowledgeEntries from '../KnowledgeEntries.vue'
import { KnowledgeRepository, knowledgeRepository } from '@/models/repositories/KnowledgeRepository'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

// Control locale: distinct from en.json, so a hard-coded label cannot pass.
const i18n = () =>
  createI18n({
    legacy: false,
    locale: 'ctl',
    missingWarn: false,
    fallbackWarn: false,
    messages: { ctl: { knowledge: { manSection: { format: 'CMD={name} SEC={section} NAME={sectionName}', '1': 'ctl-user' } } } },
  })
const SHOWN = 'CMD=gettext SEC=1 NAME=ctl-user'
const RAW = 'man gettext(1)'

/** Stored metadata of a man-page fact, as `ManPageContent.get_metadata_for_storage` writes it. */
const FACT_META = { type: 'man_page', command: 'gettext', section: '1', title: RAW, category: 'system_commands', source: 'man_page_parser' }
/** A `POST /knowledge_base/search` hit. */
const SEARCH_HIT = { content: 'GETTEXT(1)', metadata: { ...FACT_META, fact_id: 'f1' }, score: 0.9, node_id: 'n1' }
/** Tree node from `GET /facts/by_category` (KnowledgeBrowser `buildNestedTree`: fact metadata, flat). */
const BROWSE_NODE = { id: 'f1', name: RAW, type: 'file' as const, path: `/system_commands/${RAW}`, metadata: { ...FACT_META, key: 'fact:f1' } }
/** Tree node lazy-loaded from `POST /search` (KnowledgeBrowser `loadFolderContents`: the whole hit). */
const FOLDER_NODE = { id: 'file-x-0', name: RAW, type: 'file' as const, path: `/system_commands/${RAW}`, metadata: SEARCH_HIT }

const treeNode = (node: object) =>
  mount(TreeNodeComponent, {
    props: { node, expandedNodes: new Set<string>(), selectedDocuments: new Set<string>(), vectorizationStates: new Map() },
    global: { plugins: [i18n()], stubs: { Icon: true, VectorizationStatusBadge: true } },
  })

const viewer = (selectedFile: object) =>
  mount(KnowledgeContentViewer, { props: { selectedFile, content: '' }, global: { plugins: [i18n()], stubs: { Icon: true } } })

afterEach(() => vi.restoreAllMocks())

describe('man-page titles at each call site (#21037)', () => {
  it('TreeNodeComponent: a browse node and a folder-search node', () => {
    expect(treeNode(BROWSE_NODE).find('.node-name-btn').text()).toBe(SHOWN)
    expect(treeNode(FOLDER_NODE).find('.node-name-btn').text()).toBe(SHOWN)
    const plain = { ...BROWSE_NODE, name: 'gettext(1)', metadata: { type: 'document', key: 'fact:f2' } }
    expect(treeNode(plain).find('.node-name-btn').text()).toBe('gettext(1)')
  })

  it('KnowledgeContentViewer: a browse node and a folder-search node', () => {
    expect(viewer(BROWSE_NODE).find('h4').text()).toBe(SHOWN)
    expect(viewer(FOLDER_NODE).find('h4').text()).toBe(SHOWN)
  })

  it('KBSearchResultPanel: results mapped from a backend search payload', async () => {
    const repository = new KnowledgeRepository()
    vi.spyOn(repository, 'post').mockResolvedValue({ data: { results: [SEARCH_HIT] } } as never)
    const results = await repository.searchKnowledge({ query: 'gettext' })
    const panel = mount(KBSearchResultPanel, {
      props: { results, query: 'gettext', loading: false, repository },
      global: { plugins: [i18n()], stubs: { Icon: true } },
    })
    expect(panel.find('.result-title').text()).toBe(SHOWN)
  })

  it('KnowledgeEntries: entries loaded from GET /entries; the stored title stays raw', async () => {
    // `_format_knowledge_entry` shape: the controller maps it into the store.
    const entry = { id: 'f1', content: 'GETTEXT(1)', title: RAW, source: 'man_page_parser', category: 'system_commands', type: 'man_page', metadata: FACT_META }
    vi.spyOn(knowledgeRepository, 'get').mockImplementation(async (url: string) =>
      ({ data: url.includes('/entries') ? { entries: [entry], total: 1 } : {} }) as never,
    )
    const pinia = createPinia()
    const wrapper = mount(KnowledgeEntries, { global: { plugins: [pinia, i18n()] } })
    await flushPromises()
    expect(wrapper.find('.entry-title').text()).toBe(SHOWN)
    expect(useKnowledgeStore(pinia).documents.map(d => d.title)).toEqual([RAW])
  })
})
