// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SystemStatusModal (#18240): the status panel on the kit BaseModal, reading
 * the shell's one shared useSystemStatus instance.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import SystemStatusModal from '../SystemStatusModal.vue'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { SYSTEM_STATUS_KEY } from '@/composables/systemStatusContext'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountModal() {
  const status = useSystemStatus()
  const wrapper = mount(SystemStatusModal, {
    attachTo: document.body,
    global: { plugins: [i18n], provide: { [SYSTEM_STATUS_KEY as symbol]: status } },
  })
  return { wrapper, status }
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('SystemStatusModal', () => {
  it('renders nothing while closed', () => {
    mountModal()
    expect(document.querySelector('[data-testid="system-status-modal"]')).toBeNull()
  })

  it('opens from the shared state as an aria-modal dialog listing every service', async () => {
    const { wrapper, status } = mountModal()
    status.showSystemStatus.value = true
    await wrapper.vm.$nextTick()

    const dialog = document.querySelector('[role="dialog"]')
    expect(dialog?.getAttribute('aria-modal')).toBe('true')
    expect(dialog?.textContent).toContain(en.nav.systemStatus)
    const rows = document.querySelectorAll('[data-testid="system-status-modal"] li')
    expect(rows.length).toBe(status.systemServices.value.length)
  })

  it('the Close button closes it through the shared state', async () => {
    const { wrapper, status } = mountModal()
    status.showSystemStatus.value = true
    await wrapper.vm.$nextTick()
    const close = [...document.querySelectorAll('.aui-dialog-actions button')].find(
      (b) => b.textContent?.trim() === en.common.close,
    ) as HTMLButtonElement
    close.click()
    await wrapper.vm.$nextTick()

    expect(status.showSystemStatus.value).toBe(false)
  })
})
