// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #22082: the panel previews, then confirms, the removal of the
 * `removed_from_source` files. Preview sends only the component; confirm sends
 * back exactly the previewed paths; nothing is removed until the operator
 * confirms; the drift report is re-run after a removal.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import FullTreeDriftPanel from './FullTreeDriftPanel.vue'
import en from '@/locales/en.json'
import type { FullTreeDriftReport } from '@/composables/useCodeSync'

const fetchFullTreeDrift = vi.fn()
const reportRef = ref<FullTreeDriftReport | null>(null)
const post = vi.fn()

vi.mock('@/composables/useCodeSync', () => ({
  useCodeSync: () => ({
    error: ref(null),
    fullTreeDriftReport: reportRef,
    fullTreeDriftError: ref(null),
    fetchFullTreeDrift,
  }),
}))
vi.mock('@/utils/ApiClient', () => ({ default: { call: (...args: unknown[]) => post(...args) } }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const REPORT: FullTreeDriftReport = {
  components: [
    {
      component: 'plugins',
      compared: 10,
      drifted: [{ path: 'core-plugins/x/plugin.py', verdict: 'removed_from_source', detail: 'abc' }],
      exclusions: {},
      error: null,
      skipped: false,
    },
  ],
  total_compared: 10,
  total_drift: 1,
  exclusions: {},
  checked_at: '2026-11-22T12:00:00Z',
  errors: [],
}

function mountPanel() {
  return mount(FullTreeDriftPanel, { global: { plugins: [i18n] } })
}

describe('FullTreeDriftPanel prune (#22082)', () => {
  beforeEach(() => {
    post.mockReset()
    fetchFullTreeDrift.mockReset()
    reportRef.value = REPORT
  })

  it('offers a preview, and removes nothing before the operator confirms', async () => {
    post.mockResolvedValueOnce({ component: 'plugins', files: [{ path: 'core-plugins/x/plugin.py', detail: 'abc' }] })
    const wrapper = mountPanel()

    await wrapper.find('[data-testid="drift-prune-preview"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('post', '/api/code-sync/drift/prune/preview', { body: { component: 'plugins' } })
    expect(wrapper.find('[data-testid="drift-prune-files"]').text()).toContain('core-plugins/x/plugin.py')
    expect(wrapper.find('[data-testid="drift-prune-confirm-button"]').exists()).toBe(true)
  })

  it('confirm sends exactly the previewed paths and re-runs the drift check', async () => {
    post
      .mockResolvedValueOnce({ component: 'plugins', files: [{ path: 'core-plugins/x/plugin.py', detail: 'abc' }] })
      .mockResolvedValueOnce({ component: 'plugins', removed: ['core-plugins/x/plugin.py'], refused: {}, failed: {} })
      .mockResolvedValueOnce({ component: 'plugins', files: [{ path: 'core-plugins/y/plugin.py', detail: 'def' }] })
    const wrapper = mountPanel()

    await wrapper.find('[data-testid="drift-prune-preview"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="drift-prune-confirm-button"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenNthCalledWith(2, 'post', '/api/code-sync/drift/prune', {
      body: { component: 'plugins', paths: ['core-plugins/x/plugin.py'] },
    })
    expect(fetchFullTreeDrift).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenNthCalledWith(3, 'post', '/api/code-sync/drift/prune/preview', { body: { component: 'plugins' } })
    expect(wrapper.find('[data-testid="drift-prune-files"]').text()).toContain('core-plugins/y/plugin.py')
    expect(wrapper.find('[data-testid="drift-prune-result"]').text()).toContain('Removed 1 file(s); 0 left in place')
  })

  it('reports a refused path instead of hiding it', async () => {
    post
      .mockResolvedValueOnce({ component: 'plugins', files: [{ path: 'core-plugins/x/plugin.py', detail: 'abc' }] })
      .mockResolvedValueOnce({
        component: 'plugins',
        removed: [],
        refused: { 'core-plugins/x/plugin.py': 'not removed_from_source (left untouched)' },
        failed: {},
      })
    const wrapper = mountPanel()

    await wrapper.find('[data-testid="drift-prune-preview"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="drift-prune-confirm-button"]').trigger('click')
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="drift-prune-confirm"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="drift-prune-result"]').text()).toContain('left untouched')
  })

  it('offers no prune action when nothing was removed from source', () => {
    reportRef.value = { ...REPORT, components: [{ ...REPORT.components[0], drifted: [] }] }
    const wrapper = mountPanel()
    expect(wrapper.find('[data-testid="drift-prune-preview"]').exists()).toBe(false)
  })
})
