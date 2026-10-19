// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// LanguageSwitcher (#18354): the one language picker for both apps. Pins the
// select and menu variants' contract -- an accessible name, endonym labels,
// update:modelValue only on a real change, and the menu closing on a choice,
// Escape or an outside click -- with listbox keyboard navigation and focus
// returned to its button.

import { describe, it, expect, afterEach } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import LanguageSwitcher from '../LanguageSwitcher.vue'
import { LOCALE_ENDONYMS, localeOptions } from '../../utils/locales'

const options = localeOptions(['en', 'de', 'he'])
let wrapper: VueWrapper | null = null

function mountSwitcher(variant: 'select' | 'menu' = 'select') {
  wrapper = mount(LanguageSwitcher, {
    props: { modelValue: 'en', options, label: 'Language', variant },
    attachTo: document.body,
  })
  return wrapper
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('localeOptions', () => {
  it('labels each code by its endonym, and an unknown code by itself', () => {
    expect(localeOptions(['de', 'xx'])).toEqual([
      { code: 'de', label: 'Deutsch' },
      { code: 'xx', label: 'xx' },
    ])
    expect(Object.keys(LOCALE_ENDONYMS)).toHaveLength(11)
  })
})

describe('LanguageSwitcher select', () => {
  it('is a labelled select whose options carry endonyms and their own lang', () => {
    const w = mountSwitcher()
    const select = w.get('select')
    expect(w.get(`label[for="${select.attributes('id')}"]`).text()).toBe('Language')
    expect(w.findAll('option').map((o) => [o.text(), o.attributes('lang')])).toEqual([
      ['English', 'en'],
      ['Deutsch', 'de'],
      ['עברית', 'he'],
    ])
  })

  it('emits only when the language actually changes', async () => {
    const w = mountSwitcher()
    await w.get('select').setValue('en')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    await w.get('select').setValue('de')
    expect(w.emitted('update:modelValue')).toEqual([['de']])
  })
})

describe('LanguageSwitcher menu', () => {
  it('opens a listbox from a named button and closes it on a choice', async () => {
    const w = mountSwitcher('menu')
    const button = w.get('button')
    expect(button.attributes('aria-label')).toBe('Language')
    expect(button.attributes('aria-expanded')).toBe('false')

    await button.trigger('click')
    expect(button.attributes('aria-expanded')).toBe('true')
    const selected = w.findAll('[role="option"]').filter((o) => o.attributes('aria-selected') === 'true')
    expect(selected.map((o) => o.text())).toEqual(['English'])

    await w.findAll('[role="option"]')[1].trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([['de']])
    expect(w.find('[role="listbox"]').exists()).toBe(false)
  })

  it('closes on Escape and on a click outside', async () => {
    const w = mountSwitcher('menu')
    await w.get('button').trigger('click')
    await w.get('.aui-lang').trigger('keydown', { key: 'Escape' })
    expect(w.find('[role="listbox"]').exists()).toBe(false)

    await w.get('button').trigger('click')
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await w.vm.$nextTick()
    expect(w.find('[role="listbox"]').exists()).toBe(false)
  })

  it('focuses the current language on open, and one option is the Tab stop', async () => {
    const w = mountSwitcher('menu')
    await w.get('button').trigger('click')
    await flushPromises()
    const opts = w.findAll('[role="option"]')
    expect(document.activeElement).toBe(opts[0].element)
    expect(opts.map((o) => o.attributes('tabindex'))).toEqual(['0', '-1', '-1'])
  })

  it('moves with the arrow keys (wrapping) and Home/End, then chooses with Enter', async () => {
    const w = mountSwitcher('menu')
    await w.get('button').trigger('click')
    await flushPromises()
    const opts = () => w.findAll('[role="option"]')
    await opts()[0].trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect(document.activeElement).toBe(opts()[2].element)
    await opts()[2].trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(document.activeElement).toBe(opts()[0].element)
    await opts()[0].trigger('keydown', { key: 'End' })
    await flushPromises()
    expect(document.activeElement).toBe(opts()[2].element)
    expect(opts()[2].attributes('tabindex')).toBe('0')
    await opts()[2].trigger('keydown', { key: 'Home' })
    await opts()[0].trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    await opts()[1].trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(w.emitted('update:modelValue')).toEqual([['de']])
    expect(document.activeElement).toBe(w.get('button').element)
  })

  it('returns focus to the button on Escape', async () => {
    const w = mountSwitcher('menu')
    await w.get('button').trigger('click')
    await flushPromises()
    await w.findAll('[role="option"]')[0].trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(w.find('[role="listbox"]').exists()).toBe(false)
    expect(document.activeElement).toBe(w.get('button').element)
  })
})
