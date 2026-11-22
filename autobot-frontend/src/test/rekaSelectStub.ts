// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A stand-in for `reka-ui` in specs that choose an option of the kit's `BaseSelectMenu`.
 *
 * The kit's select is built on reka-ui, whose popper does not run in jsdom. This keeps the kit
 * component real and renders every option as a button (`data-option`) that picks its value when
 * clicked and is `disabled` when the option is. Use it as
 * `vi.mock('reka-ui', async () => (await import('@/test/rekaSelectStub')).rekaSelectStub())`.
 */
import { defineComponent, h, inject, provide } from 'vue'

const PASSTHROUGH = [
  'SelectContent', 'SelectItemText', 'SelectPortal', 'SelectValue', 'SelectViewport',
  'PopoverContent', 'PopoverPortal', 'PopoverRoot', 'PopoverTrigger',
  'TabsContent', 'TabsList', 'TabsRoot', 'TabsTrigger',
  'AccordionContent', 'AccordionHeader', 'AccordionItem', 'AccordionRoot', 'AccordionTrigger',
  'DropdownMenuContent', 'DropdownMenuItem', 'DropdownMenuPortal', 'DropdownMenuRoot', 'DropdownMenuSeparator', 'DropdownMenuTrigger',
]

const passthrough = (name: string) =>
  defineComponent({ name, setup: (_, { slots }) => () => h('div', slots.default?.()) })

const SelectRoot = defineComponent({
  name: 'SelectRoot',
  props: { modelValue: { type: String, default: '' }, disabled: Boolean },
  emits: ['update:modelValue'],
  setup(props, { slots, emit }) {
    provide('pick', (v: string) => emit('update:modelValue', v))
    const attrs = () => ({ 'data-select-value': props.modelValue, 'data-select-disabled': String(props.disabled) })
    return () => h('div', attrs(), slots.default?.())
  },
})

const SelectItem = defineComponent({
  name: 'SelectItem',
  props: { value: { type: String, required: true }, disabled: Boolean },
  setup(props, { slots }) {
    const pick = inject<(v: string) => void>('pick')!
    const attrs = () => ({ type: 'button', 'data-option': props.value, disabled: props.disabled, onClick: () => pick(props.value) })
    return () => h('button', attrs(), slots.default?.())
  },
})

const SelectTrigger = defineComponent({
  name: 'SelectTrigger',
  setup: (_, { slots, attrs }) => () => h('button', { type: 'button', 'data-trigger': '', ...attrs }, slots.default?.()),
})

export function rekaSelectStub(): Record<string, unknown> {
  return Object.fromEntries([
    ['SelectRoot', SelectRoot],
    ['SelectItem', SelectItem],
    ['SelectTrigger', SelectTrigger],
    ...PASSTHROUGH.map((n) => [n, passthrough(n)]),
  ])
}
