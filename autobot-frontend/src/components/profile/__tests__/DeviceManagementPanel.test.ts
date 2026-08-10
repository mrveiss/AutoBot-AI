// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * DeviceManagementPanel pairing entry point — Issue #13810.
 *
 * This panel is the only device surface the GUI actually mounts. It used to
 * open a static instruction list whose final step read "scan the QR code shown
 * on your desktop" — while no desktop surface rendered a QR at all, because the
 * component that does was never wired in. Pairing was therefore impossible
 * through the GUI.
 *
 * These tests pin the fix: the button opens the real pairing dialog, and the
 * device list refreshes when that dialog reports a device paired.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DeviceManagementPanel from '../DeviceManagementPanel.vue'
import PairDeviceDialog from '@/components/mobile/PairDeviceDialog.vue'
import en from '@/i18n/locales/en.json'

const fetchDevices = vi.fn().mockResolvedValue(undefined)
const deleteDevice = vi.fn().mockResolvedValue(undefined)

// Real refs: the template unwraps these, so plain objects would leave both the
// empty-state and the list branch unrendered and the test asserting on nothing.
const devices = ref<unknown[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

vi.mock('@/composables/useDevices', () => ({
  useDevices: () => ({ devices, loading, error, fetchDevices, deleteDevice }),
}))

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

// The dialog itself is covered by usePairingQR's own tests; here it is stubbed
// so the assertions are about the wiring, not about QR rendering.
vi.mock('@/components/mobile/PairDeviceDialog.vue', () => ({
  default: {
    name: 'PairDeviceDialog',
    props: ['modelValue'],
    emits: ['update:modelValue', 'paired'],
    template: '<div class="pair-dialog-stub" />',
  },
}))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountPanel() {
  return mount(DeviceManagementPanel, {
    global: {
      plugins: [i18n],
      stubs: { Icon: true },
    },
  })
}

describe('DeviceManagementPanel pairing entry point', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    devices.value = []
    loading.value = false
    error.value = null
  })

  it('mounts the real pairing dialog rather than a static instruction list', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.findComponent(PairDeviceDialog).exists()).toBe(true)
  })

  it('opens the dialog from the empty-state button', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.findComponent(PairDeviceDialog).props('modelValue')).toBe(false)

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(PairDeviceDialog).props('modelValue')).toBe(true)
  })

  it('opens the dialog from the "Add Device" button once devices exist', async () => {
    // The empty state and the populated list render different buttons; only the
    // former was covered, so a regression in the list-header path would pass.
    devices.value = [
      { id: 'd1', device_name: 'Phone', platform: 'ios', created_at: '2026-01-01T00:00:00Z', last_seen_at: null },
    ]
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('.empty-state').exists()).toBe(false)
    expect(wrapper.findComponent(PairDeviceDialog).props('modelValue')).toBe(false)

    await wrapper.find('.section-header button').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(PairDeviceDialog).props('modelValue')).toBe(true)
  })

  it('refreshes the device list once the dialog reports a device paired', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    const callsAfterMount = fetchDevices.mock.calls.length

    wrapper.findComponent(PairDeviceDialog).vm.$emit('paired')
    await flushPromises()

    // Without this the newly paired device never appears until a manual reload.
    expect(fetchDevices.mock.calls.length).toBe(callsAfterMount + 1)
  })
})
