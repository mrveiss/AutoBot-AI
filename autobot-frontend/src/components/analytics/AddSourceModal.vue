<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="visible" class="modal-overlay" @click.self="handleClose">
        <div
          class="modal-dialog"
          role="dialog"
          aria-modal="true"
          :aria-label="isEditMode ? 'Edit Code Source' : 'Add Code Source'"
        >
          <!-- Header -->
          <div class="modal-header">
            <h3>
              <i :class="isEditMode ? 'fas fa-edit' : 'fas fa-plus-circle'"></i>
              {{ isEditMode ? 'Edit Source' : 'Add Code Source' }}
            </h3>
            <button class="close-btn" @click="handleClose" aria-label="Close">
              <i class="fas fa-times"></i>
            </button>
          </div>

          <!-- Body -->
          <div class="modal-body">
            <!-- Name -->
            <div class="form-group">
              <label class="form-label" for="source-name">Name <span class="required">*</span></label>
              <input
                id="source-name"
                v-model="form.name"
                class="form-input"
                placeholder="e.g. AutoBot Main"
                type="text"
                autocomplete="off"
                :class="{ 'form-input--error': errors.name }"
              />
              <span v-if="errors.name" class="form-error">{{ errors.name }}</span>
            </div>

            <!-- Source Type -->
            <div class="form-group">
              <label class="form-label">Source Type</label>
              <div class="type-toggle">
                <button
                  class="type-btn"
                  :class="{ 'type-btn--active': form.source_type === 'github' }"
                  @click="form.source_type = 'github'"
                  type="button"
                >
                  <i class="fab fa-github"></i>
                  GitHub
                </button>
                <button
                  class="type-btn"
                  :class="{ 'type-btn--active': form.source_type === 'local' }"
                  @click="form.source_type = 'local'"
                  type="button"
                >
                  <i class="fas fa-folder"></i>
                  Local Path
                </button>
              </div>
            </div>

            <!-- GitHub fields -->
            <template v-if="form.source_type === 'github'">
              <div class="form-group">
                <label class="form-label" for="source-repo">Repository <span class="required">*</span></label>
                <input
                  id="source-repo"
                  v-model="form.repo"
                  class="form-input"
                  placeholder="owner/repository"
                  type="text"
                  autocomplete="off"
                  :class="{ 'form-input--error': errors.repo }"
                />
                <span v-if="errors.repo" class="form-error">{{ errors.repo }}</span>
              </div>

              <div class="form-group">
                <label class="form-label" for="source-branch">Branch</label>
                <input
                  id="source-branch"
                  v-model="form.branch"
                  class="form-input"
                  placeholder="main"
                  type="text"
                  autocomplete="off"
                />
              </div>

              <div class="form-group">
                <label class="form-label" for="source-credential">Credential (optional)</label>
                <select
                  id="source-credential"
                  v-model="form.credential_id"
                  class="form-select"
                >
                  <option value="">-- None (public repo) --</option>
                  <option
                    v-for="secret in filteredSecrets"
                    :key="secret.id"
                    :value="secret.id"
                  >
                    {{ secret.name }} ({{ secret.type }})
                  </option>
                </select>
                <span class="form-hint">
                  <i class="fas fa-info-circle"></i>
                  Select a stored token or API key for private repositories.
                </span>
                <div v-if="secretsLoadError" class="form-error">{{ secretsLoadError }}</div>
              </div>
            </template>

            <!-- Local Path fields -->
            <template v-if="form.source_type === 'local'">
              <div class="form-group">
                <label class="form-label" for="source-path">Local Path <span class="required">*</span></label>
                <input
                  id="source-path"
                  v-model="form.local_path"
                  class="form-input"
                  placeholder="/home/user/projects/myapp"
                  type="text"
                  autocomplete="off"
                  :class="{ 'form-input--error': errors.local_path }"
                />
                <span v-if="errors.local_path" class="form-error">{{ errors.local_path }}</span>
              </div>

              <div class="form-group">
                <label class="form-label" for="source-branch-local">Branch (optional)</label>
                <input
                  id="source-branch-local"
                  v-model="form.branch"
                  class="form-input"
                  placeholder="main"
                  type="text"
                  autocomplete="off"
                />
              </div>
            </template>

            <!-- Access -->
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

            <!-- Submission error -->
            <div v-if="submitError" class="submit-error">
              <i class="fas fa-exclamation-triangle"></i>
              {{ submitError }}
            </div>
          </div>

          <!-- Footer -->
          <div class="modal-footer">
            <button class="btn-cancel" @click="handleClose" type="button">Cancel</button>
            <button
              class="btn-submit"
              @click="handleSubmit"
              :disabled="submitting"
              type="button"
            >
              <i :class="submitting ? 'fas fa-spinner fa-spin' : (isEditMode ? 'fas fa-save' : 'fas fa-plus')"></i>
              {{ submitting ? 'Saving...' : (isEditMode ? 'Save Changes' : 'Add Source') }}
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
 * AddSourceModal Component
 *
 * Create or edit a code source entry in the registry.
 * Issue #1133: Code Source Registry for codebase analytics.
 */

import { ref, computed, watch, onMounted } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AddSourceModal')

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

interface Secret {
  id: string
  name: string
  type: string
  scope: string
}

interface FormErrors {
  name?: string
  repo?: string
  local_path?: string
}

// ---- Props & Emits --------------------------------------------------------

interface Props {
  visible: boolean
  source?: CodeSource | null
}

const props = withDefaults(defineProps<Props>(), {
  source: null
})

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
    description: 'Only you can access'
  },
  {
    value: 'shared' as const,
    label: 'Shared',
    icon: 'fas fa-users',
    description: 'Shared with specific users'
  },
  {
    value: 'public' as const,
    label: 'Public',
    icon: 'fas fa-globe',
    description: 'All users can view'
  }
]

// ---- State ----------------------------------------------------------------

const form = ref({
  name: '',
  source_type: 'github' as 'github' | 'local',
  repo: '',
  branch: 'main',
  local_path: '',
  credential_id: '',
  access: 'private' as 'private' | 'shared' | 'public'
})

const errors = ref<FormErrors>({})
const submitError = ref<string | null>(null)
const submitting = ref(false)

const secrets = ref<Secret[]>([])
const secretsLoadError = ref<string | null>(null)

// ---- Computed -------------------------------------------------------------

const isEditMode = computed(() => !!props.source)

const filteredSecrets = computed(() =>
  secrets.value.filter(s => s.type === 'token' || s.type === 'api_key')
)

// ---- API ------------------------------------------------------------------

async function getBackendUrl(): Promise<string> {
  return appConfig.getServiceUrl('backend')
}

async function loadSecrets() {
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetchWithAuth(`${backendUrl}/api/secrets`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const data = await response.json()
    secrets.value = data.secrets ?? []
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.warn('Failed to load secrets:', msg)
    secretsLoadError.value = `Could not load credentials: ${msg}`
  }
}

// ---- Form Helpers ---------------------------------------------------------

function populateFromSource(source: CodeSource) {
  form.value.name = source.name
  form.value.source_type = source.source_type
  form.value.repo = source.repo ?? ''
  form.value.branch = source.branch ?? 'main'
  form.value.local_path = source.clone_path ?? ''
  form.value.credential_id = source.credential_id ?? ''
  form.value.access = source.access
}

function resetForm() {
  form.value = {
    name: '',
    source_type: 'github',
    repo: '',
    branch: 'main',
    local_path: '',
    credential_id: '',
    access: 'private'
  }
  errors.value = {}
  submitError.value = null
}

function validate(): boolean {
  const newErrors: FormErrors = {}
  if (!form.value.name.trim()) {
    newErrors.name = 'Name is required.'
  }
  if (form.value.source_type === 'github' && !form.value.repo.trim()) {
    newErrors.repo = 'Repository (owner/repo) is required.'
  }
  if (form.value.source_type === 'local' && !form.value.local_path.trim()) {
    newErrors.local_path = 'Local path is required.'
  }
  errors.value = newErrors
  return Object.keys(newErrors).length === 0
}

// ---- Actions --------------------------------------------------------------

async function handleSubmit() {
  if (!validate()) return
  submitting.value = true
  submitError.value = null

  const payload: Record<string, unknown> = {
    name: form.value.name.trim(),
    source_type: form.value.source_type,
    branch: form.value.branch.trim() || 'main',
    access: form.value.access,
    credential_id: form.value.credential_id || null
  }

  if (form.value.source_type === 'github') {
    payload.repo = form.value.repo.trim()
  } else {
    payload.repo = form.value.local_path.trim()
  }

  try {
    const backendUrl = await getBackendUrl()
    const url = isEditMode.value
      ? `${backendUrl}/api/analytics/codebase/sources/${props.source!.id}`
      : `${backendUrl}/api/analytics/codebase/sources`
    const method = isEditMode.value ? 'PUT' : 'POST'

    const response = await fetchWithAuth(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      const text = await response.text()
      throw new Error(`HTTP ${response.status}: ${text}`)
    }

    const saved: CodeSource = await response.json()
    logger.info(isEditMode.value ? 'Source updated:' : 'Source created:', saved.name)
    emit('saved', saved)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Save failed:', msg)
    submitError.value = `Save failed: ${msg}`
  } finally {
    submitting.value = false
  }
}

function handleClose() {
  emit('close')
}

// ---- Lifecycle ------------------------------------------------------------

watch(() => props.visible, (visible) => {
  if (visible) {
    resetForm()
    if (props.source) {
      populateFromSource(props.source)
    }
    loadSecrets()
  }
}, { immediate: true })

watch(() => props.source, (source) => {
  if (source && props.visible) {
    populateFromSource(source)
  }
})

onMounted(() => {
  if (props.visible) {
    loadSecrets()
  }
})
</script>

<style scoped>
/* Issue #1133: Add Source Modal */

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
  max-width: 540px;
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
  color: var(--color-info);
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
}

.required {
  color: var(--color-error);
}

.form-input,
.form-select {
  padding: var(--spacing-2-5) var(--spacing-4);
  background: var(--bg-tertiary-alpha);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-on-primary);
  font-size: var(--text-sm);
  transition: border-color var(--duration-200);
  width: 100%;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
}

.form-input--error {
  border-color: var(--color-error);
}

.form-input::placeholder {
  color: var(--text-muted);
}

.form-error {
  font-size: var(--text-xs);
  color: var(--color-error);
}

.form-hint {
  font-size: var(--text-xs);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

/* Source Type Toggle */
.type-toggle {
  display: flex;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.type-btn {
  flex: 1;
  padding: var(--spacing-2-5) var(--spacing-4);
  border: none;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: all var(--duration-200);
}

.type-btn + .type-btn {
  border-left: 1px solid var(--border-subtle);
}

.type-btn--active {
  background: var(--color-info);
  color: var(--bg-secondary);
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
  background: var(--color-info);
  border: none;
  border-radius: var(--radius-lg);
  color: var(--bg-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  transition: background var(--duration-200);
}

.btn-submit:hover:not(:disabled) {
  background: var(--color-info-dark);
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
