// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #21963: acting on a node the store does not hold rejects with translated text from the
 * `fleet.errors.nodeNotFound` key, not a hard-coded English template.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFleetStore } from './fleet'
import i18n from '@/i18n'
import { errorText } from '@/utils/errorText'

vi.mock('@/composables/useSlmApi', () => ({ useSlmApi: () => ({}) }))

describe('fleet store not-found errors (#21963)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  const expected = () => i18n.global.t('fleet.errors.nodeNotFound', { nodeId: 'ghost' })

  it.each(['testConnection', 'assignNpuRole', 'removeNpuRole'] as const)('%s rejects with the translated text', async (action) => {
    const store = useFleetStore()
    const err = await store[action]('ghost').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(Error)
    expect((err as Error).message).toBe(expected())
    expect((err as Error).message).toContain('ghost')
    expect((err as Error).message).not.toBe('Node ghost not found')
  })

  it('the modal path renders the message through errorText', async () => {
    const store = useFleetStore()
    const err = await store.assignNpuRole('ghost').catch((e: unknown) => e)
    expect(errorText(err, 'fallback')).toBe(expected())
  })
})
