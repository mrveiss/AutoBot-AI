<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <BaseAccordion
    v-model="open"
    class="mb-4"
    type="multiple"
    size="sm"
    :items="sections"
    data-testid="hierarchy-panel"
  >
    <template #panel-rules>
      <BaseAlert v-if="rulesFailed" variant="warning" :message="t('llc.backlog.hierarchyRulesFailed')">
        <template #actions>
          <BaseButton size="sm" variant="secondary" data-testid="retry-rules" @click="loadRules">{{ t('common.retry') }}</BaseButton>
        </template>
      </BaseAlert>
      <p class="mb-2 text-xs text-autobot-text-secondary">{{ t('llc.backlog.hierarchyRulesHint') }}</p>
      <ul class="m-0 flex list-none flex-col gap-1 p-0 text-sm" data-testid="hierarchy-rules">
        <li v-for="rule in rules" :key="rule.type" class="flex gap-3">
          <strong class="min-w-24 font-semibold">{{ typeLabel(rule.type) }}</strong>
          <span>{{ parentsText(rule) }}</span>
        </li>
      </ul>
    </template>

    <template #panel-violations>
      <BaseAlert v-if="violationsFailed" variant="warning" :message="t('llc.backlog.hierarchyViolationsFailed')">
        <template #actions>
          <BaseButton size="sm" variant="secondary" data-testid="retry-violations" @click="loadViolations">{{ t('common.retry') }}</BaseButton>
        </template>
      </BaseAlert>
      <p v-else-if="violations.length === 0" class="mb-2 text-xs text-autobot-text-secondary" data-testid="no-violations">{{ t('llc.backlog.hierarchyNoViolations') }}</p>
      <ul v-else class="m-0 flex list-none flex-col gap-1 p-0 text-sm" data-testid="hierarchy-violations">
        <li v-for="row in violations" :key="row.id" class="flex gap-3">
          <span class="min-w-24 font-semibold">{{ row.identifier }}</span>
          <span>{{ reasonText(row) }}</span>
        </li>
      </ul>
      <p v-if="truncated" class="mt-2 text-xs text-autobot-text-secondary" data-testid="violations-truncated">
        {{ t('llc.backlog.hierarchyViolationsTruncated', { count: violations.length }) }}
      </p>
    </template>
  </BaseAccordion>
</template>

<script setup lang="ts">
// Read-only: the rule table (everyone) and the report of rows that already break it (company and platform admins).
// The server decides who may read the report; a refusal hides the section (#20936).
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAccordion, BaseAlert, BaseButton } from '@autobot/ui'
import { useWorkItemHierarchy, type HierarchyRule, type HierarchyViolationRow } from '@/composables/llc/useWorkItemHierarchy'
import { WORK_ITEM_TYPES } from '@/views/llc/workItemTypes'

const props = defineProps<{ companyId: string }>()
const { t } = useI18n()
const companyId = computed(() => props.companyId)
const { rules, violations, truncated, rulesFailed, violationsFailed, canSeeViolations, loadRules, loadViolations, reset } =
  useWorkItemHierarchy(companyId)

const open = ref<string[]>([])
const sections = computed(() => [
  { value: 'rules', label: t('llc.backlog.hierarchyRulesTitle') },
  ...(canSeeViolations.value
    ? [{ value: 'violations', label: t('llc.backlog.hierarchyViolationsTitle', { count: violations.value.length }) }]
    : []),
])

function typeLabel(type: string): string {
  const known = WORK_ITEM_TYPES.find(wt => wt.value === type)
  return known ? t(known.labelKey) : type
}

function parentsText(rule: HierarchyRule): string {
  if (rule.allowed_parent_types.length === 0) return t('llc.backlog.hierarchyNoParent')
  return t('llc.backlog.hierarchyUnder', { parents: rule.allowed_parent_types.map(typeLabel).join(', ') })
}

const REASON_CODES = [
  'parent_cycle',
  'parent_missing',
  'parent_type_not_allowed',
  'project_mismatch',
  'project_required',
]

/** The translated reason for a row's stable code; an unknown code falls back to the server's English text. */
function reasonText(row: HierarchyViolationRow): string {
  if (!REASON_CODES.includes(row.code)) return row.reason
  return t(`llc.backlog.hierarchyReason.${row.code}`, {
    type: typeLabel(row.type),
    parentType: row.parent_type ? typeLabel(row.parent_type) : '',
  })
}

function loadAll(): void {
  reset() // a company change never shows the previous company's rows while the new ones load
  void loadRules()
  void loadViolations()
}

onMounted(loadAll)
watch(companyId, loadAll)
</script>
