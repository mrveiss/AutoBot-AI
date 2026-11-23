// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { onCompanySwitch } from '@/utils/buildAuthenticatedWsUrl'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'

const COMPANY = '11111111-1111-4111-8111-111111111111'

describe('onCompanySwitch (#21997)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('runs the reconnect when the selected company changes, not before', async () => {
    const reconnect = vi.fn()
    onCompanySwitch(reconnect)
    await nextTick()
    expect(reconnect).not.toHaveBeenCalled()

    useLlcCompanyStore().selectedCompanyId = COMPANY
    await nextTick()
    expect(reconnect).toHaveBeenCalledTimes(1)
  })

  it('stops reacting once the returned handle is called', async () => {
    const reconnect = vi.fn()
    onCompanySwitch(reconnect)()
    useLlcCompanyStore().selectedCompanyId = COMPANY
    await nextTick()
    expect(reconnect).not.toHaveBeenCalled()
  })
})
