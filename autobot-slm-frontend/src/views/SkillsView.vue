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

import { ref, computed, onMounted, watch } from 'vue'
import { useSkills, useSkillGovernance, type SkillInfo } from '@/composables/useSkills'
import GovernanceModeSelector from '@/components/skills/GovernanceModeSelector.vue'
import ApprovalsTab from '@/components/skills/ApprovalsTab.vue'
import ReposTab from '@/components/skills/ReposTab.vue'
import DraftsTab from '@/components/skills/DraftsTab.vue'

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
} = useSkillGovernance()

const activeTab = ref<'active' | 'approvals' | 'repos' | 'drafts'>('active')

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

onMounted(async () => {
  await Promise.all([
    initializeSkills(),
    fetchGovernance(),
    fetchApprovals(),
    fetchRepos(),
    fetchDrafts(),
  ])
})

watch(searchQuery, (val) => {
  if (!val) fetchSkills()
})

// --- Status helpers ---

function statusColor(status: string): string {
  const colors: Record<string, string> = {
    enabled: 'text-emerald-400',
    disabled: 'text-gray-400',
    error: 'text-red-400',
    loading: 'text-blue-400',
    missing_deps: 'text-amber-400',
    available: 'text-cyan-400',
  }
  return colors[status] || 'text-gray-400'
}

function statusBadge(status: string): string {
  const badges: Record<string, string> = {
    enabled: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
    disabled: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
    error: 'bg-red-500/20 text-red-300 border-red-500/30',
    missing_deps: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
    available: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  }
  return badges[status] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'
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
  <div class="min-h-screen bg-gray-900 text-white p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">Skills Management</h1>
        <p class="text-gray-400 text-sm mt-1">
          Manage AI capabilities as modular skill packages
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-sm text-gray-400">
          {{ statusCounts.enabled }}/{{ statusCounts.total }} enabled
        </span>
        <button
          @click="initializeSkills()"
          :disabled="loading"
          class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm
                 disabled:opacity-50 transition-colors"
        >
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Tab Bar + Governance Mode Selector -->
    <div class="flex flex-col gap-3 mb-6">
      <div class="flex items-center justify-between">
        <div class="flex gap-1">
          <button
            :class="[
              'px-4 py-2 rounded text-sm border transition-colors',
              activeTab === 'active'
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600',
            ]"
            @click="activeTab = 'active'"
          >
            Active Skills
          </button>
          <button
            :class="[
              'px-4 py-2 rounded text-sm border transition-colors flex items-center gap-2',
              activeTab === 'approvals'
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600',
            ]"
            @click="activeTab = 'approvals'"
          >
            Pending
            <span
              v-if="approvals.length > 0"
              class="px-1.5 py-0.5 bg-amber-500 text-white text-xs rounded-full"
            >
              {{ approvals.length }}
            </span>
          </button>
          <button
            :class="[
              'px-4 py-2 rounded text-sm border transition-colors',
              activeTab === 'repos'
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600',
            ]"
            @click="activeTab = 'repos'"
          >
            Repos
          </button>
          <button
            :class="[
              'px-4 py-2 rounded text-sm border transition-colors',
              activeTab === 'drafts'
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600',
            ]"
            @click="activeTab = 'drafts'"
          >
            Drafts
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

    <!-- Error Banner (active skills tab) -->
    <template v-if="activeTab === 'active'">
    <div
      v-if="error"
      class="mb-4 p-3 bg-red-900/30 border border-red-500/30 rounded text-red-300 text-sm"
    >
      {{ error }}
    </div>

    <!-- Stats Bar -->
    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-2xl font-bold text-cyan-400">{{ statusCounts.total }}</div>
        <div class="text-sm text-gray-400">Total Skills</div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-2xl font-bold text-emerald-400">{{ statusCounts.enabled }}</div>
        <div class="text-sm text-gray-400">Enabled</div>
      </div>
      <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div class="text-2xl font-bold text-gray-400">{{ statusCounts.disabled }}</div>
        <div class="text-sm text-gray-400">Disabled</div>
      </div>
    </div>

    <!-- Search & Category Filter -->
    <div class="flex gap-4 mb-6">
      <div class="flex-1">
        <input
          v-model="searchQuery"
          @keyup.enter="handleSearch"
          type="text"
          placeholder="Search skills by name, description, or tags..."
          class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2
                 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      </div>
      <div class="flex gap-2 flex-wrap">
        <button
          @click="selectCategory(null)"
          :class="[
            'px-3 py-1.5 rounded text-sm transition-colors border',
            !activeCategory
              ? 'bg-blue-600 border-blue-500 text-white'
              : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
          ]"
        >
          All
        </button>
        <button
          v-for="cat in categories"
          :key="cat"
          @click="selectCategory(cat)"
          :class="[
            'px-3 py-1.5 rounded text-sm transition-colors border',
            activeCategory === cat
              ? 'bg-blue-600 border-blue-500 text-white'
              : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600'
          ]"
        >
          {{ categoryIcon(cat) }} {{ cat }}
        </button>
      </div>
    </div>

    <!-- Skills Grid -->
    <div v-if="loading && !skills.length" class="text-center py-12 text-gray-400">
      Loading skills...
    </div>

    <div v-else-if="!filteredSkills.length" class="text-center py-12 text-gray-400">
      No skills found{{ searchQuery ? ` for "${searchQuery}"` : '' }}
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="skill in filteredSkills"
        :key="skill.name"
        class="bg-gray-800 rounded-lg border border-gray-700 p-4
               hover:border-gray-600 transition-colors cursor-pointer"
        @click="openDetail(skill)"
      >
        <!-- Skill Header -->
        <div class="flex items-start justify-between mb-2">
          <div>
            <h3 class="font-semibold text-white">{{ skill.name }}</h3>
            <span class="text-xs text-gray-500">v{{ skill.version }}</span>
          </div>
          <button
            @click.stop="handleToggle(skill)"
            :class="[
              'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
              skill.enabled ? 'bg-emerald-600' : 'bg-gray-600'
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
        <p class="text-sm text-gray-400 mb-3 line-clamp-2">
          {{ skill.description }}
        </p>

        <!-- Status & Meta -->
        <div class="flex items-center justify-between">
          <span
            :class="['text-xs px-2 py-0.5 rounded border', statusBadge(skill.status)]"
          >
            {{ skill.status }}
          </span>
          <div class="flex items-center gap-2 text-xs text-gray-500">
            <span>{{ categoryIcon(skill.category) }} {{ skill.category }}</span>
            <span>{{ skill.tools.length }} tools</span>
          </div>
        </div>

        <!-- Tags -->
        <div v-if="skill.tags.length" class="mt-2 flex flex-wrap gap-1">
          <span
            v-for="tag in skill.tags.slice(0, 3)"
            :key="tag"
            class="text-xs px-1.5 py-0.5 bg-gray-700 rounded text-gray-400"
          >
            {{ tag }}
          </span>
          <span
            v-if="skill.tags.length > 3"
            class="text-xs text-gray-500"
          >
            +{{ skill.tags.length - 3 }}
          </span>
        </div>
      </div>
    </div>
    </template><!-- end activeTab === 'active' -->

    <!-- Skill Detail Modal -->
    <div
      v-if="showDetail && selectedSkill"
      class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      @click.self="closeDetail"
    >
      <div
        class="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-2xl
               max-h-[80vh] overflow-y-auto"
      >
        <!-- Modal Header -->
        <div class="flex items-center justify-between p-5 border-b border-gray-700">
          <div>
            <h2 class="text-xl font-bold">{{ selectedSkill.name }}</h2>
            <p class="text-sm text-gray-400 mt-1">{{ selectedSkill.description }}</p>
          </div>
          <button
            @click="closeDetail"
            class="text-gray-400 hover:text-white text-xl"
          >
            &times;
          </button>
        </div>

        <div class="p-5 space-y-5">
          <!-- Info Grid -->
          <div class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span class="text-gray-500">Version</span>
              <div class="text-white">{{ selectedSkill.version }}</div>
            </div>
            <div>
              <span class="text-gray-500">Author</span>
              <div class="text-white">{{ selectedSkill.author }}</div>
            </div>
            <div>
              <span class="text-gray-500">Category</span>
              <div class="text-white">
                {{ categoryIcon(selectedSkill.category) }} {{ selectedSkill.category }}
              </div>
            </div>
            <div>
              <span class="text-gray-500">Status</span>
              <div :class="statusColor(selectedSkill.status)">
                {{ selectedSkill.status }}
              </div>
            </div>
          </div>

          <!-- Tools -->
          <div>
            <h3 class="text-sm font-semibold text-gray-300 mb-2">Tools</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="tool in selectedSkill.tools"
                :key="tool"
                class="px-2 py-1 bg-blue-900/30 border border-blue-500/30
                       rounded text-sm text-blue-300"
              >
                {{ tool }}
              </span>
            </div>
          </div>

          <!-- Triggers -->
          <div v-if="selectedSkill.triggers.length">
            <h3 class="text-sm font-semibold text-gray-300 mb-2">Triggers</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="trigger in selectedSkill.triggers"
                :key="trigger"
                class="px-2 py-1 bg-purple-900/30 border border-purple-500/30
                       rounded text-sm text-purple-300"
              >
                {{ trigger }}
              </span>
            </div>
          </div>

          <!-- Dependencies -->
          <div v-if="selectedSkill.dependencies.length">
            <h3 class="text-sm font-semibold text-gray-300 mb-2">Dependencies</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="dep in selectedSkill.dependencies"
                :key="dep"
                class="px-2 py-1 bg-amber-900/30 border border-amber-500/30
                       rounded text-sm text-amber-300"
              >
                {{ dep }}
              </span>
            </div>
          </div>

          <!-- Configuration -->
          <div v-if="Object.keys(selectedSkill.config_schema).length">
            <h3 class="text-sm font-semibold text-gray-300 mb-2">Configuration</h3>
            <div class="space-y-3">
              <div
                v-for="(schema, key) in selectedSkill.config_schema"
                :key="key"
                class="bg-gray-900 rounded p-3"
              >
                <label class="block text-sm text-gray-300 mb-1">
                  {{ key }}
                  <span class="text-gray-500 ml-1">{{ schema.description }}</span>
                </label>

                <!-- Select for choices -->
                <select
                  v-if="schema.choices"
                  v-model="configEditing[key]"
                  class="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5
                         text-white text-sm focus:outline-none focus:border-blue-500"
                >
                  <option v-for="c in schema.choices" :key="c" :value="c">{{ c }}</option>
                </select>

                <!-- Toggle for bool -->
                <button
                  v-else-if="schema.type === 'bool'"
                  @click="configEditing[key] = !configEditing[key]"
                  :class="[
                    'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                    configEditing[key] ? 'bg-emerald-600' : 'bg-gray-600'
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
                  class="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5
                         text-white text-sm focus:outline-none focus:border-blue-500"
                />

                <!-- Text input -->
                <input
                  v-else
                  v-model="configEditing[key]"
                  type="text"
                  class="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5
                         text-white text-sm focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <button
              @click="saveConfig"
              :disabled="savingConfig"
              class="mt-3 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm
                     disabled:opacity-50 transition-colors"
            >
              {{ savingConfig ? 'Saving...' : 'Save Configuration' }}
            </button>
          </div>

          <!-- Health -->
          <div>
            <h3 class="text-sm font-semibold text-gray-300 mb-2">Health</h3>
            <div class="bg-gray-900 rounded p-3 text-sm">
              <div class="flex items-center gap-2">
                <span
                  :class="[
                    'w-2 h-2 rounded-full',
                    selectedSkill.health.config_valid && selectedSkill.health.dependencies_met
                      ? 'bg-emerald-400' : 'bg-red-400'
                  ]"
                />
                <span class="text-gray-300">
                  Config: {{ selectedSkill.health.config_valid ? 'Valid' : 'Invalid' }}
                </span>
                <span class="text-gray-500 mx-1">|</span>
                <span class="text-gray-300">
                  Deps: {{ selectedSkill.health.dependencies_met ? 'Met' : 'Missing' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
