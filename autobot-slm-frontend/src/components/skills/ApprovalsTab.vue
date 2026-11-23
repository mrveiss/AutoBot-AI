<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="approvals-tab space-y-3">
    <div v-if="approvals.length === 0" class="text-center py-12 text-autobot-text-tertiary">
      {{ $t('skills.approvalsTab.noPendingApprovals') }}
    </div>
    <div
      v-for="approval in approvals"
      :key="approval.id"
      class="bg-autobot-bg-card rounded-lg border border-autobot-border p-4"
    >
      <div class="flex items-start justify-between mb-2">
        <div>
          <span class="font-semibold text-autobot-text-primary">{{ approval.skill_id }}</span>
          <span class="text-xs text-autobot-text-tertiary ml-3">{{ $t('skills.approvalsTab.requestedByValue0', { value0: approval.requested_by }) }}</span>
        </div>
        <span
          :class="[
            'text-xs px-2 py-0.5 rounded-sm border',
            approval.status === 'pending'
              ? 'bg-autobot-warning/20 text-autobot-warning border-autobot-warning/30'
              : approval.status === 'approved'
                ? 'bg-autobot-success/20 text-autobot-success border-autobot-success/30'
                : 'bg-autobot-error/20 text-autobot-error border-autobot-error/30',
          ]"
        >
          {{ approval.status }}
        </span>
      </div>
      <p class="text-sm text-autobot-text-tertiary mb-3">{{ approval.reason }}</p>
      <div v-if="approval.status === 'pending'" class="flex items-center gap-3">
        <select
          v-model="trustLevels[approval.id]"
          class="bg-autobot-bg-primary border border-autobot-border rounded px-2 py-1 text-sm text-autobot-text-primary
                 focus:outline-hidden focus:border-autobot-primary"
        >
          <option value="monitored">{{ $t('skills.approvalsTab.monitored') }}</option>
          <option value="trusted">{{ $t('skills.approvalsTab.trusted') }}</option>
          <option value="sandboxed">{{ $t('skills.approvalsTab.sandboxed') }}</option>
          <option value="restricted">{{ $t('skills.approvalsTab.restricted') }}</option>
        </select>
        <button
          class="px-3 py-1.5 bg-autobot-success-hover hover:bg-autobot-success-hover rounded text-sm
                 text-autobot-text-primary transition-colors"
          @click="handleApprove(approval.id)"
        >
          {{ $t('skills.approvalsTab.approve') }}
        </button>
        <button
          class="px-3 py-1.5 bg-autobot-error-solid hover:bg-(--color-error-solid-hover) rounded text-sm
                 text-autobot-text-primary transition-colors"
          @click="handleReject(approval.id)"
        >
          {{ $t('skills.approvalsTab.reject') }}
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
