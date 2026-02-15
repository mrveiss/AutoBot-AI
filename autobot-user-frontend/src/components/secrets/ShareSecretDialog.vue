<script setup lang="ts">
/**
 * Share Secret Dialog Component
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Modal for sharing secrets with session participants.
 */

import { ref, computed } from 'vue'
import { useSessionCollaboration } from '@/composables/useSessionCollaboration'

const { sessionPresence, shareSecretWithSession } = useSessionCollaboration()

// Props
const props = defineProps<{
  modelValue: boolean
  secretId: string
  secretName: string
  secretType: string
}>()

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  shared: []
}>()

// Local state
const selectedParticipants = ref<Set<string>>(new Set())
const expiresIn = ref<number>(24) // hours
const sharing = ref(false)

// Available participants (excluding self)
const participants = computed(() => sessionPresence.value)

// Toggle participant selection
const toggleParticipant = (userId: string) => {
  if (selectedParticipants.value.has(userId)) {
    selectedParticipants.value.delete(userId)
  } else {
    selectedParticipants.value.add(userId)
  }
}

// Share secret
const share = async () => {
  sharing.value = true
  try {
    shareSecretWithSession(props.secretId, props.secretName, props.secretType)
    emit('shared')
    closeDialog()
  } finally {
    sharing.value = false
  }
}

// Close dialog
const closeDialog = () => {
  emit('update:modelValue', false)
  setTimeout(() => {
    selectedParticipants.value.clear()
    expiresIn.value = 24
  }, 300)
}

// Get initials
const getInitials = (username: string): string => {
  return username.substring(0, 2).toUpperCase()
}
</script>

<template>
  <Transition name="modal-backdrop">
    <div
      v-if="props.modelValue"
      class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      @click.self="closeDialog"
    >
      <Transition name="modal-content">
        <div
          v-if="props.modelValue"
          class="bg-gray-800 rounded-lg shadow-2xl w-full max-w-md border border-gray-700"
          role="dialog"
          aria-modal="true"
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-700">
            <h2 class="text-lg font-semibold text-gray-100">
              Share Secret
            </h2>
            <button
              class="text-gray-400 hover:text-gray-200 transition-colors"
              @click="closeDialog"
            >
              <i class="bi bi-x-lg" />
            </button>
          </div>

          <!-- Body -->
          <div class="px-6 py-4 space-y-4">
            <!-- Secret info -->
            <div class="px-3 py-2 bg-gray-700/50 rounded border border-gray-600">
              <div class="text-xs text-gray-400 mb-1">Secret</div>
              <div class="text-sm font-medium text-gray-200">{{ props.secretName }}</div>
              <div class="text-xs text-gray-500">{{ props.secretType }}</div>
            </div>

            <!-- Participant selection -->
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-2">
                Share with participants
              </label>
              <div class="max-h-48 overflow-y-auto space-y-2 custom-scrollbar">
                <button
                  v-for="participant in participants"
                  :key="participant.userId"
                  :class="[
                    'w-full flex items-center gap-3 p-3 rounded-lg transition-colors border',
                    selectedParticipants.has(participant.userId)
                      ? 'bg-blue-500/20 border-blue-500/30'
                      : 'bg-gray-700/50 border-gray-600 hover:bg-gray-700'
                  ]"
                  @click="toggleParticipant(participant.userId)"
                >
                  <div class="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center text-xs font-medium text-gray-200">
                    {{ getInitials(participant.username) }}
                  </div>
                  <div class="flex-1 text-left">
                    <div class="text-sm font-medium text-gray-200">
                      {{ participant.username }}
                    </div>
                    <div class="text-xs text-gray-500">
                      {{ participant.status }}
                    </div>
                  </div>
                  <i
                    v-if="selectedParticipants.has(participant.userId)"
                    class="bi bi-check-circle-fill text-blue-400"
                  />
                </button>

                <!-- Empty state -->
                <div
                  v-if="participants.length === 0"
                  class="text-center py-6 text-gray-500"
                >
                  <i class="bi bi-people text-2xl mb-2" />
                  <div class="text-sm">No participants in session</div>
                </div>
              </div>
            </div>

            <!-- Expiry -->
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-2">
                Access expires in
              </label>
              <select
                v-model="expiresIn"
                class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option :value="1">1 hour</option>
                <option :value="6">6 hours</option>
                <option :value="24">24 hours</option>
                <option :value="168">1 week</option>
                <option :value="0">Never</option>
              </select>
            </div>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-700">
            <button
              class="px-4 py-2 text-sm rounded bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors"
              @click="closeDialog"
            >
              Cancel
            </button>
            <button
              class="px-4 py-2 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white transition-colors disabled:opacity-50 flex items-center gap-2"
              :disabled="selectedParticipants.size === 0 || sharing"
              @click="share"
            >
              <i v-if="sharing" class="bi bi-arrow-repeat animate-spin" />
              <span>{{ sharing ? 'Sharing...' : 'Share Secret' }}</span>
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </Transition>
</template>

<style scoped>
.modal-backdrop-enter-active,
.modal-backdrop-leave-active {
  transition: opacity 0.3s ease;
}

.modal-backdrop-enter-from,
.modal-backdrop-leave-to {
  opacity: 0;
}

.modal-content-enter-active {
  transition: all 0.3s ease-out;
}

.modal-content-leave-active {
  transition: all 0.2s ease-in;
}

.modal-content-enter-from {
  opacity: 0;
  transform: scale(0.95) translateY(-10px);
}

.modal-content-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(10px);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(156, 163, 175, 0.3);
  border-radius: 2px;
}
</style>
