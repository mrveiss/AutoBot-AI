<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  #14221 step 6: Company OS "Roles" tab.

  Company-scoped child of LlcCompanyLayout (/llc/companies/:companyId/roles).

  The layout follows the idea the whole issue is built on: a role is the durable
  thing, and holders come and go. So the left column lists roles, and the right
  column shows what a role *carries* — holders, permissions, workflows, tools
  and credentials — with the holder panel showing past tenures as well as
  current ones, because that history is what survives a departure.

  Credentials are shown as ids only. The backend never returns a secret's value
  or name through this surface, and this view must not invent a place to put
  one.

  Every mutation here is admin-only server-side (llc/services/authz.py). The UI
  does not hide the controls based on a locally-guessed role: a client-side
  guess that disagrees with the server produces a worse experience than a clear
  403, and duplicating the rule invites the two copies to drift.
-->
<template>
  <div class="roles-view">
    <header class="roles-header">
      <div>
        <h2 class="roles-title">{{ t('llcRoles.title') }}</h2>
        <p class="roles-subtitle">{{ t('llcRoles.subtitle') }}</p>
      </div>
      <BaseButton variant="primary" :disabled="!companyId" @click="openCreateModal">
        {{ t('llcRoles.addRole') }}
      </BaseButton>
    </header>

    <p v-if="!companyId" class="roles-state">{{ t('llcRoles.noCompany') }}</p>

    <template v-else>
      <ErrorBanner v-if="errorMessage" :message="errorMessage" class="roles-error" />

      <p v-if="isLoading" class="roles-state">{{ t('llcRoles.loading') }}</p>

      <BaseCard v-else-if="roles.length === 0" class="roles-empty">
        {{ t('llcRoles.empty') }}
      </BaseCard>

      <div v-else class="roles-layout">
        <BaseCard class="roles-list-card">
          <ul class="roles-list">
            <li v-for="role in roles" :key="role.id">
              <button
                type="button"
                class="roles-list-item"
                :class="{ 'is-active': role.id === selectedRoleId }"
                @click="selectRole(role.id)"
              >
                <span class="roles-list-name">{{ role.name }}</span>
                <BaseBadge v-if="role.is_system" variant="neutral">
                  {{ t('llcRoles.systemRole') }}
                </BaseBadge>
              </button>
            </li>
          </ul>
        </BaseCard>

        <BaseCard v-if="selectedRole" class="roles-detail-card">
          <header class="roles-detail-header">
            <div>
              <h3 class="roles-detail-name">{{ selectedRole.name }}</h3>
              <p v-if="selectedRole.description" class="roles-detail-description">
                {{ selectedRole.description }}
              </p>
            </div>
            <BaseButton
              variant="error"
              :disabled="selectedRole.is_system"
              @click="removeRole(selectedRole.id)"
            >
              {{ t('llcRoles.deleteRole') }}
            </BaseButton>
          </header>

          <p v-if="isDetailLoading" class="roles-state">{{ t('llcRoles.loading') }}</p>

          <template v-else>
            <section class="roles-section">
              <h4 class="roles-section-title">{{ t('llcRoles.holders') }}</h4>
              <p v-if="holders.length === 0" class="roles-section-empty">
                {{ t('llcRoles.noHolders') }}
              </p>
              <ul v-else class="roles-chip-list">
                <li v-for="holder in holders" :key="holder.id" class="roles-chip">
                  <BaseBadge :variant="holder.ended_at ? 'neutral' : 'success'">
                    {{ t(`llcRoles.holderType.${holder.holder_type}`) }}
                  </BaseBadge>
                  <span class="roles-chip-id">{{ holder.holder_id }}</span>
                  <span v-if="holder.ended_at" class="roles-chip-note">
                    {{ t('llcRoles.pastHolder') }}
                  </span>
                  <!-- Ending a tenure is an update, never a delete: the row
                       survives so the history stays readable. Past tenures
                       therefore carry no control. -->
                  <button
                    v-else
                    type="button"
                    class="roles-chip-action"
                    :disabled="isMutating"
                    :aria-label="`${t('llcRoles.endTenure')}: ${holder.holder_id}`"
                    @click="endTenure(holder.id)"
                  >
                    ×
                  </button>
                </li>
              </ul>

              <form class="roles-assign" @submit.prevent="assignHolder">
                <select v-model="newHolderType" :disabled="isMutating" class="roles-assign-type">
                  <option v-for="kind in HOLDER_TYPES" :key="kind" :value="kind">
                    {{ t(`llcRoles.holderType.${kind}`) }}
                  </option>
                </select>
                <input
                  v-model="newHolderId"
                  type="text"
                  :placeholder="t('llcRoles.holderIdPlaceholder')"
                  :disabled="isMutating"
                  class="roles-assign-id"
                />
                <BaseButton
                  type="submit"
                  variant="secondary"
                  :disabled="isMutating || !newHolderId.trim()"
                >
                  {{ t('llcRoles.assign') }}
                </BaseButton>
              </form>
              <label class="roles-toggle">
                <input v-model="includePastHolders" type="checkbox" @change="loadDetail" />
                {{ t('llcRoles.showPastHolders') }}
              </label>
            </section>

            <RoleAttachmentPanel
              panel-key="permissions"
              :title="t('llcRoles.permissions')"
              :items="permissions"
              :add-label="t('llcRoles.grant')"
              :remove-label="t('llcRoles.revoke')"
              :empty-label="t('llcRoles.noPermissions')"
              :placeholder="t('llcRoles.permissionPlaceholder')"
              :busy="isMutating"
              @add="grantPermission"
              @remove="revokePermission"
            />

            <RoleAttachmentPanel
              panel-key="workflows"
              :title="t('llcRoles.workflows')"
              :items="workflows"
              :add-label="t('llcRoles.attach')"
              :remove-label="t('llcRoles.detach')"
              :empty-label="t('llcRoles.noWorkflows')"
              :placeholder="t('llcRoles.workflowPlaceholder')"
              :busy="isMutating"
              @add="attachWorkflow"
              @remove="detachWorkflow"
            />

            <!-- #14607: the rate the role's steps are costed against. It sits
                 with the role's other attachments because it belongs to the
                 role, not to whoever currently holds it. -->
            <section class="rounded-lg border border-autobot-border p-3" data-testid="role-rate-panel">
              <h3 class="text-sm font-semibold text-autobot-text-primary">{{ t('llcRoles.rate') }}</h3>
              <div class="mt-2 flex flex-wrap items-end gap-2">
                <label class="flex flex-col gap-1 text-xs text-autobot-text-secondary">
                  {{ t('llcRoles.rateLabel') }}
                  <input
                    v-model="rateDraft"
                    type="number"
                    min="0"
                    step="0.01"
                    class="w-28 rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-sm text-autobot-text-primary"
                    data-testid="role-rate-amount"
                  />
                </label>
                <label class="flex flex-col gap-1 text-xs text-autobot-text-secondary">
                  {{ t('llcRoles.currencyLabel') }}
                  <input
                    v-model="currencyDraft"
                    maxlength="3"
                    class="w-20 rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-sm uppercase text-autobot-text-primary"
                    data-testid="role-rate-currency"
                  />
                </label>
                <BaseButton
                  variant="primary"
                  data-testid="role-rate-save"
                  :disabled="!canSaveRate"
                  @click="saveRate"
                >
                  {{ t('llcRoles.saveRate') }}
                </BaseButton>
                <BaseButton v-if="roleRate" variant="secondary" data-testid="role-rate-clear" @click="clearRate">
                  {{ t('llcRoles.clearRate') }}
                </BaseButton>
              </div>
              <!-- Stated, not implied: no rate is not a rate of zero, and every
                   step of this role is not costable until one exists. -->
              <p v-if="!roleRate" class="mt-2 text-xs text-autobot-text-muted" data-testid="role-rate-absent">
                {{ t('llcRoles.noRate') }}
              </p>
            </section>

            <!-- #14598: how long each step takes and how often it runs. -->
            <section
              v-if="stepCosts.length > 0"
              class="rounded-lg border border-autobot-border p-3"
              data-testid="step-costs-panel"
            >
              <h3 class="text-sm font-semibold text-autobot-text-primary">{{ t('llcRoles.stepCosts') }}</h3>
              <ul class="mt-2 divide-y divide-autobot-border">
                <li
                  v-for="cost in stepCosts"
                  :key="cost.workflow_id"
                  class="flex flex-wrap items-end gap-2 py-2"
                  :data-testid="`step-cost-${cost.workflow_id}`"
                >
                  <span class="min-w-0 flex-1 truncate text-sm text-autobot-text-primary">
                    {{ cost.workflow_id }}
                  </span>
                  <label class="flex flex-col gap-1 text-xs text-autobot-text-secondary">
                    {{ t('llcRoles.minutesLabel') }}
                    <input
                      v-model="stepDrafts[cost.workflow_id].minutes"
                      type="number"
                      min="0"
                      class="w-20 rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-sm text-autobot-text-primary"
                      :data-testid="`step-minutes-${cost.workflow_id}`"
                    />
                  </label>
                  <label class="flex flex-col gap-1 text-xs text-autobot-text-secondary">
                    {{ t('llcRoles.runsLabel') }}
                    <input
                      v-model="stepDrafts[cost.workflow_id].runs"
                      type="number"
                      min="0"
                      class="w-20 rounded-md border border-autobot-border bg-autobot-bg-card px-2 py-1 text-sm text-autobot-text-primary"
                      :data-testid="`step-runs-${cost.workflow_id}`"
                    />
                  </label>
                  <BaseButton
                    variant="secondary"
                    :data-testid="`step-cost-save-${cost.workflow_id}`"
                    @click="saveStepCost(
                      cost.workflow_id,
                      stepDrafts[cost.workflow_id].minutes,
                      stepDrafts[cost.workflow_id].runs,
                    )"
                  >
                    {{ t('llcRoles.saveStepCost') }}
                  </BaseButton>
                  <span
                    class="w-full text-xs text-autobot-text-muted"
                    :data-testid="`step-cost-label-${cost.workflow_id}`"
                  >
                    {{ stepCostLabel(cost) }}
                  </span>
                </li>
              </ul>
            </section>

            <RoleAttachmentPanel
              panel-key="tools"
              :title="t('llcRoles.tools')"
              :items="tools"
              :options="toolOptions"
              :add-label="t('llcRoles.attach')"
              :remove-label="t('llcRoles.detach')"
              :empty-label="t('llcRoles.noTools')"
              :placeholder="t('llcRoles.toolPlaceholder')"
              :busy="isMutating"
              @add="attachTool"
              @remove="detachTool"
            />

            <RoleAttachmentPanel
              panel-key="credentials"
              :title="t('llcRoles.credentials')"
              :items="credentials"
              :add-label="t('llcRoles.attach')"
              :remove-label="t('llcRoles.detach')"
              :empty-label="t('llcRoles.noCredentials')"
              :placeholder="t('llcRoles.credentialPlaceholder')"
              :busy="isMutating"
              @add="attachCredential"
              @remove="detachCredential"
            />

          </template>
        </BaseCard>
      </div>
    </template>

    <BaseModal
      v-model="isCreateModalOpen"
      :title="t('llcRoles.addRole')"
      :close-label="t('ui.modal.closeDialog')"
      size="md"
    >
      <template #default>
        <label class="roles-field">
          <span>{{ t('llcRoles.fieldName') }}</span>
          <input v-model="newRoleName" type="text" maxlength="100" />
        </label>
        <label class="roles-field">
          <span>{{ t('llcRoles.fieldDescription') }}</span>
          <textarea v-model="newRoleDescription" rows="3" maxlength="2000"></textarea>
        </label>
      </template>
      <template #footer>
        <BaseButton variant="secondary" @click="closeCreateModal">
          {{ t('llcRoles.cancel') }}
        </BaseButton>
        <BaseButton variant="primary" :disabled="!newRoleName.trim()" @click="createRole">
          {{ t('llcRoles.save') }}
        </BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import RoleAttachmentPanel from '@/components/llc/RoleAttachmentPanel.vue'
import { BaseModal } from '@autobot/ui'
import ErrorBanner from '@/components/base/ErrorBanner.vue'
import { describeApiError } from '@/composables/llc/apiErrorMessage'

interface RoleRow {
  id: string
  company_id: string
  name: string
  description?: string | null
  is_system: boolean
}

interface HolderRow {
  id: string
  role_id: string
  holder_type: string
  holder_id?: string | null
  started_at?: string | null
  ended_at?: string | null
}

const logger = createLogger('LlcRolesView')
const { t } = useI18n()
const route = useRoute()
const api = useApiClient()

interface ToolCatalogueEntry {
  name: string
  description: string
  tags: string[]
  url: string | null
  logo_url: string | null
  role_count: number
}

const roles = ref<RoleRow[]>([])
const holders = ref<HolderRow[]>([])
const permissions = ref<string[]>([])
const workflows = ref<string[]>([])
const tools = ref<string[]>([])
/**
 * The company's tool catalogue (#14852) — registry identity plus this
 * company's own URL and logo. Company-scoped, so it loads with the role list
 * rather than per role: it does not change when the selection does.
 *
 * Empty is a valid state and must not block the tab. A 503 here means the tool
 * registry is unpopulated, which is an environment problem; the panel falls
 * back to its text box rather than presenting an empty picker that reads as
 * "this company has no tools".
 */
const toolCatalogue = ref<ToolCatalogueEntry[]>([])
const credentials = ref<string[]>([])

/**
 * The role's hourly rate, and the cost of each workflow it runs (#14598, #14607).
 *
 * `null` rate means nobody has set one — not a rate of zero. Every step of the
 * role is then *not costable*, which the panel says in words rather than
 * showing a total of 0.
 */
interface RoleRate {
  hourly_rate: string
  currency: string
}
interface StepCost {
  workflow_id: string
  estimated_minutes: number | null
  runs_per_month: number | null
  per_run: string | null
  per_month: string | null
  per_year: string | null
  currency: string | null
  missing: string[]
}
const roleRate = ref<RoleRate | null>(null)
const stepCosts = ref<StepCost[]>([])
const rateDraft = ref<string | number>('')
const currencyDraft = ref('')

/**
 * A draft field as text, whatever the input handed back.
 *
 * A `type="number"` input can yield a number rather than a string, and calling
 * `.trim()` on it throws inside the render function — which takes the whole
 * role detail down rather than just refusing the save.
 */
function asText(value: string | number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

/** Whether the rate is complete enough to send. */
const canSaveRate = computed(
  () => asText(rateDraft.value).trim() !== '' && asText(currencyDraft.value).trim().length === 3,
)
/**
 * Per-step edits in progress, keyed by workflow id.
 *
 * Seeded from the loaded costs and re-seeded on every load, so switching role
 * cannot leave the previous role's numbers sitting in the inputs — a stale
 * draft that is then saved would write one role's measurement onto another.
 */
const stepDrafts = ref<Record<string, { minutes: string | number; runs: string | number }>>({})

function seedStepDrafts(costs: StepCost[]): void {
  const seeded: Record<string, { minutes: string | number; runs: string | number }> = {}
  for (const cost of costs) {
    seeded[cost.workflow_id] = {
      minutes: cost.estimated_minutes === null ? '' : String(cost.estimated_minutes),
      runs: cost.runs_per_month === null ? '' : String(cost.runs_per_month),
    }
  }
  stepDrafts.value = seeded
}

const selectedRoleId = ref<string | null>(null)
const includePastHolders = ref(false)
const isLoading = ref(false)
const isDetailLoading = ref(false)
const errorMessage = ref('')

// Backend RoleHolderType (llc/models/enums.py). Listed rather than derived so
// an unknown value from a future backend version renders as an option nobody
// can select, instead of silently disappearing from the picker.
const HOLDER_TYPES = ['user', 'agent', 'contact'] as const

const newHolderType = ref<(typeof HOLDER_TYPES)[number]>('user')
const newHolderId = ref('')
// One flag for every mutation: the panels disable together, so a second call
// cannot start against a list the first is about to replace.
const isMutating = ref(false)
// Monotonic ticket for detail loads. Two loads can be in flight when a user
// switches role while a post-mutation reload is still running; without this the
// slower one wins and writes the previous role's holders and permissions into
// panels headed by the new role's name — a wrong answer on a screen about who
// may reach what. Only the newest ticket is allowed to publish.
let detailRequestId = 0

const isCreateModalOpen = ref(false)
const newRoleName = ref('')
const newRoleDescription = ref('')

const companyId = computed(() => (route.params.companyId as string) || '')

/**
 * Picker options for the tools panel. `undefined` — not an empty array — when
 * the catalogue is unavailable, because the panel treats "no options prop" as
 * "use the text box" and an empty array as "a catalogue exists and is empty".
 */
const toolOptions = computed(() =>
  toolCatalogue.value.length
    ? toolCatalogue.value.map((entry) => ({
        value: entry.name,
        label: entry.description ? `${entry.name} — ${entry.description}` : entry.name,
      }))
    : undefined,
)
const selectedRole = computed(
  () => roles.value.find((role) => role.id === selectedRoleId.value) ?? null,
)

/**
 * Surface the server's reason rather than a generic message: a 403 from the
 * admin gate and a 400 from validation need different actions from the user,
 * and collapsing them into "something went wrong" hides which one happened.
 *
 * The extraction itself lives in `composables/llc/apiErrorMessage.ts` — shared
 * with `OrgChart.vue` (#14549) rather than forked a second time.
 */
function describeError(error: unknown, fallbackKey: string): string {
  return describeApiError(error, t(fallbackKey))
}

async function loadRoles(): Promise<void> {
  if (!companyId.value) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    const loaded = await api.get<RoleRow[]>(`/api/llc/roles/${companyId.value}`)
    roles.value = Array.isArray(loaded) ? loaded : []
    await loadToolCatalogue()
    if (roles.value.length > 0 && !selectedRoleId.value) {
      await selectRole(roles.value[0].id)
    }
  } catch (error) {
    logger.error('Failed to load roles', error)
    errorMessage.value = describeError(error, 'llcRoles.errorLoad')
  } finally {
    isLoading.value = false
  }
}

/**
 * The catalogue is a convenience, not a prerequisite: a failure here leaves the
 * tools panel on its text box, which still works. So this swallows the error
 * rather than surfacing it on the tab — a red banner over a working Roles tab
 * because a picker could not be populated would be worse than the picker's
 * absence, and the attach call reports a bad name on its own anyway.
 */
async function loadToolCatalogue(): Promise<void> {
  if (!companyId.value) return
  try {
    const loaded = await api.get<ToolCatalogueEntry[]>(`/api/llc/tools/${companyId.value}`)
    toolCatalogue.value = Array.isArray(loaded) ? loaded : []
  } catch (error) {
    logger.warn('Tool catalogue unavailable; the tools panel falls back to free text', error)
    toolCatalogue.value = []
  }
}

async function loadDetail(): Promise<void> {
  const roleId = selectedRoleId.value
  if (!companyId.value || !roleId) return
  const ticket = ++detailRequestId
  isDetailLoading.value = true
  errorMessage.value = ''
  const base = `/api/llc/roles/${companyId.value}/${roleId}`
  try {
    // Fetched together so a slow panel cannot leave the others showing a
    // previous role's data — a partially-updated detail pane reads as fact.
    const [
      loadedHolders,
      loadedPermissions,
      loadedWorkflows,
      loadedTools,
      loadedCredentials,
      loadedRate,
    ] =
      await Promise.all([
        api.get<HolderRow[]>(`${base}/holders?include_past=${includePastHolders.value}`),
        api.get<string[]>(`${base}/permissions`),
        api.get<string[]>(`${base}/workflows`),
        api.get<string[]>(`${base}/tools`),
        api.get<string[]>(`${base}/credentials`),
        api.get<RoleRate | null>(`${base}/rate`),
      ])
    // A newer load started while this one was in flight: its answer is the
    // current one, so this response is discarded rather than published.
    if (ticket !== detailRequestId) return
    holders.value = Array.isArray(loadedHolders) ? loadedHolders : []
    permissions.value = Array.isArray(loadedPermissions) ? loadedPermissions : []
    workflows.value = Array.isArray(loadedWorkflows) ? loadedWorkflows : []
    tools.value = Array.isArray(loadedTools) ? loadedTools : []
    credentials.value = Array.isArray(loadedCredentials) ? loadedCredentials : []
    roleRate.value = loadedRate ?? null
    rateDraft.value = loadedRate?.hourly_rate ?? ''
    currencyDraft.value = loadedRate?.currency ?? ''
    // Costs depend on the workflow list, so they are fetched after it rather
    // than alongside — and they carry the same stale-load ticket, so a slow
    // cost fetch cannot publish a previous role's numbers.
    await loadStepCosts(roleId, ticket, workflows.value)
  } catch (error) {
    logger.error('Failed to load role detail', error)
    errorMessage.value = describeError(error, 'llcRoles.errorLoadDetail')
  } finally {
    if (ticket === detailRequestId) isDetailLoading.value = false
  }
}

/**
 * Fetch the cost of each workflow this role runs (#14598).
 *
 * One request per attached workflow. `Promise.allSettled`, not `all`: one step
 * whose cost cannot be read must not blank the costs of every other step —
 * that would turn a single failure into "nothing is costed", which reads as
 * "nothing costs anything".
 */
async function loadStepCosts(roleId: string, ticket: number, ids: string[]): Promise<void> {
  if (ids.length === 0) {
    if (ticket === detailRequestId) {
      stepCosts.value = []
      seedStepDrafts([])
    }
    return
  }
  const base = `/api/llc/roles/${companyId.value}/${roleId}`
  const results = await Promise.allSettled(
    ids.map((id) => api.get<StepCost>(`${base}/workflows/${encodeURIComponent(id)}/cost`)),
  )
  if (ticket !== detailRequestId) return
  stepCosts.value = results.flatMap((result, index) => {
    if (result.status !== 'fulfilled') {
      logger.error('Failed to load step cost', ids[index])
      return []
    }
    // Accept only rows that actually carry the shape this panel reads. A
    // response of the wrong shape reached the template once during development
    // and `cost.missing.includes(...)` threw, taking the whole role detail
    // down — the same failure #13617 fixed on the cost dashboard. Validating
    // here means a bad payload costs one row, not the view.
    const row = result.value as StepCost | undefined
    if (!row || typeof row.workflow_id !== 'string' || !Array.isArray(row.missing)) {
      logger.error('Step cost response had an unexpected shape', ids[index])
      return []
    }
    return [row]
  })
  seedStepDrafts(stepCosts.value)
}

/** A step's cost line, or the reason it has none. Never a zero standing in. */
function stepCostLabel(cost: StepCost): string {
  if (cost.per_month !== null && cost.currency) {
    return `${cost.per_month} ${cost.currency} ${t('llcRoles.perMonth')}`
  }
  if (cost.per_run !== null && cost.currency) {
    return `${cost.per_run} ${cost.currency} ${t('llcRoles.perRun')}`
  }
  // Missing is not zero, and the reason is what tells someone how to fix it.
  if (cost.missing.includes('no_role_rate')) return t('llcRoles.costNeedsRate')
  return t('llcRoles.costNeedsInputs')
}

async function saveRate(): Promise<void> {
  const amount = asText(rateDraft.value).trim()
  const currency = asText(currencyDraft.value).trim().toUpperCase()
  if (!amount || currency.length !== 3) return
  await mutate(
    () => api.put(`${detailBase()}/rate`, { hourly_rate: amount, currency }),
    'llcRoles.errorSetRate',
  )
}

async function clearRate(): Promise<void> {
  await mutate(() => api.delete(`${detailBase()}/rate`), 'llcRoles.errorClearRate')
}

/**
 * Record how long a step takes and how often it runs.
 *
 * An empty field sends `null`, which clears the value back to *not recorded*.
 * Treating empty as "leave unchanged" would make a mistyped number impossible
 * to remove, and a wrong measurement is worse than an absent one because it is
 * silently summed.
 */
async function saveStepCost(
  workflowId: string,
  minutes: string | number,
  runs: string | number,
): Promise<void> {
  const toValue = (raw: string | number): number | null => {
    const trimmed = asText(raw).trim()
    if (trimmed === '') return null
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed) : null
  }
  await mutate(
    () =>
      api.put(`${detailBase()}/workflows/${encodeURIComponent(workflowId)}/cost`, {
        estimated_minutes: toValue(minutes),
        runs_per_month: toValue(runs),
      }),
    'llcRoles.errorSetStepCost',
  )
}

async function selectRole(roleId: string): Promise<void> {
  selectedRoleId.value = roleId
  await loadDetail()
}

function openCreateModal(): void {
  newRoleName.value = ''
  newRoleDescription.value = ''
  isCreateModalOpen.value = true
}

function closeCreateModal(): void {
  isCreateModalOpen.value = false
}

async function createRole(): Promise<void> {
  if (!companyId.value || !newRoleName.value.trim()) return
  try {
    await api.post(`/api/llc/roles/${companyId.value}`, {
      name: newRoleName.value.trim(),
      description: newRoleDescription.value.trim() || null,
    })
    closeCreateModal()
    await loadRoles()
  } catch (error) {
    logger.error('Failed to create role', error)
    errorMessage.value = describeError(error, 'llcRoles.errorCreate')
  }
}

/**
 * Run one mutation, then reload from the server (#14221 step 6b).
 *
 * Deliberately no optimistic update. These lists describe who may reach what;
 * a local list that diverges from the server would show access that does not
 * exist, which is worse than a moment's latency. The reload is the assertion
 * that the change actually happened.
 */
async function mutate(call: () => Promise<unknown>, fallbackKey: string): Promise<void> {
  if (isMutating.value) return
  isMutating.value = true
  errorMessage.value = ''
  try {
    await call()
    await loadDetail()
  } catch (error) {
    logger.error('Role mutation failed', error)
    errorMessage.value = describeError(error, fallbackKey)
  } finally {
    isMutating.value = false
  }
}

function detailBase(): string {
  return `/api/llc/roles/${companyId.value}/${selectedRoleId.value}`
}

async function assignHolder(): Promise<void> {
  const holderId = newHolderId.value.trim()
  if (!holderId) return
  await mutate(
    () =>
      api.post(`${detailBase()}/holders`, {
        holder_type: newHolderType.value,
        holder_id: holderId,
      }),
    'llcRoles.errorAssign',
  )
  newHolderId.value = ''
}

async function endTenure(assignmentId: string): Promise<void> {
  await mutate(
    () => api.delete(`${detailBase()}/holders/${encodeURIComponent(assignmentId)}`),
    'llcRoles.errorEndTenure',
  )
}

async function grantPermission(permission: string): Promise<void> {
  await mutate(
    () => api.post(`${detailBase()}/permissions`, { permission }),
    'llcRoles.errorGrant',
  )
}

async function revokePermission(permission: string): Promise<void> {
  await mutate(
    () => api.delete(`${detailBase()}/permissions/${encodeURIComponent(permission)}`),
    'llcRoles.errorRevoke',
  )
}

async function attachWorkflow(workflowId: string): Promise<void> {
  await mutate(
    () => api.post(`${detailBase()}/workflows`, { workflow_id: workflowId }),
    'llcRoles.errorAttach',
  )
}

async function detachWorkflow(workflowId: string): Promise<void> {
  await mutate(
    () => api.delete(`${detailBase()}/workflows/${encodeURIComponent(workflowId)}`),
    'llcRoles.errorDetach',
  )
}

async function attachTool(toolName: string): Promise<void> {
  await mutate(
    () => api.post(`${detailBase()}/tools`, { tool_name: toolName }),
    'llcRoles.errorAttach',
  )
}

async function detachTool(toolName: string): Promise<void> {
  await mutate(
    () => api.delete(`${detailBase()}/tools/${encodeURIComponent(toolName)}`),
    'llcRoles.errorDetach',
  )
}

async function attachCredential(secretId: string): Promise<void> {
  await mutate(
    () => api.post(`${detailBase()}/credentials`, { secret_id: secretId }),
    'llcRoles.errorAttach',
  )
}

async function detachCredential(secretId: string): Promise<void> {
  await mutate(
    () => api.delete(`${detailBase()}/credentials/${encodeURIComponent(secretId)}`),
    'llcRoles.errorDetach',
  )
}

async function removeRole(roleId: string): Promise<void> {
  if (!companyId.value) return
  try {
    await api.delete(`/api/llc/roles/${companyId.value}/${roleId}`)
    if (selectedRoleId.value === roleId) selectedRoleId.value = null
    await loadRoles()
  } catch (error) {
    logger.error('Failed to delete role', error)
    errorMessage.value = describeError(error, 'llcRoles.errorDelete')
  }
}

watch(companyId, async () => {
  selectedRoleId.value = null
  await loadRoles()
})

onMounted(loadRoles)
</script>

<style scoped>
.roles-view {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.roles-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-md);
}

.roles-title {
  margin: 0;
  font-size: var(--font-size-xl);
  color: var(--color-text-primary);
}

.roles-subtitle {
  margin: var(--spacing-xs) 0 0;
  color: var(--color-text-secondary);
}

.roles-state,
.roles-section-empty {
  color: var(--color-text-secondary);
}

.roles-layout {
  display: grid;
  grid-template-columns: minmax(12rem, 18rem) 1fr;
  gap: var(--spacing-lg);
  align-items: start;
}

.roles-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.roles-list-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm);
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-primary);
  cursor: pointer;
  text-align: start;
}

.roles-list-item:hover,
.roles-list-item.is-active {
  background: var(--color-surface-hover);
}

.roles-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.roles-detail-name {
  margin: 0;
  font-size: var(--font-size-lg);
  color: var(--color-text-primary);
}

.roles-detail-description {
  margin: var(--spacing-xs) 0 0;
  color: var(--color-text-secondary);
}

.roles-section {
  margin-top: var(--spacing-md);
}

.roles-section-title {
  margin: 0 0 var(--spacing-xs);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
}

.roles-chip-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.roles-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-sm);
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  font-family: var(--font-family-mono, monospace);
  font-size: var(--font-size-sm);
}

.roles-chip-note {
  color: var(--color-text-secondary);
  font-family: var(--font-family-base, inherit);
}

.roles-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  color: var(--color-text-secondary);
}

.roles-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-md);
}

.roles-chip-action {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--font-size-md);
  line-height: 1;
  padding: 0;
}

.roles-chip-action:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.roles-chip-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.roles-assign {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
  flex-wrap: wrap;
}

.roles-assign-id {
  flex: 1 1 14rem;
  min-width: 0;
}

@media (max-width: 48rem) {
  .roles-layout {
    grid-template-columns: 1fr;
  }
}
</style>
