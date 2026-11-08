// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, computed, defineComponent, h } from 'vue'

const approveOrDeny = vi.fn()
const errorApprove = ref<Error | null>(null)

vi.mock('@/composables/useCommandPermissions', () => ({
  useCommandPermissions: () => ({
    isProcessing: ref(false),
    error: computed(() => errorApprove.value),
    errorApprove,
    errorComment: ref(null),
    approveOrDeny,
    postComment: vi.fn()
  })
}))
vi.mock('@/composables/useModal', () => ({ useModal: () => ({ isOpen: ref(true) }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() })
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => `t:${k}` }) }))
vi.mock('@autobot/ui', () => ({
  useFocusTrap: () => ({ onKeydown: vi.fn() }),
  useFocusRestore: vi.fn(),
  BaseButton: defineComponent({
    emits: ['click'],
    inheritAttrs: true,
    setup(_, { slots, emit }) {
      return (): ReturnType<typeof h> => h('button', { onClick: () => emit('click') }, slots.default?.())
    }
  })
}))

import CommandPermissionDialog from '../CommandPermissionDialog.vue'

const stubs = { StatusBadge: true, Icon: true }

const mountDialog = () =>
  mount(CommandPermissionDialog, {
    props: { show: true, command: 'rm x', terminalSessionId: 'sess-1' },
    global: { stubs }
  })

const clickDeny = async (wrapper: ReturnType<typeof mountDialog>) => {
  const deny = wrapper.findAll('button').find((b) => b.attributes('aria-label') === 't:ui.commandPermission.deny')
  expect(deny).toBeDefined()
  await deny!.trigger('click')
  await new Promise((r) => setTimeout(r, 0))
}

describe('CommandPermissionDialog handleDeny (#21174)', () => {
  beforeEach(() => {
    approveOrDeny.mockReset()
    errorApprove.value = null
  })

  it('shows the retry error and does not emit denied when the approval state is unavailable', async () => {
    approveOrDeny.mockResolvedValue({ status: 'error', error: 'Approval state unavailable, retry' })
    const wrapper = mountDialog()
    await clickDeny(wrapper)
    expect(wrapper.emitted('denied')).toBeUndefined()
    expect(errorApprove.value?.message).toBe('t:ui.commandPermission.approvalStateUnavailable')
  })

  it('does not emit denied when the request itself fails', async () => {
    approveOrDeny.mockRejectedValue(new Error('network'))
    const wrapper = mountDialog()
    await clickDeny(wrapper)
    expect(wrapper.emitted('denied')).toBeUndefined()
    expect(errorApprove.value).not.toBeNull()
  })

  it('emits denied after a real denial', async () => {
    approveOrDeny.mockResolvedValue({ status: 'denied' })
    const wrapper = mountDialog()
    await clickDeny(wrapper)
    expect(wrapper.emitted('denied')).toHaveLength(1)
  })
})
