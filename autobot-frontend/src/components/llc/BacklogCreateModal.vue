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
    <div class="flex flex-col gap-4">
      <BaseInput
        v-model="newItem.title"
        type="text"
        :label="t('llc.backlog.fieldTitle')"
        :placeholder="t('llc.backlog.titlePlaceholder')"
      />
      <BaseFormField :label="t('llc.backlog.fieldProject')">
        <template #default="{ id }">
          <select :id="id" v-model="newItem.project_id" :class="CONTROL_CLASS" :disabled="loadingProjects || projects.length === 0">
            <option value="">{{ loadingProjects ? t('llc.backlog.loadingProjects') : t('llc.backlog.selectProject') }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </template>
      </BaseFormField>
      <BaseAlert
        v-if="!loadingProjects && projects.length === 0"
        variant="error"
        :message="t('llc.backlog.noProjectsHint')"
      />
      <div class="flex gap-3">
        <BaseFormField :label="t('llc.backlog.fieldType')" class="flex-1">
          <template #default="{ id }">
            <select :id="id" v-model="newItem.type" :class="CONTROL_CLASS">
              <option v-for="wt in WORK_ITEM_TYPES" :key="wt.value" :value="wt.value">{{ wt.label }}</option>
            </select>
          </template>
        </BaseFormField>
        <BaseFormField :label="t('llc.backlog.fieldPriority')" class="flex-1">
          <template #default="{ id }">
            <select :id="id" v-model="newItem.priority" :class="CONTROL_CLASS">
              <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
          </template>
        </BaseFormField>
        <BaseInput
          v-model="storyPoints"
          type="number"
          min="0"
          :label="t('llc.backlog.fieldStoryPoints')"
          class="flex-1"
        />
      </div>
      <BaseFormField :label="t('llc.backlog.fieldDescription')">
        <template #default="{ id }">
          <textarea :id="id" v-model="newItem.description" :class="[CONTROL_CLASS, 'resize-y']" rows="4" />
        </template>
      </BaseFormField>

      <!-- AC Suggester -->
      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-autobot-text-secondary">{{ t('llc.backlog.acceptanceCriteria') }}</span>
          <BaseButton
            variant="outline"
            size="sm"
            :disabled="!newItem.title || isSuggestingAC"
            @click="suggestAC"
          >
            <span v-if="isSuggestingAC">{{ t('llc.backlog.suggesting') }}</span>
            <span v-else>✨ {{ t('llc.backlog.suggestAcs') }}</span>
          </BaseButton>
        </div>
        <div v-if="suggestedACs.length > 0" class="flex flex-col gap-1.5 p-2 rounded-md border border-autobot-border bg-autobot-bg-card">
          <label
            v-for="(ac, i) in suggestedACs"
            :key="i"
            class="flex items-start gap-2 text-sm cursor-pointer"
          >
            <input type="checkbox" v-model="ac.selected" />
            {{ ac.text }}
          </label>
        </div>
      </div>

      <BaseAlert v-if="createError" variant="error" :message="createError" />
    </div>

    <template #actions>
      <BaseButton variant="secondary" @click="emit('close')">{{ t('common.cancel') }}</BaseButton>
      <BaseButton variant="primary" :disabled="!canCreate" @click="createItem">
        {{ isCreating ? t('llc.backlog.creating') : t('common.create') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseFormField, BaseInput, BaseModal } from '@autobot/ui'
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
// Native select/textarea have no kit component; shared utility classes keep them on the tokens.
const CONTROL_CLASS =
  'w-full px-3 py-2 text-sm rounded-md border border-autobot-border bg-autobot-bg-card text-autobot-text-primary'
const newItem = ref(blankItem(props.defaultProjectId))
const isCreating = ref(false)
const createError = ref('')
const isSuggestingAC = ref(false)
const suggestedACs = ref<{ text: string; selected: boolean }[]>([])

// BaseInput speaks strings; the API wants a number or null.
const storyPoints = computed({
  get: () => (newItem.value.story_points === null ? '' : String(newItem.value.story_points)),
  set: (v: string) => { newItem.value.story_points = v === '' ? null : Number(v) },
})

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
