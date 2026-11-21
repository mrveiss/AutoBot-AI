// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14749: deleting a multi-selection from the context menu is ONE gesture, so
 * it pushes ONE history entry and a single Undo restores every node.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'

const step = (id: string, x: number): CanvasNode => ({
  id, type: 'step', position: { x, y: 0 },
  data: { command: '', description: '', risk_level: 'low', requires_confirmation: true }, connections: [],
})
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

describe('bulk delete is one history entry (#14749)', () => {
  it('one Undo re-adds every deleted node, and a second Undo has nothing left', async () => {
    const w = mount(WorkflowCanvas, {
      props: { nodes: [step('n1', 0), step('n2', 300), step('n3', 600)], selectedNodeId: null },
      global: { plugins: [i18n] },
    })
    const node = (id: string) => w.get(`[data-node-id="${id}"]`)
    await node('n1').trigger('click')
    await node('n2').trigger('click', { shiftKey: true })
    await node('n2').trigger('contextmenu', { clientX: 5, clientY: 5 })
    await w.get('[data-testid="canvas-context-menu-item-delete"]').trigger('click')

    expect(w.emitted('node-removed')).toEqual([['n1'], ['n2']])
    const undo = w.get('[data-testid="canvas-undo"]')
    await undo.trigger('click')
    expect((w.emitted('node-added') as unknown as [CanvasNode][]).map(([n]) => n.id).sort()).toEqual(['n1', 'n2'])
    expect(undo.attributes('disabled')).toBeDefined()
  })
})
