// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the Files tab folder tree -- nodes are buttons, toggling emits, expand/collapse all, empty state.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import FileTreeView from '../FileTreeView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const tree = [
  { name: 'src', path: '/src', is_dir: true, level: 0, expanded: true },
  { name: 'main.ts', path: '/src/main.ts', is_dir: false, level: 1 },
]
const mountTree = (directoryTree = tree, selectedPath = '/src') =>
  mount(FileTreeView, { props: { directoryTree, selectedPath }, global: { plugins: [i18n], stubs: { Icon: true } } })

describe('FileTreeView (#22349)', () => {
  it('renders one button per node, folders carry aria-expanded and the selected node is current', () => {
    const wrapper = mountTree()
    const nodes = wrapper.findAll('[data-testid="tree-node"]')
    expect(nodes).toHaveLength(2)
    expect(nodes[0].attributes('aria-expanded')).toBe('true')
    expect(nodes[0].attributes('aria-current')).toBe('true')
    expect(nodes[1].attributes('aria-expanded')).toBeUndefined()
  })

  it('shows nested children only while the folder is expanded', () => {
    const nested = (expanded: boolean) => [{ name: 'src', path: '/src', is_dir: true, expanded, children: [{ name: 'lib', path: '/src/lib', is_dir: true }] }]
    expect(mountTree(nested(false)).findAll('[data-testid="tree-node"]')).toHaveLength(1)
    expect(mountTree(nested(true)).findAll('[data-testid="tree-node"]')).toHaveLength(2)
  })

  it('a node click emits toggle-node with the node', async () => {
    const wrapper = mountTree()
    await wrapper.findAll('[data-testid="tree-node"]')[0].trigger('click')
    expect(wrapper.emitted('toggle-node')?.[0]).toEqual([tree[0]])
  })

  it('expand all and collapse all emit', async () => {
    const wrapper = mountTree()
    await wrapper.get('[data-testid="tree-expand-all"]').trigger('click')
    await wrapper.get('[data-testid="tree-collapse-all"]').trigger('click')
    expect(wrapper.emitted('expand-all')).toHaveLength(1)
    expect(wrapper.emitted('collapse-all')).toHaveLength(1)
  })

  it('shows the empty message for an empty tree', () => {
    const wrapper = mountTree([], '')
    expect(wrapper.text()).toContain(en.fileBrowser.treeView.noStructure)
    expect(wrapper.find('[data-testid="tree-node"]').exists()).toBe(false)
  })
})
