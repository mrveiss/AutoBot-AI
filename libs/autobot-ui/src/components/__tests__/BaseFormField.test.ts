// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// BaseFormField (#14780 group 4): the label is tied to the control; the hint and the error
// describe it; an error marks it invalid and is announced; required shows a marker the
// control also carries.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseFormField from '../BaseFormField.vue'

const control = `<template #default="{ id, describedBy, invalid, required }">
  <input :id="id" :aria-describedby="describedBy" :aria-invalid="invalid" :required="required" />
</template>`

function render(props: Record<string, unknown> = {}) {
  return mount(BaseFormField, {
    props: { label: 'Repository', ...props },
    slots: { default: control },
    attachTo: document.body,
  })
}

describe('BaseFormField', () => {
  it('ties the label to the control through a generated id', () => {
    const w = render()
    const id = w.find('input').attributes('id')
    expect(id).toBeTruthy()
    expect(w.find('label').attributes('for')).toBe(id)
    expect(w.find('label').text()).toBe('Repository')
    expect(w.find('input').attributes('aria-describedby')).toBeUndefined()
    w.unmount()
  })

  it('uses a given id', () => {
    const w = render({ id: 'source-repo' })
    expect(w.find('input').attributes('id')).toBe('source-repo')
    expect(w.find('label').attributes('for')).toBe('source-repo')
    w.unmount()
  })

  it('the hint describes the control', () => {
    const w = render({ id: 'f', hint: 'owner/name' })
    expect(w.find('#f-hint').text()).toBe('owner/name')
    expect(w.find('input').attributes('aria-describedby')).toBe('f-hint')
    w.unmount()
  })

  it('an error is announced, describes the control and marks it invalid', () => {
    const w = render({ id: 'f', hint: 'owner/name', error: 'Repository is required' })
    const error = w.find('#f-error')
    expect(error.attributes('role')).toBe('alert')
    expect(error.text()).toBe('Repository is required')
    expect(w.find('input').attributes('aria-describedby')).toBe('f-hint f-error')
    expect(w.find('input').attributes('aria-invalid')).toBe('true')
    expect(w.classes()).toContain('aui-field--invalid')
    w.unmount()
  })

  it('required shows a hidden marker and is passed to the control', () => {
    const w = render({ required: true })
    const marker = w.find('.aui-field__required')
    expect(marker.attributes('aria-hidden')).toBe('true')
    expect(w.find('input').attributes('required')).toBeDefined()
    w.unmount()
  })

  it("the label's for resolves to this control in the document", () => {
    const w = render()
    const label = w.find('label').element as HTMLLabelElement
    expect(document.getElementById(label.htmlFor)).toBe(w.find('input').element)
    expect(label.control).toBe(w.find('input').element)
    w.unmount()
  })
})
