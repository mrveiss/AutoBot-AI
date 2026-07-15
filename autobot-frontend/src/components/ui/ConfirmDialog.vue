<template>
  <Teleport to="body">
    <Transition name="confirm-fade">
      <div
        v-if="dialogVisible"
        class="confirm-overlay"
        @click.self="_resolve(false)"
        @keydown.esc="_resolve(false)"
      >
        <div
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="descId"
          class="confirm-dialog"
          tabindex="-1"
          @keydown="onFocusTrapKeydown"
        >
          <h3 :id="titleId" class="confirm-title">{{ dialogOptions?.title }}</h3>
          <p :id="descId" class="confirm-message">{{ dialogOptions?.message }}</p>
          <div class="confirm-actions">
            <button
              ref="cancelRef"
              type="button"
              class="confirm-btn confirm-btn-cancel"
              @click="_resolve(false)"
            >
              Cancel
            </button>
            <button
              type="button"
              class="confirm-btn confirm-btn-confirm"
              @click="_resolve(true)"
            >
              Confirm
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, useId } from 'vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useFocusTrap } from '@/composables/useFocusTrap'

const { dialogVisible, dialogOptions, _resolve } = useConfirmDialog()

const dialogRef = ref<HTMLElement | null>(null)
const cancelRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef)

const _uid = useId()
const titleId = `confirm-title-${_uid}`
const descId = `confirm-desc-${_uid}`

// Focus cancel button when dialog opens
watch(dialogVisible, (visible) => {
  if (visible) {
    setTimeout(() => cancelRef.value?.focus(), 0)
  }
})
</script>

<style scoped>
.confirm-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: var(--spacing-4);
}

.confirm-dialog {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2xl);
  padding: var(--spacing-6);
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.confirm-dialog:focus {
  outline: none;
}

.confirm-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.confirm-message {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
}

.confirm-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  border: none;
  transition: background var(--duration-200) var(--ease-in-out);
  min-height: 2.25rem;
}

.confirm-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.confirm-btn-cancel {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.confirm-btn-cancel:hover {
  background: var(--bg-tertiary);
}

.confirm-btn-confirm {
  background: var(--color-error, var(--color-primary));
  color: var(--text-inverse, #fff);
}

.confirm-btn-confirm:hover {
  opacity: 0.9;
}

.confirm-fade-enter-active,
.confirm-fade-leave-active {
  transition: opacity var(--duration-200) var(--ease-in-out);
}

.confirm-fade-enter-from,
.confirm-fade-leave-to {
  opacity: 0;
}

.confirm-fade-enter-active .confirm-dialog,
.confirm-fade-leave-active .confirm-dialog {
  transition: transform var(--duration-200) var(--ease-in-out);
}

.confirm-fade-enter-from .confirm-dialog,
.confirm-fade-leave-to .confirm-dialog {
  transform: scale(0.95);
}
</style>
