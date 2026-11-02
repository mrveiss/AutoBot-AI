// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20682: the card detach buttons show only when the viewer may detach (the server's own check).
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

import WorkflowCanvas from '../WorkflowCanvas.vue'
import type { CanvasNode } from '../canvasNode'
import { buildProcessCanvasNodes, buildToolCanvasNodes } from '@/composables/llc/orgCanvasGraph'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const PROCESS = buildProcessCanvasNodes([{ role_id: 'role-1', role_name: 'Head of Ops', workflow_id: 'wf-1' }], 0)
const TOOL = buildToolCanvasNodes(
  [
    { role_id: 'role-1', role_name: 'Head of Ops', tool_name: 'web_search' },
    { role_id: 'role-2', role_name: 'SRE', tool_name: 'web_search' },
  ],
  [],
  0,
)
const sel = '[data-testid="process-detach-btn"], [data-testid="tool-detach-btn"]'

function mountWith(canDetach: boolean | undefined, nodes: CanvasNode[]) {
  return mount(WorkflowCanvas, {
    props: { nodes, selectedNodeId: null, readonly: true, ...(canDetach === undefined ? {} : { canDetach }) },
    global: { plugins: [i18n] },
  })
}

describe('the card detach buttons follow canDetach (#20682)', () => {
  it.each([
    ['process', PROCESS],
    ['tool', TOOL],
  ])('%s card: no button when the viewer may not detach', (_l, nodes) => {
    expect(mountWith(false, nodes).findAll(sel)).toHaveLength(0)
  })

  it.each([
    ['process', PROCESS, 1],
    ['tool', TOOL, 2],
  ])('%s card: buttons show when the viewer may, and by default', (_l, nodes, count) => {
    expect(mountWith(true, nodes).findAll(sel)).toHaveLength(count)
    expect(mountWith(undefined, nodes).findAll(sel)).toHaveLength(count)
  })

  it('an allowed viewer still detaches from the card', async () => {
    const w = mountWith(true, PROCESS)
    await w.get('[data-testid="process-detach-btn"]').trigger('click')
    expect(w.emitted('process-detached')?.at(0)).toEqual(['role-1', 'wf-1'])
  })
})
