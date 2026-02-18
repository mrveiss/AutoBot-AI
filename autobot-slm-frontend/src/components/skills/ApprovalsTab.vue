<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="approvals-tab space-y-3">
    <div v-if="approvals.length === 0" class="text-center py-12 text-gray-400">
      No pending approvals
    </div>
    <div
      v-for="approval in approvals"
      :key="approval.id"
      class="bg-gray-800 rounded-lg border border-gray-700 p-4"
    >
      <div class="flex items-start justify-between mb-2">
        <div>
          <span class="font-semibold text-white">{{ approval.skill_id }}</span>
          <span class="text-xs text-gray-500 ml-3">Requested by: {{ approval.requested_by }}</span>
        </div>
        <span
          :class="[
            'text-xs px-2 py-0.5 rounded border',
            approval.status === 'pending'
              ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
              : approval.status === 'approved'
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                : 'bg-red-500/20 text-red-300 border-red-500/30',
          ]"
        >
          {{ approval.status }}
        </span>
      </div>
      <p class="text-sm text-gray-400 mb-3">{{ approval.reason }}</p>
      <div v-if="approval.status === 'pending'" class="flex items-center gap-3">
        <select
          v-model="trustLevels[approval.id]"
          class="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white
                 focus:outline-none focus:border-blue-500"
        >
          <option value="monitored">Monitored</option>
          <option value="trusted">Trusted</option>
          <option value="sandboxed">Sandboxed</option>
          <option value="restricted">Restricted</option>
        </select>
        <button
          class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-sm
                 text-white transition-colors"
          @click="handleApprove(approval.id)"
        >
          Approve
        </button>
        <button
          class="px-3 py-1.5 bg-red-700 hover:bg-red-800 rounded text-sm
                 text-white transition-colors"
          @click="handleReject(approval.id)"
        >
          Reject
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { SkillApproval } from '@/composables/useSkills'

defineProps<{ approvals: readonly SkillApproval[] }>()
const emit = defineEmits<{
  approve: [id: string, trustLevel: string]
  reject: [id: string]
}>()

const trustLevels = ref<Record<string, string>>({})

function handleApprove(id: string): void {
  emit('approve', id, trustLevels.value[id] || 'monitored')
}

function handleReject(id: string): void {
  emit('reject', id)
}
</script>
