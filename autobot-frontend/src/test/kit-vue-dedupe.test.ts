// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #17959: the in-tree @autobot/ui kit must share the app's single Vue instance.
// The kit's useToast() calls inject() from ITS `vue` import; with a second Vue
// copy there is no current instance for that inject(), so it silently returns
// the singleton instead of the value the app provided.
import { describe, it, expect } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useToast, TOAST_INJECT_KEY, type UseToastReturn } from '@autobot/ui'

describe('@autobot/ui shares the app Vue instance (#17959)', () => {
  it('kit inject() receives a value provided through the app', () => {
    const appProvided = { __marker: 'app-provided' } as unknown as UseToastReturn
    let seen: UseToastReturn | undefined
    const Probe = defineComponent({
      setup() {
        seen = useToast()
        return () => h('div')
      },
    })
    mount(Probe, { global: { provide: { [TOAST_INJECT_KEY as symbol]: appProvided } } })
    expect(seen).toBe(appProvided)
  })
})
