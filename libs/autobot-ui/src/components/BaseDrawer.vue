<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseDrawer — a panel that slides in from the right edge over the page (#14780).

  The side-panel sibling of BaseModal, and built from the same parts: the focus trap,
  initial focus, focus restore and reference-counted body scroll lock composables, and the
  same `--aui-*` tokens, so each app renders it in its own identity. Its API was taken from
  the three hand-rolled SLM drawers it replaces (the FleetOverview node-details and services
  panels, NPUDetailsPanel): a title with a subtitle under it, a scrolling body, an optional
  footer, and a width per use.

    props   : modelValue (v-model), title, width (CSS length or px number, default 32rem),
              closeLabel, closeOnOverlay, closeOnEsc, locked, flush (body without padding,
              for content that pads its own sections)
    slots   : title, subtitle, default (body), actions (footer)
    emits   : update:modelValue, close
    attrs   : non-prop attributes land on the role="dialog" element, not the Teleport

  Accessibility: role="dialog" + aria-modal, labelled by the title; Tab wraps inside the
  panel; focus moves in on open and back to the trigger on close; Escape and a backdrop
  click close it unless `closeOnEsc` / `closeOnOverlay` say otherwise or it is `locked`.
  Motion honours prefers-reduced-motion. The kit ships no user-facing text: the close
  button's name is the `closeLabel` prop, which apps pass translated.
-->
<script setup lang="ts">
import { ref, computed, useId, toRef } from 'vue'
import { useFocusTrap } from '../composables/useFocusTrap'
import { useFocusRestore } from '../composables/useFocusRestore'
import { useInitialFocus } from '../composables/useInitialFocus'
import { useBodyScrollLock } from '../composables/useBodyScrollLock'

interface Props {
  /** v-model binding for visibility */
  modelValue: boolean
  /** Panel title (used when the #title slot is not provided) */
  title: string
  /** Panel width: a CSS length ("42rem") or a number of px. Never wider than the viewport. */
  width?: string | number
  /** aria-label for the close button (apps pass a translated string) */
  closeLabel?: string
  /** Close on a backdrop click */
  closeOnOverlay?: boolean
  /** Close on Escape */
  closeOnEsc?: boolean
  /** Turns off backdrop click, Escape and the close button together while set */
  locked?: boolean
  /** Body without padding, for content that lays out its own padded sections */
  flush?: boolean
}

// The root is a Teleport, which cannot take fallthrough attributes: a consumer's
// data-testid / aria-describedby / class land on the dialog element instead.
defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  width: '32rem',
  closeLabel: 'Close',
  closeOnOverlay: true,
  closeOnEsc: true,
  locked: false,
  flush: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  close: []
}>()

const panelRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(panelRef)
useFocusRestore(toRef(props, 'modelValue'))
useBodyScrollLock(toRef(props, 'modelValue'))
const { focusFirst } = useInitialFocus(panelRef)

const titleId = `drawer-title-${useId()}`

const canOverlayClose = computed(() => props.closeOnOverlay && !props.locked)
const canEscClose = computed(() => props.closeOnEsc && !props.locked)

const panelStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width,
}))

function handleClose(): void {
  emit('update:modelValue', false)
  emit('close')
}

function handleOverlayClick(): void {
  if (canOverlayClose.value) handleClose()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="aui-drawer" appear @after-enter="focusFirst">
      <div
        v-if="modelValue"
        class="aui-drawer-overlay"
        @click="handleOverlayClick"
        @keydown.esc="canEscClose && handleClose()"
      >
        <aside
          ref="panelRef"
          v-bind="$attrs"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="aui-drawer"
          :style="panelStyle"
          tabindex="-1"
          @click.stop
          @keydown="onFocusTrapKeydown"
        >
          <header class="aui-drawer-header">
            <div class="aui-drawer-heading">
              <h2 :id="titleId"><slot name="title">{{ title }}</slot></h2>
              <div v-if="$slots.subtitle" class="aui-drawer-subtitle"><slot name="subtitle" /></div>
            </div>
            <button
              v-if="!locked"
              class="aui-drawer-close"
              type="button"
              :aria-label="closeLabel"
              @click="handleClose"
            >
              <svg
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </header>

          <div class="aui-drawer-body" :class="{ 'aui-drawer-body--flush': flush }">
            <slot />
          </div>

          <footer v-if="$slots.actions" class="aui-drawer-actions">
            <slot name="actions" />
          </footer>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.aui-drawer-overlay {
  position: fixed;
  inset: 0;
  background: var(--aui-color-overlay);
  z-index: var(--aui-z-modal);
  display: flex;
  justify-content: flex-end;
}

.aui-drawer {
  height: 100%;
  max-width: 100vw;
  display: flex;
  flex-direction: column;
  background: var(--aui-color-surface);
  color: var(--aui-color-text);
  font-family: var(--aui-font-sans);
  box-shadow: var(--aui-shadow-xl);
}

.aui-drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--aui-space-4);
  padding: var(--aui-space-4) var(--aui-space-6);
  border-bottom: 1px solid var(--aui-color-border);
  flex-shrink: 0;
}

.aui-drawer-heading {
  min-width: 0;
}

.aui-drawer-header h2 {
  margin: 0;
  font-size: var(--aui-text-lg);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

.aui-drawer-subtitle {
  margin-top: var(--aui-space-1);
  font-size: var(--aui-text-sm);
  color: var(--aui-color-text-muted);
}

.aui-drawer-close {
  min-width: 2.75rem;
  min-height: 2.75rem;
  border: none;
  background: var(--aui-color-surface-raised);
  border-radius: var(--aui-radius-md);
  color: var(--aui-color-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color var(--aui-transition), color var(--aui-transition);
}

.aui-drawer-close:hover {
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
}

.aui-drawer-close:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-drawer-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--aui-space-6);
}

.aui-drawer-body--flush {
  padding: 0;
}

.aui-drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--aui-space-3);
  padding: var(--aui-space-4) var(--aui-space-6);
  border-top: 1px solid var(--aui-color-border);
  flex-shrink: 0;
}

.aui-drawer-enter-active,
.aui-drawer-leave-active {
  transition: opacity var(--aui-transition);
}

.aui-drawer-enter-active .aui-drawer,
.aui-drawer-leave-active .aui-drawer {
  transition: transform var(--aui-transition);
}

.aui-drawer-enter-from,
.aui-drawer-leave-to {
  opacity: 0;
}

.aui-drawer-enter-from .aui-drawer,
.aui-drawer-leave-to .aui-drawer {
  transform: translateX(100%);
}

@media (prefers-reduced-motion: reduce) {
  .aui-drawer-enter-active,
  .aui-drawer-leave-active,
  .aui-drawer-enter-active .aui-drawer,
  .aui-drawer-leave-active .aui-drawer {
    transition: none;
  }
}
</style>
