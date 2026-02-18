<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="governance-mode-selector flex items-center gap-4">
    <label class="text-sm text-gray-400 whitespace-nowrap">Governance Mode</label>
    <div class="flex gap-1">
      <button
        v-for="m in modes"
        :key="m.value"
        :class="[
          'px-3 py-1.5 rounded text-sm border transition-colors',
          modelValue === m.value
            ? 'bg-blue-600 border-blue-500 text-white'
            : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-600',
        ]"
        @click="$emit('update:modelValue', m.value)"
      >
        {{ m.label }}
      </button>
    </div>
    <p v-if="currentMode" class="text-xs text-gray-500 max-w-xs">
      {{ currentMode.description }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type GovernanceMode = 'full_auto' | 'semi_auto' | 'locked'

const props = defineProps<{ modelValue: GovernanceMode }>()
defineEmits<{ 'update:modelValue': [value: GovernanceMode] }>()

const modes = [
  {
    value: 'full_auto' as GovernanceMode,
    label: 'Full Auto',
    description: 'AutoBot installs and activates skills without approval.',
  },
  {
    value: 'semi_auto' as GovernanceMode,
    label: 'Semi Auto',
    description: 'AutoBot proposes skills — you approve before activation.',
  },
  {
    value: 'locked' as GovernanceMode,
    label: 'Locked',
    description: 'Only admin-approved skills run. No self-generation.',
  },
]

const currentMode = computed(() => modes.find((m) => m.value === props.modelValue))
</script>
