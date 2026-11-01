<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<template>
  <BaseModal
    :model-value="modelValue"
    :title="t('llc.backlog.createTitle')"
    :close-label="t('ui.modal.closeDialog')"
    :width="560"
    @close="emit('close')"
  >
    <div class="modal-form-body">
      <div class="form-field">
        <label>{{ t('llc.backlog.fieldTitle') }}</label>
        <input v-model="newItem.title" type="text" class="form-input" :placeholder="t('llc.backlog.titlePlaceholder')" />
      </div>
      <div class="form-field">
        <label>{{ t('llc.backlog.fieldProject') }}</label>
        <select v-model="newItem.project_id" class="form-select" :disabled="loadingProjects || projects.length === 0">
          <option value="">{{ loadingProjects ? t('llc.backlog.loadingProjects') : t('llc.backlog.selectProject') }}</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <p v-if="!loadingProjects && projects.length === 0" class="create-error" role="alert">
          {{ t('llc.backlog.noProjectsHint') }}
        </p>
      </div>
      <div class="form-row">
        <div class="form-field">
          <label>{{ t('llc.backlog.fieldType') }}</label>
          <select v-model="newItem.type" class="form-select">
            <option v-for="wt in WORK_ITEM_TYPES" :key="wt.value" :value="wt.value">{{ wt.label }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>{{ t('llc.backlog.fieldPriority') }}</label>
          <select v-model="newItem.priority" class="form-select">
            <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>{{ t('llc.backlog.fieldStoryPoints') }}</label>
          <input v-model.number="newItem.story_points" type="number" class="form-input" min="0" />
        </div>
      </div>
      <div class="form-field">
        <label>{{ t('llc.backlog.fieldDescription') }}</label>
        <textarea v-model="newItem.description" class="form-textarea" rows="4" />
      </div>

      <!-- AC Suggester -->
      <div class="ac-suggester">
        <div class="ac-header">
          <label>{{ t('llc.backlog.acceptanceCriteria') }}</label>
          <button
            class="btn-suggest"
            :disabled="!newItem.title || isSuggestingAC"
            @click="suggestAC"
          >
            <span v-if="isSuggestingAC">{{ t('llc.backlog.suggesting') }}</span>
            <span v-else>✨ {{ t('llc.backlog.suggestAcs') }}</span>
          </button>
        </div>
        <div v-if="suggestedACs.length > 0" class="suggested-acs">
          <label
            v-for="(ac, i) in suggestedACs"
            :key="i"
            class="ac-item"
          >
            <input type="checkbox" v-model="ac.selected" />
            {{ ac.text }}
          </label>
        </div>
      </div>

      <p v-if="createError" class="create-error" role="alert">{{ createError }}</p>

    </div>

    <template #actions>
      <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
      <button class="btn-primary" :disabled="!canCreate" @click="createItem">
        {{ isCreating ? t('llc.backlog.creating') : t('common.create') }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseModal } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { WORK_ITEM_TYPES, PRIORITIES, type WorkItem } from '@/views/llc/workItemTypes'

/**
 * Create-work-item form of the backlog (#18978). Every work item belongs to a
 * project, so the form needs one before Create is enabled.
 */
interface ProjectOpt { id: string; name: string }

const props = defineProps<{
  modelValue: boolean
  companyId: string
  projects: ProjectOpt[]
  loadingProjects: boolean
  defaultProjectId: string
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'created', item: WorkItem): void }>()

const logger = createLogger('BacklogCreateModal')
const api = useApiClient()
const { t } = useI18n()

const blankItem = (projectId: string) => ({
  title: '', type: 'pbi', priority: 'medium', story_points: null as number | null, description: '', project_id: projectId,
})
const newItem = ref(blankItem(props.defaultProjectId))
const isCreating = ref(false)
const createError = ref('')
const isSuggestingAC = ref(false)
const suggestedACs = ref<{ text: string; selected: boolean }[]>([])

const canCreate = computed(() => !!newItem.value.title && !!newItem.value.project_id && !isCreating.value)

// Prefill from the backlog's project filter each time the form opens, so a
// project listed after the form is already open can still be the default.
watch(
  () => [props.modelValue, props.projects.length] as const,
  ([open]) => {
    if (open && !newItem.value.project_id) newItem.value.project_id = props.defaultProjectId
  },
)

// Request advisory acceptance criteria for the in-progress new item. Company
// scope is derived from the org context server-side — never send company_id.
// Backend: POST /api/llc/work-items/suggest-ac (#9861); empty list on LLM-down.
async function suggestAC() {
  if (!newItem.value.title) return
  isSuggestingAC.value = true
  try {
    const res = await api.post<{ suggestions: string[] }>(`/api/llc/work-items/suggest-ac`, {
      title: newItem.value.title,
      description: newItem.value.description,
    })
    suggestedACs.value = (res.suggestions ?? []).map(text => ({ text, selected: true }))
  } catch (err) {
    logger.error('AC suggestion failed', err)
    suggestedACs.value = []
  } finally {
    isSuggestingAC.value = false
  }
}

async function createItem() {
  if (!canCreate.value) return
  isCreating.value = true
  createError.value = ''
  try {
    const ac = suggestedACs.value.filter(a => a.selected).map(a => a.text)
    const created = await api.post<WorkItem>(`/api/llc/work-items`, {
      company_id: props.companyId,
      ...newItem.value,
      acceptance_criteria: ac,
    })
    emit('created', created)
    newItem.value = blankItem(props.defaultProjectId)
    suggestedACs.value = []
  } catch (err) {
    // Surface the backend reason instead of a silent console-only log (#11411).
    logger.error('Create work item failed', err)
    const detail = err instanceof Error ? err.message : ''
    createError.value = detail
      ? t('llc.backlog.createErrorDetail', { detail })
      : t('llc.backlog.createError')
  } finally {
    isCreating.value = false
  }
}
</script>

<style scoped>
.modal-form-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.form-field label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.875rem;
  width: 100%;
}

.form-row {
  display: flex;
  gap: 0.75rem;
}

.form-row .form-field {
  flex: 1;
}

.form-select,
.form-textarea {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.875rem;
  width: 100%;
}

.form-textarea {
  resize: vertical;
}

.ac-suggester {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.ac-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ac-header label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.btn-suggest {
  font-size: 0.8rem;
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-elevated);
  cursor: pointer;
}

.btn-suggest:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.suggested-acs {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 0.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-elevated);
}

.ac-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.875rem;
  cursor: pointer;
}

.create-error {
  margin: 0 0 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-danger);
}


.btn-primary,
.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-primary {
  background: var(--color-primary);
  color: white;
  border: none;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-surface);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}
</style>
