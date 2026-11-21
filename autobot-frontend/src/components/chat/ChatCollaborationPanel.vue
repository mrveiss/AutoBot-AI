<template>
  <div
    tabindex="-1" role="complementary" :aria-label="$t('collaboration.panel.title')"
    class="chat-collab-panel"
  >
    <!-- Header -->
    <div class="chat-collab-panel__header">
      <div class="chat-collab-panel__title">
        <Icon name="users" />
        <h3>{{ $t('collaboration.panel.title') }}</h3>
      </div>
      <div class="chat-collab-panel__actions">
        <BaseButton
          variant="ghost"
          size="xs"
          :title="$t('collaboration.panel.invite')"
          :aria-label="$t('collaboration.panel.invite')"
          @click="showInviteDialog = true"
        >
          <Icon name="user-plus" class="text-xs" />
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="xs"
          :title="$t('collaboration.panel.closePanel')"
          :aria-label="$t('collaboration.panel.closePanel')"
          @click="$emit('close')"
        >
          <Icon name="times" class="text-xs" />
        </BaseButton>
      </div>
    </div>

    <!-- Tabs: Participants / Activity / Notifications / Invitations. List-only: the panel below owns the tabpanel. -->
    <BaseTabs
      list-only
      size="sm"
      :items="tabItems"
      :label="$t('collaboration.panel.tabsLabel')"
      :model-value="activeTab"
      @update:model-value="activeTab = $event as PanelTab"
    />

    <!-- Tab content -->
    <div
      id="chat-collab-tabpanel"
      role="tabpanel"
      :aria-labelledby="`chat-collab-tab-${activeTab}`"
      class="chat-collab-panel__body"
    >
      <template v-if="activeTab === 'participants'">
        <!-- #21993: who is present, above the roster -->
        <PresenceIndicator expanded class="chat-collab-panel__presence" />
        <ParticipantList
          allow-management
          @invite="showInviteDialog = true"
          @remove-participant="handleRemoveParticipant"
          @change-role="handleChangeRole"
        />
      </template>
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
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseTabs } from '@autobot/ui'
import type { TabItem } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import PresenceIndicator from '@/components/collaboration/PresenceIndicator.vue'
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

type PanelTab = 'participants' | 'activity' | 'notifications' | 'invitations'
const activeTab = ref<PanelTab>('participants')
const showInviteDialog = ref(false)

/** A tab's text carries its pending count, so the number is read with the name. */
function withCount(label: string, count: number): string {
  return count > 0 ? `${label} (${count})` : label
}

const tabItems = computed<TabItem[]>(() => [
  { value: 'participants', label: t('collaboration.panel.tabParticipants') },
  { value: 'activity', label: t('collaboration.panel.tabActivity') },
  { value: 'notifications', label: withCount(t('collaboration.panel.tabNotifications'), secretNotifications.value.length) },
  { value: 'invitations', label: withCount(t('collaboration.panel.tabInvitations'), pendingInvitations.value.length) },
].map((tab) => ({
  ...tab,
  id: `chat-collab-tab-${tab.value}`,
  controls: tab.value === activeTab.value ? 'chat-collab-tabpanel' : undefined,
})))

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
.chat-collab-panel {
  display: flex;
  flex-direction: column;
  block-size: 100%;
  inline-size: 20rem;
  min-inline-size: 20rem;
  max-inline-size: 20rem;
  background: var(--aui-color-surface);
  border-inline-start: 1px solid var(--aui-color-border);
}

.chat-collab-panel__header {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  padding: var(--aui-space-3);
  border-block-end: 1px solid var(--aui-color-border);
}

.chat-collab-panel__title {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  color: var(--aui-color-text-muted);
}

.chat-collab-panel__title h3 {
  margin: 0;
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

.chat-collab-panel__actions {
  display: flex;
  align-items: center;
  gap: var(--aui-space-1);
}

.chat-collab-panel__body {
  flex: 1;
  min-block-size: 0;
  overflow-y: auto;
}

.chat-collab-panel__presence {
  padding: var(--aui-space-3);
  border-block-end: 1px solid var(--aui-color-border);
}
</style>
