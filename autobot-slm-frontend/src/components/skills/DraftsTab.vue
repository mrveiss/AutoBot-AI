<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="drafts-tab space-y-3">
    <div v-if="!Array.isArray(drafts) || drafts.length === 0" class="text-center py-12 text-gray-400">
      No draft skills. AutoBot will generate skills here when it detects capability gaps.
    </div>
    <div
      v-for="draft in typedDrafts"
      :key="draft.id"
      class="bg-gray-800 rounded-lg border border-gray-700 p-4"
    >
      <div class="flex items-start justify-between mb-2">
        <span class="font-semibold text-white">{{ draft.name }}</span>
        <span class="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/30
                     px-2 py-0.5 rounded">
          draft
        </span>
      </div>
      <p v-if="draft.gap_reason" class="text-sm text-gray-400 mb-3">{{ draft.gap_reason }}</p>
      <pre
        v-if="draft.skill_md"
        class="text-xs text-gray-500 bg-gray-900 rounded p-3 mb-3
               overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto"
      >{{ String(draft.skill_md).slice(0, 300) }}{{ String(draft.skill_md).length > 300 ? '...' : '' }}</pre>
      <div class="flex gap-3">
        <button
          class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm
                 text-gray-300 transition-colors"
          @click="$emit('test', draft.id)"
        >
          Test Run
        </button>
        <button
          class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm
                 text-white transition-colors"
          @click="$emit('promote', draft.id)"
        >
          Promote to Builtin
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
