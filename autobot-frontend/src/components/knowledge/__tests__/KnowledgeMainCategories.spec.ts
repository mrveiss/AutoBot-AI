// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Tests for KnowledgeMainCategories.vue — empty-KB vs broken-KB panels.
 *
 * Covers issue #5201:
 *  - All counts == 0 AND kb_connected == true → empty-state banner visible
 *  - kb_connected == false → broken-KB error panel visible (takes precedence)
 *  - Any count > 0 → neither banner visible
 *  - Empty categories array (still loading) → no banner (prevents flash)
 *
 * Covers issue #5590:
 *  - kbFetchError == true → fetch-error panel visible (top priority)
 *  - kbFetchError overrides both !kbConnected and empty-state
 *  - kbFetchError defaults to false when prop omitted
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KnowledgeMainCategories from '../KnowledgeMainCategories.vue'

const stubT = (key: string) => key

const SYSTEM_CATEGORIES = [
  {
    id: 'autobot-documentation',
    name: 'AutoBot Documentation',
    description: 'docs',
    icon: 'fas fa-book',
    color: '#3b82f6',
    count: 0,
  },
  {
    id: 'system-knowledge',
    name: 'System Knowledge',
    description: 'system',
    icon: 'fas fa-server',
    color: '#10b981',
    count: 0,
  },
  {
    id: 'user-knowledge',
    name: 'User Knowledge',
    description: 'user',
    icon: 'fas fa-user-circle',
    color: '#f59e0b',
    count: 0,
  },
]

function mountComponent(props: {
  categories?: typeof SYSTEM_CATEGORIES
  kbConnected?: boolean
  kbFetchError?: boolean
}) {
  return mount(KnowledgeMainCategories, {
    props: {
      categories: props.categories ?? SYSTEM_CATEGORIES,
      populationStates: {},
      kbConnected: props.kbConnected,
      kbFetchError: props.kbFetchError,
    },
    global: {
      mocks: { $t: stubT },
      stubs: {
        BaseButton: {
          template: '<button><slot /></button>',
          props: ['variant', 'size', 'loading', 'disabled'],
        },
      },
    },
  })
}

describe('KnowledgeMainCategories — empty-KB vs broken-KB panels (#5201)', () => {
  it('shows empty-state hint when all counts are 0 and kb is connected', () => {
    const wrapper = mountComponent({ kbConnected: true })
    expect(wrapper.find('.kb-status-panel--info').exists()).toBe(true)
    expect(wrapper.find('.kb-status-panel--error').exists()).toBe(false)
    expect(wrapper.text()).toContain('knowledge.emptyState.title')
    expect(wrapper.text()).toContain('knowledge.emptyState.hint')
  })

  it('shows broken-KB error panel when kb is disconnected (overrides empty-state)', () => {
    const wrapper = mountComponent({ kbConnected: false })
    expect(wrapper.find('.kb-status-panel--error').exists()).toBe(true)
    expect(wrapper.find('.kb-status-panel--info').exists()).toBe(false)
    expect(wrapper.text()).toContain('knowledge.categoriesError.title')
    expect(wrapper.text()).toContain('knowledge.categoriesError.description')
  })

  it('shows neither banner when any category has count > 0', () => {
    const populated = SYSTEM_CATEGORIES.map((c, i) =>
      i === 0 ? { ...c, count: 5 } : c,
    )
    const wrapper = mountComponent({ categories: populated, kbConnected: true })
    expect(wrapper.find('.kb-status-panel--info').exists()).toBe(false)
    expect(wrapper.find('.kb-status-panel--error').exists()).toBe(false)
  })

  it('shows broken-KB panel even when counts would otherwise trigger empty-state', () => {
    const wrapper = mountComponent({ kbConnected: false })
    // Error panel present, info panel absent — error takes precedence
    expect(wrapper.find('.kb-status-panel--error').exists()).toBe(true)
    expect(wrapper.find('.kb-status-panel--info').exists()).toBe(false)
  })

  it('does not flash empty-state hint while categories are still loading', () => {
    const wrapper = mountComponent({ categories: [], kbConnected: true })
    expect(wrapper.find('.kb-status-panel--info').exists()).toBe(false)
    expect(wrapper.find('.kb-status-panel--error').exists()).toBe(false)
  })

  it('defaults kbConnected to true when prop omitted', () => {
    const wrapper = mount(KnowledgeMainCategories, {
      props: {
        categories: SYSTEM_CATEGORIES,
        populationStates: {},
      },
      global: {
        mocks: { $t: stubT },
        stubs: {
          BaseButton: {
            template: '<button><slot /></button>',
            props: ['variant', 'size', 'loading', 'disabled'],
          },
        },
      },
    })
    // No kbConnected prop → default true → empty-state shown (counts are 0)
    expect(wrapper.find('.kb-status-panel--info').exists()).toBe(true)
    expect(wrapper.find('.kb-status-panel--error').exists()).toBe(false)
  })
})

describe('KnowledgeMainCategories — fetch-layer error panel (#5590)', () => {
  it('shows fetch-error panel when kbFetchError is true', () => {
    const wrapper = mountComponent({ kbFetchError: true, kbConnected: true })
    expect(wrapper.find('.kb-status-panel--error').exists()).toBe(true)
    expect(wrapper.text()).toContain('knowledge.categoriesFetchError.title')
    expect(wrapper.text()).toContain('knowledge.categoriesFetchError.description')
    expect(wrapper.find('.kb-status-panel--info').exists()).toBe(false)
  })

  it('fetch-error panel takes precedence over Redis-down panel', () => {
    const wrapper = mountComponent({ kbFetchError: true, kbConnected: false })
    // Both would show error, but fetch-error is first in v-if chain
    expect(wrapper.text()).toContain('knowledge.categoriesFetchError.title')
    expect(wrapper.text()).not.toContain('knowledge.categoriesError.title')
  })

  it('does not show fetch-error panel when kbFetchError is false', () => {
    const wrapper = mountComponent({ kbFetchError: false, kbConnected: true })
    expect(wrapper.text()).not.toContain('knowledge.categoriesFetchError.title')
  })

  it('defaults kbFetchError to false when prop omitted', () => {
    const wrapper = mountComponent({ kbConnected: false })
    // No kbFetchError prop → default false → Redis-down panel shown, not fetch-error
    expect(wrapper.text()).toContain('knowledge.categoriesError.title')
    expect(wrapper.text()).not.toContain('knowledge.categoriesFetchError.title')
  })
})
