// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import CommandPalette from '../CommandPalette.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      commands: {
        search: 'Search commands...',
        noResults: 'No commands found',
        newTask: 'New Task',
        newTaskDesc: 'Create a new task agent',
        newResearch: 'New Research',
        newResearchDesc: 'Start a research session',
        newCode: 'New Code Agent',
        newCodeDesc: 'Start a code analysis session',
        newAnalysis: 'New Analysis',
        newAnalysisDesc: 'Start an analysis session',
        task: 'Task',
        research: 'Research',
        code: 'Code',
        analysis: 'Analysis'
      }
    }
  }
})

describe('CommandPalette.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('renders modal hidden by default', () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n],
        stubs: {
          Teleport: true
        }
      }
    })

    expect(wrapper.find('.fixed.inset-0').exists()).toBe(false)
  })

  it('opens palette when open() is called', async () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n],
        stubs: {
          Teleport: false
        }
      },
      attachTo: document.body
    })

    const palette = wrapper.vm as unknown as { open: () => void; closeModal: () => void }
    palette.open()
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.isOpen).toBe(true)
  })

  it('closes palette on escape key', async () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n],
        stubs: {
          Teleport: false
        }
      },
      attachTo: document.body
    })

    const palette = wrapper.vm as unknown as { open: () => void; closeModal: () => void }
    palette.open()
    await wrapper.vm.$nextTick()

    palette.closeModal()
    expect(wrapper.vm.isOpen).toBe(false)
  })

  it('filters commands by search query', async () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n]
      }
    })

    wrapper.vm.searchQuery = 'task'
    await wrapper.vm.$nextTick()

    const filtered = wrapper.vm.filteredCommands
    expect(filtered.length).toBeGreaterThan(0)
    expect(filtered.every((cmd: { label: string; description: string }) =>
      cmd.label.toLowerCase().includes('task') ||
      cmd.description.toLowerCase().includes('task')
    )).toBe(true)
  })

  it('navigates commands with arrow keys', async () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n]
      }
    })

    wrapper.vm.selectedIndex = 0
    wrapper.vm.moveDown()
    expect(wrapper.vm.selectedIndex).toBe(1)

    wrapper.vm.moveUp()
    expect(wrapper.vm.selectedIndex).toBe(0)
  })

  it('executes command on enter', async () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n]
      }
    })

    const actionSpy = vi.fn()
    const command = wrapper.vm.filteredCommands[0]
    command.action = actionSpy

    wrapper.vm.selectedIndex = 0
    wrapper.vm.executeCommand()

    expect(actionSpy).toHaveBeenCalled()
    expect(wrapper.vm.isOpen).toBe(false)
  })

  it('resets selection on search query change', async () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n]
      }
    })

    wrapper.vm.selectedIndex = 2
    wrapper.vm.searchQuery = 'research'
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.selectedIndex).toBe(0)
  })

  it('returns correct agent colors', () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n]
      }
    })

    expect(wrapper.vm.getAgentColor('task')).toBe('#3b82f6')
    expect(wrapper.vm.getAgentColor('research')).toBe('#8b5cf6')
    expect(wrapper.vm.getAgentColor('code')).toBe('#10b981')
    expect(wrapper.vm.getAgentColor('analysis')).toBe('#f59e0b')
  })

  it('returns correct agent emojis', () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n]
      }
    })

    expect(wrapper.vm.getAgentEmoji('task')).toBe('✓')
    expect(wrapper.vm.getAgentEmoji('research')).toBe('🔍')
    expect(wrapper.vm.getAgentEmoji('code')).toBe('</')
    expect(wrapper.vm.getAgentEmoji('analysis')).toBe('📊')
  })

  it('handles no results gracefully', async () => {
    const wrapper = mount(CommandPalette, {
      global: {
        plugins: [i18n]
      }
    })

    wrapper.vm.searchQuery = 'nonexistentcommand12345'
    await wrapper.vm.$nextTick()

    expect(wrapper.vm.filteredCommands.length).toBe(0)
  })
})
