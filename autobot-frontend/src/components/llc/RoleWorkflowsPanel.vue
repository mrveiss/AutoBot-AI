<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #21241: the workflows a role runs, on the Roles tab: the attached ones, a picker over the company's
  workflows to attach one, and "New workflow" (create, then attach to this role).

  Attach and detach are admin writes, so the controls show only when the members response says the
  viewer may manage the company (`viewer_can_manage`, as on the org chart). The parent owns the role
  detail: this announces `changed` after a write and the parent reloads, so what is drawn is what the
  server last returned. Every await re-checks that the company and role it started for are still
  shown before it writes state.
-->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseSelectMenu } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import { useCompanyMembers } from '@/composables/llc/useCompanyMembers'
import { useCompanyWorkflows } from '@/composables/llc/useCompanyWorkflows'
import CompanyWorkflowCreateModal from './CompanyWorkflowCreateModal.vue'

const props = defineProps<{
  companyId: string
  roleId: string
  /** Workflow ids already attached to the role. */
  attached: string[]
  /** A role mutation elsewhere on the page is in flight. */
  busy: boolean
}>()
const emit = defineEmits<{
  (e: 'changed'): void
  /** A write of this panel is in flight (true) or over (false): the page folds it into its own busy flag. */
  (e: 'busy', busy: boolean): void
}>()

const { t } = useI18n()
const api = useApiClient()
const service = useCompanyWorkflows(() => props.companyId)
const { workflows, state, pending } = service
const members = useCompanyMembers(api, () => props.companyId)
const { viewerCanManage, errorMessage: standingError } = members

const picked = ref('')
const actionError = ref('')
const showCreate = ref(false)

const options = computed(() =>
  service
    .attachable(props.attached)
    .map((o) => ({ value: o.id, label: o.label, disabled: o.disabled })),
)
const nothingAttachable = computed(() => state.value === 'ready' && options.value.every((o) => o.disabled))
const working = computed(() => props.busy || pending.value)

onMounted(() => {
  void service.load()
  void members.load()
})
watch(pending, (busy) => emit('busy', busy))
// Unmounted mid-write: the page must not stay locked by a flag nobody will clear.
onBeforeUnmount(() => emit('busy', false))

// Another company or role: nothing chosen or reported for the old one carries over.
watch(
  () => [props.companyId, props.roleId],
  () => {
    picked.value = ''
    actionError.value = ''
    showCreate.value = false
  },
)

/** Run one write for the company and role shown; a result for any other is dropped. */
async function write(action: () => Promise<unknown>, fallbackKey: string): Promise<boolean> {
  const company = props.companyId
  const role = props.roleId
  actionError.value = ''
  try {
    await action()
  } catch (err: unknown) {
    if (company === props.companyId && role === props.roleId) {
      actionError.value = describeApiError(err, t(fallbackKey))
    }
    return false
  }
  if (company !== props.companyId || role !== props.roleId) return false
  emit('changed')
  return true
}

async function attach(): Promise<void> {
  const id = picked.value
  if (!id || working.value) return
  if (await write(() => service.attach(props.roleId, id), 'llcRoles.errorAttach')) picked.value = ''
}

async function detach(id: string): Promise<void> {
  if (working.value) return
  await write(() => service.detach(props.roleId, id), 'llcRoles.errorDetach')
}

function onCreated(_id: string, attachedNow: boolean): void {
  showCreate.value = false
  if (attachedNow) emit('changed')
}
</script>

<template>
  <section class="mt-4" data-testid="role-workflows-panel">
    <header class="flex items-baseline gap-2">
      <h4 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llcRoles.workflows') }}</h4>
      <span v-if="attached.length" class="text-sm text-autobot-text-secondary">{{ attached.length }}</span>
    </header>

    <p v-if="attached.length === 0" class="m-0 mb-1 text-autobot-text-secondary">{{ t('llcRoles.noWorkflows') }}</p>
    <ul v-else class="m-0 mb-1 flex list-none flex-wrap gap-1 p-0">
      <li
        v-for="id in attached"
        :key="id"
        class="inline-flex items-center gap-1 rounded-md bg-autobot-bg-secondary px-2 py-1 font-mono text-sm text-autobot-text-primary"
      >
        <span>{{ id }}</span>
        <button
          v-if="viewerCanManage"
          type="button"
          class="cursor-pointer border-0 bg-transparent p-0 leading-none text-autobot-text-secondary disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="working"
          :aria-label="`${t('llcRoles.detach')}: ${id}`"
          :data-testid="`role-workflow-detach-${id}`"
          @click="detach(id)"
        >
          ×
        </button>
      </li>
    </ul>

    <p v-if="state === 'loading'" class="m-0 text-sm text-autobot-text-muted" data-testid="role-workflows-loading">
      {{ t('llc.workflows.loading') }}
    </p>
    <div v-else-if="state === 'failed'" class="flex flex-col items-start gap-2" data-testid="role-workflows-unavailable">
      <BaseAlert variant="warning" :message="t('llc.workflows.unavailable')" />
      <BaseButton variant="outline" size="sm" data-testid="role-workflows-retry" @click="service.load()">
        {{ t('common.retry') }}
      </BaseButton>
    </div>

    <p v-if="standingError" class="m-0 text-sm text-autobot-text-muted" data-testid="role-workflows-standing-unavailable">
      {{ t('llc.workflows.standingUnavailable') }}
    </p>

    <template v-if="viewerCanManage">
      <div class="flex flex-wrap items-center gap-2" data-testid="role-workflows-controls">
        <div data-testid="role-workflows-picker" class="min-w-48 flex-1">
          <BaseSelectMenu
            v-model="picked"
            :options="options"
            :label="t('llc.workflows.pickerLabel')"
            :placeholder="t('llc.workflows.pickerPlaceholder')"
            :disabled="working || state !== 'ready' || nothingAttachable"
          />
        </div>
        <BaseButton variant="secondary" data-testid="role-workflows-attach" :disabled="working || !picked" @click="attach">
          {{ t('llcRoles.attach') }}
        </BaseButton>
        <BaseButton variant="outline" data-testid="role-workflows-new" :disabled="working" @click="showCreate = true">
          {{ t('llc.workflows.newWorkflow') }}
        </BaseButton>
      </div>
      <p
        v-if="nothingAttachable"
        class="m-0 mt-1 text-sm text-autobot-text-muted"
        role="status"
        data-testid="role-workflows-nothing-attachable"
      >
        {{ workflows.length === 0 ? t('llc.workflows.nothingAttachable') : t('llc.workflows.allAttached') }}
      </p>
    </template>
    <BaseAlert v-if="actionError" variant="error" :message="actionError" class="mt-2" data-testid="role-workflows-error" />

    <CompanyWorkflowCreateModal
      v-if="viewerCanManage"
      :model-value="showCreate"
      :company-id="companyId"
      :role-id="roleId"
      :service="service"
      @close="showCreate = false"
      @created="onCreated"
    />
  </section>
</template>
