// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #14611: the minimap — an overview of a canvas larger than the viewport.
 *
 * As with `WorkflowCanvas.zoomFit.test.ts`, `getBoundingClientRect` is mocked
 * to a fixed size so the "you are here" viewport rectangle's own geometry is
 * deterministic rather than collapsing to zero.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'
import { firePointer } from './pointerTestUtils'

const VIEW_WIDTH = 1000
const VIEW_HEIGHT = 700

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: VIEW_WIDTH,
    height: VIEW_HEIGHT,
    top: 0,
    left: 0,
    right: VIEW_WIDTH,
    bottom: VIEW_HEIGHT,
    x: 0,
    y: 0,
    toJSON() {
      return this
    },
  } as DOMRect)
})

afterEach(() => {
  vi.restoreAllMocks()
})

function node(id: string, x: number, y: number): CanvasNode {
  return {
    id,
    type: 'org-person',
    position: { x, y },
    data: { label: id, title: 'role' },
    connections: [],
  }
}

const NODES = [node('a', 0, 0), node('b', 2000, 1000)]

function mountCanvas(props: Record<string, unknown> = {}) {
  return mount(WorkflowCanvas, {
    props: { nodes: NODES, selectedNodeId: null, readonly: true, ...props },
    global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
  })
}

describe('minimap (#14611)', () => {
  it('is present with an accessible label when the canvas has nodes', () => {
    const wrapper = mountCanvas()
    const minimap = wrapper.get('[data-testid="canvas-minimap"]')

    expect(minimap.attributes('role')).toBe('img')
    expect(minimap.attributes('aria-label')).toBe(en.workflow.canvas.minimapLabel)
  })

  it('is absent from an empty canvas — nothing to show an overview of', () => {
    const wrapper = mountCanvas({ nodes: [] })

    expect(wrapper.find('[data-testid="canvas-minimap"]').exists()).toBe(false)
  })

  it('draws one dot per node currently on the canvas', () => {
    const wrapper = mountCanvas()

    expect(wrapper.findAll('.canvas-minimap-node')).toHaveLength(NODES.length)
  })

  it('draws the "you are here" viewport rectangle', () => {
    const wrapper = mountCanvas()

    expect(wrapper.find('[data-testid="canvas-minimap-viewport"]').exists()).toBe(true)
  })

  it('moves the viewport rectangle when the main view pans', async () => {
    const wrapper = mountCanvas()
    const before = wrapper.get('[data-testid="canvas-minimap-viewport"]').attributes('style')

    await wrapper.get('[data-testid="canvas-fit-view"]').trigger('click')

    const after = wrapper.get('[data-testid="canvas-minimap-viewport"]').attributes('style')
    expect(after).not.toBe(before)
  })

  it('is never gated on readonly — an overview is a view concern', () => {
    const authoringWrapper = mountCanvas({ readonly: false })

    expect(authoringWrapper.find('[data-testid="canvas-minimap"]').exists()).toBe(true)
  })

  it('a click on the minimap pans the main view to the clicked point', async () => {
    const wrapper = mountCanvas()
    const before = wrapper.get('.canvas-content').attributes('style')

    const minimap = wrapper.get('[data-testid="canvas-minimap"]')
    await firePointer(minimap.element, 'pointerdown', { clientX: 40, clientY: 30 })

    const after = wrapper.get('.canvas-content').attributes('style')
    expect(after).not.toBe(before)
  })

  it('the minimap click never changes zoom — it only answers "where"', async () => {
    const wrapper = mountCanvas()

    const minimap = wrapper.get('[data-testid="canvas-minimap"]')
    await firePointer(minimap.element, 'pointerdown', { clientX: 40, clientY: 30 })

    const style = wrapper.get('.canvas-content').attributes('style') ?? ''
    expect(style).toContain('scale(1)')
  })
})
