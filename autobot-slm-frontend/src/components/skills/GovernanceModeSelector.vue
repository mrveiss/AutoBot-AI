<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="governance-mode-selector flex items-center gap-4">
    <label class="text-sm text-autobot-text-tertiary whitespace-nowrap">{{ $t('skills.governanceModeSelector.governanceMode') }}</label>
    <div class="flex gap-1">
      <button
        v-for="m in modes"
        :key="m.value"
        :class="[
          'px-3 py-1.5 rounded-sm text-sm border transition-colors',
          modelValue === m.value
            ? 'bg-autobot-primary border-autobot-primary text-autobot-text-on-primary'
            : 'bg-autobot-bg-card border-autobot-border text-autobot-text-secondary hover:border-autobot-border-strong',
        ]"
        @click="$emit('update:modelValue', m.value)"
      >
        {{ m.label }}
      </button>
    </div>
    <p v-if="currentMode" class="text-xs text-autobot-text-tertiary max-w-xs">
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
