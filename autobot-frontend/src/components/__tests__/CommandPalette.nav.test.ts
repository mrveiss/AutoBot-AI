// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The command palette's navigation section is the nav registry (#17561):
 * every registry entry is offered, flagged-off entries are not, admin entries
 * only for admins, and search matches an entry's translated keywords.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import en from '@/i18n/locales/en.json'
import CommandPalette from '../CommandPalette.vue'
import { navItems, profileMenuItems, adminMenuItems } from '@/config/navItems'

const mockPush = vi.fn()
let isAdmin = false

vi.mock('vue-router', () => ({ useRouter: () => ({ push: mockPush }) }))
vi.mock('@/stores/useUserStore', () => ({
  useUserStore: () => ({
    get isAdmin() {
      return isAdmin
    },
  }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

type PaletteVm = {
  commands: Array<{ id: string; action: () => void }>
  filteredCommands: Array<{ id: string }>
  searchQuery: string
}

const paletteIds = (): string[] => {
  const vm = mount(CommandPalette, { global: { plugins: [i18n] } }).vm as unknown as PaletteVm
  return vm.commands.map((c) => c.id)
}

describe('CommandPalette navigation section (#17561)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    isAdmin = false
    mockPush.mockClear()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('offers every nav-registry entry, admin entries included for an admin', () => {
    isAdmin = true
    vi.stubEnv('VITE_FEATURE_CANVAS', 'true')
    const ids = paletteIds()

    const missing = [...navItems, ...profileMenuItems, ...adminMenuItems]
      .map((item) => `nav:${item.to}`)
      .filter((id) => !ids.includes(id))
    expect(missing).toEqual([])
  })

  it('does not offer admin entries to a non-admin', () => {
    const ids = paletteIds()

    expect(ids).toContain('nav:/home')
    expect(adminMenuItems.filter((item) => ids.includes(`nav:${item.to}`))).toEqual([])
  })

  it('leaves out an entry whose feature flag is off, and offers it once on', () => {
    vi.stubEnv('VITE_FEATURE_CANVAS', 'false')
    expect(paletteIds()).not.toContain('nav:/canvas')

    vi.stubEnv('VITE_FEATURE_CANVAS', 'true')
    expect(paletteIds()).toContain('nav:/canvas')
  })

  it('finds an entry by a translated keyword its label never says', async () => {
    const wrapper = mount(CommandPalette, { global: { plugins: [i18n] } })
    const vm = wrapper.vm as unknown as PaletteVm
    vm.searchQuery = 'visitors'
    await wrapper.vm.$nextTick()

    expect(vm.filteredCommands.map((c) => c.id)).toEqual(['nav:/analytics'])
  })

  it('navigates to the entry route when chosen', () => {
    const vm = mount(CommandPalette, { global: { plugins: [i18n] } }).vm as unknown as PaletteVm
    vm.commands.find((c) => c.id === 'nav:/automation')!.action()

    expect(mockPush).toHaveBeenCalledWith('/automation')
  })

  it('shows the locale-neutral ↵ key for a navigation row, never English "Enter"', () => {
    const vm = mount(CommandPalette, { global: { plugins: [i18n] } }).vm as unknown as PaletteVm & {
      getShortcutText: (c: unknown) => string
    }
    const nav = vm.commands.find((c) => c.id === 'nav:/home')!
    expect(vm.getShortcutText(nav)).toBe('↵')
  })
})
