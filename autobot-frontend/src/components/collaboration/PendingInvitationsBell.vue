<script setup lang="ts">
/**
 * Pending Invitations Bell
 *
 * #16470 follow-up: ChatCollaborationPanel.vue's Invitations tab is only
 * reachable when the current session is already collaborative
 * (`ChatInterface.vue`'s `isCollaborativeSession` gate) -- but the person an
 * invitation is FOR is, by definition, not yet a participant of the session
 * they're invited to, so they typically have no collaborative session of
 * their own and could never reach that tab. This is a small, always-
 * mountable entry point, independent of session mode, so that gap doesn't
 * leave the invitee stranded. Deliberately does not touch
 * ChatCollaborationPanel.vue or ChatInterface.vue's existing panel gating --
 * it renders the same PendingInvitations.vue list in its own dropdown.
 */

import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import PendingInvitations from '@/components/collaboration/PendingInvitations.vue'
import { useSessionCollaboration } from '@/composables/useSessionCollaboration'

const { t } = useI18n()
const { pendingInvitations, refreshPendingInvitations } = useSessionCollaboration()

const showDropdown = ref(false)
// Once opened, stays mounted even if the count drops to 0 (e.g. the user
// just responded to their only invitation) so the panel doesn't vanish out
// from under them mid-interaction.
const hasPendingInvitations = computed(() => pendingInvitations.value.length > 0)

const toggleDropdown = () => {
  showDropdown.value = !showDropdown.value
}

onMounted(() => {
  refreshPendingInvitations()
})
</script>

<template>
  <div v-if="hasPendingInvitations || showDropdown" class="relative">
    <button
      class="header-btn relative"
      :class="{ 'bg-electric-100 text-electric-600': showDropdown }"
      :title="t('collaboration.invitations.bellTitle')"
      :aria-label="t('collaboration.invitations.bellTitle')"
      :aria-pressed="showDropdown"
      @click="toggleDropdown"
    >
      <Icon name="bell" />
      <span v-if="pendingInvitations.length > 0" class="invitation-badge">
        {{ pendingInvitations.length }}
      </span>
    </button>

    <div v-if="showDropdown" class="invitation-dropdown" role="dialog" :aria-label="t('collaboration.invitations.bellTitle')">
      <div class="flex items-center justify-between px-3 py-2 border-b border-autobot-border">
        <span class="text-sm font-semibold text-autobot-text-primary">{{ t('collaboration.invitations.bellTitle') }}</span>
        <button
          class="action-btn"
          :aria-label="t('collaboration.panel.closePanel')"
          @click="showDropdown = false"
        >
          <Icon name="times" class="text-xs" />
        </button>
      </div>
      <PendingInvitations />
    </div>
  </div>
</template>

<style scoped>
.invitation-badge {
  @apply absolute -top-1 -right-1 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-medium leading-none;
}

.invitation-dropdown {
  @apply absolute right-0 top-full mt-1 w-80 max-h-96 overflow-y-auto rounded-lg border border-autobot-border bg-autobot-bg-card shadow-lg;
  z-index: 40;
}

.action-btn {
  @apply w-6 h-6 flex items-center justify-center rounded transition-colors text-autobot-text-muted hover:text-autobot-text-secondary hover:bg-autobot-bg-secondary;
}
</style>
