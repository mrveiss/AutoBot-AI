<template>
  <div class="host-selector">
    <div class="selector-label">
      <Icon name="server" class="text-autobot-text-secondary mr-2" />
      <span class="text-sm font-medium text-autobot-text-primary">{{ $t('terminal.host') }}</span>
    </div>
    <select
      v-model="selectedHostId"
      @change="handleHostChange"
      class="host-select"
      :disabled="disabled || loading"
    >
      <!-- Infrastructure hosts from API (Issue #715) -->
      <optgroup v-if="terminalHosts.length > 0" :label="$t('terminal.infrastructureHosts')">
        <option
          v-for="host in terminalHosts"
          :key="host.id"
          :value="host.id"
        >
          {{ host.name }} ({{ host.ip }})
        </option>
      </optgroup>
      <!-- Default VM hosts -->
      <optgroup :label="$t('terminal.autobotVMs')">
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
      <Icon name="info-circle" class="text-blue-500 mr-1" />
      <span class="text-xs text-autobot-text-secondary">{{ selectedHostConfig.description }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch, onMounted } from 'vue'
import { useTerminalStore, AVAILABLE_HOSTS, type HostConfig } from '@/composables/useTerminalStore'
import { createLogger } from '@/utils/debugUtils'
import { useHostSelection } from '@/composables/useHostSelection'

const logger = createLogger('HostSelector')

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

// Composable
const { terminalHosts, terminalHostsLoading, loadTerminalHosts } = useHostSelection()

// Local state
const selectedHostId = ref(props.modelValue)
const loading = terminalHostsLoading

// Computed
const defaultHosts = computed(() => props.hosts)

const allHosts = computed(() => {
  return [...terminalHosts.value, ...defaultHosts.value]
})

const selectedHostConfig = computed(() => {
  return allHosts.value.find(host => host.id === selectedHostId.value)
})

// Load infrastructure hosts from API via composable (Issue #715, #6089)
const loadInfrastructureHosts = async () => {
  await loadTerminalHosts()

  logger.info(`Loaded ${terminalHosts.value.length} infrastructure hosts`)

  // If no host is selected yet and we have infrastructure hosts, select the first one
  if (!selectedHostId.value && terminalHosts.value.length > 0) {
    selectedHostId.value = terminalHosts.value[0].id
    handleHostChange()
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
@reference "../../assets/tailwind.css";
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
  font-size: var(--text-sm);
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
