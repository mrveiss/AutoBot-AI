<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  BaseModal — canonical modal/dialog for @autobot/ui.

  Promoted from autobot-frontend/src/components/ui/BaseModal.vue (#10750 C2c):
  one implementation of the modal, consumed by both apps. Made theme-agnostic —
  every color / radius / shadow / font / z-index references an `--aui-*`
  semantic token, so each app renders it in its own identity (see
  ../tokens/contract.css).

  Public API is preserved unchanged from the app version:
    props   : modelValue (v-model), title, size (sm|md|lg), showClose,
              closeOnOverlay, scrollable, closeLabel
    slots   : title (rich header, falls back to `title` prop), default (body),
              actions (footer)
    emits   : update:modelValue, close

  Accessibility (unchanged behavior):
    - role="dialog" + aria-modal, labelled/described via generated ids
    - focus trap (Tab / Shift+Tab wrap), initial focus, focus restore on close
    - ESC to close, backdrop click to close (when closeOnOverlay)
    - body scroll lock while open (reference-counted for stacked modals)
    - honors prefers-reduced-motion via token motion values

  Note on i18n: the kit hardcodes no user-facing text beyond a sensible English
  default. The close-button aria-label is the `closeLabel` prop (default
  "Close") — apps pass a translated string (e.g. t('ui.modal.closeDialog')).
-->
<script setup lang="ts">
import { ref, computed, useId, toRef } from 'vue'
import { useFocusTrap } from '../composables/useFocusTrap'
import { useFocusRestore } from '../composables/useFocusRestore'
import { useInitialFocus } from '../composables/useInitialFocus'
import { useBodyScrollLock } from '../composables/useBodyScrollLock'

export type ModalSize = 'sm' | 'md' | 'lg'

interface Props {
  /** v-model binding for modal visibility */
  modelValue: boolean
  /** Modal title (used by the header when the #title slot is not provided) */
  title: string
  /** Modal size: sm (500px), md (900px), lg (1200px) */
  size?: ModalSize
  /** Show close button */
  showClose?: boolean
  /** Close on overlay click */
  closeOnOverlay?: boolean
  /** Enable scrollable content */
  scrollable?: boolean
  /** aria-label for the close button (apps pass a translated string) */
  closeLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  showClose: true,
  closeOnOverlay: true,
  scrollable: true,
  closeLabel: 'Close',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  close: []
}>()

// Refs
const dialogRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef)

// Save activeElement on open, restore on close — driven by modelValue.
// Fires before onAfterEnter focuses the first focusable, so the saved
// reference is the trigger element (correct).
useFocusRestore(toRef(props, 'modelValue'))
useBodyScrollLock(toRef(props, 'modelValue'))

const { focusFirst } = useInitialFocus(dialogRef)

// Stable unique IDs for ARIA labeling (Vue 3.5+ useId)
const _uid = useId()
const titleId = computed(() => `modal-title-${_uid}`)
const descriptionId = computed(() => `modal-desc-${_uid}`)

const sizeClass = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'aui-dialog-sm'
    case 'lg':
      return 'aui-dialog-lg'
    default:
      return 'aui-dialog-md'
  }
})

const handleClose = () => {
  emit('update:modelValue', false)
  emit('close')
}

const handleOverlayClick = () => {
  if (props.closeOnOverlay) {
    handleClose()
  }
}

// Focus, restore, and scroll-lock all driven by composables above.
const onAfterEnter = () => focusFirst()
</script>

<template>
  <Teleport to="body">
    <Transition name="aui-modal-fade" @after-enter="onAfterEnter">
      <div
        v-if="modelValue"
        class="aui-dialog-overlay"
        @click="handleOverlayClick"
        @keydown.esc="handleClose"
      >
        <div
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descriptionId"
          class="aui-dialog"
          :class="[sizeClass, { 'aui-dialog-scrollable': scrollable }]"
          tabindex="-1"
          @click.stop
          @keydown="onFocusTrapKeydown"
        >
          <!-- Header -->
          <div class="aui-dialog-header">
            <h3 :id="titleId"><slot name="title">{{ title }}</slot></h3>
            <button
              v-if="showClose"
              class="aui-dialog-close"
              type="button"
              :aria-label="closeLabel"
              @click="handleClose"
            >
              <svg
                class="aui-dialog-close__icon"
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
          </div>

          <!-- Content -->
          <div :id="descriptionId" class="aui-dialog-content">
            <slot></slot>
          </div>

          <!-- Actions -->
          <div v-if="$slots.actions" class="aui-dialog-actions">
            <slot name="actions"></slot>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* Modal overlay */
.aui-dialog-overlay {
  position: fixed;
  inset: 0;
  background: var(--aui-color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--aui-z-modal);
  padding: var(--aui-space-4);
}

/* Modal dialog */
.aui-dialog {
  contain: layout style;
  background: var(--aui-color-surface);
  border-radius: var(--aui-radius-lg);
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--aui-shadow-xl);
  font-family: var(--aui-font-sans);
  color: var(--aui-color-text);
}

.aui-dialog-sm {
  max-width: 500px;
}

.aui-dialog-md {
  max-width: 900px;
}

.aui-dialog-lg {
  max-width: 1200px;
}

/* #10750 C2: scroll only .aui-dialog-content, never the whole .aui-dialog
   (overflow on both created a double scrollbar + header/actions scrolling away) */
.aui-dialog-scrollable .aui-dialog-content {
  overflow-y: auto;
}

/* Header */
.aui-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--aui-space-6);
  border-bottom: 1px solid var(--aui-color-border);
}

.aui-dialog-header h3 {
  font-size: var(--aui-text-xl);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
  margin: 0;
}

.aui-dialog-close {
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

.aui-dialog-close:hover {
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
}

.aui-dialog-close:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.aui-dialog-close__icon {
  display: block;
}

/* Content */
.aui-dialog-content {
  flex: 1;
  min-height: 0;
  padding: var(--aui-space-6);
}

/* Actions */
.aui-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--aui-space-3);
  padding: var(--aui-space-6);
  border-top: 1px solid var(--aui-color-border);
}

/* Transitions */
.aui-modal-fade-enter-active,
.aui-modal-fade-leave-active {
  transition: opacity var(--aui-transition);
}

.aui-modal-fade-enter-active .aui-dialog,
.aui-modal-fade-leave-active .aui-dialog {
  transition: transform var(--aui-transition);
}

.aui-modal-fade-enter-from,
.aui-modal-fade-leave-to {
  opacity: 0;
}

.aui-modal-fade-enter-from .aui-dialog,
.aui-modal-fade-leave-to .aui-dialog {
  transform: scale(0.95);
}

@media (prefers-reduced-motion: reduce) {
  .aui-modal-fade-enter-active,
  .aui-modal-fade-leave-active,
  .aui-modal-fade-enter-active .aui-dialog,
  .aui-modal-fade-leave-active .aui-dialog {
    transition: none;
  }
}
</style>
