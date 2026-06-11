<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { companyStatusColor } from '@/composables/llc/llcStatus'

export interface CompanyNode {
  id: string
  name: string
  status: 'active' | 'paused' | 'inactive'
  budget_spent: number
  budget_total: number
  agent_count: number
  children: CompanyNode[]
  expanded?: boolean
}

defineProps<{ node: CompanyNode; depth?: number }>()
const emit = defineEmits<{ toggle: [node: CompanyNode]; navigate: [node: CompanyNode] }>()

const budgetPercent = (node: CompanyNode) =>
  node.budget_total > 0 ? Math.min(100, Math.round((node.budget_spent / node.budget_total) * 100)) : 0

const budgetBarColor = (node: CompanyNode) => {
  const pct = budgetPercent(node)
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-yellow-400'
  return 'bg-green-500'
}
</script>

<template>
  <div>
    <div
      class="group flex items-center gap-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-600 transition-colors"
      :style="{ marginLeft: `${(depth ?? 0) * 24}px` }"
      @click="emit('navigate', node)"
    >
      <button
        v-if="node.children.length > 0"
        class="w-5 h-5 flex items-center justify-center text-gray-400 hover:text-gray-600 flex-shrink-0"
        @click.stop="emit('toggle', node)"
      >
        <svg class="w-4 h-4 transition-transform" :class="node.expanded ? 'rotate-90' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <span v-else class="w-5 flex-shrink-0" />

      <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :class="companyStatusColor(node.status)" />
      <span class="flex-1 font-semibold text-sm text-gray-900 dark:text-gray-100">{{ node.name }}</span>

      <div class="flex items-center gap-2 w-32">
        <div class="flex-1 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
          <div class="h-1.5 rounded-full" :class="budgetBarColor(node)" :style="{ width: `${budgetPercent(node)}%` }" />
        </div>
        <span class="text-xs text-gray-400 w-8 text-right">{{ budgetPercent(node) }}%</span>
      </div>

      <span class="text-xs text-gray-500">{{ node.agent_count }} agents</span>
      <svg class="w-4 h-4 text-gray-300 group-hover:text-indigo-400 transition-colors flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
    </div>

    <template v-if="node.expanded && node.children.length > 0">
      <div class="mt-2 space-y-2">
        <CompanyTreeNode
          v-for="child in node.children"
          :key="child.id"
          :node="child"
          :depth="(depth ?? 0) + 1"
          @toggle="emit('toggle', $event)"
          @navigate="emit('navigate', $event)"
        />
      </div>
    </template>
  </div>
</template>
