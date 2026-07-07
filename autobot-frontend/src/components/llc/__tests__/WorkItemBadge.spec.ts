// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #11076 part 3 — shared WorkItemBadge: localized label + color/size/variant classes.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

import WorkItemBadge from '../WorkItemBadge.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const t = i18n.global.t as (key: string) => string

function mountBadge(props: Record<string, unknown>) {
  return mount(WorkItemBadge, { props, global: { plugins: [i18n] } })
}

describe('WorkItemBadge', () => {
  it('renders a type pill with the localized label and md size by default', () => {
    const w = mountBadge({ kind: 'type', value: 'epic' })
    const span = w.get('span')
    expect(span.classes()).toEqual(expect.arrayContaining(['wib', 'wib--md', 'type-epic']))
    expect(span.text()).toBe(t('llc.enums.workItemType.epic'))
  })

  it('maps kind to the matching label + color class for status and priority', () => {
    const status = mountBadge({ kind: 'status', value: 'in_progress' })
    expect(status.get('span').classes()).toContain('status-in_progress')
    expect(status.get('span').text()).toBe(t('llc.enums.workItemStatus.in_progress'))

    const priority = mountBadge({ kind: 'priority', value: 'critical' })
    expect(priority.get('span').classes()).toContain('priority-critical')
    expect(priority.get('span').text()).toBe(t('llc.enums.priority.critical'))
  })

  it('honors the size prop for pills', () => {
    expect(mountBadge({ kind: 'type', value: 'bug', size: 'xs' }).get('span').classes()).toContain('wib--xs')
    expect(mountBadge({ kind: 'type', value: 'bug', size: 'sm' }).get('span').classes()).toContain('wib--sm')
  })

  it('renders the dot variant with dot color/size class, a title, and no text', () => {
    const w = mountBadge({ kind: 'priority', value: 'high', variant: 'dot', size: 'xs' })
    const span = w.get('span')
    expect(span.classes()).toEqual(expect.arrayContaining(['wib-dot', 'wib-dot--xs', 'dot-high']))
    expect(span.attributes('title')).toBe(t('llc.enums.priority.high'))
    expect(span.text()).toBe('')
  })

  it('falls back to the humanized raw value when no translation key exists', () => {
    const w = mountBadge({ kind: 'status', value: 'weird_custom' })
    expect(w.get('span').text()).toBe('weird custom')
  })

  it('renders empty for a null value', () => {
    const w = mountBadge({ kind: 'type', value: null })
    expect(w.get('span').text()).toBe('')
  })
})
