// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Chat files upload target -- a real button that picks or accepts dropped files, with a progress bar.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatFilePanelUpload from '../ChatFilePanelUpload.vue'

const mountUpload = (props: { loading?: boolean; progress?: number } = {}) =>
  mount(ChatFilePanelUpload, {
    props: { loading: false, progress: 0, ...props },
    global: { mocks: { $t: (k: string) => k }, stubs: { Icon: true } },
  })

const file = (name: string) => new File(['x'], name, { type: 'text/plain' })

describe('ChatFilePanelUpload (#22349)', () => {
  it('is a real button that opens the file picker on click', async () => {
    const wrapper = mountUpload()
    const target = wrapper.get('[data-testid="upload-target"]')
    expect(target.element.tagName).toBe('BUTTON')
    let opened = 0
    ;(wrapper.get('[data-testid="upload-input"]').element as HTMLInputElement).click = () => { opened += 1 }
    await target.trigger('click')
    expect(opened).toBe(1)
  })

  it('emits the dropped files as an array and leaves the drag state', async () => {
    const wrapper = mountUpload()
    const target = wrapper.get('[data-testid="upload-target"]')
    await target.trigger('dragover')
    expect(target.classes()).toContain('upload-area--dragging')
    await target.trigger('drop', { dataTransfer: { files: [file('a.txt')] } })
    expect(wrapper.emitted('files')?.[0]?.[0]).toHaveLength(1)
    expect(target.classes()).not.toContain('upload-area--dragging')
  })

  it('emits nothing for an empty drop', async () => {
    const wrapper = mountUpload()
    await wrapper.get('[data-testid="upload-target"]').trigger('drop', { dataTransfer: { files: [] } })
    expect(wrapper.emitted('files')).toBeUndefined()
  })

  it('is disabled while loading', () => {
    expect(mountUpload({ loading: true }).get('[data-testid="upload-target"]').attributes('disabled')).toBeDefined()
  })

  it.each([[0, false], [1, true], [50, true], [99, true], [100, false]])('progress %i renders the bar: %s', (progress, shown) => {
    const wrapper = mountUpload({ progress })
    expect(wrapper.find('[data-testid="upload-progress"]').exists()).toBe(shown)
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(shown)
  })
})
