<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { useLlcCompanyContext } from '@/composables/llc/useLlcCompanyContext'
import { markExpanded, buildTreeFromParent } from '@/composables/llc/useLlcTree'
import GoalTreeNode from './GoalTreeNode.vue'
import type { Goal } from './GoalTreeNode.vue'

const logger = createLogger('GoalTree')
const api = useApiClient()
const { resolveCompanyId } = useLlcCompanyContext()

const goals = ref<Goal[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const selectedGoal = ref<Goal | null>(null)

// Flat goal row returned by GET /api/llc/goals?company_id=.
interface FlatGoal {
  id: string
  parent_goal_id: string | null
  title: string
  status: string
}

function toGoalNode(g: FlatGoal): Goal {
  return {
    id: g.id,
    title: g.title,
    status: g.status as Goal['status'],
    linked_item_count: 0,
    children: [],
    expanded: false,
  }
}

async function fetchGoals() {
  isLoading.value = true
  error.value = null
  try {
    const cid = await resolveCompanyId()
    if (!cid) {
      goals.value = []
      return
    }
    // No /goals/tree route — fetch flat goals and assemble the tree client-side
    // from parent_goal_id (#9861).
    const flat = await api.get<FlatGoal[]>(`/api/llc/goals?company_id=${cid}`)
    goals.value = buildTreeFromParent(flat ?? [], 'id', 'parent_goal_id', toGoalNode)
    markExpanded(goals.value, true)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch goal tree:', msg)
    error.value = msg
  } finally {
    isLoading.value = false
  }
}

function toggle(goal: Goal) {
  goal.expanded = !goal.expanded
}

async function selectGoal(goal: Goal) {
  if (selectedGoal.value?.id === goal.id) {
    selectedGoal.value = null
    return
  }
  selectedGoal.value = goal
  if (!goal.linked_items && goal.linked_item_count > 0) {
    goal.loading_items = true
    try {
      // GH#9851: backend route is /tasks and returns an array directly.
      const resp = await api.get<NonNullable<Goal['linked_items']>>(`/api/llc/goals/${goal.id}/tasks`)
      goal.linked_items = resp ?? []
    } catch (err: unknown) {
      logger.error('Failed to fetch goal items', err)
      goal.linked_items = []
    } finally {
      goal.loading_items = false
    }
  }
}

const itemStatusColor = (status: string) => {
  if (status === 'done') return 'text-green-600'
  if (status === 'in_progress') return 'text-blue-600'
  if (status === 'blocked') return 'text-red-500'
  return 'text-gray-500'
}

onMounted(fetchGoals)
</script>

<template>
  <div class="p-4 max-w-5xl mx-auto">
    <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Goal Tree</h1>

    <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm mb-4">
      {{ error }}
      <button class="ml-4 underline" @click="fetchGoals">Retry</button>
    </div>

    <div v-if="isLoading" class="text-center py-12 text-gray-500">Loading…</div>

    <div v-else-if="goals.length === 0 && !error" class="text-center py-12 text-gray-400">No goals found.</div>

    <div v-else class="space-y-1">
      <GoalTreeNode
        v-for="goal in goals"
        :key="goal.id"
        :goal="goal"
        :depth="0"
        :selected-id="selectedGoal?.id ?? null"
        @toggle="toggle"
        @select="selectGoal"
      />
    </div>

    <!-- Linked Work Items Panel -->
    <transition name="fade">
      <div
        v-if="selectedGoal"
        class="mt-6 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
      >
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">
            Linked items for: <span class="text-indigo-600">{{ selectedGoal.title }}</span>
          </h2>
          <button class="text-gray-400 hover:text-gray-600 text-sm" @click="selectedGoal = null">✕</button>
        </div>

        <div v-if="selectedGoal.loading_items" class="text-sm text-gray-400">Loading items…</div>
        <div v-else-if="!selectedGoal.linked_items || selectedGoal.linked_items.length === 0" class="text-sm text-gray-400">
          No linked work items.
        </div>
        <ul v-else class="space-y-1">
          <li
            v-for="item in selectedGoal.linked_items"
            :key="item.id"
            class="flex items-center justify-between text-sm py-1 border-b border-gray-100 dark:border-gray-700 last:border-0"
          >
            <span class="text-gray-800 dark:text-gray-200">
              <span class="text-xs text-gray-400 mr-1">{{ item.identifier }}</span>
              {{ item.title }}
            </span>
            <span class="text-xs font-medium" :class="itemStatusColor(item.status)">{{ item.status }}</span>
          </li>
        </ul>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
