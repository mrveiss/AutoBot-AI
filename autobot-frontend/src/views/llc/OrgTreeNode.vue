<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { agentStatusColor } from '@/composables/llc/llcStatus'
import type { AgentDisplayStatus } from '@/composables/llc/llcStatus'

export interface OrgNode {
  id: string
  name: string
  title: string
  status: AgentDisplayStatus
  adapter_type: string
  is_human: boolean
  last_heartbeat: string | null
  budget_spent: number
  budget_total: number
  assigned_item_count: number
  children: OrgNode[]
  parent_id: string | null
  expanded?: boolean
}

defineProps<{ node: OrgNode; depth?: number }>()
const emit = defineEmits<{ select: [node: OrgNode] }>()
</script>

<template>
  <div class="flex flex-col items-center gap-1">
    <div
      class="relative cursor-pointer rounded-xl border-2 p-3 min-w-[130px] text-center transition-shadow hover:shadow-md"
      :class="node.is_human ? 'border-blue-300 bg-blue-50 dark:bg-blue-900/20' : 'border-indigo-200 bg-autobot-bg-card'"
      @click="emit('select', node)"
    >
      <div class="flex justify-center mb-1">
        <div
          class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold"
          :class="node.is_human ? 'bg-blue-100 text-blue-700' : 'bg-indigo-100 text-indigo-700'"
        >
          {{ node.name.charAt(0).toUpperCase() }}
        </div>
      </div>
      <p class="text-xs font-semibold text-autobot-text-primary truncate">{{ node.name }}</p>
      <p class="text-xs text-autobot-text-muted truncate">{{ node.title }}</p>
      <div class="flex justify-center items-center gap-1 mt-1">
        <span class="w-2 h-2 rounded-full" :class="agentStatusColor(node.status)" />
        <span class="text-xs text-autobot-text-muted">{{ node.adapter_type }}</span>
      </div>
    </div>

    <template v-if="node.children.length > 0">
      <div class="w-px h-4 bg-autobot-border" />
      <div class="flex gap-4">
        <div v-for="child in node.children" :key="child.id" class="flex flex-col items-center">
          <div class="w-px h-4 bg-autobot-border" />
          <OrgTreeNode :node="child" :depth="(depth ?? 0) + 1" @select="emit('select', $event)" />
        </div>
      </div>
    </template>
  </div>
</template>
