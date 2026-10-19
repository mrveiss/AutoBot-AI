<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  LanguageSwitcher -- the one language picker for both apps (#18354).

  Presentational: the app supplies the current locale, the options (labelled
  by endonym, see utils/locales.ts) and its translated accessible label, and
  applies the change itself on `update:modelValue`. Two variants:
    select -- a labelled native <select> (the SLM sidebar);
    menu   -- an icon button opening a listbox (a nav bar). Opening focuses
              the current language; Arrow keys move (wrapping), Home/End
              jump, Enter/Space choose; a choice or Escape closes it and
              returns focus to the button; an outside click closes it.
  Token-only styling.
-->
<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import type { LocaleOption } from '../utils/locales'

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: LocaleOption[]
    /** Translated accessible name, e.g. "Language". */
    label: string
    variant?: 'select' | 'menu'
  }>(),
  { variant: 'select' },
)

const emit = defineEmits<{ 'update:modelValue': [code: string] }>()

const uid = useId()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
/** Indexed by option position (a v-for ref array does not keep source order). */
const optionEls: HTMLElement[] = []
/** The option holding the one Tab stop in the open list. */
const active = ref(0)

function setOptionEl(el: unknown, index: number): void {
  if (el instanceof HTMLElement) optionEls[index] = el
}

function selectedIndex(): number {
  return Math.max(0, props.options.findIndex((o) => o.code === props.modelValue))
}

function focusOption(index: number): void {
  active.value = index
  nextTick(() => optionEls[index]?.focus())
}

function toggle(): void {
  open.value = !open.value
  if (open.value) focusOption(selectedIndex())
}

function close(): void {
  open.value = false
  nextTick(() => trigger.value?.focus())
}

function choose(code: string): void {
  if (props.variant === 'menu') close()
  if (code !== props.modelValue) emit('update:modelValue', code)
}

/** WAI-ARIA listbox: arrows wrap, Home/End jump. */
function onOptionKey(event: KeyboardEvent, index: number): void {
  const count = props.options.length
  const target = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: count - 1 }[event.key]
  if (target === undefined) return
  event.preventDefault()
  focusOption((target + count) % count)
}

function onOutside(event: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(event.target as Node)) open.value = false
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) close()
}

onMounted(() => document.addEventListener('click', onOutside))
onBeforeUnmount(() => document.removeEventListener('click', onOutside))
</script>

<template>
  <div ref="root" class="aui-lang" @keydown="onKey">
    <template v-if="variant === 'select'">
      <label :for="`${uid}-lang`" class="aui-lang__sr">{{ label }}</label>
      <select
        :id="`${uid}-lang`"
        class="aui-lang__select"
        :value="modelValue"
        @change="choose(($event.target as HTMLSelectElement).value)"
      >
        <option v-for="o in options" :key="o.code" :value="o.code" :lang="o.code">{{ o.label }}</option>
      </select>
    </template>
    <template v-else>
      <button
        ref="trigger"
        type="button"
        class="aui-lang__trigger"
        :aria-label="label"
        :aria-expanded="open"
        aria-haspopup="listbox"
        :aria-controls="`${uid}-list`"
        @click="toggle"
      >
        <svg class="aui-lang__globe" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18" />
        </svg>
      </button>
      <ul v-if="open" :id="`${uid}-list`" role="listbox" class="aui-lang__list" :aria-label="label">
        <li
          v-for="(o, i) in options"
          :key="o.code"
          :ref="(el: unknown) => setOptionEl(el, i)"
          role="option"
          :tabindex="i === active ? 0 : -1"
          :lang="o.code"
          :aria-selected="o.code === modelValue"
          class="aui-lang__option"
          :class="{ 'is-on': o.code === modelValue }"
          @click="choose(o.code)"
          @keydown.enter.prevent="choose(o.code)"
          @keydown.space.prevent="choose(o.code)"
          @keydown="onOptionKey($event, i)"
        >
          {{ o.label }}
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.aui-lang {
  position: relative;
  font-family: var(--aui-font-sans);
}

.aui-lang__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

.aui-lang__select {
  width: 100%;
  padding: var(--aui-space-2) var(--aui-space-3);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
  color: var(--aui-color-text);
  font-size: var(--aui-text-sm);
}

.aui-lang__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--aui-space-2);
  border: 0;
  border-radius: var(--aui-radius-md);
  background: transparent;
  color: var(--aui-color-text-muted);
  cursor: pointer;
  transition: color var(--aui-transition-fast);
}

.aui-lang__trigger:hover {
  color: var(--aui-color-text);
}

.aui-lang__select:focus-visible,
.aui-lang__trigger:focus-visible,
.aui-lang__option:focus-visible {
  outline: 2px solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-lang__globe {
  width: 1.25rem;
  height: 1.25rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
}

.aui-lang__list {
  position: absolute;
  inset-inline-end: 0;
  z-index: var(--aui-z-dropdown);
  min-width: 10rem;
  margin: var(--aui-space-1) 0 0;
  padding: var(--aui-space-1);
  list-style: none;
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface-raised);
  box-shadow: var(--aui-shadow-md);
}

.aui-lang__option {
  padding: var(--aui-space-2) var(--aui-space-3);
  border-radius: var(--aui-radius-sm);
  color: var(--aui-color-text);
  font-size: var(--aui-text-sm);
  cursor: pointer;
}

.aui-lang__option:hover,
.aui-lang__option.is-on {
  background: var(--aui-color-surface-sunken);
}

.aui-lang__option.is-on {
  font-weight: var(--aui-font-weight-semibold);
}
</style>
