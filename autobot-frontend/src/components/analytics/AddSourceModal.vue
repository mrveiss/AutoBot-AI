<template>
  <BaseModal
    :model-value="visible"
    :title="isEditMode ? $t('analytics.sources.editSource') : $t('analytics.sources.addCodeSource')"
    size="sm"
    @close="handleClose"
  >
    <template #title>
      <span class="modal-title-inner">
        <Icon :name="isEditMode ? 'edit' : 'plus-circle'" />
        {{ isEditMode ? $t('analytics.sources.editSource') : $t('analytics.sources.addCodeSource') }}
      </span>
    </template>

            <!-- Name -->
            <div class="form-group">
              <label class="form-label" for="source-name">{{ $t('analytics.sources.form.name') }} <span class="required">*</span></label>
              <input
                id="source-name"
                v-model="form.name"
                class="form-input"
                :placeholder="$t('analytics.sources.form.namePlaceholder')"
                type="text"
                autocomplete="off"
                :class="{ 'form-input--error': errors.name }"
              />
              <span v-if="errors.name" class="form-error">{{ errors.name }}</span>
            </div>

            <!-- Source Type -->
            <div class="form-group">
              <label class="form-label">{{ $t('analytics.sources.form.sourceType') }}</label>
              <div class="type-toggle">
                <button
                  class="type-btn"
                  :class="{ 'type-btn--active': form.source_type === 'github' }"
                  @click="form.source_type = 'github'"
                  type="button"
                >
                  <Icon name="code-branch" />
                  {{ $t('analytics.sources.form.github') }}
                </button>
                <button
                  class="type-btn"
                  :class="{ 'type-btn--active': form.source_type === 'local' }"
                  @click="form.source_type = 'local'"
                  type="button"
                >
                  <Icon name="folder" />
                  {{ $t('analytics.sources.form.localPath') }}
                </button>
              </div>
            </div>

            <!-- GitHub fields -->
            <template v-if="form.source_type === 'github'">
              <div class="form-group">
                <label class="form-label" for="source-repo">{{ $t('analytics.sources.form.repository') }} <span class="required">*</span></label>
                <input
                  id="source-repo"
                  v-model="form.repo"
                  class="form-input"
                  :placeholder="$t('analytics.sources.form.repoPlaceholder')"
                  type="text"
                  autocomplete="off"
                  :class="{ 'form-input--error': errors.repo }"
                />
                <span v-if="errors.repo" class="form-error">{{ errors.repo }}</span>
              </div>

              <div class="form-group">
                <label class="form-label" for="source-branch">{{ $t('analytics.sources.form.branch') }}</label>
                <input
                  id="source-branch"
                  v-model="form.branch"
                  class="form-input"
                  :placeholder="$t('analytics.sources.form.branchPlaceholder')"
                  type="text"
                  autocomplete="off"
                />
              </div>

              <div class="form-group">
                <label class="form-label" for="source-credential">{{ $t('analytics.sources.form.credentialOptional') }}</label>
                <select
                  id="source-credential"
                  v-model="form.credential_id"
                  class="form-select"
                >
                  <option value="">{{ $t('analytics.sources.form.nonePublicRepo') }}</option>
                  <option
                    v-for="secret in filteredSecrets"
                    :key="secret.id"
                    :value="secret.id"
                  >
                    {{ secret.name }} ({{ secret.type }})
                  </option>
                </select>
                <span class="form-hint">
                  <Icon name="info-circle" />
                  {{ $t('analytics.sources.form.credentialHint') }}
                </span>
                <div v-if="secretsLoadError" class="form-error">{{ secretsLoadError }}</div>
              </div>
            </template>

            <!-- Local Path fields -->
            <template v-if="form.source_type === 'local'">
              <div class="form-group">
                <label class="form-label" for="source-path">{{ $t('analytics.sources.form.localPath') }} <span class="required">*</span></label>
                <input
                  id="source-path"
                  v-model="form.local_path"
                  class="form-input"
                  :placeholder="$t('analytics.sources.form.localPathPlaceholder')"
                  type="text"
                  autocomplete="off"
                  :class="{ 'form-input--error': errors.local_path }"
                />
                <span v-if="errors.local_path" class="form-error">{{ errors.local_path }}</span>
              </div>

              <div class="form-group">
                <label class="form-label" for="source-branch-local">{{ $t('analytics.sources.form.branchOptional') }}</label>
                <input
                  id="source-branch-local"
                  v-model="form.branch"
                  class="form-input"
                  :placeholder="$t('analytics.sources.form.branchPlaceholder')"
                  type="text"
                  autocomplete="off"
                />
              </div>
            </template>

            <!-- Access -->
            <div class="form-group">
              <label class="form-label">{{ $t('analytics.sources.form.accessLevel') }}</label>
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
                  <Icon :name="level.icon" />
                  <span>{{ level.label }}</span>
                  <small>{{ level.description }}</small>
                </label>
              </div>
            </div>

            <!-- Submission error -->
            <div v-if="submitError" class="submit-error">
              <Icon name="exclamation-triangle" />
              {{ submitError }}
            </div>

    <template #actions>
      <button class="btn-cancel" @click="handleClose" type="button">{{ $t('analytics.sources.form.cancel') }}</button>
      <button
        class="btn-submit"
        @click="handleSubmit"
        :disabled="submitting"
        type="button"
      >
        <i v-if="submitting" class="fas fa-spinner fa-spin"></i>
        <Icon v-else :name="isEditMode ? 'save' : 'plus'" />
        {{ submitting ? $t('analytics.sources.form.saving') : (isEditMode ? $t('analytics.sources.form.saveChanges') : $t('analytics.sources.addSource')) }}
      </button>
    </template>
  </BaseModal>
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

import Icon from '@/components/ui/Icon.vue'
import { BaseModal } from '@autobot/ui'
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchSourceSecrets, saveCodeSource } from '@/composables/analytics/useSourceRegistry'
import type { RegistrySecret } from '@/composables/analytics/useSourceRegistry'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AddSourceModal')
const { t } = useI18n()

// ---- Types ----------------------------------------------------------------

import type { CodeSource } from '@/types/analytics'

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

const accessLevels = computed(() => [
  {
    value: 'private' as const,
    label: t('analytics.sources.access.private'),
    icon: 'lock' as const,
    description: t('analytics.sources.access.privateDesc')
  },
  {
    value: 'shared' as const,
    label: t('analytics.sources.access.shared'),
    icon: 'users' as const,
    description: t('analytics.sources.access.sharedDesc')
  },
  {
    value: 'public' as const,
    label: t('analytics.sources.access.public'),
    icon: 'globe' as const,
    description: t('analytics.sources.access.publicDesc')
  }
])

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

const secrets = ref<RegistrySecret[]>([])
const secretsLoadError = ref<string | null>(null)

// ---- Computed -------------------------------------------------------------

const isEditMode = computed(() => !!props.source)

const filteredSecrets = computed(() =>
  secrets.value.filter(s => s.type === 'token' || s.type === 'api_key')
)

// ---- API ------------------------------------------------------------------

async function loadSecrets() {
  try {
    secrets.value = await fetchSourceSecrets()
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
    newErrors.name = t('analytics.sources.validation.nameRequired')
  }
  if (form.value.source_type === 'github' && !form.value.repo.trim()) {
    newErrors.repo = t('analytics.sources.validation.repoRequired')
  }
  if (form.value.source_type === 'local' && !form.value.local_path.trim()) {
    newErrors.local_path = t('analytics.sources.validation.localPathRequired')
  }
  errors.value = newErrors
  return Object.keys(newErrors).length === 0
}

// ---- Actions --------------------------------------------------------------

async function handleSubmit() {
  if (!validate()) return
  submitting.value = true
  submitError.value = null

  const payload = {
    name: form.value.name.trim(),
    source_type: form.value.source_type,
    repo: form.value.source_type === 'github'
      ? form.value.repo.trim()
      : form.value.local_path.trim(),
    branch: form.value.branch.trim() || 'main',
    access: form.value.access,
    credential_id: form.value.credential_id || null
  }

  try {
    const saved = await saveCodeSource(payload, props.source?.id)
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

<style scoped src="@/design-system/styles/source-modal-shared.css"></style>

<style scoped>
/* Issue #1133: Add Source Modal */

.modal-title-inner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.modal-title-inner i {
  color: var(--color-info);
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

.form-input:focus-visible,
.form-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
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
</style>
