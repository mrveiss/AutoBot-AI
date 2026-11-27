// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab header -- the titled page header with New folder and Upload file, and the folder path.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import FileBrowserHeader from '../FileBrowserHeader.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountHeader = () =>
  mount(FileBrowserHeader, { props: { viewMode: 'list', currentPath: '/docs' }, global: { plugins: [i18n], stubs: { Icon: true } } })

describe('FileBrowserHeader (#22349)', () => {
  it('shows the title and an Upload file button with its accessible name', () => {
    const wrapper = mountHeader()
    expect(wrapper.find('h2').text()).toBe(en.fileBrowser.header.title)
    expect(wrapper.get(`button[aria-label="${en.fileBrowser.header.uploadFile}"]`).text()).toContain(en.fileBrowser.header.uploadFile)
  })

  it('Upload file and New folder emit', async () => {
    const wrapper = mountHeader()
    await wrapper.get(`button[aria-label="${en.fileBrowser.header.uploadFile}"]`).trigger('click')
    await wrapper.get(`button[aria-label="${en.fileBrowser.header.newFolder}"]`).trigger('click')
    expect(wrapper.emitted('upload')).toHaveLength(1)
    expect(wrapper.emitted('new-folder')).toHaveLength(1)
  })

  it('passes a navigation from the path field up', async () => {
    const wrapper = mountHeader()
    await wrapper.get('[data-testid="path-go"]').trigger('click')
    expect(wrapper.emitted('navigate-to-path')?.[0]).toEqual(['/docs'])
  })
})
