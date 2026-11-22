// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** KBSearchResultPanel (#3296 / #18244): ranked list, keyboard navigation, the document pane beside it. */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import KBSearchResultPanel from '../KBSearchResultPanel.vue'

beforeAll(() => {
  // jsdom has no layout, so no scrollIntoView
  Element.prototype.scrollIntoView = vi.fn()
})

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const hit = (id: string, title: string, score: number, content = 'body text') => ({
  score,
  highlights: [`about ${title}`],
  document: { id, title, content, category: 'docs', type: 'text', metadata: {} },
})
const RESULTS = [hit('1', 'Alpha', 0.9), hit('2', 'Beta', 0.65)]

const mountPanel = (props: Record<string, unknown> = {}) => {
  const repository = { getDocument: vi.fn().mockResolvedValue({ content: 'the full alpha document' }) }
  const w = mount(KBSearchResultPanel, {
    props: { results: RESULTS as never, query: 'alpha', loading: false, repository: repository as never, ...props },
    global: { plugins: [i18n] },
  })
  return { w, repository }
}

describe('KBSearchResultPanel', () => {
  it('lists the ranked hits with title, score and a highlighted snippet', () => {
    const { w } = mountPanel()
    expect(w.findAll('[role="option"]')).toHaveLength(2)
    expect(w.findAll('.result-title').map((t) => t.text())).toEqual(['Alpha', 'Beta'])
    expect(w.text()).toContain('90%')
    expect(w.get('.result-snippet').html()).toContain('<mark class="kb-highlight">Alpha</mark>')
  })

  it('arrow keys move the selection; Enter emits select; Escape emits close', async () => {
    const { w } = mountPanel()
    const root = w.get('[role="region"]')
    await root.trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(w.findAll('[role="option"]')[0].attributes('aria-selected')).toBe('true')
    await root.trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(w.findAll('[role="option"]')[1].attributes('aria-selected')).toBe('true')
    await root.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('select')!.length).toBeGreaterThanOrEqual(1)
    await root.trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('selecting a short hit fetches the full document and shows it in the pane', async () => {
    const { w, repository } = mountPanel()
    await w.findAll('[role="option"]')[0].trigger('click')
    await flushPromises()
    expect(repository.getDocument).toHaveBeenCalledWith('1')
    expect(w.get('.viewer-content').text()).toBe('the full alpha document')
  })

  it('shows the empty message with the query, and the close button emits close', async () => {
    const { w } = mountPanel({ results: [] })
    expect(w.get('.empty-state').text()).toContain('No results for "alpha"')
    await w.get('button[aria-label="Close search results"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('shows the loading skeleton while searching', () => {
    const { w } = mountPanel({ loading: true })
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    expect(w.text()).toContain('Searching…')
  })
})
