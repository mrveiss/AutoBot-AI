<template>
  <Teleport to="body">
    <Transition name="pair-confirm-fade">
      <div
        v-if="modelValue"
        class="pair-confirm-overlay"
        @click.self="cancel"
        @keydown.esc="cancel"
      >
        <div
          ref="dialogRef"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          class="pair-confirm-dialog"
          tabindex="-1"
          @keydown="onFocusTrapKeydown"
        >
          <h3 :id="titleId" class="pair-confirm-title">Confirm NPU Worker Profile</h3>

          <p class="pair-confirm-worker-id">
            Worker <code>{{ pairResult.worker_id }}</code> paired successfully.
          </p>

          <div class="pair-confirm-profile-section">
            <div class="pair-confirm-label-row">
              <label :for="selectId" class="pair-confirm-label">Worker profile</label>
              <div
                v-if="pairResult.capabilities_summary"
                class="pair-confirm-tooltip-wrap"
              >
                <button
                  type="button"
                  class="pair-confirm-why-btn"
                  :aria-describedby="tooltipId"
                  @mouseenter="tooltipVisible = true"
                  @mouseleave="tooltipVisible = false"
                  @focus="tooltipVisible = true"
                  @blur="tooltipVisible = false"
                >
                  Why?
                </button>
                <div
                  v-if="tooltipVisible"
                  :id="tooltipId"
                  role="tooltip"
                  class="pair-confirm-tooltip"
                >
                  {{ pairResult.capabilities_summary }}
                </div>
              </div>
            </div>

            <select
              :id="selectId"
              v-model="selectedProfile"
              class="pair-confirm-select"
            >
              <option
                v-for="option in PROFILE_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
                <template v-if="option.value === pairResult.recommended_profile"> (recommended)</template>
              </option>
            </select>

            <p
              v-if="isManualOverride"
              class="pair-confirm-override-note"
            >
              Manual override — your choice will be saved.
            </p>
          </div>

          <div class="pair-confirm-actions">
            <button
              ref="cancelRef"
              type="button"
              class="pair-confirm-btn pair-confirm-btn-cancel"
              @click="cancel"
            >
              Cancel
            </button>
            <button
              type="button"
              class="pair-confirm-btn pair-confirm-btn-confirm"
              @click="confirm"
            >
              Save profile
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, useId } from 'vue'
import { useFocusTrap } from '@/composables/useFocusTrap'
import type { NpuWorkerPairResult, NpuWorkerProfile } from '@/composables/useNpuWorkers'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROFILE_OPTIONS: Array<{ value: NpuWorkerProfile; label: string }> = [
  { value: 'inference', label: 'Inference' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'mixed', label: 'Mixed (inference + embedding)' },
  { value: 'relay', label: 'Relay (CPU-only forwarding)' },
]

// ---------------------------------------------------------------------------
// Props / Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  modelValue: boolean
  pairResult: NpuWorkerPairResult
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [payload: { workerId: string; profile: NpuWorkerProfile }]
  cancel: []
}>()

// ---------------------------------------------------------------------------
// IDs
// ---------------------------------------------------------------------------

const _uid = useId()
const titleId = `npu-pair-title-${_uid}`
const selectId = `npu-pair-profile-${_uid}`
const tooltipId = `npu-pair-tooltip-${_uid}`

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const dialogRef = ref<HTMLElement | null>(null)
const cancelRef = ref<HTMLElement | null>(null)
const tooltipVisible = ref(false)

const selectedProfile = ref<NpuWorkerProfile>(
  props.pairResult.recommended_profile ?? 'inference'
)

const isManualOverride = computed(
  () =>
    props.pairResult.recommended_profile !== null &&
    selectedProfile.value !== props.pairResult.recommended_profile
)

// Focus cancel button when dialog opens; reset profile to recommendation
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      selectedProfile.value = props.pairResult.recommended_profile ?? 'inference'
      setTimeout(() => cancelRef.value?.focus(), 0)
    }
  }
)

// ---------------------------------------------------------------------------
// Focus trap
// ---------------------------------------------------------------------------

const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef)

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function confirm() {
  emit('confirm', { workerId: props.pairResult.worker_id, profile: selectedProfile.value })
  emit('update:modelValue', false)
}

function cancel() {
  emit('cancel')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.pair-confirm-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: var(--spacing-4);
}

.pair-confirm-dialog {
  background: var(--bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2xl);
  padding: var(--spacing-6);
  width: 100%;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.pair-confirm-dialog:focus {
  outline: none;
}

.pair-confirm-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.pair-confirm-worker-id {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
}

.pair-confirm-worker-id code {
  font-family: var(--font-mono);
  background: var(--bg-secondary);
  padding: 0 var(--spacing-1);
  border-radius: var(--radius-sm);
}

/* Profile section */
.pair-confirm-profile-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.pair-confirm-label-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.pair-confirm-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

/* Tooltip */
.pair-confirm-tooltip-wrap {
  position: relative;
}

.pair-confirm-why-btn {
  background: none;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  padding: 1px var(--spacing-2);
  line-height: 1.4;
}

.pair-confirm-why-btn:hover,
.pair-confirm-why-btn:focus-visible {
  color: var(--color-primary);
  border-color: var(--color-primary);
  outline: none;
}

.pair-confirm-tooltip {
  position: absolute;
  bottom: calc(100% + var(--spacing-2));
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-overlay-dark);
  color: var(--text-inverse, #fff);
  font-size: var(--text-xs);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  white-space: nowrap;
  max-width: 280px;
  white-space: normal;
  z-index: var(--z-tooltip, 9999);
  pointer-events: none;
}

.pair-confirm-select {
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  width: 100%;
  cursor: pointer;
}

.pair-confirm-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.pair-confirm-override-note {
  font-size: var(--text-xs);
  color: var(--color-warning, #f59e0b);
  margin: 0;
}

/* Actions */
.pair-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
}

.pair-confirm-btn {
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  border: none;
  transition: background var(--duration-200) var(--ease-in-out);
  min-height: 2.25rem;
}

.pair-confirm-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.pair-confirm-btn-cancel {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.pair-confirm-btn-cancel:hover {
  background: var(--bg-tertiary);
}

.pair-confirm-btn-confirm {
  background: var(--color-primary);
  color: var(--text-inverse, #fff);
}

.pair-confirm-btn-confirm:hover {
  opacity: 0.9;
}

/* Transitions */
.pair-confirm-fade-enter-active,
.pair-confirm-fade-leave-active {
  transition: opacity var(--duration-200) var(--ease-in-out);
}

.pair-confirm-fade-enter-from,
.pair-confirm-fade-leave-to {
  opacity: 0;
}

.pair-confirm-fade-enter-active .pair-confirm-dialog,
.pair-confirm-fade-leave-active .pair-confirm-dialog {
  transition: transform var(--duration-200) var(--ease-in-out);
}

.pair-confirm-fade-enter-from .pair-confirm-dialog,
.pair-confirm-fade-leave-to .pair-confirm-dialog {
  transform: scale(0.95);
}
</style>
