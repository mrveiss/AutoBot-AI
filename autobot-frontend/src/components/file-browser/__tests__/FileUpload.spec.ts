// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import FileUpload from '../FileUpload.vue'

// vue-i18n: provide a minimal $t stub so template calls resolve to the key
const i18nPlugin = {
  install(app: any) {
    app.config.globalProperties.$t = (key: string) => key
  }
}

function mountFileUpload() {
  return mount(FileUpload, {
    global: {
      plugins: [i18nPlugin]
    }
  })
}

describe('FileUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Idle / render ──────────────────────────────────────────────────────────

  it('renders the visible file input and label in idle state', () => {
    const wrapper = mountFileUpload()

    expect(wrapper.find('label[for="visible-file-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="visible-file-upload-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="file-upload-input"]').exists()).toBe(true)
  })

  it('both file inputs have the multiple attribute', () => {
    const wrapper = mountFileUpload()

    const visibleInput = wrapper.find('[data-testid="visible-file-upload-input"]')
    const hiddenInput = wrapper.find('[data-testid="file-upload-input"]')

    expect(visibleInput.attributes('multiple')).toBeDefined()
    expect(hiddenInput.attributes('multiple')).toBeDefined()
  })

  it('hidden file input is not visible', () => {
    const wrapper = mountFileUpload()

    const hiddenInput = wrapper.find('[data-testid="file-upload-input"]')
    // The component sets style="display: none" on the hidden input
    expect(hiddenInput.attributes('style')).toContain('display: none')
  })

  // ── File selection — visible input ─────────────────────────────────────────

  it('emits files-selected when files are chosen via the visible input', async () => {
    const wrapper = mountFileUpload()

    const file = new File(['hello'], 'test.txt', { type: 'text/plain' })
    const input = wrapper.find('[data-testid="visible-file-upload-input"]')

    // Simulate a change event with a FileList-like object
    Object.defineProperty(input.element, 'files', {
      value: [file],
      writable: false
    })
    await input.trigger('change')

    expect(wrapper.emitted('files-selected')).toBeTruthy()
    const emittedPayload = wrapper.emitted('files-selected')![0][0] as FileList
    expect(emittedPayload).toBeDefined()
  })

  it('does NOT emit files-selected when the change event has no files', async () => {
    const wrapper = mountFileUpload()

    const input = wrapper.find('[data-testid="visible-file-upload-input"]')
    // Leave files empty (default HTMLInputElement.files is null)
    await input.trigger('change')

    expect(wrapper.emitted('files-selected')).toBeFalsy()
  })

  // ── File selection — hidden input ──────────────────────────────────────────

  it('emits files-selected when files are chosen via the hidden input', async () => {
    const wrapper = mountFileUpload()

    const file = new File(['data'], 'document.pdf', { type: 'application/pdf' })
    const hiddenInput = wrapper.find('[data-testid="file-upload-input"]')

    Object.defineProperty(hiddenInput.element, 'files', {
      value: [file],
      writable: false
    })
    await hiddenInput.trigger('change')

    expect(wrapper.emitted('files-selected')).toBeTruthy()
  })

  // ── Multiple files ─────────────────────────────────────────────────────────

  it('emits a single files-selected event carrying multiple files', async () => {
    const wrapper = mountFileUpload()

    const files = [
      new File(['a'], 'a.txt', { type: 'text/plain' }),
      new File(['b'], 'b.txt', { type: 'text/plain' }),
      new File(['c'], 'c.md', { type: 'text/markdown' })
    ]

    const input = wrapper.find('[data-testid="visible-file-upload-input"]')
    Object.defineProperty(input.element, 'files', {
      value: files,
      writable: false
    })
    await input.trigger('change')

    expect(wrapper.emitted('files-selected')).toHaveLength(1)
    const emitted = wrapper.emitted('files-selected')![0][0] as File[]
    expect(emitted.length).toBe(3)
  })

  // ── Exposed method ─────────────────────────────────────────────────────────

  it('exposes triggerFileSelect method', () => {
    const wrapper = mountFileUpload()
    expect(typeof wrapper.vm.triggerFileSelect).toBe('function')
  })

  it('triggerFileSelect calls click() on the hidden file input', async () => {
    const wrapper = mountFileUpload()

    const hiddenInputEl = wrapper.find('[data-testid="file-upload-input"]').element as HTMLInputElement
    const clickSpy = vi.spyOn(hiddenInputEl, 'click').mockImplementation(() => {})

    // Expose the ref by calling the exposed method
    wrapper.vm.triggerFileSelect()

    expect(clickSpy).toHaveBeenCalledOnce()
  })
})
