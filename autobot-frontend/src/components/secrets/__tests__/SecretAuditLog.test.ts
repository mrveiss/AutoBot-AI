// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #20173: SecretAuditLog reads the row `GET /audit/logs` really sends
 * (AuditEntry.to_response_dict in services/audit_logger.py): `timestamp` is
 * epoch SECONDS, the operation is `secret.<verb>` (api/secrets_audit.py), the
 * secret's name is `details.name`, and there is no `metadata` or username.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import SecretAuditLog from '../SecretAuditLog.vue'

const FIVE_MINUTES_AGO = Math.floor(Date.now() / 1000) - (5 * 60 + 30)

// Shape of a `secret.create` row as the backend emits it.
const createRow = {
  id: '6f1c2f0e-8f44-4f55-a0a1-2f3a5b7c9d10',
  timestamp: FIVE_MINUTES_AGO + 0.25,
  date: '2026-10-31',
  operation: 'secret.create',
  result: 'success',
  user_id: 'alice',
  ip_address: '10.0.0.5',
  session_id: null,
  user_role: null,
  resource: '3b1e5c9a7d20', // pragma: allowlist secret -- the 12-hex hash secret_log_ref makes
  vm_source: 'main',
  vm_name: 'backend',
  details: { name: 'prod-db-credential' },
  performance_ms: null
}

const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

describe('SecretAuditLog (#20173)', () => {
  it('shows the real date, secret name and user of a backend row', async () => {
    get.mockResolvedValue({
      success: true,
      total_returned: 1,
      has_more: false,
      entries: [createRow],
      query: {}
    })
    const wrapper = mount(SecretAuditLog, { global: { plugins: [i18n] } })
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('prod-db-credential')
    expect(text).toContain('alice')
    // seconds read as milliseconds would land in January 1970 and print a date
    expect(text).toContain('5m ago')
    expect(text).not.toContain('1970')
  })
})
