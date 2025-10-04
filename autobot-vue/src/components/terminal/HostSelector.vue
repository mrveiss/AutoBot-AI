<template>
  <div class="host-selector">
    <div class="selector-label">
      <i class="fas fa-server text-gray-600 mr-2"></i>
      <span class="text-sm font-medium text-gray-700">Host:</span>
    </div>
    <select
      v-model="selectedHostId"
      @change="handleHostChange"
      class="host-select"
      :disabled="disabled"
    >
      <option
        v-for="host in hosts"
        :key="host.id"
        :value="host.id"
      >
        {{ host.name }} ({{ host.ip }})
      </option>
    </select>
    <div v-if="showDescription && selectedHostConfig" class="host-description">
      <i class="fas fa-info-circle text-blue-500 mr-1"></i>
      <span class="text-xs text-gray-600">{{ selectedHostConfig.description }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useTerminalStore, AVAILABLE_HOSTS, type HostConfig } from '@/composables/useTerminalStore'

// Props
interface Props {
  modelValue?: string // Host ID
  hosts?: HostConfig[]
  disabled?: boolean
  showDescription?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: 'main',
  hosts: () => AVAILABLE_HOSTS,
  disabled: false,
  showDescription: true
})

// Emits
const emit = defineEmits<{
  'update:modelValue': [hostId: string]
  'host-change': [host: HostConfig]
}>()

// Store
const terminalStore = useTerminalStore()

// Local state
const selectedHostId = ref(props.modelValue)

// Computed
const selectedHostConfig = computed(() => {
  return props.hosts.find(host => host.id === selectedHostId.value)
})

// Methods
const handleHostChange = () => {
  const host = selectedHostConfig.value
  if (host) {
    emit('update:modelValue', host.id)
    emit('host-change', host)

    // Update store
    terminalStore.setSelectedHost(host)

    console.log('[HostSelector] Host changed:', {
      hostId: host.id,
      hostName: host.name,
      hostIp: host.ip
    })
  }
}

// Watch for external modelValue changes
watch(() => props.modelValue, (newValue) => {
  if (newValue !== selectedHostId.value) {
    selectedHostId.value = newValue
  }
})

// Watch for store selectedHost changes
watch(() => terminalStore.selectedHost, (newHost) => {
  if (newHost && newHost.id !== selectedHostId.value) {
    selectedHostId.value = newHost.id
  }
}, { immediate: true })
</script>

<style scoped>
.host-selector {
  @apply flex flex-col gap-2;
}

.selector-label {
  @apply flex items-center text-sm font-medium text-gray-700;
}

.host-select {
  @apply w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm;
  @apply focus:ring-2 focus:ring-blue-500 focus:border-blue-500;
  @apply bg-white text-gray-900;
  @apply transition-colors duration-200;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.875rem;
}

.host-select:disabled {
  @apply bg-gray-100 text-gray-500 cursor-not-allowed;
}

.host-select:hover:not(:disabled) {
  @apply border-gray-400;
}

.host-description {
  @apply flex items-center text-xs text-gray-600 px-2;
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
  .selector-label {
    @apply text-gray-300;
  }

  .host-select {
    @apply bg-gray-800 text-gray-200 border-gray-600;
  }

  .host-select:hover:not(:disabled) {
    @apply border-gray-500;
  }

  .host-select:disabled {
    @apply bg-gray-900 text-gray-600;
  }

  .host-description {
    @apply text-gray-400;
  }
}
</style>
