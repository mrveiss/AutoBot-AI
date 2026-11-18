// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20658: an unscored phase (completion_percentage absent) is "not scored", never a measured 0%.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const getMock = vi.hoisted(() => vi.fn())
vi.mock('@/utils/ApiClient', () => ({ ApiClient: class { get = getMock } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

import PhaseProgressionIndicator from '../PhaseProgressionIndicator.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: en as never } })

async function render(phase_details: Array<Record<string, unknown>>) {
  getMock.mockResolvedValue({ status: 'success', report: { phase_details } })
  const w = mount(PhaseProgressionIndicator, {
    global: { plugins: [i18n], stubs: { Icon: true } },
  })
  await w.find('.btn-load-validation').trigger('click')
  await flushPromises()
  return w
}

describe('PhaseProgressionIndicator unscored phases', () => {
  beforeEach(() => getMock.mockReset())

  it('reads an unscored phase as not scored with no aria-valuenow or fill', async () => {
    const w = await render([{ name: 'Phase 1' }])
    const card = w.find('.phase-card')
    expect(card.find('.phase-completion').text()).toBe('Not scored')
    expect(card.text()).not.toContain('0%')
    const bar = card.find('.progress-bar')
    expect(bar.attributes('aria-valuenow')).toBeUndefined()
    expect(bar.attributes('aria-valuetext')).toBe('Not scored')
    expect(card.find('.progress-fill').exists()).toBe(false)
    expect(card.find('.phase-status').text()).toBe('Not scored')
    expect(card.classes()).not.toContain('phase-incomplete')
    expect(card.find('.phase-status').classes()).not.toContain('status-incomplete')
  })

  it('keeps a genuinely measured 0% as 0%', async () => {
    const w = await render([{ name: 'Phase 1', completion_percentage: 0 }])
    const card = w.find('.phase-card')
    expect(card.find('.phase-completion').text()).toBe('0%')
    expect(card.find('.progress-bar').attributes('aria-valuenow')).toBe('0')
    expect(card.classes()).toContain('phase-incomplete')
  })

  it('averages only scored phases in a mixed set', async () => {
    const w = await render([
      { name: 'Phase 1', completion_percentage: 100 },
      { name: 'Phase 2', completion_percentage: 60 },
      { name: 'Phase 3' },
    ])
    expect(w.find('.maturity-percentage').text()).toBe('80%')
    expect(w.find('.maturity-bar').attributes('aria-valuenow')).toBe('80')
  })

  it('says none are scored when every phase is unscored', async () => {
    const w = await render([{ name: 'Phase 1' }, { name: 'Phase 2' }])
    expect(w.find('.maturity-percentage').text()).toBe('No phases scored')
    expect(w.find('.maturity-bar').attributes('aria-valuenow')).toBeUndefined()
    expect(w.find('.maturity-fill').exists()).toBe(false)
  })

  it('control: all scored averages every phase', async () => {
    const w = await render([
      { name: 'Phase 1', completion_percentage: 90 },
      { name: 'Phase 2', completion_percentage: 50 },
    ])
    expect(w.find('.maturity-percentage').text()).toBe('70%')
    expect(w.findAll('.progress-fill')).toHaveLength(2)
  })

  it('shows a scored status through its i18n key and falls back to formatStatus without one (#20723)', async () => {
    const w = await render([{ name: 'A', completion_percentage: 80 }, { name: 'B', completion_percentage: 10 }])
    expect(w.findAll('.phase-status').map((n) => n.text())).toEqual(['Mostly complete', 'Incomplete'])
    // 'Incomplete' must come from its own en.json key, not from the formatStatus fallback
    const statusKeys = (en as { workflow: { phaseProgression: { status: Record<string, string> } } }).workflow.phaseProgression.status
    expect(statusKeys.incomplete).toBe('Incomplete')
    i18n.global.setLocaleMessage('xx', {
      workflow: { phaseProgression: { notScored: 'x', status: { mostly_complete: 'translated!' } } },
    } as never)
    i18n.global.locale.value = 'xx' as never
    await w.vm.$nextTick()
    // translated where a key exists, formatStatus where it does not
    expect(w.findAll('.phase-status').map((n) => n.text())).toEqual(['translated!', 'Incomplete'])
    // and a locale that defines `incomplete` renders it, proving the key is read rather than the fallback
    i18n.global.setLocaleMessage('yy', {
      workflow: { phaseProgression: { notScored: 'x', status: { incomplete: 'translated incomplete' } } },
    } as never)
    i18n.global.locale.value = 'yy' as never
    await w.vm.$nextTick()
    expect(w.findAll('.phase-status').map((n) => n.text())).toEqual(['Mostly complete', 'translated incomplete'])
    i18n.global.locale.value = 'en' as never
  })

  it('states the remaining room in the quotaExceeded wording (#20723)', () => {
    const msg = (en as { chat: { input: { uploadError: { quotaExceeded: string } } } }).chat.input.uploadError.quotaExceeded
    expect(msg).toContain('larger than the room')
    expect(msg).toContain('{remainingMb}')
    expect(msg).not.toContain('is reached')
  })
})
