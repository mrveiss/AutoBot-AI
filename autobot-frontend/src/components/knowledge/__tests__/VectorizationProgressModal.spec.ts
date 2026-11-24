// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** VectorizationProgressModal (#18244): the overall and per-document bars are the kit's BaseProgress. */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import VectorizationProgressModal from '../VectorizationProgressModal.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const states = (rows: Array<[string, string, number?]>) =>
  new Map(rows.map(([id, status, progress]) => [id, { documentId: id, name: `${id}.md`, status, progress }])) as never

const mountModal = (documentStates: never) =>
  mount(VectorizationProgressModal, {
    props: { show: true, documentStates },
    global: { plugins: [i18n], stubs: { teleport: true, BaseModal: { template: '<div><slot /><slot name="actions" /></div>' } } },
  })

describe('VectorizationProgressModal', () => {
  it('shows the overall bar as a progressbar at the completed share', () => {
    const w = mountModal(states([['a', 'vectorized'], ['b', 'pending', 40], ['c', 'failed']]))
    const bars = w.findAll('[role="progressbar"]')
    expect(bars[0].attributes('aria-label')).toBe(en.knowledge.vectorization.overallProgress)
    expect(Number(bars[0].attributes('aria-valuenow'))).toBeCloseTo(33.33, 1)
  })

  it('draws a per-document bar only for a pending document that reports progress', () => {
    const w = mountModal(states([['a', 'pending', 40], ['b', 'pending']]))
    const bars = w.findAll('[role="progressbar"]')
    expect(bars).toHaveLength(2)
    expect(bars[1].attributes('aria-valuenow')).toBe('40')
  })

  it('offers Retry for failures and Cancel while running, and Done when all complete', async () => {
    const running = mountModal(states([['a', 'failed'], ['b', 'pending', 10]]))
    const labels = running.findAll('button').map((b) => b.text())
    expect(labels).toContain(en.knowledge.vectorization.retryFailed)
    expect(labels).toContain(en.knowledge.vectorization.cancelButton)
    await running.findAll('button').find((b) => b.text() === en.knowledge.vectorization.retryFailed)!.trigger('click')
    expect(running.emitted('retry-failed')).toHaveLength(1)
    const done = mountModal(states([['a', 'vectorized']]))
    expect(done.findAll('button').map((b) => b.text())).toEqual([en.knowledge.vectorization.done])
  })
})
