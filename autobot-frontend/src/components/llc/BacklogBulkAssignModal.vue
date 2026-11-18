<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <BaseModal
    :model-value="modelValue"
    :title="t('llc.backlog.assignToSprint')"
    :close-label="t('ui.modal.closeDialog')"
    :width="560"
    @close="emit('close')"
  >
    <div class="flex flex-col gap-4">
      <p>{{ t('llc.backlog.itemsSelected', { count: workItemIds.length }) }}</p>
      <BaseFormField :label="t('llc.backlog.project')">
        <template #default="{ id }">
          <select :id="id" :class="CONTROL_CLASS" :value="selectedProjectId" :disabled="loadingProjects"
                  @change="onProjectSelect(($event.target as HTMLSelectElement).value)">
            <option value="">{{ loadingProjects ? t('llc.backlog.loadingProjects') : t('llc.backlog.selectProject') }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </template>
      </BaseFormField>
      <BaseFormField :label="t('llc.backlog.sprint')">
        <template #default="{ id }">
          <select :id="id" v-model="sprintId" :class="CONTROL_CLASS" :disabled="!selectedProjectId || isLoadingSprints">
            <option value="">{{ isLoadingSprints ? t('llc.backlog.loadingSprints') : t('llc.backlog.selectSprint') }}</option>
            <option v-for="s in sprints" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </template>
      </BaseFormField>
      <p v-if="selectedProjectId && !isLoadingSprints && sprints.length === 0" class="text-xs text-autobot-text-secondary">
        {{ t('llc.backlog.noSprints') }}
      </p>
    </div>

    <template #actions>
      <BaseButton variant="secondary" @click="emit('close')">{{ t('common.cancel') }}</BaseButton>
      <BaseButton :disabled="!sprintId || isAssigning" @click="assign">
        {{ isAssigning ? t('llc.backlog.assigning') : t('llc.backlog.assign') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
// Cascade picker for bulk sprint assignment: pick a Project, then a Sprint from that project. Only assignable
// (non-archived) projects and (open) sprints are offered so a user never pastes a raw Sprint UUID (#10853).
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseFormField, BaseModal } from '@autobot/ui'
import { CONTROL_CLASS } from './controlClass'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

interface ProjectOpt { id: string; name: string }
interface SprintOpt { id: string; name: string; status: string }

const props = defineProps<{
  modelValue: boolean
  companyId: string
  workItemIds: string[]
  projects: ProjectOpt[]
  loadingProjects: boolean
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'assigned'): void }>()

const logger = createLogger('BacklogBulkAssignModal')
const api = useApiClient()
const { t } = useI18n()

const sprints = ref<SprintOpt[]>([])
const selectedProjectId = ref('')
const sprintId = ref('')
const isLoadingSprints = ref(false)
const isAssigning = ref(false)

async function onProjectSelect(projectId: string) {
  selectedProjectId.value = projectId
  sprintId.value = ''
  sprints.value = []
  if (!projectId) return
  isLoadingSprints.value = true
  try {
    const result = await api.get<SprintOpt[]>(`/api/llc/projects/${projectId}/sprints`)
    sprints.value = (result ?? []).filter(sp => sp.status !== 'closed' && sp.status !== 'archived')
  } catch (err) {
    logger.error('Failed to load sprints', err)
  } finally {
    isLoadingSprints.value = false
  }
}

async function assign() {
  if (!sprintId.value) return
  isAssigning.value = true
  try {
    await api.post<unknown>(`/api/llc/backlog/bulk-assign-sprint`, {
      work_item_ids: props.workItemIds,
      sprint_id: sprintId.value,
    })
    sprintId.value = ''
    emit('assigned')
  } catch (err) {
    logger.error('Bulk assign failed', err)
  } finally {
    isAssigning.value = false
  }
}

// Each opening, and a company change, starts from an empty choice: another company has other projects and sprints.
watch(() => [props.modelValue, props.companyId], () => onProjectSelect(''))
</script>
