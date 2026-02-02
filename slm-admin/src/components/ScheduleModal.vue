<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/**
 * Schedule Modal Component (Issue #741 - Phase 7)
 *
 * Modal form for creating and editing update schedules with cron expression
 * support and preset options.
 */

import { ref, computed, watch } from 'vue'
import type { ScheduleCreateRequest, UpdateSchedule } from '@/composables/useCodeSync'

interface Props {
  show: boolean
  schedule?: UpdateSchedule | null
  nodes?: Array<{ node_id: string; hostname: string }>
}

const props = withDefaults(defineProps<Props>(), {
  schedule: null,
  nodes: () => [],
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', schedule: ScheduleCreateRequest): void
}>()

// Form state
const name = ref('')
const cronExpression = ref('0 2 * * *')
const enabled = ref(true)
const targetType = ref<'all' | 'specific' | 'tag'>('all')
const targetNodes = ref<string[]>([])
const restartStrategy = ref('graceful')
const restartAfterSync = ref(true)

// Cron presets
const cronPresets = [
  { label: 'Daily at 2 AM', value: '0 2 * * *' },
  { label: 'Daily at midnight', value: '0 0 * * *' },
  { label: 'Every Sunday', value: '0 2 * * 0' },
  { label: 'First of month', value: '0 2 1 * *' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Every hour', value: '0 * * * *' },
]

const isEditing = computed(() => props.schedule !== null)

const modalTitle = computed(() =>
  isEditing.value ? 'Edit Schedule' : 'Create Schedule'
)

// Human-readable cron description
const cronDescription = computed(() => {
  const expr = cronExpression.value
  const preset = cronPresets.find((p) => p.value === expr)
  if (preset) return preset.label

  // Basic pattern matching for common expressions
  const parts = expr.split(' ')
  if (parts.length !== 5) return 'Custom schedule'

  const [minute, hour, day, month, weekday] = parts

  if (minute === '0' && hour !== '*' && day === '*' && month === '*' && weekday === '*') {
    const h = parseInt(hour)
    if (!isNaN(h)) {
      const period = h < 12 ? 'AM' : 'PM'
      const displayHour = h === 0 ? 12 : h > 12 ? h - 12 : h
      return `Daily at ${displayHour}:00 ${period}`
    }
  }

  return 'Custom schedule'
})

// Watch for schedule prop changes to populate form
watch(
  () => props.schedule,
  (schedule) => {
    if (schedule) {
      name.value = schedule.name
      cronExpression.value = schedule.cron_expression
      enabled.value = schedule.enabled
      targetType.value = schedule.target_type
      targetNodes.value = schedule.target_nodes || []
      restartStrategy.value = schedule.restart_strategy
      restartAfterSync.value = schedule.restart_after_sync
    } else {
      resetForm()
    }
  },
  { immediate: true }
)

function resetForm(): void {
  name.value = ''
  cronExpression.value = '0 2 * * *'
  enabled.value = true
  targetType.value = 'all'
  targetNodes.value = []
  restartStrategy.value = 'graceful'
  restartAfterSync.value = true
}

function selectPreset(preset: (typeof cronPresets)[0]): void {
  cronExpression.value = preset.value
}

function handleClose(): void {
  emit('close')
}

function handleSave(): void {
  const schedule: ScheduleCreateRequest = {
    name: name.value.trim(),
    cron_expression: cronExpression.value.trim(),
    enabled: enabled.value,
    target_type: targetType.value,
    target_nodes: targetType.value === 'specific' ? targetNodes.value : undefined,
    restart_strategy: restartStrategy.value,
    restart_after_sync: restartAfterSync.value,
  }

  emit('save', schedule)
}

function toggleNodeSelection(nodeId: string): void {
  const index = targetNodes.value.indexOf(nodeId)
  if (index > -1) {
    targetNodes.value.splice(index, 1)
  } else {
    targetNodes.value.push(nodeId)
  }
}

const isFormValid = computed(() => {
  return (
    name.value.trim().length > 0 &&
    cronExpression.value.trim().length >= 9 &&
    (targetType.value !== 'specific' || targetNodes.value.length > 0)
  )
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="show"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
        @click.self="handleClose"
      >
        <div class="bg-white rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-hidden">
          <!-- Header -->
          <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h2 class="text-lg font-semibold text-gray-900">{{ modalTitle }}</h2>
            <button
              @click="handleClose"
              class="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Body -->
          <div class="px-6 py-4 overflow-y-auto max-h-[60vh]">
            <!-- Schedule Name -->
            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Schedule Name
              </label>
              <input
                v-model="name"
                type="text"
                placeholder="e.g., Nightly Updates"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <!-- Cron Expression -->
            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Schedule (Cron Expression)
              </label>
              <input
                v-model="cronExpression"
                type="text"
                placeholder="0 2 * * *"
                class="w-full px-3 py-2 border border-gray-300 rounded-md font-mono focus:ring-primary-500 focus:border-primary-500"
              />
              <p class="mt-1 text-sm text-gray-500">{{ cronDescription }}</p>

              <!-- Presets -->
              <div class="mt-2 flex flex-wrap gap-2">
                <button
                  v-for="preset in cronPresets"
                  :key="preset.value"
                  @click="selectPreset(preset)"
                  :class="[
                    'px-2 py-1 text-xs rounded-full transition-colors',
                    cronExpression === preset.value
                      ? 'bg-primary-100 text-primary-700 border border-primary-300'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
                  ]"
                >
                  {{ preset.label }}
                </button>
              </div>
            </div>

            <!-- Target Type -->
            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Target Nodes
              </label>
              <select
                v-model="targetType"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="all">All outdated nodes</option>
                <option value="specific">Specific nodes</option>
              </select>
            </div>

            <!-- Node Selection (when specific) -->
            <div v-if="targetType === 'specific' && nodes.length > 0" class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Select Nodes
              </label>
              <div class="border border-gray-200 rounded-md max-h-40 overflow-y-auto">
                <div
                  v-for="node in nodes"
                  :key="node.node_id"
                  @click="toggleNodeSelection(node.node_id)"
                  :class="[
                    'px-3 py-2 cursor-pointer flex items-center gap-2 hover:bg-gray-50',
                    targetNodes.includes(node.node_id) ? 'bg-primary-50' : '',
                  ]"
                >
                  <input
                    type="checkbox"
                    :checked="targetNodes.includes(node.node_id)"
                    class="w-4 h-4 text-primary-600 rounded"
                    @click.stop
                    @change="toggleNodeSelection(node.node_id)"
                  />
                  <span class="text-sm text-gray-900">{{ node.hostname }}</span>
                </div>
              </div>
              <p v-if="targetNodes.length > 0" class="mt-1 text-sm text-gray-500">
                {{ targetNodes.length }} node(s) selected
              </p>
            </div>

            <!-- Restart Strategy -->
            <div class="mb-4">
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Restart Strategy
              </label>
              <select
                v-model="restartStrategy"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="graceful">Graceful (wait for tasks)</option>
                <option value="immediate">Immediate</option>
                <option value="manual">Manual (no restart)</option>
              </select>
            </div>

            <!-- Options -->
            <div class="mb-4 space-y-3">
              <label class="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  v-model="restartAfterSync"
                  class="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                />
                <span class="text-sm text-gray-700">Restart service after sync</span>
              </label>

              <label class="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  v-model="enabled"
                  class="w-4 h-4 text-primary-600 rounded focus:ring-primary-500"
                />
                <span class="text-sm text-gray-700">Schedule enabled</span>
              </label>
            </div>
          </div>

          <!-- Footer -->
          <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
            <button
              @click="handleClose"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              @click="handleSave"
              :disabled="!isFormValid"
              class="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ isEditing ? 'Save Changes' : 'Create Schedule' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .bg-white,
.modal-leave-active .bg-white {
  transition: transform 0.2s ease;
}

.modal-enter-from .bg-white,
.modal-leave-to .bg-white {
  transform: scale(0.95);
}
</style>
