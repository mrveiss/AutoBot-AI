// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * RunStateNotice: results of a run that did not finish are shown, labelled partial (#21003).
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { createDateFormatter } from '@/utils/formatHelpers'
import { RUN_STATE_KEY, type CodebaseRunState, type RunStateHandle } from '@/composables/analytics/useRunState'
import RunStateNotice from '../RunStateNotice.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const msg = en.analytics.codebase.runState

const run = (over: Partial<CodebaseRunState>): CodebaseRunState => ({
  run_id: 'r2',
  status: 'killed',
  partial: true,
  reason: 'killed by the hard timeout: run exceeded 1800s',
  started_at: '2026-11-01T14:25:50+00:00',
  finished_at: '2026-11-01T14:54:53+00:00',
  last_completed_at: '2026-10-30T09:00:00+00:00',
  ...over,
})

function render(value: CodebaseRunState | null) {
  const handle: RunStateHandle = { run: ref(value), applyRunFields: () => {}, loadRunState: async () => {} }
  return mount(RunStateNotice, { global: { plugins: [i18n], provide: { [RUN_STATE_KEY as symbol]: handle } } })
}

describe('RunStateNotice (#21003)', () => {
  it('a killed run: says it did not finish, why, that the findings are partial, and the last completed run', () => {
    const text = render(run({})).text()
    const when = createDateFormatter({ locale: () => 'en' })('2026-10-30T09:00:00+00:00')
    expect(text).toContain(msg.partialTitle)
    expect(text).toContain('killed by the hard timeout: run exceeded 1800s')
    expect(text).toContain(msg.partialFindings)
    expect(text).toContain(msg.lastCompleted.replace('{when}', when))
  })

  it('a first run that never completed says no run has completed', () => {
    const text = render(run({ status: 'failed', reason: '', last_completed_at: '' })).text()
    expect(text).toContain(msg.neverCompleted)
    expect(text).not.toContain(msg.lastCompleted.split('{')[0])
  })

  it('a running run is called updating, never a failure', () => {
    const text = render(run({ status: 'running', reason: '', finished_at: '' })).text()
    expect(text).toContain(msg.runningTitle)
    expect(text).toContain(msg.running)
    expect(text).not.toContain(msg.partialTitle)
    expect(text).not.toContain(msg.partialFindings)
  })

  it('shows nothing for a completed run, for no run record, or without a provider', () => {
    expect(render(run({ status: 'completed', partial: false })).find('[data-testid="run-state-notice"]').exists()).toBe(false)
    expect(render(null).find('[data-testid="run-state-notice"]').exists()).toBe(false)
    expect(mount(RunStateNotice, { global: { plugins: [i18n] } }).find('[data-testid="run-state-notice"]').exists()).toBe(false)
  })

  it('keys on the contract flag: a partial run shows even for a status the page does not know', () => {
    const text = render(run({ status: 'something-new' })).text()
    expect(text).toContain(msg.partialTitle)
    expect(text).toContain('something-new')
  })

  it('a flag that says not partial shows nothing, whatever the status', () => {
    expect(render(run({ status: 'killed', partial: false })).find('[data-testid="run-state-notice"]').exists()).toBe(false)
  })

  it('an empty status never reads "ended as ."', () => {
    const text = render(run({ status: '', reason: '' })).text()
    expect(text).toContain(msg.unfinished)
    expect(text).not.toContain('ended as .')
    expect(render(run({ status: '', reason: 'lost' })).text()).toContain(msg.unfinishedWithReason.replace('{reason}', 'lost'))
  })

  it('a cancelled run says cancelled', () => {
    const text = render(run({ status: 'cancelled', reason: 'cancelled by user' })).text()
    expect(text).toContain(msg.status.cancelled)
    expect(text).toContain('cancelled by user')
  })
})
