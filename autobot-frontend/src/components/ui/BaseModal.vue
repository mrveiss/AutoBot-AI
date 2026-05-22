<template>
  <Teleport to="body">
    <Transition
      name="modal-fade"
      @after-enter="onAfterEnter"
    >
      <div
        v-if="modelValue"
        class="dialog-overlay"
        @click="handleOverlayClick"
        @keydown.esc="handleClose"
      >
        <div
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descriptionId"
          class="dialog"
          :class="[sizeClass, { 'dialog-scrollable': scrollable }]"
          @click.stop
          @keydown="onFocusTrapKeydown"
          tabindex="-1"
        >
          <!-- Header -->
          <div class="dialog-header">
            <h3 :id="titleId">{{ title }}</h3>
            <button
              v-if="showClose"
              class="close-btn"
              @click="handleClose"
              :aria-label="t('ui.modal.closeDialog')"
              type="button"
            >
              <Icon name="times" size="sm" />
            </button>
          </div>

          <!-- Content -->
          <div :id="descriptionId" class="dialog-content">
            <slot></slot>
          </div>

          <!-- Actions -->
          <div v-if="$slots.actions" class="dialog-actions">
            <slot name="actions"></slot>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, useId, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { useInitialFocus } from '@/composables/useInitialFocus'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'
import Icon from './Icon.vue'

/**
 * Reusable Modal/Dialog Component
 *
 * Provides consistent modal behavior across the application.
 * Eliminates duplicate modal implementations in 14+ components.
 *
 * Accessibility Features:
 * - WCAG 2.1 Level AA compliant
 * - Focus trap via Tab/Shift+Tab wrap (does not fight browser devtools or outside clicks)
 * - ESC key to close
 * - Focus restoration (returns focus to trigger element)
 * - Screen reader announcements (role="dialog", aria-modal="true")
 * - Body scroll lock when modal is open
 *
 * Usage:
 * ```vue
 * <BaseModal
 *   v-model="showModal"
 *   title="Delete Item"
 *   size="sm"
 *   @close="handleClose"
 * >
 *   <p>Are you sure you want to delete this item?</p>
 *   <template #actions>
 *     <button @click="handleCancel">Cancel</button>
 *     <button @click="handleConfirm">Delete</button>
 *   </template>
 * </BaseModal>
 * ```
 */

interface Props {
  /** v-model binding for modal visibility */
  modelValue: boolean
  /** Modal title */
  title: string
  /** Modal size: sm (500px), md (900px), lg (1200px) */
  size?: 'sm' | 'md' | 'lg'
  /** Show close button */
  showClose?: boolean
  /** Close on overlay click */
  closeOnOverlay?: boolean
  /** Enable scrollable content */
  scrollable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  showClose: true,
  closeOnOverlay: true,
  scrollable: true
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'close': []
}>()

const { t } = useI18n()

// Refs
const dialogRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef)

// Save activeElement on open, restore on close — driven by modelValue.
// Note: this fires immediately on the prop change, before BaseModal's
// onAfterEnter focuses the first focusable, so the saved reference is
// the trigger element (correct).
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
      return 'dialog-sm'
    case 'lg':
      return 'dialog-lg'
    default:
      return 'dialog-md'
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

<style scoped>
/* Issue #704: Migrated to CSS design tokens */

/* Modal overlay */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-overlay-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: var(--spacing-4);
}

/* Modal dialog */
.dialog {
  contain: layout style paint;
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-2xl);
  contain: layout style;
}

.dialog-sm {
  max-width: 500px;
}

.dialog-md {
  max-width: 900px;
}

.dialog-lg {
  max-width: 1200px;
}

.dialog-scrollable {
  overflow-y: auto;
}

/* Header */
.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
}

.dialog-header h3 {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.close-btn {
  min-width: 2.75rem;
  min-height: 2.75rem;
  border: none;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-200) var(--ease-in-out);
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.close-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Content */
.dialog-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6);
}

/* Actions */
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-6);
  border-top: 1px solid var(--border-default);
}

/* Transitions */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity var(--duration-300) var(--ease-in-out);
}

.modal-fade-enter-active .dialog,
.modal-fade-leave-active .dialog {
  contain: layout style paint;
  transition: all var(--duration-300) var(--ease-in-out);
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .dialog,
.modal-fade-leave-to .dialog {
  contain: layout style paint;
  transform: scale(0.95);
}
</style>
