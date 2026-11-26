// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22191: a REAL HttpError carrying `details.detail.code` (the backend's stable code) travels through
 * the shared `useVncControls` and the desktop's error mapping to an i18n key; and the Secrets save path
 * treats the same 422 object detail as an ordinary failed write, never rendering the object.
 */
import { describe, it, expect, vi } from 'vitest'
import { HttpError } from '@autobot/ui'
import { useVncControls } from '@autobot/vnc'
import { controlErrorText } from '../controlErrors'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: vi.fn() }) }))
vi.mock('@/utils/SecretsApiClient', () => ({ secretsApiClient: {} }))

import { useSecretWrites } from '@/composables/security/useSecretWrites'

const t = (key: string) => `i18n:${key}`
const refusal = (code: string) =>
  new HttpError(422, 'refused', { detail: { code, message: 'English text that must not be shown' } })

describe('stable desktop error codes', () => {
  it.each([
    ['vnc_credential_missing', 'desktop.interface.vncCredentialMissing'],
    ['host_not_found', 'desktop.interface.hostNotFound'],
    ['host_fields_missing', 'desktop.interface.hostFieldsMissing'],
    ['host_vnc_unavailable', 'desktop.interface.hostVncUnavailable'],
  ])('%s from a real HttpError reaches %s', async (code, key) => {
    const request = vi.fn(async () => { throw refusal(code) })
    const api = useVncControls({ baseUrl: '/api', hostId: 'h', request: request as never })
    const result = await api.mouseClick({ x: 1, y: 1 })
    expect(result.code).toBe(code)
    expect(controlErrorText(result, t)).toBe(`i18n:${key}`)
  })

  it('an unknown or missing code falls back to the response message', () => {
    expect(controlErrorText({ message: 'boom', code: 'new_code' }, t)).toBe('boom')
    expect(controlErrorText({ message: 'boom' }, t)).toBe('boom')
  })
})

describe('Secrets save with the create-422 object detail', () => {
  it('is an ordinary failed write: outcome failed, writeFailed set, nothing thrown', async () => {
    const { runWrite, writeFailed } = useSecretWrites()
    const outcome = await runWrite('save', async () => { throw refusal('host_fields_missing') })
    expect(outcome).toBe('failed')
    expect(writeFailed.value).toBe(true)
  })
})
