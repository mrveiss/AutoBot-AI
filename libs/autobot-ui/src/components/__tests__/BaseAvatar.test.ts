// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseAvatar and initialsOf (#14780): one initials rule; the avatar is named by the person
// unless decorative; size, variant, ring and the presence dot render as asked.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseAvatar from '../BaseAvatar.vue'
import { initialsOf } from '../../utils/initials'

describe('initialsOf', () => {
  it.each([
    ['Ada Lovelace', 'AL'],
    ['ada_lovelace', 'AL'],
    ['grace-brewster-hopper', 'GB'],
    ['first.last', 'FL'],
    ['  spaced   out  ', 'SO'],
    ['admin', 'AD'],
    ['x', 'X'],
    ['Émile Zola', 'ÉZ'],
    ['e\u0301mile Zola', 'ÉZ'], // decomposed accent: the mark stays with its letter
    ['', ''],
  ])('%j gives %j', (name, expected) => {
    expect(initialsOf(name)).toBe(expected)
  })

  it('treats a missing name as empty', () => {
    expect(initialsOf(null)).toBe('')
    expect(initialsOf(undefined)).toBe('')
  })
})

describe('BaseAvatar', () => {
  it('shows the initials and is an image named by the person', () => {
    const w = mount(BaseAvatar, { props: { name: 'Ada Lovelace' } })
    expect(w.text()).toBe('AL')
    expect(w.attributes('role')).toBe('img')
    expect(w.attributes('aria-label')).toBe('Ada Lovelace')
    expect(w.attributes('title')).toBe('Ada Lovelace')
    expect(w.classes()).toEqual(expect.arrayContaining(['aui-avatar--md', 'aui-avatar--neutral']))
  })

  it('decorative: hidden from assistive tech, the name is shown beside it', () => {
    const w = mount(BaseAvatar, { props: { name: 'Ada Lovelace', decorative: true } })
    expect(w.attributes('role')).toBeUndefined()
    expect(w.attributes('aria-label')).toBeUndefined()
    expect(w.attributes('aria-hidden')).toBe('true')
  })

  it('size, variant and ring map to their classes', () => {
    const w = mount(BaseAvatar, { props: { name: 'A B', size: 'xs', variant: 'primary', ring: true } })
    expect(w.classes()).toEqual(expect.arrayContaining(['aui-avatar--xs', 'aui-avatar--primary', 'aui-avatar--ring']))
  })

  it('renders a presence dot only when a status is given', () => {
    expect(mount(BaseAvatar, { props: { name: 'A' } }).find('.aui-avatar__status').exists()).toBe(false)
    const dot = mount(BaseAvatar, { props: { name: 'A', status: 'away' } }).get('.aui-avatar__status')
    expect(dot.attributes('data-status')).toBe('away')
    expect(dot.classes()).toContain('aui-avatar__status--away')
  })
})
