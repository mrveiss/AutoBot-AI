// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ChatInput (#18243): the orchestrator wires its parts together -- draft, send, the shared Knowledge state, the
// Overseer injection, the emoji picker and the file input. Behaviour of each part is pinned in its own spec.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const m = vi.hoisted(() => ({ sendMessage: vi.fn(), toggleOverseer: vi.fn() }))

vi.mock('@/models/controllers', () => ({ useChatController: () => ({ sendMessage: m.sendMessage }) }))
vi.mock('@/composables/useVoiceOutput', () => ({ useVoiceOutput: () => ({ unlockAudio: vi.fn() }) }))
vi.mock('@/composables/usePreferences', () => ({ usePreferences: () => ({ reasoningEffort: { value: 'auto' } }) }))
vi.mock('@/composables/useStopGeneration', () => ({ useStopGeneration: () => ({ stopping: ref(false), failed: ref(false), stop: vi.fn() }) }))
vi.mock('@/composables/useSlashCommands', async () => {
  const { ref: r, computed } = await import('vue')
  const noop = vi.fn()
  return {
    useSlashCommands: () => ({
      suggestions: r([]), showDropdown: computed(() => false), selectedIndex: r(0), onInput: noop, moveUp: noop, moveDown: noop,
      applyPreset: noop, confirmSelection: noop, setSelectedIndex: noop, close: noop, fetchPresets: noop,
    }),
  }
})
vi.mock('@/composables/chat/useChatModelSelection', async () => {
  const { ref: r, computed } = await import('vue')
  return {
    useChatModelSelection: () => ({
      selectedModel: r(''), pickerModels: computed(() => []), overrideFields: computed(() => ({})), fetchModels: vi.fn(),
    }),
  }
})
vi.mock('@/composables/useThinkingMode', async () => {
  const { ref: r } = await import('vue')
  return {
    BUDGET_STEPS: [1000, 5000], BUDGET_STEP_LABELS: { 1000: '1k', 5000: '5k' },
    useThinkingMode: () => ({ enabled: r(false), budgetTokens: r(5000), load: vi.fn(), toggle: vi.fn(), setBudget: vi.fn() }),
  }
})

import ChatInput from '../ChatInput.vue'
import { resetChatKnowledgeState, useChatKnowledge } from '@/composables/chat/useChatKnowledge'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const stub = (name: string) => ({ name, template: `<span data-stub="${name}" />` })

function render(overseer = false) {
  setActivePinia(createPinia())
  return mount(ChatInput, {
    attachTo: document.body,
    global: {
      plugins: [i18n],
      provide: { overseerEnabled: ref(overseer), toggleOverseer: m.toggleOverseer, submitOverseerQuery: async () => true },
      stubs: {
        VisionAnalysisModal: stub('vision'), PresetManagementModal: stub('presets'), TranslationShortcutPanel: stub('translate'),
        McpPromptPicker: stub('mcp'), ChatImageGenDialog: stub('imagegen'), Teleport: true,
      },
    },
  })
}
const textarea = (w: ReturnType<typeof render>) => w.get('#chat-message-input')

beforeEach(() => {
  m.sendMessage.mockReset().mockResolvedValue('id')
  m.toggleOverseer.mockReset()
  setActivePinia(createPinia())
  resetChatKnowledgeState()
})

describe('ChatInput', () => {
  it('labels the textarea, describes it by its help text and starts with the idle placeholder', () => {
    const w = render()
    const input = textarea(w)
    expect(input.attributes('placeholder')).toBe(en.chat.input.typeMessage)
    expect(input.attributes('aria-describedby')).toBe('chat-input-help')
    expect(w.get('label[for="chat-message-input"]').text()).toBe(en.chat.input.chatMessage)
    w.unmount()
  })

  it('enables Send once there is text, and Enter sends it with use_knowledge on and clears the box', async () => {
    const w = render()
    const send = () => w.get(`[aria-label="${en.chat.input.sendMessage}"]`)
    expect(w.find(`[aria-label="${en.chat.input.sendMessage}"]`).exists()).toBe(false)
    await textarea(w).setValue('Hello, AutoBot!')
    expect(send().attributes('disabled')).toBeUndefined()
    await textarea(w).trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(m.sendMessage).toHaveBeenCalledWith('Hello, AutoBot!', expect.objectContaining({ use_knowledge: true }))
    expect((textarea(w).element as HTMLTextAreaElement).value).toBe('')
    w.unmount()
  })

  it('the Use Knowledge chip writes the state the header reads, and the send carries it', async () => {
    const w = render()
    await w.get('[data-testid="toggle-knowledge"] button').trigger('click')
    expect(useChatKnowledge().enabled.value).toBe(false)
    await textarea(w).setValue('hi')
    await textarea(w).trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(m.sendMessage).toHaveBeenCalledWith('hi', expect.objectContaining({ use_knowledge: false }))
    w.unmount()
  })

  it('the Overseer chip calls the injected toggle and shows the injected state', async () => {
    const w = render(true)
    const chip = w.get('[data-testid="toggle-overseer"] button')
    expect(chip.attributes('aria-pressed')).toBe('true')
    await chip.trigger('click')
    expect(m.toggleOverseer).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('opens the emoji picker from its button and inserts the pick into the draft', async () => {
    const w = render()
    await textarea(w).setValue('ab')
    ;(textarea(w).element as HTMLTextAreaElement).setSelectionRange(1, 1)
    await w.get(`[aria-label="${en.chat.input.addEmoji}"]`).trigger('click')
    expect(w.find('[role="dialog"]').exists()).toBe(true)
    await w.get(`[aria-label="${en.chat.input.emoji.u1f525}"]`).trigger('click')
    expect((textarea(w).element as HTMLTextAreaElement).value).toBe('a🔥b')
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    w.unmount()
  })

  it('closes the emoji picker on an outside click, not on a click inside it or on its own button', async () => {
    const w = render()
    const trigger = w.get(`[aria-label="${en.chat.input.addEmoji}"]`)
    await trigger.trigger('click')
    await w.get('[role="dialog"]').trigger('click')
    expect(w.find('[role="dialog"]').exists()).toBe(true)
    document.body.click()
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    w.unmount()
  })

  it('Attach opens the hidden file input', async () => {
    const w = render()
    const input = w.get('input[type="file"]').element as HTMLInputElement
    const click = vi.spyOn(input, 'click')
    await w.get(`[aria-label="${en.chat.input.attachFile}"]`).trigger('click')
    expect(click).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})
