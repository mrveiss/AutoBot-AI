// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * DecommissionModal - cannot be dismissed while the decommission runs, and a dismissal
 * after it completed still refreshes the fleet (CodeRabbit on #18941).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { BaseModal } from '@autobot/ui'

const { decommissionPreflight, decommissionNode } = vi.hoisted(() => ({
  decommissionPreflight: vi.fn(),
  decommissionNode: vi.fn(),
}))

vi.mock('@/composables/useRoles', () => ({
  useRoles: () => ({ decommissionPreflight, decommissionNode }),
}))

import DecommissionModal from './DecommissionModal.vue'

const node = { node_id: 'node-1', hostname: 'worker-1', ip_address: 'worker-1.test' }

function mountModal() {
  return mount(DecommissionModal, {
    props: { node },
    global: { mocks: { $t: (k: string) => k }, stubs: { teleport: true } },
  })
}

async function startDecommission() {
  let finish: (r: { success: boolean; output: string }) => void = () => {}
  decommissionNode.mockReturnValue(new Promise((resolve) => { finish = resolve }))
  const wrapper = mountModal()
  // Each step waits for its own effect: one flush is not enough on a loaded machine (#18833).
  await vi.waitFor(() => expect(decommissionPreflight).toHaveBeenCalled())
  await flushPromises()
  await wrapper.find('#confirm-node-id').setValue(node.node_id)
  await vi.waitFor(() => expect(wrapper.find('button.btn-error').attributes('disabled')).toBeUndefined())
  await wrapper.find('button.btn-error').trigger('click')
  await vi.waitFor(() => expect(decommissionNode).toHaveBeenCalled())
  await flushPromises()
  return { wrapper, finish: (r: { success: boolean; output: string }) => finish(r) }
}

describe('DecommissionModal dismissal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    decommissionPreflight.mockResolvedValue({ must_migrate: [], should_migrate: [], safe_to_remove: [] })
  })

  it('is not locked before the decommission starts', async () => {
    const wrapper = mountModal()
    await flushPromises()
    expect(wrapper.findComponent(BaseModal).props('locked')).toBe(false)
  })

  it('locks the modal while the decommission is running', async () => {
    const { wrapper } = await startDecommission()
    expect(decommissionNode).toHaveBeenCalledOnce()
    expect(wrapper.findComponent(BaseModal).props('locked')).toBe(true)
  })

  it('a dismissal after completion emits decommissioned so the fleet refreshes', async () => {
    const { wrapper, finish } = await startDecommission()
    finish({ success: true, output: '' })
    await flushPromises()
    const modal = wrapper.findComponent(BaseModal)
    expect(modal.props('locked')).toBe(false)
    modal.vm.$emit('close')
    expect(wrapper.emitted('decommissioned')).toHaveLength(1)
    expect(wrapper.emitted('close')).toBeUndefined()
  })
})
