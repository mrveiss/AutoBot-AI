// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useFocusRestore, trigger mode (#14780 review): focus returns to the trigger when the flag
// goes false AND when the owner is unmounted while the flag is still true (a parent v-if
// removing an open dialog). Before the fix only the first case restored.

import { describe, it, expect, afterEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref, type Ref } from 'vue'
import { useFocusRestore } from '../useFocusRestore'

function probe(active: Ref<boolean>) {
  return defineComponent({
    setup() {
      useFocusRestore(active)
      return () => h('button', { class: 'inside' }, 'inside')
    },
  })
}

let trigger: HTMLButtonElement
let wrapper: VueWrapper | null = null

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

function focusTrigger(): void {
  trigger = document.createElement('button')
  document.body.appendChild(trigger)
  trigger.focus()
}

describe('useFocusRestore (trigger mode)', () => {
  it('restores focus to the trigger when the flag goes false', async () => {
    focusTrigger()
    const active = ref(true)
    wrapper = mount(probe(active), { attachTo: document.body })
    ;(wrapper.find('.inside').element as HTMLElement).focus()
    active.value = false
    await nextTick()
    expect(document.activeElement).toBe(trigger)
  })

  it('restores focus to the trigger when unmounted while still active', () => {
    // fails if only the flag's true -> false transition restores focus
    focusTrigger()
    wrapper = mount(probe(ref(true)), { attachTo: document.body })
    ;(wrapper.find('.inside').element as HTMLElement).focus()
    wrapper.unmount()
    wrapper = null
    expect(document.activeElement).toBe(trigger)
  })

  it('contrast: unmounting while inactive moves no focus', () => {
    focusTrigger()
    const other = document.createElement('input')
    document.body.appendChild(other)
    wrapper = mount(probe(ref(false)), { attachTo: document.body })
    other.focus()
    wrapper.unmount()
    wrapper = null
    expect(document.activeElement).toBe(other)
  })
})
