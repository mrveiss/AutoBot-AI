// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The zero-size text of a knowledge tree file node comes from an i18n key (#19885),
 * so a locale can change it; it is not a literal passed to the size formatter.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import TreeNodeComponent from '../TreeNodeComponent.vue'

function mountNode(zeroSize: string, size: number) {
  const messages = { knowledge: { treeNode: { ...en.knowledge.treeNode, zeroSize } } }
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: messages } })
  return mount(TreeNodeComponent, {
    props: {
      node: { id: 'f1', name: 'a.md', type: 'file', path: '/a.md', size },
      expandedNodes: new Set<string>(),
      selectedDocuments: new Set<string>(),
      vectorizationStates: new Map(),
    },
    global: { plugins: [i18n], stubs: { Icon: true, VectorizationStatusBadge: true } },
  })
}

describe('TreeNodeComponent zero-size text (#19885)', () => {
  it('renders the locale key for a zero size', () => {
    expect(mountNode('NULL-BAJTI', 0).find('.node-size').text()).toBe('NULL-BAJTI')
  })

  it('still formats a non-zero size with the unit', () => {
    expect(mountNode('NULL-BAJTI', 2048).find('.node-size').text()).toBe('2KB')
  })
})
