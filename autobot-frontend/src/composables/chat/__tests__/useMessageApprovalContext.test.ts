// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ONE approval state for the whole stream (#18243): every injecting card sees the same refs, as the single
// useCommandApproval() in ChatMessages did before the split.
import { describe, it, expect, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'

const state = vi.hoisted(() => ({ approveCommand: vi.fn() }))
vi.mock('@/composables/useCommandApproval', async () => {
  const { ref } = await import('vue')
  return {
    useCommandApproval: () => ({
      processingApproval: ref(false), approveCommand: state.approveCommand, promptForComment: vi.fn(),
    }),
  }
})
vi.mock('@/composables/useGraphApproval', () => ({ useApprovalRouting: (fn: unknown) => fn }))
vi.mock('@/stores/usePermissionStore', () => ({ usePermissionStore: () => ({ isEnabled: true }) }))

import { provideMessageApproval, useMessageApproval } from '../useMessageApprovalContext'

describe('message approval context', () => {
  it('shares one instance between sibling consumers', () => {
    const seen: unknown[] = []
    const Child = defineComponent({ setup() { seen.push(useMessageApproval()); return () => h('i') } })
    const Parent = defineComponent({ setup() { provideMessageApproval(); return () => [h(Child), h(Child)] } })
    mount(Parent)
    expect(seen).toHaveLength(2)
    expect(seen[0]).toBe(seen[1])
    expect((seen[0] as { permissionStore: { isEnabled: boolean } }).permissionStore.isEnabled).toBe(true)
  })

  it('routes approveCommand through useApprovalRouting', () => {
    let ctx: ReturnType<typeof useMessageApproval> | undefined
    const Parent = defineComponent({ setup() { ctx = provideMessageApproval(); return () => h('i') } })
    mount(Parent)
    expect(ctx?.approveCommand).toBe(state.approveCommand)
  })

  it('throws a clear error without a provider', () => {
    const Lone = defineComponent({ setup() { useMessageApproval(); return () => h('i') } })
    expect(() => mount(Lone)).toThrow(/provideMessageApproval/)
  })
})
