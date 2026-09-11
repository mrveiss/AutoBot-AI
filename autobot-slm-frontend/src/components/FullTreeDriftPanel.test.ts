// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16310 owner requirement (11 Sep 2026): "We need to have drift check for
 * all the files." Proves FullTreeDriftPanel renders all three verdict kinds
 * the report can carry -- `removed_from_source` (+ commit), `build_bundle`
 * (count), and `host_state:<category>` (count) -- and that the verdict
 * filter narrows what is shown without losing data.
 *
 * #16310 review round 6, item 4: also proves the panel's error state is
 * ISOLATED from the rest of the page -- it reads `fullTreeDriftError`
 * (dedicated), never the composable's shared `error` (written by every
 * other useCodeSync method), so an unrelated page failure never shows up
 * here and a genuine drift-fetch failure is never silently displaced by an
 * unrelated success elsewhere clearing the shared ref.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import FullTreeDriftPanel from './FullTreeDriftPanel.vue'
import en from '@/locales/en.json'
import type { FullTreeDriftReport } from '@/composables/useCodeSync'

const fetchFullTreeDrift = vi.fn()
const reportRef = ref<FullTreeDriftReport | null>(null)
// The composable's PAGE-WIDE error -- other methods (fetchStatus, syncNode,
// ...) write this. The panel must never read it.
const pageErrorRef = ref<string | null>(null)
// The panel's OWN, dedicated error -- only fetchFullTreeDrift's catch writes it.
const fullTreeDriftErrorRef = ref<string | null>(null)

vi.mock('@/composables/useCodeSync', () => ({
  useCodeSync: () => ({
    error: pageErrorRef,
    fullTreeDriftReport: reportRef,
    fullTreeDriftError: fullTreeDriftErrorRef,
    fetchFullTreeDrift,
  }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const REPORT: FullTreeDriftReport = {
  components: [
    {
      component: 'autobot-backend',
      compared: 120,
      drifted: [
        { path: 'utils/old_module.py', verdict: 'removed_from_source', detail: '3fc18e79a123' },
        { path: 'config/settings.py', verdict: 'modified', detail: null },
      ],
      exclusions: { build_bundle: 3, 'host_state:data': 2 },
      error: null,
      skipped: false,
    },
    {
      component: 'autobot-frontend',
      compared: 0,
      drifted: [],
      exclusions: {},
      error: null,
      skipped: true,
    },
  ],
  total_compared: 120,
  total_drift: 2,
  exclusions: { build_bundle: 3, 'host_state:data': 2 },
  checked_at: '2026-09-11T12:00:00Z',
  errors: [],
}

function mountPanel() {
  return mount(FullTreeDriftPanel, { global: { plugins: [i18n] } })
}

describe('FullTreeDriftPanel (#16310)', () => {
  it('calls fetchFullTreeDrift when "Check All Files" is clicked', async () => {
    reportRef.value = null
    const wrapper = mountPanel()
    await wrapper.find('button').trigger('click')
    expect(fetchFullTreeDrift).toHaveBeenCalledTimes(1)
  })

  it('shows the no-report placeholder before any check has run', () => {
    reportRef.value = null
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('No report yet')
  })

  it('renders all three verdict kinds from one report', () => {
    reportRef.value = REPORT
    const wrapper = mountPanel()
    const text = wrapper.text()

    // removed_from_source: path + commit detail
    expect(text).toContain('utils/old_module.py')
    expect(text).toContain('3fc18e79a123')

    // modified: path only
    expect(text).toContain('config/settings.py')

    // build_bundle: aggregate count, not a per-file list
    expect(text).toContain('3 build bundle file')

    // host_state:<category>: aggregate count, category name verbatim
    expect(text).toContain('host_state:data')
    expect(text).toContain('2 file')

    // a skipped component is reported, not silently omitted
    expect(text).toContain('autobot-frontend')
    expect(text).toContain('Not deployed on this host')
  })

  it('the "Removed from source" filter hides the modified-file group', async () => {
    reportRef.value = REPORT
    const wrapper = mountPanel()

    const removedButton = wrapper
      .findAll('button')
      .find((btn) => btn.text() === 'Removed from source')
    expect(removedButton).toBeTruthy()
    await removedButton!.trigger('click')

    expect(wrapper.text()).toContain('utils/old_module.py')
    expect(wrapper.text()).not.toContain('config/settings.py')
  })

  it('shows its own error on a failed fetch, never the page-wide error', () => {
    reportRef.value = null
    pageErrorRef.value = 'an unrelated page error (e.g. syncNode failed)'
    fullTreeDriftErrorRef.value = null
    const wrapper = mountPanel()

    // An unrelated page-wide failure must not surface on this panel.
    expect(wrapper.text()).not.toContain('an unrelated page error')

    pageErrorRef.value = null
  })

  it('shows its own error on a failed fetch, and no stale "no drift" report', () => {
    reportRef.value = null
    fullTreeDriftErrorRef.value = 'Failed to fetch full-tree drift report'
    const wrapper = mountPanel()

    expect(wrapper.text()).toContain('Failed to fetch full-tree drift report')
    // report is still null (the fetch never succeeded) -- must not render
    // any per-component "No drift" verdict as if a check had completed.
    expect(wrapper.text()).not.toContain('No drift')

    fullTreeDriftErrorRef.value = null
  })
})
