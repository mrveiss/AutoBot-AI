<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="modelValue" class="dialog-overlay" @click="handleOverlayClick">
        <div
          class="dialog"
          :class="[sizeClass, { 'dialog-scrollable': scrollable }]"
          @click.stop
        >
          <!-- Header -->
          <div class="dialog-header">
            <h3>{{ title }}</h3>
            <button
              v-if="showClose"
              class="close-btn"
              @click="handleClose"
              aria-label="Close dialog"
            >
              <i class="fas fa-times"></i>
            </button>
          </div>

          <!-- Content -->
          <div class="dialog-content">
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
import { computed } from 'vue'

/**
 * Reusable Modal/Dialog Component
 *
 * Provides consistent modal behavior across the application.
 * Eliminates duplicate modal implementations in 14+ components.
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
</script>

<style scoped>
/* Modal overlay */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

/* Modal dialog */
.dialog {
  background: white;
  border-radius: 0.5rem;
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
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
  padding: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.dialog-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.close-btn {
  width: 2.5rem;
  height: 2.5rem;
  border: none;
  background: #f3f4f6;
  border-radius: 0.375rem;
  color: #6b7280;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

/* Content */
.dialog-content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

/* Actions */
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid #e5e7eb;
}

/* Transitions */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-active .dialog,
.modal-fade-leave-active .dialog {
  transition: all 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .dialog,
.modal-fade-leave-to .dialog {
  transform: scale(0.95);
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .dialog {
    background: #1f2937;
  }

  .dialog-header {
    border-bottom-color: #374151;
  }

  .dialog-header h3 {
    color: #f9fafb;
  }

  .close-btn {
    background: #374151;
    color: #d1d5db;
  }

  .close-btn:hover {
    background: #4b5563;
    color: #f9fafb;
  }

  .dialog-actions {
    border-top-color: #374151;
  }
}
</style>
