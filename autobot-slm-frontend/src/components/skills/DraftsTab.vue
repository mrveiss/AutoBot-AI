<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="drafts-tab space-y-3">
    <div v-if="!Array.isArray(drafts) || drafts.length === 0" class="text-center py-12 text-autobot-text-tertiary">
      {{ $t('skills.draftsTab.noDraftSkillsAutoBot') }}
    </div>
    <div
      v-for="draft in typedDrafts"
      :key="draft.id"
      class="bg-autobot-bg-card rounded-lg border border-autobot-border p-4"
    >
      <div class="flex items-start justify-between mb-2">
        <span class="font-semibold text-autobot-text-primary">{{ draft.name }}</span>
        <span class="text-xs text-autobot-warning bg-autobot-warning/10 border border-autobot-warning/30
                     px-2 py-0.5 rounded">{{ $t('skills.draftsTab.draft') }}</span>
      </div>
      <p v-if="draft.gap_reason" class="text-sm text-autobot-text-tertiary mb-3">{{ draft.gap_reason }}</p>
      <pre
        v-if="draft.skill_md"
        class="text-xs text-autobot-text-tertiary bg-autobot-bg-primary rounded p-3 mb-3
               overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto"
      >{{ String(draft.skill_md).slice(0, 300) }}{{ String(draft.skill_md).length > 300 ? '...' : '' }}</pre>
      <div class="flex gap-3">
        <button
          class="px-3 py-1.5 bg-autobot-bg-tertiary hover:bg-autobot-bg-active rounded text-sm
                 text-autobot-text-secondary transition-colors"
          @click="$emit('test', draft.id)"
        >
          {{ $t('skills.draftsTab.testRun') }}
        </button>
        <button
          class="px-3 py-1.5 bg-autobot-primary hover:bg-autobot-primary-hover rounded text-sm
                 text-autobot-text-primary transition-colors"
          @click="$emit('promote', draft.id)"
        >
          {{ $t('skills.draftsTab.promoteToBuiltin') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface DraftSkill {
  id: string
  name: string
  gap_reason?: string
  skill_md?: string
}

const props = defineProps<{ drafts: readonly Record<string, unknown>[] }>()
defineEmits<{ test: [id: string]; promote: [id: string] }>()

const typedDrafts = computed<DraftSkill[]>(() => {
  if (!Array.isArray(props.drafts)) return []
  return props.drafts.map((d) => ({
    id: String(d['id'] ?? ''),
    name: String(d['name'] ?? 'Unnamed Skill'),
    gap_reason: d['gap_reason'] != null ? String(d['gap_reason']) : undefined,
    skill_md: d['skill_md'] != null ? String(d['skill_md']) : undefined,
  }))
})
</script>
