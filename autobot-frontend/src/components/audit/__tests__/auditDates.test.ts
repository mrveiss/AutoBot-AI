// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #20176: the audit dashboard reads the row `GET /audit/logs` sends. `timestamp` is epoch SECONDS
// (a float), so `new Date(timestamp)` lands in January 1970; the table, the timeline and the CSV
// export convert it, and no `error_message` is read because the backend never sends one.

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import type { AuditEntry } from '@/types/audit'
import AuditLogTable from '../AuditLogTable.vue'
import AuditTimeline from '../AuditTimeline.vue'
import { useAuditState } from '@/composables/useAuditApi'

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: vi.fn(), post: vi.fn() }) }))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })

const ISO = '2026-10-31T10:00:00.000Z'
const SECONDS = Date.parse(ISO) / 1000 + 0.25

const row = (id: string, timestamp: number, user = 'alice'): AuditEntry => ({
  id,
  timestamp,
  date: '2026-10-31',
  operation: 'secret.create',
  result: 'success',
  user_id: user,
  ip_address: '10.0.0.5',
  session_id: null,
  user_role: null,
  resource: null,
  vm_source: 'main',
  vm_name: 'backend',
  details: {},
  performance_ms: null
})

const stubs = { BaseModal: true, Icon: true }

describe('audit dashboard dates (#20176)', () => {
  it('AuditLogTable shows the 2026 date of an epoch-seconds row, never 1970', () => {
    const w = mount(AuditLogTable, { props: { entries: [row('1', SECONDS)] }, global: { plugins: [i18n], stubs } })
    const text = w.find('.timestamp-full').text()
    expect(text).toContain('2026')
    expect(text).not.toContain('1970')
  })

  it('AuditLogTable sorts newest first by the numeric timestamp', () => {
    const entries = [row('1', SECONDS - 3600, 'older-user'), row('2', SECONDS, 'newer-user')]
    const w = mount(AuditLogTable, { props: { entries }, global: { plugins: [i18n], stubs } })
    const rows = w.findAll('tbody tr').map((tr) => tr.text())
    expect(rows[0]).toContain('newer-user')
    expect(rows[1]).toContain('older-user')
  })

  it('AuditTimeline shows the 2026 date range of epoch-seconds rows', () => {
    const entries = [row('1', SECONDS), row('2', SECONDS + 60)]
    const w = mount(AuditTimeline, { props: { type: 'user', entityId: 'alice', entries }, global: { plugins: [i18n], stubs } })
    expect(w.text()).toContain('2026')
    expect(w.text()).not.toContain('1970')
  })

  it('the CSV export writes the real moment as ISO text and has no error-message column', () => {
    const state = useAuditState()
    state.entries.value = [row('1', SECONDS)]
    const [header, line] = state.exportToCsv().split('\n')
    expect(line.split(',')[0]).toBe('2026-10-31T10:00:00.250Z')
    expect(header).not.toContain('Error Message')
    expect(header.split(',')).toHaveLength(line.split(',').length)
  })
})
