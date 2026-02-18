<template>
  <div class="host-selector">
    <div class="selector-label">
      <i class="fas fa-server text-autobot-text-secondary mr-2"></i>
      <span class="text-sm font-medium text-autobot-text-primary">Host:</span>
    </div>
    <select
      v-model="selectedHostId"
      @change="handleHostChange"
      class="host-select"
      :disabled="disabled || loading"
    >
      <!-- Infrastructure hosts from API (Issue #715) -->
      <optgroup v-if="infrastructureHosts.length > 0" label="Infrastructure Hosts">
        <option
          v-for="host in infrastructureHosts"
          :key="host.id"
          :value="host.id"
        >
          {{ host.name }} ({{ host.ip }})
        </option>
      </optgroup>
      <!-- Default VM hosts -->
      <optgroup label="AutoBot VMs">
        <option
          v-for="host in defaultHosts"
          :key="host.id"
          :value="host.id"
        >
          {{ host.name }} ({{ host.ip }})
        </option>
      </optgroup>
    </select>
    <div v-if="showDescription && selectedHostConfig" class="host-description">
      <i class="fas fa-info-circle text-blue-500 mr-1"></i>
      <span class="text-xs text-autobot-text-secondary">{{ selectedHostConfig.description }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useTerminalStore, AVAILABLE_HOSTS, type HostConfig } from '@/composables/useTerminalStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('HostSelector')

/**
 * Infrastructure host from API (Issue #715).
 */
interface InfrastructureHost {
  id: string
  name: string
  host: string
  ssh_port?: number
  vnc_port?: number
  capabilities?: string[]
  description?: string
  os?: string
}

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
const infrastructureHosts = ref<HostConfig[]>([])
const loading = ref(false)

// Computed
const defaultHosts = computed(() => props.hosts)

const allHosts = computed(() => {
  return [...infrastructureHosts.value, ...defaultHosts.value]
})

const selectedHostConfig = computed(() => {
  return allHosts.value.find(host => host.id === selectedHostId.value)
})

// Load infrastructure hosts from API (Issue #715)
const loadInfrastructureHosts = async () => {
  loading.value = true
  try {
    // Use relative URL to go through Vite proxy
    const response = await fetch('/api/infrastructure/hosts')
    if (!response.ok) {
      throw new Error(`Failed to load hosts: ${response.statusText}`)
    }
    const data = await response.json()

    // Convert infrastructure hosts to HostConfig format
    infrastructureHosts.value = (data.hosts || []).map((h: InfrastructureHost) => ({
      id: h.id,
      name: h.name,
      ip: h.host,
      port: h.ssh_port || 22,
      description: h.description || `${h.os || 'Host'} - ${h.capabilities?.join(', ') || 'SSH'}`
    }))

    logger.info(`Loaded ${infrastructureHosts.value.length} infrastructure hosts`)

    // If no host is selected yet and we have infrastructure hosts, select the first one
    if (!selectedHostId.value && infrastructureHosts.value.length > 0) {
      selectedHostId.value = infrastructureHosts.value[0].id
      handleHostChange()
    }
  } catch (error) {
    logger.error('Failed to load infrastructure hosts:', error)
  } finally {
    loading.value = false
  }
}

// Methods
const handleHostChange = () => {
  const host = selectedHostConfig.value
  if (host) {
    emit('update:modelValue', host.id)
    emit('host-change', host)

    // Update store
    terminalStore.setSelectedHost(host)

    logger.info('Host changed:', {
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

// Load infrastructure hosts on mount
onMounted(() => {
  loadInfrastructureHosts()
})
</script>

<style scoped>
.host-selector {
  @apply flex flex-col gap-2;
}

.selector-label {
  @apply flex items-center text-sm font-medium text-autobot-text-primary;
}

.host-select {
  @apply w-full px-3 py-2 border border-autobot-border rounded-lg shadow-sm;
  @apply focus:ring-2 focus:ring-blue-500 focus:border-blue-500;
  @apply bg-autobot-bg-card text-autobot-text-primary;
  @apply transition-colors duration-200;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.875rem;
}

.host-select:disabled {
  @apply bg-autobot-bg-tertiary text-autobot-text-muted cursor-not-allowed;
}

.host-select:hover:not(:disabled) {
  @apply border-autobot-border;
}

.host-description {
  @apply flex items-center text-xs text-autobot-text-secondary px-2;
}


</style>
