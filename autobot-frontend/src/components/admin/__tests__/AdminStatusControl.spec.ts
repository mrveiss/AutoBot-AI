// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// The revocation-incomplete 503 offers a retry that re-sends the SAME value (#20670).
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { HttpError } from '@autobot/ui'

const callMock = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { call: (...args: unknown[]) => callMock(...args) } }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import AdminStatusControl from '../AdminStatusControl.vue'

const ADMIN_PATH = '/api/user-management/users/{user_id}/admin'
// The plain-string detail ``commit_or_503`` sends (autobot_shared/user_management/revocation_outcome.py).
const incomplete = () => new HttpError(503, 'Service Unavailable', { detail: 'Repeat the request to retry the revocation' })

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const wrappers: VueWrapper<any>[] = []

function mountControl(isPlatformAdmin: boolean) {
  const w = mount(AdminStatusControl, {
    props: { user: { id: 'u-1', username: 'alice', is_platform_admin: isPlatformAdmin }, isSelf: false },
    attachTo: document.body,
  })
  wrappers.push(w)
  return w
}

function sentValues(): boolean[] {
  return callMock.mock.calls.map(([, , init]) => (init as { body: { is_platform_admin: boolean } }).body.is_platform_admin)
}

function buttonByText(text: string): HTMLElement {
  const button = Array.from(document.body.querySelectorAll<HTMLElement>('button')).find(b => b.textContent?.trim() === text)
  if (!button) throw new Error(`no button: ${text}`)
  return button
}

beforeEach(() => callMock.mockReset())
afterEach(() => {
  wrappers.forEach(w => w.unmount())
  wrappers.length = 0
})

describe('AdminStatusControl', () => {
  it('a promotion whose revocation did not finish is retried with true, not toggled to false', async () => {
    callMock.mockRejectedValueOnce(incomplete()).mockResolvedValueOnce({ changed: false, sessions_revoked: true })
    const w = mountControl(false)

    await w.get('[role="switch"]').trigger('click')
    await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('adminUsers.adminStatusRevocationIncomplete')
    expect(w.emitted('changed')).toEqual([[null]])

    buttonByText('adminUsers.adminStatusRetryRevocation').click()
    await flushPromises()

    expect(callMock.mock.calls.map(([method, path]) => [method, path])).toEqual([['put', ADMIN_PATH], ['put', ADMIN_PATH]])
    expect(sentValues()).toEqual([true, true])
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('a demotion whose revocation did not finish is retried with false', async () => {
    callMock.mockRejectedValueOnce(incomplete()).mockResolvedValueOnce({ changed: false, sessions_revoked: true })
    const w = mountControl(true)

    await w.get('[role="switch"]').trigger('click')
    buttonByText('adminUsers.revokeAdminAction').click()
    await flushPromises()
    buttonByText('adminUsers.adminStatusRetryRevocation').click()
    await flushPromises()

    expect(sentValues()).toEqual([false, false])
  })

  it('the last-admin refusal is worded and offers no retry', async () => {
    const detail = { code: 'last_platform_admin', message: 'server text' }
    callMock.mockRejectedValueOnce(new HttpError(409, 'Conflict', { detail }))
    const w = mountControl(true)

    await w.get('[role="switch"]').trigger('click')
    buttonByText('adminUsers.revokeAdminAction').click()
    await flushPromises()

    expect(w.emitted('changed')).toEqual([['adminUsers.adminStatusLastAdmin']])
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })
})
