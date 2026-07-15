<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  AdapterTypeSelect (GH#10219) — a <select> of registered LLC agent adapter
  types, populated from GET /api/llc/adapters. Unavailable adapters (CLI absent
  or not implemented) are disabled with an explanatory suffix.
-->
<template>
  <select class="adapter-select" :value="modelValue" @change="onChange">
    <option v-for="a in adapters" :key="a.type" :value="a.type" :disabled="!a.available">
      {{ label(a) }}
    </option>
  </select>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

interface AdapterInfo {
  type: string
  available: boolean
  requires_cli: string | null
  implemented: boolean
}

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const logger = createLogger('AdapterTypeSelect')
const api = useApiClient()
const adapters = ref<AdapterInfo[]>([])

function label(a: AdapterInfo): string {
  if (!a.implemented) return `${a.type} (not implemented)`
  if (!a.available) return `${a.type} (CLI not installed)`
  return a.type
}

function onChange(e: Event): void {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
}

async function loadAdapters(): Promise<void> {
  try {
    adapters.value = await api.get<AdapterInfo[]>('/api/llc/adapters')
    // Default to the first available adapter when nothing is selected yet.
    if (!props.modelValue) {
      const first = adapters.value.find((a) => a.available)
      if (first) emit('update:modelValue', first.type)
    }
  } catch (err) {
    logger.error('Failed to load adapter types', err)
    adapters.value = []
  }
}

onMounted(loadAdapters)
</script>

<style scoped>
.adapter-select {
  width: 100%;
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--border-default, #d1d5db);
  background: var(--bg-surface, #fff);
  color: var(--text-primary, #111827);
}
</style>
