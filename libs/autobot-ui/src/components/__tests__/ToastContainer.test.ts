// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ToastContainer behavioral tests (#19903). The contract both apps rely on:
// it renders the shared useToast stack, names its region and each dismiss
// button from the CALLER's labels (the kit holds no text), and dismissing
// removes the toast from the stack.

import { describe, it, expect, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ToastContainer from '../ToastContainer.vue'
import { useToast } from '../../composables/useToast'

const props = { label: 'Notifications', dismissLabel: 'Dismiss notification' }

describe('ToastContainer', () => {
  afterEach(() => {
    useToast().clearAllToasts()
    document.body.innerHTML = ''
  })

  it('names the region from the caller label and renders nothing when empty', () => {
    const wrapper = mount(ToastContainer, { props, attachTo: document.body })
    const region = document.querySelector('[role="region"]')
    expect(region?.getAttribute('aria-label')).toBe('Notifications')
    expect(document.querySelectorAll('[role="alert"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it('renders each toast with its message and a status class', async () => {
    const wrapper = mount(ToastContainer, { props, attachTo: document.body })
    const { showToast } = useToast()
    showToast('Saved', 'success')
    showToast('Careful', 'warning')
    await nextTick()

    const alerts = Array.from(document.querySelectorAll('[role="alert"]'))
    expect(alerts.map((a) => a.textContent?.trim())).toEqual(['Saved', 'Careful'])
    expect(alerts[0].classList.contains('aui-toast--success')).toBe(true)
    expect(alerts[1].classList.contains('aui-toast--warning')).toBe(true)
    wrapper.unmount()
  })

  it('names every dismiss button from the caller label and removes the toast on click', async () => {
    const wrapper = mount(ToastContainer, { props, attachTo: document.body })
    const { showToast, toasts } = useToast()
    showToast('Failed', 'error')
    await nextTick()

    const button = document.querySelector('button.aui-toast__close') as HTMLButtonElement
    expect(button.getAttribute('aria-label')).toBe('Dismiss notification')

    button.click()
    await nextTick()
    expect(toasts.value).toHaveLength(0)
    wrapper.unmount()
  })
})
