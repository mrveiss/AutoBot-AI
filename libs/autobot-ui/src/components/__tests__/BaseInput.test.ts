// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseInput behavioral tests (#14778). Covers v-model both ways, the
// label/for linkage, the error and helper aria wiring, every ported prop and
// both slots — the main app's four llc views and the showcase depend on it.

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import inputSource from '../BaseInput.vue?raw'
import BaseInput, { type InputSize, type InputType } from '../BaseInput.vue'

const SIZES: InputSize[] = ['sm', 'md', 'lg']
const TYPES: InputType[] = ['text', 'email', 'password', 'search', 'tel', 'url']

describe('BaseInput', () => {
  it('renders a real <input> with defaults: type=text, size=md, no label', () => {
    // fails if the root stops being a native <input> or a default silently changes
    const wrapper = mount(BaseInput)
    const input = wrapper.get('input')
    expect(input.attributes('type')).toBe('text')
    expect(wrapper.classes()).toContain('aui-input--md')
    expect(wrapper.find('label').exists()).toBe(false)
  })

  it('shows modelValue in the field', () => {
    // fails if :value stops reading modelValue (parent -> input direction of v-model)
    const wrapper = mount(BaseInput, { props: { modelValue: 'hello' } })
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('hello')
  })

  it('emits update:modelValue with the typed string', async () => {
    // fails if typing stops emitting update:modelValue (input -> parent direction)
    const wrapper = mount(BaseInput)
    await wrapper.get('input').setValue('abc')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['abc'])
  })

  it('ties <label for> to the input id when label is given', () => {
    // fails if the label's `for` and the input's `id` diverge (click-to-focus and the accessible name break)
    const wrapper = mount(BaseInput, { props: { label: 'Name' } })
    const label = wrapper.get('label')
    expect(label.text()).toBe('Name')
    expect(label.attributes('for')).toBeTruthy()
    expect(label.attributes('for')).toBe(wrapper.get('input').attributes('id'))
  })

  it('uses an explicit id for the input and its label', () => {
    // fails if a caller's id is ignored, so a form's own label or test hook cannot target the field
    const wrapper = mount(BaseInput, { props: { label: 'Email', id: 'signup-email' } })
    expect(wrapper.get('input').attributes('id')).toBe('signup-email')
    expect(wrapper.get('label').attributes('for')).toBe('signup-email')
  })

  it('passes autocomplete to the native input, and omits it when not given', () => {
    // fails if autocomplete is dropped, so password managers and autofill lose the field
    expect(mount(BaseInput, { props: { autocomplete: 'email' } }).get('input').attributes('autocomplete')).toBe('email')
    expect(mount(BaseInput).get('input').attributes('autocomplete')).toBeUndefined()
  })

  it('gives two instances in one app distinct ids', () => {
    // fails if the generated id is constant, so two labels target the same input.
    // useId() is unique per app, so both inputs must share one app, as on a real page.
    const Pair = defineComponent({
      render: () => h('div', [h(BaseInput, { label: 'A' }), h(BaseInput, { label: 'B' })]),
    })
    const [a, b] = mount(Pair).findAll('input').map((i) => i.attributes('id'))
    expect(a).toBeTruthy()
    expect(a).not.toBe(b)
  })

  it('marks the asterisk aria-hidden and sets required on the input', () => {
    // fails if required stops reaching the native input or the asterisk is read aloud
    const wrapper = mount(BaseInput, { props: { label: 'Name', required: true } })
    expect(wrapper.get('input').attributes('required')).toBeDefined()
    expect(wrapper.get('.aui-input__asterisk').attributes('aria-hidden')).toBe('true')
  })

  it('sets aria-invalid and points aria-describedby at the error text', () => {
    // fails if an error is shown visually but not exposed to assistive tech
    const wrapper = mount(BaseInput, { props: { error: 'Bad value', helperText: 'Help' } })
    const input = wrapper.get('input')
    const error = wrapper.get('.aui-input__error')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(input.attributes('aria-describedby')).toBe(error.attributes('id'))
    expect(error.text()).toBe('Bad value')
    expect(wrapper.find('.aui-input__helper').exists()).toBe(false)
  })

  it('points aria-describedby at the helper text and omits aria-invalid', () => {
    // fails if the helper text loses its id link, or aria-invalid is rendered as "false"
    const wrapper = mount(BaseInput, { props: { helperText: 'Help' } })
    const input = wrapper.get('input')
    expect(input.attributes('aria-describedby')).toBe(wrapper.get('.aui-input__helper').attributes('id'))
    expect(input.attributes('aria-invalid')).toBeUndefined()
  })

  it("keeps the caller's aria-describedby ids and appends the generated one", () => {
    // fails if the generated helper/error id replaces external help text the caller linked
    const attrs = { 'aria-describedby': 'outside-hint' }
    const helper = mount(BaseInput, { props: { helperText: 'Help' }, attrs })
    expect(helper.get('input').attributes('aria-describedby')).toBe(`outside-hint ${helper.get('.aui-input__helper').attributes('id')}`)
    const error = mount(BaseInput, { props: { error: 'Bad' }, attrs })
    expect(error.get('input').attributes('aria-describedby')).toBe(`outside-hint ${error.get('.aui-input__error').attributes('id')}`)
    // Contrast: with no helper or error, the caller's ids alone remain.
    expect(mount(BaseInput, { attrs }).get('input').attributes('aria-describedby')).toBe('outside-hint')
  })

  it("keeps the caller's aria-invalid unless error sets it", () => {
    // fails if a caller's validation state is dropped because the kit shows no error text
    expect(mount(BaseInput, { attrs: { 'aria-invalid': 'true' } }).get('input').attributes('aria-invalid')).toBe('true')
    // Contrast: error overrides a caller's "false", and nothing set means no attribute.
    const both = mount(BaseInput, { props: { error: 'Bad' }, attrs: { 'aria-invalid': 'false' } })
    expect(both.get('input').attributes('aria-invalid')).toBe('true')
    expect(mount(BaseInput).get('input').attributes('aria-invalid')).toBeUndefined()
  })

  it('omits aria-describedby when there is neither helper nor error', () => {
    // fails if aria-describedby dangles at an element that does not exist
    expect(mount(BaseInput).get('input').attributes('aria-describedby')).toBeUndefined()
  })

  it('applies disabled to the input and the control', () => {
    // fails if disabled stops reaching the native input or its visual state
    const wrapper = mount(BaseInput, { props: { disabled: true } })
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.aui-input__control').classes()).toContain('aui-input__control--disabled')
  })

  it('applies readonly to the input', () => {
    // fails if readonly stops reaching the native input
    const wrapper = mount(BaseInput, { props: { readonly: true } })
    expect(wrapper.get('input').attributes('readonly')).toBeDefined()
  })

  it.each(TYPES)('forwards type=%s to the native input', (type) => {
    // fails if the `:type` binding is dropped or hardcoded
    expect(mount(BaseInput, { props: { type } }).get('input').attributes('type')).toBe(type)
  })

  it.each(SIZES)('applies the aui-input--%s class for size=%s', (size) => {
    // fails if a size stops mapping to its own class (heights come from the size tokens)
    expect(mount(BaseInput, { props: { size } }).classes()).toContain(`aui-input--${size}`)
  })

  it('forwards placeholder to the input', () => {
    // fails if the placeholder prop stops reaching the native input
    const wrapper = mount(BaseInput, { props: { placeholder: 'Type here' } })
    expect(wrapper.get('input').attributes('placeholder')).toBe('Type here')
  })

  it('renders the prefix and suffix slots around the field', () => {
    // fails if a slot is dropped or rendered on the wrong side of the input
    const wrapper = mount(BaseInput, { slots: { prefix: '<i class="pre">$</i>', suffix: '<i class="suf">USD</i>' } })
    const html = wrapper.get('.aui-input__control').html()
    expect(html.indexOf('class="pre"')).toBeLessThan(html.indexOf('<input'))
    expect(html.indexOf('class="suf"')).toBeGreaterThan(html.indexOf('<input'))
  })

  it('renders no affix wrappers without slots', () => {
    // fails if empty affix spans are rendered and add stray gap/padding
    expect(mount(BaseInput).find('.aui-input__affix').exists()).toBe(false)
  })

  it('shows the clear button only when clearable and non-empty, labelled by clearLabel', () => {
    // fails if the clear button shows on an empty field or has no accessible name
    const empty = mount(BaseInput, { props: { clearable: true, clearLabel: 'Clear' } })
    expect(empty.find('.aui-input__clear').exists()).toBe(false)
    const filled = mount(BaseInput, { props: { clearable: true, clearLabel: 'Clear', modelValue: 'x' } })
    expect(filled.get('.aui-input__clear').attributes('aria-label')).toBe('Clear')
  })

  it('clear empties the value and emits clear', async () => {
    // fails if clicking clear leaves the value or skips the clear event
    const wrapper = mount(BaseInput, { props: { clearable: true, clearLabel: 'Clear', modelValue: 'x' } })
    await wrapper.get('.aui-input__clear').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([''])
    expect(wrapper.emitted('clear')).toHaveLength(1)
  })

  it('does not offer clear on a disabled field', () => {
    // fails if a disabled field can still be wiped through the clear button
    const wrapper = mount(BaseInput, { props: { clearable: true, clearLabel: 'Clear', disabled: true, modelValue: 'x' } })
    expect(wrapper.find('.aui-input__clear').exists()).toBe(false)
  })

  it('renders no nameless clear button and warns when clearable lacks clearLabel', () => {
    // fails if an icon-only clear button renders with no accessible name, or the gap is silent
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const warned = () => spy.mock.calls.some((c) => String(c[0]).includes('clearLabel'))
    for (const clearLabel of [undefined, '', '   ']) {
      const wrapper = mount(BaseInput, { props: { clearable: true, clearLabel, modelValue: 'x' } })
      expect(wrapper.find('.aui-input__clear').exists()).toBe(false)
    }
    expect(warned()).toBe(true)
    spy.mockClear()
    // Contrast: with a name the button renders, named, and nothing is warned.
    const named = mount(BaseInput, { props: { clearable: true, clearLabel: 'Clear', modelValue: 'x' } })
    expect(named.get('.aui-input__clear').attributes('aria-label')).toBe('Clear')
    expect(warned()).toBe(false)
    spy.mockRestore()
  })

  it('puts parent attrs (class, style) on the wrapper, not the input', () => {
    // fails if a consumer's style="max-width" stops constraining the whole field
    const wrapper = mount(BaseInput, { attrs: { style: 'max-width: 300px', class: 'mine' } })
    expect(wrapper.classes()).toContain('mine')
    expect(wrapper.attributes('style')).toContain('max-width')
    expect(wrapper.get('input').classes()).not.toContain('mine')
  })

  it('names a label-less field through aria-label or aria-labelledby on the <input>', () => {
    // fails if the accessible name lands on the wrapper div and the native input stays unnamed
    const named = mount(BaseInput, { attrs: { 'aria-label': 'Search', 'data-testid': 'search' } })
    expect(named.get('input').attributes('aria-label')).toBe('Search')
    expect(named.attributes('aria-label')).toBeUndefined()
    const byRef = mount(BaseInput, { attrs: { 'aria-labelledby': 'heading-1' } })
    expect(byRef.get('input').attributes('aria-labelledby')).toBe('heading-1')
    // Contrast: data-* stays on the wrapper, with class and style.
    expect(named.attributes('data-testid')).toBe('search')
    expect(named.get('input').attributes('data-testid')).toBeUndefined()
  })

  it('forwards native input attrs and listeners to the <input>', async () => {
    // fails if name/maxlength/inputmode or a focus listener stop reaching the field
    let focused = 0
    const wrapper = mount(BaseInput, {
      attrs: { name: 'q', maxlength: '20', inputmode: 'search', onFocus: () => focused++ },
    })
    const input = wrapper.get('input')
    expect([input.attributes('name'), input.attributes('maxlength'), input.attributes('inputmode')]).toEqual(['q', '20', 'search'])
    await input.trigger('focus')
    expect(focused).toBe(1)
  })

  it('style block uses no shadow and no raw colour', () => {
    // jsdom does not apply SFC <style>, so the rules are read from the source.
    // fails if a box-shadow or a literal colour sneaks past the token contract
    const css = inputSource.split('<style scoped>')[1]
    expect(css).not.toMatch(/box-shadow/)
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(css).not.toMatch(/\b(?:rgb|rgba|hsl|hsla)\(/)
  })
})
