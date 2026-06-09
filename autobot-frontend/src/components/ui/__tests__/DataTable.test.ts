// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * DataTable empty-state prop tests (#6874)
 *
 * The empty-state slot in DataTable.vue passes `:message` to <EmptyState>.
 * The previous claim in #6874 was that EmptyState expects `:description` —
 * but the source of truth (EmptyState.vue defineProps) shows `message`.
 * The actual mismatch was in EmptyState.stories.ts (which used `description`
 * as an argType + arg name, making Storybook stories render blank body text).
 *
 * These tests pin the contract: DataTable empty-state passes the
 * caller-provided text through to EmptyState.message and that prop renders.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import DataTable from '../DataTable.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      ui: {
        dataTable: {
          loading: 'Loading…',
          noDataAvailable: 'No data available',
          noItemsToDisplay: 'No items to display',
          dataTable: 'Data table',
          actions: 'Actions',
          sortBy: 'Sort by {column}',
        },
      },
    },
  },
})

const mountDataTable = (props: Record<string, unknown> = {}) =>
  mount(DataTable, {
    props: {
      data: [],
      columns: [{ key: 'name', label: 'Name' }],
      loading: false,
      ...props,
    },
    global: {
      plugins: [i18n],
      stubs: { Icon: true, LoadingSpinner: true },
    },
  })

describe('DataTable empty state (#6874)', () => {
  it('renders the default empty message when no rows are passed', () => {
    const wrapper = mountDataTable({ data: [] })

    const emptyState = wrapper.findComponent({ name: 'EmptyState' })
    expect(emptyState.exists()).toBe(true)
    // The default falls through to t('ui.dataTable.noItemsToDisplay').
    expect(emptyState.props('message')).toBe('No items to display')
  })

  it('passes a custom emptyMessage prop to EmptyState.message', () => {
    const wrapper = mountDataTable({
      data: [],
      emptyMessage: 'Nothing to show here yet',
    })

    const emptyState = wrapper.findComponent({ name: 'EmptyState' })
    expect(emptyState.props('message')).toBe('Nothing to show here yet')
  })

  it('renders the message text in the DOM (not blank)', () => {
    const wrapper = mountDataTable({
      data: [],
      emptyMessage: 'Concrete empty body text',
    })

    // EmptyState.vue renders <p class="empty-message">{{ message }}</p>.
    // If the prop name were wrong (the original #6874 premise), this DOM
    // assertion would fail.
    expect(wrapper.text()).toContain('Concrete empty body text')
  })

  it('does not render the empty state when rows are present', () => {
    const wrapper = mountDataTable({
      data: [{ name: 'Alice' }, { name: 'Bob' }],
    })

    const emptyState = wrapper.findComponent({ name: 'EmptyState' })
    expect(emptyState.exists()).toBe(false)
  })
})
