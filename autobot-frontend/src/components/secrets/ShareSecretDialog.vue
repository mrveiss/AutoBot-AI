<script setup lang="ts">
/**
 * Share Secret Dialog Component
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Modal for sharing secrets with session participants.
 */

import { ref, computed, toRef, watch } from 'vue'
import { useSessionCollaboration } from '@/composables/useSessionCollaboration'
import { useBatchSelection } from '@/composables/useBatchSelection'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { useInitialFocus } from '@/composables/useInitialFocus'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'

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
const expiresIn = ref<number>(24) // hours
const sharing = ref(false)

const dialogRef = ref<HTMLElement | null>(null)
const { onKeydown: onFocusTrapKeydown } = useFocusTrap(dialogRef)
useFocusRestore(toRef(props, 'modelValue'))
useBodyScrollLock(toRef(props, 'modelValue'))
const { focusFirst } = useInitialFocus(dialogRef)
watch(() => props.modelValue, (open) => { if (open) focusFirst() }, { immediate: true })

// Available participants (excluding self)
const participants = computed(() => sessionPresence.value)

// Selection: keyed on userId. The previous bespoke `ref(new Set())` mutated
// the Set in place via .add()/.delete(), which Vue does not track — clicks
// failed to update the highlight class. The composable replaces the Set on
// every mutation, fixing reactivity.
const selection = useBatchSelection<typeof participants.value[number], string>(
  participants,
  (p) => p.userId
)

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
    selection.clear()
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
          ref="dialogRef"
          class="bg-autobot-bg-card rounded-lg shadow-2xl w-full max-w-md border border-autobot-border"
          role="dialog"
          aria-modal="true"
          tabindex="-1"
          @keydown="onFocusTrapKeydown"
          @keydown.escape="closeDialog"
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-autobot-border">
            <h2 class="text-lg font-semibold text-autobot-text-primary">
              {{ $t('secrets.share.title') }}
            </h2>
            <button
              class="text-autobot-text-muted hover:text-autobot-text-primary transition-colors"
              @click="closeDialog"
            >
              <i class="bi bi-x-lg" />
            </button>
          </div>

          <!-- Body -->
          <div class="px-6 py-4 space-y-4">
            <!-- Secret info -->
            <div class="px-3 py-2 bg-autobot-bg-secondary rounded border border-autobot-border">
              <div class="text-xs text-autobot-text-muted mb-1">{{ $t('secrets.share.secretLabel') }}</div>
              <div class="text-sm font-medium text-autobot-text-primary">{{ props.secretName }}</div>
              <div class="text-xs text-autobot-text-muted">{{ props.secretType }}</div>
            </div>

            <!-- Participant selection -->
            <div>
              <label class="block text-sm font-medium text-autobot-text-secondary mb-2">
                {{ $t('secrets.share.shareWithParticipants') }}
              </label>
              <div class="max-h-48 overflow-y-auto space-y-2 custom-scrollbar">
                <button
                  v-for="participant in participants"
                  :key="participant.userId"
                  :class="[
                    'w-full flex items-center gap-3 p-3 rounded-lg transition-colors border',
                    selection.isSelected(participant)
                      ? 'bg-blue-500/20 border-blue-500/30'
                      : 'bg-autobot-bg-secondary border-autobot-border hover:bg-autobot-bg-tertiary'
                  ]"
                  @click="selection.toggle(participant)"
                >
                  <div class="w-8 h-8 rounded-full bg-autobot-bg-tertiary flex items-center justify-center text-xs font-medium text-autobot-text-primary">
                    {{ getInitials(participant.username) }}
                  </div>
                  <div class="flex-1 text-left">
                    <div class="text-sm font-medium text-autobot-text-primary">
                      {{ participant.username }}
                    </div>
                    <div class="text-xs text-autobot-text-muted">
                      {{ participant.status }}
                    </div>
                  </div>
                  <i
                    v-if="selection.isSelected(participant)"
                    class="bi bi-check-circle-fill text-blue-400"
                  />
                </button>

                <!-- Empty state -->
                <div
                  v-if="participants.length === 0"
                  class="text-center py-6 text-autobot-text-muted"
                >
                  <i class="bi bi-people text-2xl mb-2" />
                  <div class="text-sm">{{ $t('secrets.share.noParticipants') }}</div>
                </div>
              </div>
            </div>

            <!-- Expiry -->
            <div>
              <label class="block text-sm font-medium text-autobot-text-secondary mb-2">
                {{ $t('secrets.share.expiresIn') }}
              </label>
              <select
                v-model="expiresIn"
                class="w-full px-3 py-2 bg-autobot-bg-secondary border border-autobot-border rounded-lg text-autobot-text-primary focus:outline-none focus:ring-2 focus:ring-electric-500"
              >
                <option :value="1">{{ $t('secrets.share.expire1Hour') }}</option>
                <option :value="6">{{ $t('secrets.share.expire6Hours') }}</option>
                <option :value="24">{{ $t('secrets.share.expire24Hours') }}</option>
                <option :value="168">{{ $t('secrets.share.expire1Week') }}</option>
                <option :value="0">{{ $t('secrets.share.expireNever') }}</option>
              </select>
            </div>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-end gap-3 px-6 py-4 border-t border-autobot-border">
            <button
              class="px-4 py-2 text-sm rounded bg-autobot-bg-secondary hover:bg-autobot-bg-tertiary text-autobot-text-primary transition-colors"
              @click="closeDialog"
            >
              {{ $t('secrets.share.cancel') }}
            </button>
            <button
              class="px-4 py-2 text-sm rounded bg-blue-500 hover:bg-blue-600 text-white transition-colors disabled:opacity-50 flex items-center gap-2"
              :disabled="selection.selectedCount.value === 0 || sharing"
              @click="share"
            >
              <i v-if="sharing" class="bi bi-arrow-repeat animate-spin" />
              <span>{{ sharing ? $t('secrets.share.sharing') : $t('secrets.share.shareSecret') }}</span>
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
  transition: opacity var(--duration-300) var(--ease-out);
}

.modal-backdrop-enter-from,
.modal-backdrop-leave-to {
  opacity: 0;
}

.modal-content-enter-active {
  transition: all var(--duration-300) var(--ease-out);
}

.modal-content-leave-active {
  transition: all var(--duration-200) var(--ease-in);
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
  border-radius: var(--radius-xs);
}
</style>
