<script setup lang="ts">
/**
 * Pending Invitations Component
 *
 * #16470: surfaces `useSessionCollaboration`'s `pendingInvitations` (#16460)
 * -- invitations to collaborate on OTHER sessions, addressed to the current
 * user, across every session (not scoped to whichever session is currently
 * open). Lets the user accept or decline via the real
 * `POST /sessions/{id}/invitations/respond` endpoint.
 */

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSessionCollaboration } from '@/composables/useSessionCollaboration'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('PendingInvitations')
const { t } = useI18n()
const { pendingInvitations, refreshPendingInvitations, respondToInvitation } = useSessionCollaboration()

const isLoading = ref(false)
const respondingSessionIds = ref<Set<string>>(new Set())
const respondErrorSessionIds = ref<Set<string>>(new Set())

const hasInvitations = computed(() => pendingInvitations.value.length > 0)

const getPermissionLabel = (permission: string): string => {
  switch (permission) {
    case 'owner': return t('collaboration.participants.roleOwner')
    case 'editor': return t('collaboration.participants.roleEditor')
    default: return t('collaboration.participants.roleViewer')
  }
}

// Matches SecretNotifications.vue's own ad-hoc relative-time formatting.
const formatInvitedAt = (iso: string): string => {
  const invited = new Date(iso)
  if (Number.isNaN(invited.getTime())) return ''
  const seconds = Math.floor((Date.now() - invited.getTime()) / 1000)
  const minutes = Math.floor(seconds / 60)
  if (seconds < 60) return t('collaboration.invitations.justNow')
  if (minutes < 60) return t('collaboration.invitations.minutesAgo', { count: minutes })
  return invited.toLocaleString()
}

const respond = async (sessionId: string, accept: boolean): Promise<void> => {
  if (respondingSessionIds.value.has(sessionId)) return
  respondingSessionIds.value.add(sessionId)
  // A retry gets a clean slate rather than stacking with a stale error.
  respondErrorSessionIds.value.delete(sessionId)
  try {
    const success = await respondToInvitation(sessionId, accept)
    if (!success) {
      logger.error(`Failed to ${accept ? 'accept' : 'decline'} invitation for session ${sessionId}`)
      respondErrorSessionIds.value.add(sessionId)
    }
  } finally {
    respondingSessionIds.value.delete(sessionId)
  }
}

onMounted(async () => {
  isLoading.value = true
  try {
    await refreshPendingInvitations()
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <div class="pending-invitations">
    <div v-if="isLoading" class="text-center py-6 text-autobot-text-muted text-sm">
      <i class="bi bi-hourglass-split mr-1" />
      {{ $t('collaboration.invitations.loading') }}
    </div>

    <div v-else-if="!hasInvitations" class="text-center py-6 text-autobot-text-muted">
      <i class="bi bi-envelope text-2xl mb-2" />
      <div class="text-sm">{{ $t('collaboration.invitations.noInvitations') }}</div>
    </div>

    <div v-else class="space-y-2 p-2">
      <TransitionGroup name="invitation">
        <div
          v-for="invitation in pendingInvitations"
          :key="invitation.sessionId"
          class="invitation-item rounded-lg p-3 bg-autobot-bg-tertiary/50 border border-autobot-border"
        >
          <div class="flex items-center justify-between gap-2 mb-2">
            <span class="text-sm font-medium text-autobot-text-primary truncate">
              {{ $t('collaboration.invitations.sessionLabel', { id: invitation.sessionId }) }}
            </span>
            <span class="px-2 py-0.5 text-xs rounded border bg-blue-500/20 text-blue-400 border-blue-500/30 shrink-0">
              {{ getPermissionLabel(invitation.permission) }}
            </span>
          </div>
          <div class="text-xs text-autobot-text-muted mb-2">
            {{ $t('collaboration.invitations.invitedAt', { time: formatInvitedAt(invitation.invitedAt) }) }}
          </div>
          <div
            v-if="respondErrorSessionIds.has(invitation.sessionId)"
            class="text-xs text-red-400 mb-2"
          >
            {{ $t('collaboration.invitations.respondError') }}
          </div>
          <div class="flex items-center gap-2">
            <button
              class="flex-1 px-2 py-1 text-xs rounded bg-green-500 hover:bg-green-600 text-white transition-colors disabled:opacity-50"
              :disabled="respondingSessionIds.has(invitation.sessionId)"
              @click="respond(invitation.sessionId, true)"
            >
              {{ $t('collaboration.invitations.accept') }}
            </button>
            <button
              class="flex-1 px-2 py-1 text-xs rounded bg-autobot-bg-tertiary hover:bg-red-500/10 hover:text-red-400 text-autobot-text-secondary transition-colors disabled:opacity-50"
              :disabled="respondingSessionIds.has(invitation.sessionId)"
              @click="respond(invitation.sessionId, false)"
            >
              {{ $t('collaboration.invitations.decline') }}
            </button>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </div>
</template>

<style scoped>
.invitation-enter-active {
  transition: all var(--duration-300) var(--ease-out);
}

.invitation-leave-active {
  transition: all var(--duration-200) var(--ease-in);
}

.invitation-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.invitation-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.invitation-move {
  transition: transform var(--duration-300) var(--ease-out);
}
</style>
