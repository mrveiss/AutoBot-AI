// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the folder path -- kit Breadcrumb (last crumb is the current page) and the typed path field.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import FilePathNavigation from '../FilePathNavigation.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountNav = (currentPath = '/a/b') =>
  mount(FilePathNavigation, { props: { currentPath }, global: { plugins: [i18n], stubs: { Icon: true } } })

describe('FilePathNavigation (#22349)', () => {
  it('marks the last crumb as the current page', () => {
    const wrapper = mountNav()
    const current = wrapper.findAll('[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0].text()).toContain('b')
  })

  it('a crumb click emits the path up to that crumb', async () => {
    const wrapper = mountNav()
    const crumbs = wrapper.findAll('nav button')
    await crumbs[1].trigger('click')
    expect(wrapper.emitted('navigate-to-path')?.[0]).toEqual(['/a'])
    await crumbs[0].trigger('click')
    expect(wrapper.emitted('navigate-to-path')?.[1]).toEqual(['/'])
  })

  it('Enter in the path field and the Go button emit the typed path', async () => {
    const wrapper = mountNav('/')
    const input = wrapper.get('[data-testid="path-input"]')
    await input.setValue('/x/y')
    await input.trigger('keyup', { key: 'Enter' })
    expect(wrapper.emitted('navigate-to-path')?.[0]).toEqual(['/x/y'])
    await wrapper.get('[data-testid="path-go"]').trigger('click')
    expect(wrapper.emitted('navigate-to-path')?.[1]).toEqual(['/x/y'])
  })

  it('follows an external path change', async () => {
    const wrapper = mountNav('/')
    await wrapper.setProps({ currentPath: '/moved' })
    expect((wrapper.get('[data-testid="path-input"]').element as HTMLInputElement).value).toBe('/moved')
  })
})
