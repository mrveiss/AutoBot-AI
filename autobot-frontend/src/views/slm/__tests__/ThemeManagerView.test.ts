// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const AQUA = { id: 'aqua', name: 'Aqua', author: 'me', version: '1.0.0', supports: ['light'] }
const { fetchInstalledThemesMock } = vi.hoisted(() => ({ fetchInstalledThemesMock: vi.fn() }))

vi.mock('@/composables/useThemeRegistry', () => ({ fetchInstalledThemes: fetchInstalledThemesMock }))
vi.mock('@/utils/ApiClient', () => ({ default: { post: vi.fn(), delete: vi.fn() } }))
import ThemeManagerView from '../ThemeManagerView.vue'

describe('ThemeManagerView', () => {
  it('lists installed themes on mount', async () => {
    fetchInstalledThemesMock.mockResolvedValue([AQUA])
    const wrapper = mount(ThemeManagerView)
    await flushPromises()
    expect(wrapper.text()).toContain('Aqua')
  })
})
