<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts" generic="T extends DashboardWidget">
/**
 * 12-column dashboard grid (#18242, spec §4.4).
 *
 * Widgets take a span of 4/6/8/12 columns (`--widget-s/m/l/full`) and a height in px.
 * In edit mode a widget can be moved by pointer drag or by keyboard grab mode, and
 * resized with its width and height buttons. Every change goes out through
 * `update:widgets`. The parent persists it (useDashboardLayout); this component holds
 * no storage. Styled with token utility classes only: no component-local style block (#12730).
 */
import { computed, nextTick, ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import {
  HEIGHT_STEP,
  WIDGET_SPANS,
  clampHeight,
  moveWidget,
  stepSpan,
  type DashboardWidget,
} from '@/composables/dashboard/dashboardLayoutModel'
import { useDashboardGrabMode } from '@/composables/dashboard/useDashboardGrabMode'

const props = defineProps<{
  widgets: T[]
  editing: boolean
  /** The name a widget is announced by; the view translates stored i18n keys here. */
  labelOf?: (widget: T) => string
}>()

const emit = defineEmits<{ 'update:widgets': [widgets: T[]] }>()
defineSlots<{ widget(props: { widget: T }): unknown }>()
const { t } = useI18n()

const model = computed({
  get: () => props.widgets,
  set: (next: T[]) => emit('update:widgets', next),
})
const label = (w: T) => props.labelOf?.(w) || w.title || w.type
const { grabbedId, announcement, onKeydown, cancel } = useDashboardGrabMode(model, label)
const editing = toRef(props, 'editing')
const draggingId = ref<string | null>(null)

// Leaving edit mode mid-grab (Done, Save) puts the widget back; no outline or grab outlives it.
watch(editing, (on) => {
  if (!on && grabbedId.value) cancel()
})

const SPAN_TOKEN: Record<number, string> = { 4: '--widget-s', 6: '--widget-m', 8: '--widget-l', 12: '--widget-full' }

function itemStyle(w: DashboardWidget): Record<string, string> {
  return { '--item-span': `var(${SPAN_TOKEN[w.span]})`, '--item-height': `${w.height}px` }
}

const root = ref<HTMLElement | null>(null)
// True while a keyboard move re-renders the keyed list: moving a node can blur its handle,
// and that blur is ours, not the user leaving, so it must not cancel the grab.
let moving = false

async function handleKeydown(id: string, e: KeyboardEvent): Promise<void> {
  if (!editing.value || !onKeydown(id, e)) return
  e.preventDefault()
  moving = true
  await nextTick()
  root.value?.querySelector<HTMLElement>(`[data-grab-handle="${CSS.escape(id)}"]`)?.focus()
  moving = false
}

// Leaving the handle while a widget is grabbed puts it back, as Escape would.
function handleBlur(id: string): void {
  if (!moving && grabbedId.value === id) cancel()
}

// Only span/height change here; the result keeps every field of the caller's own widget type.
function patch(id: string, change: Pick<Partial<DashboardWidget>, 'span' | 'height'>): void {
  model.value = props.widgets.map((w) => (w.id === id ? ({ ...w, ...change } as T) : w))
}

function resizeWidth(w: DashboardWidget, dir: 1 | -1): void {
  patch(w.id, { span: stepSpan(w.span, dir) })
}

function resizeHeight(w: DashboardWidget, dir: 1 | -1): void {
  patch(w.id, { height: clampHeight(w.height + dir * HEIGHT_STEP) })
}

function onDragStart(id: string, e: DragEvent): void {
  draggingId.value = id
  e.dataTransfer?.setData('text/plain', id)
}

function onDrop(targetId: string): void {
  const from = props.widgets.findIndex((w) => w.id === draggingId.value)
  const to = props.widgets.findIndex((w) => w.id === targetId)
  draggingId.value = null
  if (from < 0 || to < 0 || from === to) return
  model.value = moveWidget(props.widgets, from, to - from)
}

const atMinSpan = (w: DashboardWidget) => w.span === WIDGET_SPANS[0]
const atMaxSpan = (w: DashboardWidget) => w.span === WIDGET_SPANS[WIDGET_SPANS.length - 1]
</script>

<template>
  <div ref="root" class="grid grid-cols-12 gap-(--stack)">
    <section
      v-for="w in widgets"
      :key="w.id"
      class="relative col-span-(--item-span) h-(--item-height) overflow-auto rounded-lg border bg-autobot-bg-card border-autobot-border max-md:col-span-12"
      :class="{
        'cursor-grab border-dashed': editing,
        'outline-2 outline-offset-2 outline-autobot-focus': grabbedId === w.id,
        'opacity-50': draggingId === w.id,
      }"
      :style="itemStyle(w)"
      :draggable="editing"
      @dragstart="onDragStart(w.id, $event)"
      @dragover.prevent
      @drop.prevent="onDrop(w.id)"
      @dragend="draggingId = null"
    >
      <div v-if="editing" class="flex justify-end gap-0.5 border-b border-autobot-border bg-autobot-bg-elevated p-1">
        <button
          type="button"
          class="cursor-grab rounded-md px-1.5 text-autobot-text-secondary focus-visible:outline-2 focus-visible:outline-autobot-focus"
          :data-grab-handle="w.id"
          :aria-pressed="grabbedId === w.id"
          :aria-roledescription="t('dashboardGrid.movableWidget')"
          :aria-label="t('dashboardGrid.widgetLabel', { name: label(w) })"
          aria-describedby="dashboard-grid-help"
          @keydown="handleKeydown(w.id, $event)"
          @blur="handleBlur(w.id)"
        >⠿</button>
        <BaseButton size="sm" variant="ghost" :aria-label="t('dashboardGrid.narrower')" :disabled="atMinSpan(w)" @click="resizeWidth(w, -1)">−</BaseButton>
        <BaseButton size="sm" variant="ghost" :aria-label="t('dashboardGrid.wider')" :disabled="atMaxSpan(w)" @click="resizeWidth(w, 1)">+</BaseButton>
        <BaseButton size="sm" variant="ghost" :aria-label="t('dashboardGrid.shorter')" @click="resizeHeight(w, -1)">↑</BaseButton>
        <BaseButton size="sm" variant="ghost" :aria-label="t('dashboardGrid.taller')" @click="resizeHeight(w, 1)">↓</BaseButton>
      </div>
      <slot name="widget" :widget="w" />
    </section>
    <p id="dashboard-grid-help" class="sr-only">{{ t('dashboardGrid.keyboardHelp') }}</p>
    <div class="sr-only" aria-live="polite" aria-atomic="true">{{ announcement }}</div>
  </div>
</template>
