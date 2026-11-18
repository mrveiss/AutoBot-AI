<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseTooltip — accessible tooltip on the shared tooltip tokens (#18240, #15469).
  The default slot is the trigger and receives `{ describedby }`: bind it to
  the focusable element as `aria-describedby`. Content is `text` or the
  `content` slot (the kit holds no strings). Opens on hover (after
  --aui-tooltip-delay) and on focus (immediately); closes on Esc, blur, and
  leave (after --aui-tooltip-hide-delay). The bubble is hoverable (WCAG 1.4.13):
  it sits inside the root, so moving the pointer onto it cancels the pending
  hide. Mouse events the browser emulates after a touch are ignored. A touch long-press opens it; focus is
  the fallback for keyboard/AT. The bubble is position:absolute, so showing it
  never shifts layout; motion is off under prefers-reduced-motion.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right'

const props = withDefaults(
  defineProps<{
    /** Tooltip text; use the `content` slot for rich content. */
    text?: string
    placement?: TooltipPlacement
    disabled?: boolean
  }>(),
  { text: undefined, placement: 'bottom', disabled: false },
)

const LONG_PRESS_MS = 500
const TOUCH_LINGER_MS = 1500
/** Browsers emulate mouseenter/leave up to ~this long after a touch. */
const EMULATED_MOUSE_MS = 1000

const id = `aui-tooltip-${useId()}`
const root = ref<HTMLElement | null>(null)
const open = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let lastTouchAt = -Infinity

const active = computed(() => open.value && !props.disabled)

/** Read a duration token ("500ms" / "0.5s") off the element; 0 when unset. */
function tokenMs(name: string): number {
  if (!root.value) return 0
  const raw = getComputedStyle(root.value).getPropertyValue(name).trim()
  const n = parseFloat(raw)
  if (Number.isNaN(n)) return 0
  return raw.endsWith('ms') ? n : n * 1000
}

function schedule(next: boolean, ms: number): void {
  clearTimeout(timer)
  if (ms <= 0) {
    open.value = next
    return
  }
  timer = setTimeout(() => {
    open.value = next
  }, ms)
}

const isEmulatedMouse = () => Date.now() - lastTouchAt < EMULATED_MOUSE_MS
const onEnter = () => {
  if (!isEmulatedMouse()) schedule(true, tokenMs('--aui-tooltip-delay'))
}
const onLeave = () => {
  if (!isEmulatedMouse()) schedule(false, tokenMs('--aui-tooltip-hide-delay'))
}
const onFocus = () => schedule(true, 0)
const onBlur = () => schedule(false, 0)

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) schedule(false, 0)
}

function onTouchStart(): void {
  lastTouchAt = Date.now()
  schedule(true, LONG_PRESS_MS)
}

function onTouchEnd(): void {
  lastTouchAt = Date.now()
  // Cancels a press that never reached the threshold; lingers if it did.
  if (open.value) schedule(false, TOUCH_LINGER_MS)
  else clearTimeout(timer)
}

// Esc closes a hover-opened tooltip too, so listen on the window while open.
watch(open, (isOpen) => {
  if (isOpen) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  clearTimeout(timer)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <span
    ref="root"
    class="aui-tooltip"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @focusin="onFocus"
    @focusout="onBlur"
    @touchstart.passive="onTouchStart"
    @touchend="onTouchEnd"
    @touchcancel="onTouchEnd"
  >
    <slot :describedby="id" />
    <span
      :id="id"
      role="tooltip"
      class="aui-tooltip__bubble"
      :class="[`aui-tooltip__bubble--${placement}`, { 'aui-tooltip__bubble--open': active }]"
    >
      <slot name="content">{{ text }}</slot>
    </span>
  </span>
</template>

<style scoped>
.aui-tooltip {
  position: relative;
  display: inline-flex;
}

.aui-tooltip__bubble {
  position: absolute;
  z-index: var(--aui-z-tooltip);
  width: max-content;
  max-width: var(--aui-tooltip-max);
  padding: var(--aui-space-1) var(--aui-space-2);
  border-radius: var(--aui-radius-sm);
  background: var(--aui-color-text);
  color: var(--aui-color-text-inverse);
  font-family: var(--aui-font-sans);
  font-size: var(--aui-text-sm);
  visibility: hidden;
  opacity: 0;
  transition: opacity var(--aui-transition-fast);
}

.aui-tooltip__bubble--open {
  visibility: visible;
  opacity: 1;
}

.aui-tooltip__bubble--bottom {
  top: calc(100% + var(--aui-tooltip-offset));
  left: 50%;
  transform: translateX(-50%);
}

.aui-tooltip__bubble--top {
  bottom: calc(100% + var(--aui-tooltip-offset));
  left: 50%;
  transform: translateX(-50%);
}

.aui-tooltip__bubble--left {
  right: calc(100% + var(--aui-tooltip-offset));
  top: 50%;
  transform: translateY(-50%);
}

.aui-tooltip__bubble--right {
  left: calc(100% + var(--aui-tooltip-offset));
  top: 50%;
  transform: translateY(-50%);
}

@media (prefers-reduced-motion: reduce) {
  .aui-tooltip__bubble {
    transition: none;
  }
}
</style>
