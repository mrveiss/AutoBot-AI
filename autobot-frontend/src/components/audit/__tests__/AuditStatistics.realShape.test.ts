// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The statistics panel fed with what GET /audit/statistics really sends (the counters of
// AuditLogger.get_statistics, no per-result counts or rate) resolves to figures derived from the
// loaded rows, and an `attempted` row is neither a success nor a failure (#21513).

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import AuditStatistics from '../AuditStatistics.vue'
import { resolveAuditStatistics, type AuditServerStatistics } from '@/types/audit'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })
const L = en.audit.statistics

// Exactly the keys services/audit_logger.py get_statistics returns.
const realServerResponse: AuditServerStatistics = {
  total_logged: 42,
  total_failed: 1,
  redis_available: true,
  entries_last_24h: 7,
}
const rows = (...results: string[]) => results.map((result) => ({ result }))

function render(statistics: AuditServerStatistics | null, entries: Array<{ result: string }>) {
  return mount(AuditStatistics, {
    props: { statistics: resolveAuditStatistics(statistics, entries), vmInfo: { vm_source: 'host', vm_name: 'vm-a' } },
    global: { plugins: [i18n], stubs: { Icon: true } },
  })
}
const valueOf = (w: ReturnType<typeof render>, label: string) =>
  w.findAll('.stat-card').find((c) => c.text().includes(label))!.find('.stat-value').text()

describe('AuditStatistics with a real-shaped server response', () => {
  it('derives the counts and rate from the rows, counting attempted as neither success nor failure', () => {
    const w = render(realServerResponse, rows('success', 'success', 'success', 'failed', 'denied', 'attempted', 'attempted'))
    expect(valueOf(w, L.totalEvents)).toBe('7')
    expect(valueOf(w, L.successful)).toBe('3')
    expect(valueOf(w, L.failed)).toBe('1')
    expect(valueOf(w, L.denied)).toBe('1')
    expect(valueOf(w, L.successRate)).toContain('60%') // 3 of 5 final rows; the 2 attempted rows are out
  })

  it('uses the counts the server does send over the loaded rows', () => {
    const w = render({ ...realServerResponse, success_count: 90, failed_count: 10, denied_count: 0, error_count: 0 }, rows('failed'))
    expect(valueOf(w, L.successful)).toBe('90')
    expect(valueOf(w, L.successRate)).toContain('90%')
  })

  it('renders zeros, not a crash, for a real-shaped response with no rows', () => {
    const w = render(realServerResponse, [])
    expect(valueOf(w, L.successful)).toBe('0')
    expect(valueOf(w, L.successRate)).toContain('0%')
  })
})
