<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Skills Management View (Issue #731)
 *
 * Admin interface for viewing, enabling/disabling, and configuring
 * AI skills across the AutoBot platform.
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSkills, useSkillGovernance, type SkillInfo } from '@/composables/useSkills'
import GovernanceModeSelector from '@/components/skills/GovernanceModeSelector.vue'
import ApprovalsTab from '@/components/skills/ApprovalsTab.vue'
import ReposTab from '@/components/skills/ReposTab.vue'
import DraftsTab from '@/components/skills/DraftsTab.vue'
import { BaseModal, PollingPausedAlert } from '@autobot/ui'

const {
  skills,
  categories,
  selectedSkill,
  loading,
  error,
  enabledSkills,
  disabledSkills,
  skillsByCategory,
  fetchSkills,
  fetchSkillDetail,
  enableSkill,
  disableSkill,
  updateConfig,
  initializeSkills,
} = useSkills()

const {
  repos,
  approvals,
  drafts,
  governanceConfig,
  newDraftNotification,
  fetchRepos,
  syncRepo,
  addRepo,
  fetchApprovals,
  decideApproval,
  fetchDrafts,
  testDraft,
  promoteDraft,
  fetchGovernance,
  setGovernanceMode,
  approvalPoller, startApprovalPolling,
  dismissDraftNotification,
} = useSkillGovernance()

const route = useRoute()
const router = useRouter()

// Active tab — route-based
type SkillTab = 'active' | 'approvals' | 'repos' | 'drafts'
const validSkillTabs: SkillTab[] = ['active', 'approvals', 'repos', 'drafts']
function resolveSkillTab(param: unknown): SkillTab {
  return validSkillTabs.includes(param as SkillTab) ? (param as SkillTab) : 'active'
}
const activeTab = computed(() => resolveSkillTab(route.params.tab))
function navigateToTab(tab: SkillTab): void {
  router.push({ name: 'skills', params: { tab } })
}

const activeCategory = ref<string | null>(null)
const searchQuery = ref('')
const showDetail = ref(false)
const configEditing = ref<Record<string, unknown>>({})
const savingConfig = ref(false)

// --- Computed ---

const filteredSkills = computed(() => {
  if (activeCategory.value) {
    return skillsByCategory.value[activeCategory.value] || []
  }
  return skills.value
})

const statusCounts = computed(() => ({
  total: skills.value.length,
  enabled: enabledSkills.value.length,
  disabled: disabledSkills.value.length,
}))

// --- Actions ---

async function handleToggle(skill: SkillInfo): Promise<void> {
  if (skill.enabled) {
    await disableSkill(skill.name)
  } else {
    await enableSkill(skill.name)
  }
}

async function openDetail(skill: SkillInfo): Promise<void> {
  await fetchSkillDetail(skill.name)
  showDetail.value = true
  if (selectedSkill.value) {
    configEditing.value = { ...selectedSkill.value.current_config }
  }
}

function closeDetail(): void {
  showDetail.value = false
}

async function saveConfig(): Promise<void> {
  if (!selectedSkill.value) return
  savingConfig.value = true
  await updateConfig(selectedSkill.value.name, configEditing.value)
  savingConfig.value = false
}

function handleSearch(): void {
  fetchSkills(undefined, searchQuery.value || undefined)
}

function selectCategory(cat: string | null): void {
  activeCategory.value = cat
  if (cat) {
    fetchSkills(cat)
  } else {
    fetchSkills()
  }
}

// --- Lifecycle ---

let unmounted = false
onUnmounted(() => { unmounted = true })
onMounted(async () => {
  await Promise.all([initializeSkills(), fetchGovernance(), fetchApprovals(), fetchRepos(), fetchDrafts()])
  if (!unmounted) startApprovalPolling()
})

watch(searchQuery, (val) => {
  if (!val) fetchSkills()
})

// --- Status helpers ---

function statusColor(status: string): string {
  const colors: Record<string, string> = {
    enabled: 'text-autobot-success',
    disabled: 'text-autobot-text-tertiary',
    error: 'text-autobot-error',
    loading: 'text-autobot-info',
    missing_deps: 'text-autobot-warning',
    available: 'text-autobot-info',
  }
  return colors[status] || 'text-autobot-text-tertiary'
}

function statusBadge(status: string): string {
  const badges: Record<string, string> = {
    enabled: 'bg-autobot-success/20 text-autobot-success border-autobot-success/30',
    disabled: 'bg-autobot-text-muted/20 text-autobot-text-secondary border-autobot-text-muted/30',
    error: 'bg-autobot-error/20 text-autobot-error border-autobot-error/30',
    missing_deps: 'bg-autobot-warning/20 text-autobot-warning border-autobot-warning/30',
    available: 'bg-autobot-info-solid/20 text-autobot-info border-autobot-info/30',
  }
  return badges[status] || 'bg-autobot-text-muted/20 text-autobot-text-secondary border-autobot-text-muted/30'
}

function categoryIcon(category: string): string {
  const icons: Record<string, string> = {
    audio: '🎙',
    analysis: '📊',
    development: '💻',
    automation: '🤖',
    productivity: '📋',
    general: '⚡',
  }
  return icons[category] || '📦'
}
</script>

<template>
  <div class="min-h-screen bg-autobot-bg-primary text-autobot-text-primary p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">{{ $t('skillsView.skillsManagement') }}</h1>
        <p class="text-autobot-text-tertiary text-sm mt-1">
          {{ $t('skillsView.manageAICapabilitiesAs') }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-sm text-autobot-text-tertiary">{{ $t('skillsView.value0Value1Enabled', { value0: statusCounts.enabled, value1: statusCounts.total }) }}</span>
        <button
          @click="initializeSkills()"
          :disabled="loading"
          class="px-3 py-1.5 bg-autobot-primary hover:bg-autobot-primary-hover rounded text-sm
                 disabled:opacity-50 transition-colors"
        >
          {{ loading ? $t('skillsView.loading') : $t('skillsView.refresh') }}
        </button>
      </div>
    </div>

    <!-- Issue #951: autonomous skill development notification -->
    <div
      v-if="newDraftNotification"
      class="flex items-center justify-between bg-autobot-warning/15 border border-autobot-warning/30
             rounded-lg px-4 py-3 mb-4 text-autobot-warning text-sm"
    >
      <span>{{ newDraftNotification }}</span>
      <div class="flex items-center gap-3">
        <button
          class="underline hover:no-underline text-autobot-warning"
          @click="navigateToTab('approvals')"
        >
          {{ $t('skillsView.review') }}
        </button>
        <button class="opacity-60 hover:opacity-100" @click="dismissDraftNotification">
          ✕
        </button>
      </div>
    </div>

    <!-- Tab Bar + Governance Mode Selector -->
    <div class="flex flex-col gap-3 mb-6">
      <div class="flex items-center justify-between">
        <div class="flex gap-1">
          <button
            :class="[
              'px-4 py-2 rounded-sm text-sm border transition-colors',
              activeTab === 'active'
                ? 'bg-autobot-primary border-autobot-primary text-autobot-text-on-primary'
                : 'bg-autobot-bg-card border-autobot-border text-autobot-text-secondary hover:border-autobot-border-strong',
            ]"
            @click="navigateToTab('active')"
          >
            {{ $t('skillsView.activeSkills') }}
          </button>
          <button
            :class="[
              'px-4 py-2 rounded-sm text-sm border transition-colors flex items-center gap-2',
              activeTab === 'approvals'
                ? 'bg-autobot-primary border-autobot-primary text-autobot-text-on-primary'
                : 'bg-autobot-bg-card border-autobot-border text-autobot-text-secondary hover:border-autobot-border-strong',
            ]"
            @click="navigateToTab('approvals')"
          >
            {{ $t('skillsView.pending') }}
            <span
              v-if="approvals.length > 0"
              class="px-1.5 py-0.5 bg-autobot-dot-warn text-(--text-on-warning) text-xs rounded-full"
            >
              {{ approvals.length }}
            </span>
          </button>
          <button
            :class="[
              'px-4 py-2 rounded-sm text-sm border transition-colors',
              activeTab === 'repos'
                ? 'bg-autobot-primary border-autobot-primary text-autobot-text-on-primary'
                : 'bg-autobot-bg-card border-autobot-border text-autobot-text-secondary hover:border-autobot-border-strong',
            ]"
            @click="navigateToTab('repos')"
          >
            {{ $t('skillsView.repos') }}
          </button>
          <button
            :class="[
              'px-4 py-2 rounded-sm text-sm border transition-colors',
              activeTab === 'drafts'
                ? 'bg-autobot-primary border-autobot-primary text-autobot-text-on-primary'
                : 'bg-autobot-bg-card border-autobot-border text-autobot-text-secondary hover:border-autobot-border-strong',
            ]"
            @click="navigateToTab('drafts')"
          >
            {{ $t('skillsView.drafts') }}
          </button>
        </div>
        <GovernanceModeSelector
          v-if="governanceConfig"
          :model-value="governanceConfig.mode"
          @update:model-value="setGovernanceMode"
        />
      </div>
    </div>

    <!-- Non-active-tab panels -->
    <ApprovalsTab
      v-if="activeTab === 'approvals'"
      :approvals="approvals"
      @approve="(id, trust) => decideApproval(id, true, trust)"
      @reject="(id) => decideApproval(id, false)"
    />
    <ReposTab
      v-if="activeTab === 'repos'"
      :repos="repos"
      @sync="syncRepo"
      @add="addRepo"
    />
    <DraftsTab
      v-if="activeTab === 'drafts'"
      :drafts="drafts"
      @test="testDraft"
      @promote="promoteDraft"
    />

    <PollingPausedAlert :poller="approvalPoller" :message="$t('common.polling.paused')" :retry-label="$t('common.polling.retry')" @retry="startApprovalPolling" />

    <!-- Error Banner (active skills tab) -->
    <template v-if="activeTab === 'active'">
    <div
      v-if="error"
      class="mb-4 p-3 bg-autobot-error/30 border border-autobot-error/30 rounded-sm text-autobot-error text-sm"
    >
      {{ error }}
    </div>

    <!-- Stats Bar -->
    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-autobot-bg-card rounded-lg p-4 border border-autobot-border">
        <div class="text-2xl font-bold text-autobot-info">{{ statusCounts.total }}</div>
        <div class="text-sm text-autobot-text-tertiary">{{ $t('skillsView.totalSkills') }}</div>
      </div>
      <div class="bg-autobot-bg-card rounded-lg p-4 border border-autobot-border">
        <div class="text-2xl font-bold text-autobot-success">{{ statusCounts.enabled }}</div>
        <div class="text-sm text-autobot-text-tertiary">{{ $t('skillsView.enabled') }}</div>
      </div>
      <div class="bg-autobot-bg-card rounded-lg p-4 border border-autobot-border">
        <div class="text-2xl font-bold text-autobot-text-tertiary">{{ statusCounts.disabled }}</div>
        <div class="text-sm text-autobot-text-tertiary">{{ $t('skillsView.disabled') }}</div>
      </div>
    </div>

    <!-- Search & Category Filter -->
    <div class="flex gap-4 mb-6">
      <div class="flex-1">
        <input
          v-model="searchQuery"
          @keyup.enter="handleSearch"
          type="text"
          :placeholder="$t('skillsView.searchSkillsByNameDescriptionOr')"
          class="w-full bg-autobot-bg-card border border-autobot-border rounded-lg px-4 py-2
                 text-autobot-text-primary placeholder-autobot-text-tertiary focus:outline-hidden focus:border-autobot-primary"
        />
      </div>
      <div class="flex gap-2 flex-wrap">
        <button
          @click="selectCategory(null)"
          :class="[
            'px-3 py-1.5 rounded-sm text-sm transition-colors border',
            !activeCategory
              ? 'bg-autobot-primary border-autobot-primary text-autobot-text-on-primary'
              : 'bg-autobot-bg-card border-autobot-border text-autobot-text-secondary hover:border-autobot-border-strong'
          ]"
        >
          {{ $t('skillsView.all') }}
        </button>
        <button
          v-for="cat in categories"
          :key="cat"
          @click="selectCategory(cat)"
          :class="[
            'px-3 py-1.5 rounded-sm text-sm transition-colors border',
            activeCategory === cat
              ? 'bg-autobot-primary border-autobot-primary text-autobot-text-on-primary'
              : 'bg-autobot-bg-card border-autobot-border text-autobot-text-secondary hover:border-autobot-border-strong'
          ]"
        >
          {{ categoryIcon(cat) }} {{ cat }}
        </button>
      </div>
    </div>

    <!-- Skills Grid -->
    <div v-if="loading && !skills.length" class="text-center py-12 text-autobot-text-tertiary">
      {{ $t('skillsView.loadingSkills') }}
    </div>

    <div v-else-if="!filteredSkills.length" class="text-center py-12 text-autobot-text-tertiary">
      {{ searchQuery ? $t('skillsView.noSkillsFoundForQuery', { query: searchQuery }) : $t('skillsView.noSkillsFound') }}
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="skill in filteredSkills"
        :key="skill.name"
        class="bg-autobot-bg-card rounded-lg border border-autobot-border p-4
               hover:border-autobot-border-strong transition-colors cursor-pointer"
        @click="openDetail(skill)"
      >
        <!-- Skill Header -->
        <div class="flex items-start justify-between mb-2">
          <div>
            <h3 class="font-semibold text-autobot-text-primary">{{ skill.name }}</h3>
            <span class="text-xs text-autobot-text-tertiary">v{{ skill.version }}</span>
          </div>
          <button
            @click.stop="handleToggle(skill)"
            :class="[
              'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
              skill.enabled ? 'bg-autobot-success-hover' : 'bg-autobot-bg-active'
            ]"
          >
            <span
              :class="[
                'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                skill.enabled ? 'translate-x-6' : 'translate-x-1'
              ]"
            />
          </button>
        </div>

        <!-- Description -->
        <p class="text-sm text-autobot-text-tertiary mb-3 line-clamp-2">
          {{ skill.description }}
        </p>

        <!-- Status & Meta -->
        <div class="flex items-center justify-between">
          <span
            :class="['text-xs px-2 py-0.5 rounded-sm border', statusBadge(skill.status)]"
          >
            {{ skill.status }}
          </span>
          <div class="flex items-center gap-2 text-xs text-autobot-text-tertiary">
            <span>{{ categoryIcon(skill.category) }} {{ skill.category }}</span>
            <span>{{ $t('skillsView.countTools', { count: skill.tools.length }) }}</span>
          </div>
        </div>

        <!-- Tags -->
        <div v-if="skill.tags.length" class="mt-2 flex flex-wrap gap-1">
          <span
            v-for="tag in skill.tags.slice(0, 3)"
            :key="tag"
            class="text-xs px-1.5 py-0.5 bg-autobot-bg-tertiary rounded-sm text-autobot-text-tertiary"
          >
            {{ tag }}
          </span>
          <span
            v-if="skill.tags.length > 3"
            class="text-xs text-autobot-text-tertiary"
          >
            +{{ skill.tags.length - 3 }}
          </span>
        </div>
      </div>
    </div>
    </template><!-- end activeTab === 'active' -->

    <!-- Skill Detail Modal -->
    <BaseModal
      v-if="selectedSkill"
      :model-value="showDetail"
      :title="selectedSkill?.name ?? ''"
      width="42rem"
      :close-label="$t('ui.modal.closeDialog')"
      @close="closeDetail"
    >
      <template #subtitle>
        {{ selectedSkill?.description }}
      </template>
      <div class="space-y-5">
        <!-- Info Grid -->
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span class="text-autobot-text-tertiary">{{ $t('skillsView.version') }}</span>
            <div class="text-autobot-text-primary">{{ selectedSkill.version }}</div>
          </div>
          <div>
            <span class="text-autobot-text-tertiary">{{ $t('skillsView.author') }}</span>
            <div class="text-autobot-text-primary">{{ selectedSkill.author }}</div>
          </div>
          <div>
            <span class="text-autobot-text-tertiary">{{ $t('skillsView.category') }}</span>
            <div class="text-autobot-text-primary">
              {{ categoryIcon(selectedSkill.category) }} {{ selectedSkill.category }}
            </div>
          </div>
          <div>
            <span class="text-autobot-text-tertiary">{{ $t('skillsView.status') }}</span>
            <div :class="statusColor(selectedSkill.status)">
              {{ selectedSkill.status }}
            </div>
          </div>
        </div>

        <!-- Tools -->
        <div>
          <h3 class="text-sm font-semibold text-autobot-text-secondary mb-2">{{ $t('skillsView.tools') }}</h3>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="tool in selectedSkill.tools"
              :key="tool"
              class="px-2 py-1 bg-autobot-info-solid/30 border border-autobot-info/30
                     rounded text-sm text-autobot-info"
            >
              {{ tool }}
            </span>
          </div>
        </div>

        <!-- Triggers -->
        <div v-if="selectedSkill.triggers.length">
          <h3 class="text-sm font-semibold text-autobot-text-secondary mb-2">{{ $t('skillsView.triggers') }}</h3>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="trigger in selectedSkill.triggers"
              :key="trigger"
              class="px-2 py-1 bg-autobot-illus-2/30 border border-autobot-illus-2/30
                     rounded text-sm text-autobot-text-primary"
            >
              {{ trigger }}
            </span>
          </div>
        </div>

        <!-- Dependencies -->
        <div v-if="selectedSkill.dependencies.length">
          <h3 class="text-sm font-semibold text-autobot-text-secondary mb-2">{{ $t('skillsView.dependencies') }}</h3>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="dep in selectedSkill.dependencies"
              :key="dep"
              class="px-2 py-1 bg-autobot-warning/30 border border-autobot-warning/30
                     rounded text-sm text-autobot-warning"
            >
              {{ dep }}
            </span>
          </div>
        </div>

        <!-- Configuration -->
        <div v-if="Object.keys(selectedSkill.config_schema).length">
          <h3 class="text-sm font-semibold text-autobot-text-secondary mb-2">{{ $t('skillsView.configuration') }}</h3>
          <div class="space-y-3">
            <div
              v-for="(schema, key) in selectedSkill.config_schema"
              :key="key"
              class="bg-autobot-bg-primary rounded-sm p-3"
            >
              <label class="block text-sm text-autobot-text-secondary mb-1">
                {{ key }}
                <span class="text-autobot-text-tertiary ml-1">{{ schema.description }}</span>
              </label>

              <!-- Select for choices -->
              <select
                v-if="schema.choices"
                v-model="configEditing[key]"
                class="w-full bg-autobot-bg-card border border-autobot-border rounded px-3 py-1.5
                       text-autobot-text-primary text-sm focus:outline-hidden focus:border-autobot-primary"
              >
                <option v-for="c in schema.choices" :key="c" :value="c">{{ c }}</option>
              </select>

              <!-- Toggle for bool -->
              <button
                v-else-if="schema.type === 'bool'"
                @click="configEditing[key] = !configEditing[key]"
                :class="[
                  'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                  configEditing[key] ? 'bg-autobot-success-hover' : 'bg-autobot-bg-active'
                ]"
              >
                <span
                  :class="[
                    'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                    configEditing[key] ? 'translate-x-6' : 'translate-x-1'
                  ]"
                />
              </button>

              <!-- Number input -->
              <input
                v-else-if="schema.type === 'int' || schema.type === 'float'"
                v-model.number="configEditing[key]"
                type="number"
                class="w-full bg-autobot-bg-card border border-autobot-border rounded px-3 py-1.5
                       text-autobot-text-primary text-sm focus:outline-hidden focus:border-autobot-primary"
              />

              <!-- Text input -->
              <input
                v-else
                v-model="configEditing[key]"
                type="text"
                class="w-full bg-autobot-bg-card border border-autobot-border rounded px-3 py-1.5
                       text-autobot-text-primary text-sm focus:outline-hidden focus:border-autobot-primary"
              />
            </div>
          </div>

          <button
            @click="saveConfig"
            :disabled="savingConfig"
            class="mt-3 px-4 py-2 bg-autobot-primary hover:bg-autobot-primary-hover rounded text-sm
                   disabled:opacity-50 transition-colors"
          >
            {{ savingConfig ? $t('skillsView.saving') : $t('skillsView.saveConfiguration') }}
          </button>
        </div>

        <!-- Health -->
        <div>
          <h3 class="text-sm font-semibold text-autobot-text-secondary mb-2">{{ $t('skillsView.health') }}</h3>
          <div class="bg-autobot-bg-primary rounded-sm p-3 text-sm">
            <div class="flex items-center gap-2">
              <span
                :class="[
                  'w-2 h-2 rounded-full',
                  selectedSkill.health.config_valid && selectedSkill.health.dependencies_met
                    ? 'bg-autobot-success' : 'bg-autobot-error'
                ]"
              />
              <span class="text-autobot-text-secondary">{{ $t('skillsView.configValue0', { value0: selectedSkill.health.config_valid ? $t('skillsView.valid') : $t('skillsView.invalid') }) }}</span>
              <span class="text-autobot-text-tertiary mx-1">|</span>
              <span class="text-autobot-text-secondary">{{ $t('skillsView.depsValue0', { value0: selectedSkill.health.dependencies_met ? $t('skillsView.met') : $t('skillsView.missing') }) }}</span>
            </div>
          </div>
        </div>
      </div>
    </BaseModal>
  </div>
</template>
