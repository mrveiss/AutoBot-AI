// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** #22191: the picker shows the desktop-VM hint line (none registered / registry unreadable) when it has one. */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

const hint = ref('')
vi.mock('@/composables/useHostSelector', () => ({
  useHostSelector: () => ({
    hosts: ref([]),
    loading: ref(false),
    error: ref(null),
    loadHosts: vi.fn(async () => {}),
    desktopVmHint: hint
  })
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

import HostSelector from '../HostSelector.vue'

async function expanded() {
  const wrapper = mount(HostSelector, { props: { requiredCapability: 'vnc', includeDesktopVm: true } })
  await flushPromises()
  await wrapper.find('button.host-selector-collapsed').trigger('click')
  return wrapper
}

describe('HostSelector desktop VM hint', () => {
  it('renders the hint line when the composable has one', async () => {
    hint.value = 'ui.hostSelection.noDesktopVm'
    const wrapper = await expanded()
    const line = wrapper.find('[data-testid="desktop-vm-hint"]')
    expect(line.exists()).toBe(true)
    expect(line.text()).toBe('ui.hostSelection.noDesktopVm')
    expect(line.classes()).toContain('empty-state') // the existing token-styled muted block: no new CSS
  })

  it('renders nothing when there is no hint', async () => {
    hint.value = ''
    const wrapper = await expanded()
    expect(wrapper.find('[data-testid="desktop-vm-hint"]').exists()).toBe(false)
  })
})
