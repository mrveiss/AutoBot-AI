// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// McpPromptPicker (#18243): an insert still rendering is discarded once its form is left (Back or close),
// and a render that finishes while its form is still open is inserted.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { h, nextTick, defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const m = vi.hoisted(() => ({ renderSelected: vi.fn(), reset: vi.fn() }))

vi.mock('@/composables/chat/useMcpPrompts', async () => {
  const { ref, computed } = await import('vue')
  const state = {
    activeBridge: ref('git'), loading: ref(false), error: ref(null), selectedPrompt: ref<unknown>({ name: 'p', arguments: [] }),
    formValues: ref({}), formError: ref(null), insertLoading: ref(false), currentPrompts: computed(() => []),
    promptsByBridge: ref({ git: [{ name: 'p' }], knowledge: [], filesystem: [] }), failedBridges: ref([]),
    loadPrompts: vi.fn(), selectPrompt: vi.fn(), renderSelected: m.renderSelected, reset: m.reset,
  }
  return { MCP_BRIDGES: ['git', 'knowledge', 'filesystem'], useMcpPrompts: () => state }
})

import McpPromptPicker from '../McpPromptPicker.vue'

const ModalStub = defineComponent({
  props: { modelValue: Boolean },
  setup: (_p, { slots }) => () => h('div', [slots.default?.(), slots.actions?.()]),
})
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountPicker = () => mount(McpPromptPicker, { global: { plugins: [i18n], stubs: { BaseModal: ModalStub } } })
const clickByText = async (w: ReturnType<typeof mountPicker>, text: string): Promise<void> => {
  await w.findAll('button').find((b) => b.text().includes(text))!.trigger('click')
}

let finish!: (text: string | null) => void
beforeEach(() => {
  m.reset.mockReset()
  m.renderSelected.mockReset().mockImplementation(() => new Promise((resolve) => { finish = resolve }))
})

describe('McpPromptPicker', () => {
  it('inserts a render that finishes while its form is still open', async () => {
    const w = mountPicker()
    await clickByText(w, en.chat.mcpPrompts.insert)
    finish('rendered')
    await nextTick()
    expect(w.emitted('insert')).toEqual([['rendered']])
  })

  it('discards a render still pending when Back leaves its form', async () => {
    const w = mountPicker()
    await clickByText(w, en.chat.mcpPrompts.insert) // the render of this form starts
    await clickByText(w, en.common.back) // and the person leaves it before it finishes
    finish('stale')
    await nextTick()
    expect(w.emitted('insert')).toBeUndefined()
  })
})
