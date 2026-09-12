<template>
  <div class="chat-collaboration-panel h-full flex flex-col bg-autobot-bg-card border-l border-autobot-border">
    <!-- Header -->
    <div class="flex items-center justify-between p-3 border-b border-autobot-border shrink-0">
      <div class="flex items-center gap-2">
        <Icon name="users" class="text-autobot-text-secondary" />
        <h3 class="text-sm font-semibold text-autobot-text-primary">{{ $t('collaboration.panel.title') }}</h3>
      </div>
      <div class="flex items-center gap-1">
        <button
          @click="showInviteDialog = true"
          class="action-btn"
          :title="$t('collaboration.panel.invite')"
          :aria-label="$t('collaboration.panel.invite')"
        >
          <Icon name="user-plus" class="text-xs" />
        </button>
        <button
          @click="$emit('close')"
          class="action-btn"
          :title="$t('collaboration.panel.closePanel')"
          :aria-label="$t('collaboration.panel.closePanel')"
        >
          <Icon name="times" class="text-xs" />
        </button>
      </div>
    </div>

    <!-- Tabs: Participants / Activity / Notifications -->
    <div class="flex border-b border-autobot-border shrink-0" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        role="tab"
        :aria-selected="activeTab === tab.id"
        class="flex-1 px-3 py-2 text-xs font-medium border-b-2 transition-colors"
        :class="activeTab === tab.id
          ? 'border-electric-500 text-autobot-text-primary'
          : 'border-transparent text-autobot-text-muted hover:text-autobot-text-secondary'"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
        <span v-if="tab.id === 'notifications' && secretNotifications.length > 0" class="ml-1 text-electric-500">
          ({{ secretNotifications.length }})
        </span>
        <span v-if="tab.id === 'invitations' && pendingInvitations.length > 0" class="ml-1 text-electric-500">
          ({{ pendingInvitations.length }})
        </span>
      </button>
    </div>

    <!-- Tab content -->
    <div class="flex-1 min-h-0 overflow-y-auto">
      <ParticipantList
        v-if="activeTab === 'participants'"
        allow-management
        @invite="showInviteDialog = true"
        @remove-participant="handleRemoveParticipant"
        @change-role="handleChangeRole"
      />
      <ActivityFeed v-else-if="activeTab === 'activity'" />
      <SecretNotifications v-else-if="activeTab === 'notifications'" />
      <PendingInvitations v-else-if="activeTab === 'invitations'" />
    </div>

    <InviteUserDialog
      v-model="showInviteDialog"
      @invited="handleInvited"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * Chat Collaboration Panel
 *
 * #16443: hosts the previously-unwired collaboration components
 * (ParticipantList, ActivityFeed, SecretNotifications, InviteUserDialog)
 * in a real view -- a togglable right-side panel in ChatInterface.vue,
 * mirroring ChatFilePanel's existing pattern. Shown only for a
 * collaborative session (session.mode === 'collaborative'), gated by the
 * parent that mounts this panel.
 *
 * #16470: added the Invitations tab (PendingInvitations.vue). Note
 * `pendingInvitations` itself is NOT scoped to the panel's current
 * session -- it lists invitations to every session addressed to the
 * current user, so this tab is reachable (and useful) even though the
 * panel that hosts it only opens for an already-collaborative session.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import ParticipantList from '@/components/collaboration/ParticipantList.vue'
import ActivityFeed from '@/components/collaboration/ActivityFeed.vue'
import SecretNotifications from '@/components/collaboration/SecretNotifications.vue'
import PendingInvitations from '@/components/collaboration/PendingInvitations.vue'
import InviteUserDialog from '@/components/collaboration/InviteUserDialog.vue'
import { useSessionCollaboration } from '@/composables/useSessionCollaboration'
import { apiService } from '@/services/api'
import { useChatStore } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatCollaborationPanel')
const { t } = useI18n()
const chatStore = useChatStore()
const { secretNotifications, pendingInvitations } = useSessionCollaboration()

defineEmits<{
  close: []
}>()

const activeTab = ref<'participants' | 'activity' | 'notifications' | 'invitations'>('participants')
const showInviteDialog = ref(false)

const tabs = [
  { id: 'participants' as const, get label() { return t('collaboration.panel.tabParticipants') } },
  { id: 'activity' as const, get label() { return t('collaboration.panel.tabActivity') } },
  { id: 'notifications' as const, get label() { return t('collaboration.panel.tabNotifications') } },
  { id: 'invitations' as const, get label() { return t('collaboration.panel.tabInvitations') } }
]

const handleInvited = (_userId: string, username: string) => {
  logger.info(`Invited ${username} to the session`)
}

// api/collaboration.py's invite_user upsserts collaborators/permission (the
// same route re-invites with a new permission level), so "change role" reuses
// it rather than needing a dedicated endpoint.
const handleChangeRole = async (userId: string, role: 'owner' | 'collaborator' | 'viewer') => {
  const sessionId = chatStore.currentSession?.id
  if (!sessionId || role === 'owner') return
  try {
    await apiService.inviteToSession(sessionId, userId, role === 'collaborator' ? 'editor' : 'viewer')
  } catch (error) {
    logger.error('Failed to change participant role:', error)
  }
}

const handleRemoveParticipant = async (userId: string) => {
  const sessionId = chatStore.currentSession?.id
  if (!sessionId) return
  try {
    await apiService.removeFromSession(sessionId, userId)
  } catch (error) {
    logger.error('Failed to remove participant:', error)
  }
}
</script>

<style scoped>
.chat-collaboration-panel {
  width: 320px;
  max-width: 320px;
  min-width: 320px;
}

.action-btn {
  @apply w-6 h-6 flex items-center justify-center rounded transition-colors text-autobot-text-muted hover:text-autobot-text-secondary hover:bg-autobot-bg-secondary;
}
</style>
