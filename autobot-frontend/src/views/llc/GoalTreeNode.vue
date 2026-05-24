<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

export interface Goal {
  id: string
  title: string
  level: 'company' | 'team' | 'agent'
  status: 'active' | 'paused' | 'done' | 'cancelled'
  owner: string | null
  linked_item_count: number
  children: Goal[]
  expanded?: boolean
  linked_items?: { id: string; title: string; status: string; identifier: string }[]
  loading_items?: boolean
}

defineProps<{ goal: Goal; depth?: number; selectedId: string | null }>()
const emit = defineEmits<{ toggle: [goal: Goal]; select: [goal: Goal] }>()

const levelBadgeClass = (level: string) => {
  if (level === 'company') return 'bg-purple-100 text-purple-700'
  if (level === 'team') return 'bg-blue-100 text-blue-700'
  return 'bg-gray-100 text-gray-600'
}

const statusBadgeClass = (status: string) => {
  if (status === 'active') return 'bg-green-100 text-green-700'
  if (status === 'done') return 'bg-gray-100 text-gray-500'
  if (status === 'paused') return 'bg-yellow-100 text-yellow-700'
  return 'bg-red-100 text-red-600'
}
</script>

<template>
  <div class="select-none">
    <div
      class="flex items-center gap-2 py-2 px-3 rounded-lg cursor-pointer transition-colors"
      :class="selectedId === goal.id
        ? 'bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-700'
        : 'hover:bg-gray-50 dark:hover:bg-gray-800'"
      :style="{ paddingLeft: `${(depth ?? 0) * 20 + 12}px` }"
      @click="emit('select', goal)"
    >
      <button
        v-if="goal.children.length > 0"
        class="w-4 h-4 flex items-center justify-center text-gray-400 hover:text-gray-600 flex-shrink-0"
        @click.stop="emit('toggle', goal)"
      >
        <svg class="w-3 h-3 transition-transform" :class="goal.expanded ? 'rotate-90' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <span v-else class="w-4 flex-shrink-0" />

      <span class="text-xs font-semibold px-1.5 py-0.5 rounded" :class="levelBadgeClass(goal.level)">
        {{ goal.level }}
      </span>
      <span class="flex-1 text-sm font-medium text-gray-900 dark:text-gray-100">{{ goal.title }}</span>
      <span v-if="goal.owner" class="text-xs text-gray-400">{{ goal.owner }}</span>
      <span class="text-xs px-1.5 py-0.5 rounded" :class="statusBadgeClass(goal.status)">
        {{ goal.status }}
      </span>
      <span v-if="goal.linked_item_count > 0" class="text-xs bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded">
        {{ goal.linked_item_count }} items
      </span>
    </div>

    <template v-if="goal.expanded && goal.children.length > 0">
      <GoalTreeNode
        v-for="child in goal.children"
        :key="child.id"
        :goal="child"
        :depth="(depth ?? 0) + 1"
        :selected-id="selectedId"
        @toggle="emit('toggle', $event)"
        @select="emit('select', $event)"
      />
    </template>
  </div>
</template>
