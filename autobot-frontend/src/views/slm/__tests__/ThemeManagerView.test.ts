// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const AQUA = { id: 'aqua', name: 'Aqua', author: 'me', version: '1.0.0', supports: ['light'] }
const { fetchInstalledThemesMock, admin } = vi.hoisted(() => ({
  fetchInstalledThemesMock: vi.fn(),
  admin: { value: false },
}))

vi.mock('@/composables/useThemeRegistry', () => ({ fetchInstalledThemes: fetchInstalledThemesMock }))
vi.mock('@/utils/ApiClient', () => ({ default: { post: vi.fn(), delete: vi.fn() } }))
// #16494: the view gates install/uninstall on the user store. Mocked rather
// than backed by a real pinia so the admin/non-admin split is set per test.
vi.mock('@/stores/useUserStore', () => ({
  useUserStore: () => ({
    get isAdmin() {
      return admin.value
    },
  }),
}))
import ThemeManagerView from '../ThemeManagerView.vue'

describe('ThemeManagerView', () => {
  beforeEach(() => {
    admin.value = false
    fetchInstalledThemesMock.mockResolvedValue([AQUA])
  })

  it('lists installed themes on mount', async () => {
    const wrapper = mount(ThemeManagerView)
    await flushPromises()
    expect(wrapper.text()).toContain('Aqua')
  })

  it('shows a non-admin the list without the controls the backend would refuse (#16494)', async () => {
    const wrapper = mount(ThemeManagerView)
    await flushPromises()

    // The listing GETs are open, so the list itself stays visible.
    expect(wrapper.text()).toContain('Aqua')
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('offers install and uninstall to an admin (#16494)', async () => {
    admin.value = true
    const wrapper = mount(ThemeManagerView)
    await flushPromises()

    expect(wrapper.find('input[type="file"]').exists()).toBe(true)
    expect(wrapper.find('button').text()).toContain('Uninstall')
  })
})
