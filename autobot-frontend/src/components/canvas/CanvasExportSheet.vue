<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Export canvas"
      aria-labelledby="export-sheet-title"
    >
      <div class="absolute inset-0 bg-bg-overlay" @click="$emit('close')" />
      <div data-testid="canvas-export-modal" class="relative bg-bg-card border border-border-default rounded-t-xl sm:rounded-xl w-full max-w-md p-6 shadow-xl z-10">
        <h2 id="export-sheet-title" class="text-lg font-semibold mb-4">Export Canvas</h2>

        <!-- Format selection -->
        <fieldset class="mb-4">
          <legend class="text-sm font-medium text-text-secondary mb-2">Format</legend>
          <div class="grid grid-cols-2 gap-2">
            <label
              v-for="fmt in formats"
              :key="fmt.id"
              :class="[
                'flex items-center gap-2 p-3 rounded border cursor-pointer transition-colors',
                selectedFormat === fmt.id
                  ? 'border-autobot-primary bg-autobot-primary/5'
                  : 'border-border-default hover:bg-bg-hover',
              ]"
            >
              <input
                type="radio"
                :value="fmt.id"
                v-model="selectedFormat"
                class="sr-only"
              />
              <span class="text-xl" aria-hidden="true">{{ fmt.icon }}</span>
              <span class="text-sm font-medium">{{ fmt.label }}</span>
            </label>
          </div>
        </fieldset>

        <!-- Cell type toggles -->
        <fieldset class="mb-6">
          <legend class="text-sm font-medium text-text-secondary mb-2">Include cell types</legend>
          <div class="space-y-2">
            <label
              v-for="toggle in cellTypeToggles"
              :key="toggle.id"
              class="flex items-center gap-3 cursor-pointer"
            >
              <input
                type="checkbox"
                :value="toggle.id"
                v-model="includedTypes"
                class="rounded border-border-default"
              />
              <span class="text-sm">{{ toggle.label }}</span>
            </label>
          </div>
        </fieldset>

        <div class="flex gap-3">
          <button
            class="flex-1 px-4 py-2 bg-autobot-primary text-white rounded hover:opacity-90 font-medium"
            aria-label="Export canvas"
            @click="doExport"
          >
            Export
          </button>
          <button
            class="px-4 py-2 border border-border-default rounded hover:bg-bg-hover"
            aria-label="Cancel export"
            @click="$emit('close')"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ open: boolean }>()
const emit = defineEmits<{
  close: []
  export: [format: string, includedTypes: string[]]
}>()

const formats = [
  { id: 'markdown', label: 'Markdown', icon: '📝' },
  { id: 'pdf', label: 'PDF', icon: '📄' },
  { id: 'html', label: 'HTML', icon: '🌐' },
  { id: 'json', label: 'JSON', icon: '{ }' },
]

const cellTypeToggles = [
  { id: 'markdown', label: 'Markdown cells' },
  { id: 'chart', label: 'Chart cells' },
  { id: 'code', label: 'Code cells' },
]

const selectedFormat = ref('markdown')
const includedTypes = ref(['markdown', 'chart', 'code'])

function doExport() {
  emit('export', selectedFormat.value, [...includedTypes.value])
  emit('close')
}
</script>
