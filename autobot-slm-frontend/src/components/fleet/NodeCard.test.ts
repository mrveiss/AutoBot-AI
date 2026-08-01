// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import NodeCard from './NodeCard.vue'
import en from '@/locales/en.json'
import type { SLMNode, NodeStatus } from '@/types/slm'

// NodeCard only needs getNodeUpdateSummary from the fleet store.
vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({
    getNodeUpdateSummary: () => null,
  }),
}))

// vue-i18n 11 requires app.use(); install a real i18n plugin since the
// template uses the global $t (#11359).
const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function makeNode(status: NodeStatus): SLMNode {
  return {
    node_id: 'node-1',
    hostname: 'test-host',
    ip_address: '10.0.0.1',
    status,
    roles: [],
    health: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

async function mountCard(status: NodeStatus) {
  const wrapper = mount(NodeCard, {
    props: { node: makeNode(status) },
    global: { plugins: [i18n] },
  })
  // The actions dropdown is rendered lazily (v-if="showMenu"); open it first.
  await wrapper.find('[aria-haspopup="true"]').trigger('click')
  return wrapper
}

describe('NodeCard enroll/recovery action (#12477)', () => {
  it('shows the Enroll action for pending nodes', async () => {
    const btn = (await mountCard('pending')).find('[data-test="enroll-action"]')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain(en.fleet.nodeCard.enrollNode)
  })

  it('exposes the recovery action labelled "Recover Connection" for degraded nodes', async () => {
    const btn = (await mountCard('degraded')).find('[data-test="enroll-action"]')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain(en.fleet.nodeCard.recoverConnection)
  })

  it('exposes the recovery action for offline and error nodes', async () => {
    for (const status of ['offline', 'error'] as NodeStatus[]) {
      const btn = (await mountCard(status)).find('[data-test="enroll-action"]')
      expect(btn.exists()).toBe(true)
      expect(btn.text()).toContain(en.fleet.nodeCard.recoverConnection)
    }
  })

  it('emits the enroll action (not the decommissioned-only reenroll) when recovering a degraded node', async () => {
    const wrapper = await mountCard('degraded')
    await wrapper.find('[data-test="enroll-action"]').trigger('click')
    const events = wrapper.emitted('action')
    expect(events).toBeTruthy()
    expect(events![0]).toEqual(['enroll', 'node-1'])
  })

  it('does not show the enroll/recovery action for online nodes', async () => {
    expect((await mountCard('online')).find('[data-test="enroll-action"]').exists()).toBe(false)
  })
})
