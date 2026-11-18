<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  HandbookPageDetail (#18431): one generated reference page, the "From the company model"
  half of the mockup. Every line is read from the model's own routes; the owner-written
  explanation half has no store yet, so the page says so instead of showing prose.
-->
<template>
  <article class="flex flex-col gap-3" data-testid="handbook-page">
    <header class="flex flex-wrap items-center gap-2">
      <h2 class="m-0 text-lg text-autobot-text-primary" data-testid="handbook-page-title">{{ page.title }}</h2>
      <BaseBadge size="sm" variant="neutral">{{ t(`llc.handbook.kind.${page.kind}`) }}</BaseBadge>
    </header>

    <p v-if="page.description" class="m-0 text-autobot-text-primary" data-testid="handbook-description">{{ page.description }}</p>
    <p v-else class="m-0 text-autobot-text-secondary" data-testid="handbook-no-description">{{ t('llc.handbook.noDescription') }}</p>

    <p v-if="ownerName" class="m-0 text-autobot-text-secondary" data-testid="handbook-owner">{{ t('llc.handbook.ownedBy', { role: ownerName }) }}</p>

    <p v-if="detail.state === 'loading'" class="m-0 text-autobot-text-secondary" role="status">{{ t('llc.handbook.loadingPage') }}</p>
    <template v-else>
      <BaseAlert v-if="detail.failed.length > 0" variant="error" data-testid="handbook-page-failed"
        :message="t('llc.handbook.partsFailed', { parts: detail.failed.map((p) => t(`llc.handbook.part.${p}`)).join(', ') })" />

      <section v-if="page.kind === 'role'" class="flex flex-col gap-3">
        <div>
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.holders') }}</h3>
          <p v-if="!failed('holders') && detail.holders.length === 0" class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.noHolders') }}</p>
          <ul class="m-0 ps-4" data-testid="handbook-holders">
            <li v-for="h in detail.holders" :key="h.id">{{ t(`llcRoles.holderType.${h.holder_type}`) }}: {{ h.holder_id }}</li>
          </ul>
        </div>
        <div>
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.workflowsItPerforms') }}</h3>
          <p v-if="!failed('workflows') && detail.workflowIds.length === 0" class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.noWorkflows') }}</p>
          <ul class="m-0 ps-4" data-testid="handbook-role-workflows">
            <li v-for="id in detail.workflowIds" :key="id">{{ names.workflow(id) }}</li>
          </ul>
        </div>
        <div>
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.processesItOwns') }}</h3>
          <p v-if="ownedProcesses.length === 0" class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.noProcesses') }}</p>
          <ul class="m-0 ps-4" data-testid="handbook-role-processes">
            <li v-for="p in ownedProcesses" :key="p.id">{{ p.title }}</li>
          </ul>
        </div>
        <div>
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.skills') }}</h3>
          <p v-if="!failed('skills') && heldSkills.length === 0" class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.noSkills') }}</p>
          <ul class="m-0 ps-4" data-testid="handbook-role-skills">
            <li v-for="s in heldSkills" :key="s.skill">{{ s.skill }}</li>
          </ul>
        </div>
        <div>
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.tools') }}</h3>
          <p v-if="!failed('tools') && detail.tools.length === 0" class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.noTools') }}</p>
          <ul class="m-0 ps-4" data-testid="handbook-role-tools">
            <li v-for="tool in detail.tools" :key="tool">{{ tool }}</li>
          </ul>
        </div>
      </section>

      <section v-else-if="page.kind === 'process'" class="flex flex-col gap-3">
        <div>
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.requiredSkills') }}</h3>
          <p v-if="requiredSkills.length === 0" class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.noSkillsNeeded') }}</p>
          <ul class="m-0 ps-4" data-testid="handbook-process-skills">
            <li v-for="s in requiredSkills" :key="s">{{ s }}</li>
          </ul>
        </div>
      </section>

      <section v-else class="flex flex-col gap-3">
        <div v-if="workflow && workflow.trigger_type">
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.trigger') }}</h3>
          <p class="m-0" data-testid="handbook-trigger">{{ t(`llc.handbook.triggerKind.${workflow.trigger_type}`) }}</p>
          <ul class="m-0 ps-4">
            <li v-for="[key, value] in triggerConfig" :key="key">{{ key }}: {{ value }}</li>
          </ul>
        </div>
        <div>
          <h3 class="m-0 mb-1 text-base text-autobot-text-primary">{{ t('llc.handbook.steps') }}</h3>
          <p v-if="!failed('graph') && steps.length === 0" class="m-0 text-autobot-text-secondary" data-testid="handbook-no-steps">{{ t('llc.handbook.noSteps') }}</p>
          <ol class="m-0 ps-4" data-testid="handbook-steps">
            <li v-for="s in steps" :key="s.key">
              {{ s.title }}
              <ul class="m-0 ps-4 text-autobot-text-secondary">
                <li v-for="(o, i) in s.outcomes" :key="i">{{ o }}</li>
              </ul>
            </li>
          </ol>
        </div>
      </section>
    </template>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseBadge } from '@autobot/ui'
import { graphSteps, type GraphNames } from '@/composables/llc/handbookGraphText'
import type { HandbookPage, HandbookProcess, HandbookWorkflow, PageDetail } from '@/composables/llc/useHandbook'

const props = defineProps<{
  page: HandbookPage
  detail: PageDetail
  pages: HandbookPage[]
  workflows: HandbookWorkflow[]
  processes: HandbookProcess[]
  names: GraphNames & { role: (id: string | null) => string }
}>()

const { t } = useI18n()
const failed = (part: string): boolean => props.detail.failed.includes(part)
const ownerName = computed(() => props.names.role(props.page.ownerRoleId))
const workflow = computed(() => props.workflows.find((w) => w.workflow_id === props.page.id))
const triggerConfig = computed(() => Object.entries(workflow.value?.trigger_config ?? {}).map(([k, v]) => [k, String(v)]))
const requiredSkills = computed(() => props.processes.find((p) => p.process_key === props.page.id)?.required_skills ?? [])
const heldSkills = computed(() => props.detail.skills?.skills ?? [])
const ownedProcesses = computed(() => props.pages.filter((p) => p.kind === 'process' && p.ownerRoleId === props.page.id))
const steps = computed(() => (props.detail.graph ? graphSteps(props.detail.graph.graph, props.names, (key, params) => t(key, params ?? {})) : []))
</script>
