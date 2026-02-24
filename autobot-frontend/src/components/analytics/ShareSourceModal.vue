<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
        <div
          class="modal-dialog"
          role="dialog"
          aria-modal="true"
          aria-label="Share Code Source"
        >
          <!-- Header -->
          <div class="modal-header">
            <h3>
              <i class="fas fa-share-alt"></i>
              Share Source
            </h3>
            <button class="close-btn" @click="$emit('close')" aria-label="Close">
              <i class="fas fa-times"></i>
            </button>
          </div>

          <!-- Body -->
          <div class="modal-body">
            <!-- Source info -->
            <div v-if="source" class="source-info-bar">
              <i :class="source.source_type === 'github' ? 'fab fa-github' : 'fas fa-folder'"></i>
              <div>
                <div class="source-name">{{ source.name }}</div>
                <div class="source-detail">{{ source.repo ?? source.clone_path }}</div>
              </div>
            </div>

            <!-- Access Level -->
            <div class="form-group">
              <label class="form-label">Access Level</label>
              <div class="access-selector">
                <label
                  v-for="level in accessLevels"
                  :key="level.value"
                  class="access-option"
                  :class="{ 'access-option--active': form.access === level.value }"
                >
                  <input
                    type="radio"
                    :value="level.value"
                    v-model="form.access"
                    class="sr-only"
                  />
                  <i :class="level.icon"></i>
                  <span>{{ level.label }}</span>
                  <small>{{ level.description }}</small>
                </label>
              </div>
            </div>

            <!-- User IDs for shared access -->
            <div v-if="form.access === 'shared'" class="form-group">
              <label class="form-label" for="share-user-ids">
                User IDs
                <span class="form-label-hint">(one per line or comma-separated)</span>
              </label>
              <textarea
                id="share-user-ids"
                v-model="userIdsText"
                class="form-textarea"
                placeholder="user1&#10;user2&#10;user3"
                rows="4"
                autocomplete="off"
              ></textarea>
              <span class="form-hint">
                <i class="fas fa-info-circle"></i>
                Enter user IDs separated by commas or new lines.
              </span>
            </div>

            <!-- Current shared_with display -->
            <div v-if="currentSharedWith.length > 0" class="shared-with-section">
              <div class="form-label">Currently shared with:</div>
              <div class="shared-tags">
                <span v-for="uid in currentSharedWith" :key="uid" class="shared-tag">
                  <i class="fas fa-user"></i>
                  {{ uid }}
                </span>
              </div>
            </div>

            <!-- Submit error -->
            <div v-if="submitError" class="submit-error">
              <i class="fas fa-exclamation-triangle"></i>
              {{ submitError }}
            </div>
          </div>

          <!-- Footer -->
          <div class="modal-footer">
            <button class="btn-cancel" @click="$emit('close')" type="button">Cancel</button>
            <button
              class="btn-submit"
              @click="handleSubmit"
              :disabled="submitting || !source"
              type="button"
            >
              <i :class="submitting ? 'fas fa-spinner fa-spin' : 'fas fa-save'"></i>
              {{ submitting ? 'Saving...' : 'Update Access' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * ShareSourceModal Component
 *
 * Access control dialog for code sources.
 * Issue #1133: Code Source Registry for codebase analytics.
 */

import { ref, computed, watch } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ShareSourceModal')

// ---- Types ----------------------------------------------------------------

interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  credential_id: string | null
  clone_path: string | null
  last_synced: string | null
  status: 'configured' | 'syncing' | 'ready' | 'error'
  error_message: string | null
  owner_id: string | null
  access: 'private' | 'shared' | 'public'
  shared_with: string[]
  created_at: string
}

// ---- Props & Emits --------------------------------------------------------

interface Props {
  visible: boolean
  source: CodeSource | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'saved', source: CodeSource): void
  (e: 'close'): void
}>()

// ---- Constants ------------------------------------------------------------

const accessLevels = [
  {
    value: 'private' as const,
    label: 'Private',
    icon: 'fas fa-lock',
    description: 'Only you'
  },
  {
    value: 'shared' as const,
    label: 'Shared',
    icon: 'fas fa-users',
    description: 'Specific users'
  },
  {
    value: 'public' as const,
    label: 'Public',
    icon: 'fas fa-globe',
    description: 'All users'
  }
]

// ---- State ----------------------------------------------------------------

const form = ref({
  access: 'private' as 'private' | 'shared' | 'public'
})
const userIdsText = ref('')
const submitError = ref<string | null>(null)
const submitting = ref(false)

// ---- Computed -------------------------------------------------------------

const currentSharedWith = computed<string[]>(() =>
  props.source?.shared_with ?? []
)

const parsedUserIds = computed<string[]>(() =>
  userIdsText.value
    .split(/[\n,]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0)
)

// ---- API ------------------------------------------------------------------

async function getBackendUrl(): Promise<string> {
  return appConfig.getServiceUrl('backend')
}

// ---- Actions --------------------------------------------------------------

async function handleSubmit() {
  if (!props.source) return
  submitting.value = true
  submitError.value = null

  const payload = {
    user_ids: parsedUserIds.value,
    access: form.value.access
  }

  try {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(
      `${backendUrl}/api/analytics/codebase/sources/${props.source.id}/share`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }
    )

    if (!response.ok) {
      const text = await response.text()
      throw new Error(`HTTP ${response.status}: ${text}`)
    }

    const saved: CodeSource = await response.json()
    logger.info('Access updated for source:', saved.name)
    emit('saved', saved)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Share update failed:', msg)
    submitError.value = `Update failed: ${msg}`
  } finally {
    submitting.value = false
  }
}

// ---- Lifecycle ------------------------------------------------------------

watch(() => props.visible, (visible) => {
  if (visible && props.source) {
    form.value.access = props.source.access
    userIdsText.value = (props.source.shared_with ?? []).join('\n')
    submitError.value = null
  }
}, { immediate: true })

watch(() => props.source, (source) => {
  if (source && props.visible) {
    form.value.access = source.access
    userIdsText.value = (source.shared_with ?? []).join('\n')
  }
})
</script>

<style scoped>
/* Issue #1133: Share Source Modal */

.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--bg-overlay-dark);
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-4);
}

.modal-dialog {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-2xl);
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-5) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  flex-shrink: 0;
}

.modal-header h3 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.modal-header h3 i {
  color: var(--color-success);
}

.close-btn {
  width: 2rem;
  height: 2rem;
  border: none;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* Body */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

/* Source info bar */
.source-info-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3) var(--spacing-4);
  border: 1px solid var(--border-subtle);
}

.source-info-bar i {
  font-size: var(--text-xl);
  color: var(--color-info);
  flex-shrink: 0;
}

.source-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.source-detail {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
}

/* Form Groups */
.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
}

.form-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  display: flex;
  align-items: baseline;
  gap: var(--spacing-1-5);
}

.form-label-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-weight: var(--font-normal);
}

.form-textarea {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary-alpha);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  font-family: var(--font-mono, monospace);
  resize: vertical;
  width: 100%;
  transition: border-color var(--duration-200);
}

.form-textarea:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
}

.form-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

/* Access Selector */
.access-selector {
  display: flex;
  gap: var(--spacing-2-5);
}

.access-option {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-3) var(--spacing-2);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  cursor: pointer;
  text-align: center;
  transition: all var(--duration-200);
  background: var(--bg-tertiary);
}

.access-option:hover {
  border-color: var(--border-default);
}

.access-option--active {
  border-color: var(--color-info);
  background: rgba(59, 130, 246, 0.08);
}

.access-option i {
  font-size: var(--text-lg);
  color: var(--text-muted);
}

.access-option--active i {
  color: var(--color-info);
}

.access-option span {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.access-option small {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

/* Shared-with section */
.shared-with-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.shared-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1-5);
}

.shared-tag {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  background: rgba(59, 130, 246, 0.12);
  color: var(--color-info);
  font-size: var(--text-xs);
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-full);
}

/* Submit error */
.submit-error {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  color: var(--color-error);
}

/* Footer */
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-5) var(--spacing-6);
  border-top: 1px solid var(--border-default);
  flex-shrink: 0;
}

.btn-cancel {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200);
}

.btn-cancel:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.btn-submit {
  padding: var(--spacing-2-5) var(--spacing-5);
  background: var(--color-success);
  border: none;
  border-radius: var(--radius-lg);
  color: var(--bg-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: opacity var(--duration-200);
}

.btn-submit:hover:not(:disabled) {
  opacity: 0.85;
}

.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Transitions */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity var(--duration-300);
}

.modal-fade-enter-active .modal-dialog,
.modal-fade-leave-active .modal-dialog {
  transition: all var(--duration-300);
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .modal-dialog,
.modal-fade-leave-to .modal-dialog {
  transform: scale(0.95);
}
</style>
