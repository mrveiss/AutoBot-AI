<template>
  <Teleport to="body">
    <Transition
      name="modal-fade"
      @after-enter="onAfterEnter"
      @after-leave="onAfterLeave"
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
          tabindex="-1"
        >
          <!-- Header -->
          <div class="dialog-header">
            <h3 :id="titleId">{{ title }}</h3>
            <button
              v-if="showClose"
              class="close-btn"
              @click="handleClose"
              aria-label="Close dialog"
              type="button"
            >
              <i class="fas fa-times" aria-hidden="true"></i>
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
import { ref, computed, nextTick, onUnmounted } from 'vue'

/**
 * Reusable Modal/Dialog Component
 *
 * Provides consistent modal behavior across the application.
 * Eliminates duplicate modal implementations in 14+ components.
 *
 * Accessibility Features:
 * - WCAG 2.1 Level AA compliant
 * - Focus trap (prevents focus from escaping modal)
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
 *   size="small"
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
  /** Modal size: small (500px), medium (900px), large (1200px) */
  size?: 'small' | 'medium' | 'large'
  /** Show close button */
  showClose?: boolean
  /** Close on overlay click */
  closeOnOverlay?: boolean
  /** Enable scrollable content */
  scrollable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'medium',
  showClose: true,
  closeOnOverlay: true,
  scrollable: true
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'close': []
}>()

// Refs
const dialogRef = ref<HTMLElement | null>(null)
let previousActiveElement: HTMLElement | null = null

// Generate unique IDs for ARIA labeling
const titleId = computed(() => `modal-title-${Math.random().toString(36).substr(2, 9)}`)
const descriptionId = computed(() => `modal-desc-${Math.random().toString(36).substr(2, 9)}`)

const sizeClass = computed(() => {
  switch (props.size) {
    case 'small':
      return 'dialog-small'
    case 'large':
      return 'dialog-large'
    default:
      return 'dialog-medium'
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

// Focus trap implementation
const onAfterEnter = async () => {
  // Store element that had focus before modal opened
  previousActiveElement = document.activeElement as HTMLElement

  await nextTick()

  // Focus the dialog or first focusable element
  if (dialogRef.value) {
    const firstFocusable = dialogRef.value.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )

    if (firstFocusable) {
      firstFocusable.focus()
    } else {
      dialogRef.value.focus()
    }
  }

  // Lock body scroll
  document.body.style.overflow = 'hidden'

  // Add focus trap
  document.addEventListener('focusin', trapFocus)
}

const onAfterLeave = () => {
  // Restore focus to element that opened modal
  if (previousActiveElement && typeof previousActiveElement.focus === 'function') {
    previousActiveElement.focus()
  }

  // Unlock body scroll
  document.body.style.overflow = ''

  // Remove focus trap
  document.removeEventListener('focusin', trapFocus)
}

const trapFocus = (event: FocusEvent) => {
  if (!dialogRef.value) return

  const focusableElements = dialogRef.value.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )

  if (focusableElements.length === 0) return

  const firstElement = focusableElements[0]

  // If focus leaves dialog, trap it back to first element
  if (!dialogRef.value.contains(event.target as Node)) {
    firstElement.focus()
    event.preventDefault()
  }
}

// Cleanup on unmount
onUnmounted(() => {
  document.removeEventListener('focusin', trapFocus)
  document.body.style.overflow = ''
})
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
  z-index: 1000;
  padding: var(--spacing-4);
}

/* Modal dialog */
.dialog {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-2xl);
}

.dialog-small {
  max-width: 500px;
}

.dialog-medium {
  max-width: 900px;
}

.dialog-large {
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
  margin: 0;
}

.close-btn {
  width: 2.5rem;
  height: 2.5rem;
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
  transition: all var(--duration-300) var(--ease-in-out);
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .dialog,
.modal-fade-leave-to .dialog {
  transform: scale(0.95);
}
</style>
