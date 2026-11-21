<template>
  <div
    class="chat-sidebar"
    :class="{ 'w-12': store.sidebarCollapsed, 'w-80': !store.sidebarCollapsed }"
  >
    <!-- Toggle Button row: desktop collapse toggle + mobile close button (#1804) -->
    <div class="flex items-center border-b border-autobot-border shrink-0">
      <BaseButton
        variant="ghost"
        class="flex-1 p-3 text-autobot-text-secondary hidden lg:flex"
        @click="controller.toggleSidebar()"
        :aria-label="store.sidebarCollapsed ? $t('chat.sidebar.expandSidebar') : $t('chat.sidebar.collapseSidebar')"
      >
        <Icon :name="store.sidebarCollapsed ? 'chevron-right' : 'chevron-left'" />
      </BaseButton>
      <!--
        Mobile header: close button only.

        #5456: previously also rendered a `<span>{{ chatHistory }}</span>`
        title which duplicated the `<h3>` below on L36 — in the DOM at
        all viewports (CSS media queries don't hide the subtree from
        jsdom / a11y readers in every case). The `<h3>` serves as the
        single accessible section heading; the mobile header keeps just
        the close button, which already has an `aria-label`.
      -->
      <div class="lg:hidden flex items-center justify-end w-full px-3 py-2">
        <BaseButton
          variant="ghost"
          class="p-2 text-autobot-text-secondary"
          @click="emit('close-mobile')"
          :aria-label="$t('common.close')"
        >
          <Icon name="times" />
        </BaseButton>
      </div>
    </div>

    <!-- Sidebar Content -->
    <div v-if="!store.sidebarCollapsed" class="chat-sidebar__content">

      <!-- Folders Section (GH#8987) -->
      <section v-if="folderStore.folders.length > 0" class="border-b border-autobot-border p-3 pb-2 shrink-0 max-h-56 overflow-y-auto" style="scrollbar-width: thin;">
        <div class="flex items-center justify-between mb-1">
          <BaseButton variant="ghost" size="xs" :aria-expanded="showFolders" @click="showFolders = !showFolders">
            <template #icon-left><Icon :name="showFolders ? 'chevron-down' : 'chevron-right'" class="text-xs" /></template>
            {{ $t('chat.folders.folders') }}
            <span v-if="folderStore.folders.length" class="text-autobot-text-muted font-normal">({{ folderStore.folders.length }})</span>
          </BaseButton>
        </div>
        <ChatFolderTree
          v-if="showFolders"
          :sessions="filteredSessions"
          :current-session-id="store.currentSessionId"
          @session-click="(id) => controller.switchToSession(id)"
        />

        <!-- GH#8987: Archived folders (hidden by default, chats remain searchable) -->
        <div v-if="folderStore.archivedFolders.length > 0" class="mt-2 pt-2 border-t border-autobot-border">
          <BaseButton variant="ghost" size="xs" :aria-expanded="showArchived" @click="showArchived = !showArchived">
            <template #icon-left><Icon :name="showArchived ? 'chevron-down' : 'chevron-right'" class="text-xs" /></template>
            {{ $t('chat.folders.archived') }}
            <span class="font-normal">({{ folderStore.archivedFolders.length }})</span>
          </BaseButton>
          <FolderNode
            v-for="folder in folderStore.archivedFolders"
            v-show="showArchived"
            :key="folder.id"
            :folder="folder"
            :depth="0"
            :sessions="filteredSessions"
            :current-session-id="store.currentSessionId"
            @session-click="(id) => controller.switchToSession(id)"
          />
        </div>
      </section>

      <!-- Chat History: toolbar (new chat, select, search) over the scrollable list -->
      <section class="chat-sidebar__history">
        <h3 class="chat-sidebar__heading">{{ $t('chat.sidebar.chatHistory') }}</h3>
        <ChatSidebarToolbar
          v-model:search="searchQuery"
          :selection-mode="selectionMode"
          :selected-count="sessionSelection.selectedCount.value"
          @new-chat="controller.createNewSession()"
          @toggle-selection="selectionMode ? cancelSelection() : enableSelectionMode()"
        />
        <ChatSessionList
          class="chat-sidebar__list"
          :sessions="filteredSessions"
          :total-count="store.sessions.length"
          :current-session-id="store.currentSessionId"
          :selection-mode="selectionMode"
          :is-selected="sessionSelection.isSelected"
          :title-of="(s) => s.title || getSessionPreview(s)"
          :folders="folderStore.folders"
          @open="openSession"
          @toggle-select="sessionSelection.toggle"
          @share="openShareDialog"
          @rename="editSessionName"
          @delete="deleteSession"
          @assign-folder="(id, folderId) => folderStore.assignSessionToFolder(id, folderId)"
        />

        <!-- Chat actions stay at the bottom of the history area -->
        <div v-if="!selectionMode" class="chat-sidebar__actions">
          <BaseButton
            variant="secondary"
            size="xs"
            :disabled="!store.currentSessionId"
            :aria-label="$t('chat.sidebar.resetChat')"
            @click="controller.resetCurrentChat()"
          >
            <template #icon-left><Icon name="redo" /></template>
            {{ $t('common.reset') }}
          </BaseButton>
          <BaseButton
            variant="error"
            size="xs"
            :disabled="!store.currentSessionId"
            :aria-label="$t('chat.sidebar.deleteChat')"
            @click="deleteCurrentSession()"
          >
            <template #icon-left><Icon name="trash" /></template>
            {{ $t('common.delete') }}
          </BaseButton>
          <BaseButton
            variant="outline"
            size="xs"
            :aria-label="$t('chat.sidebar.refreshList')"
            @click="controller.loadChatSessions()"
          >
            <template #icon-left><Icon name="sync" /></template>
            {{ $t('common.refresh') }}
          </BaseButton>
        </div>
        <div v-else class="chat-sidebar__actions">
          <BaseButton
            variant="error"
            size="xs"
            block
            :disabled="sessionSelection.selectedCount.value === 0"
            :aria-label="$t('chat.sidebar.deleteSelected')"
            @click="deleteSelectedSessions()"
          >
            <template #icon-left><Icon name="trash" /></template>
            {{ $t('chat.sidebar.deleteNSelected', { count: sessionSelection.selectedCount.value }) }}
          </BaseButton>
        </div>
      </section>

      <!-- Advanced: Reload System (leaves Chat for the SLM in step 5f) -->
      <ChatSidebarSystemControl />
    </div>
  </div>

  <!-- Delete Conversation Dialog (Issue #547: Added KB facts preview) -->
  <DeleteConversationDialog
    :visible="showDeleteDialog"
    :session-id="deleteTargetSessionId || ''"
    :session-name="store.sessions.find(s => s.id === deleteTargetSessionId)?.title"
    :file-stats="deleteFileStats"
    :kb-facts="deleteKBFacts"
    :kb-facts-loading="kbFactsLoading"
    @confirm="handleDeleteConfirm"
    @cancel="handleDeleteCancel"
  />

  <!-- Share Conversation Dialog (Issue #689) -->
  <ShareConversationDialog
    :visible="showShareDialog"
    :session-id="shareTargetSessionId || ''"
    @update:visible="showShareDialog = $event"
    @shared="handleShareComplete"
    @cancel="showShareDialog = false"
  />

  <!-- Edit Session Name Modal -->
  <BaseModal
    :close-label="t('ui.modal.closeDialog')"
    v-model="showEditModal"
    :title="$t('chat.sidebar.editChatName')"
    size="md"
  >
    <BaseInput
      v-model="editingName"
      ref="editInput"
      :aria-label="$t('chat.sidebar.editChatName')"
      :placeholder="$t('chat.sidebar.enterChatName')"
      @keyup.enter="saveSessionName"
      @keyup.escape="cancelEdit"
    />

    <template #actions>
      <BaseButton
        variant="secondary"
        @click="cancelEdit"
      >
        {{ $t('common.cancel') }}
      </BaseButton>
      <BaseButton
        variant="primary"
        @click="saveSessionName"
      >
        {{ $t('common.save') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseModal, BaseButton, BaseInput } from '@autobot/ui'
import { useChatStore } from '@/stores/useChatStore'
import type { ChatSession } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useFolderStore } from '@/stores/useFolderStore'
import { useChatSidebarSessions } from '@/composables/chat/useChatSidebarSessions'
import ChatFolderTree from './ChatFolderTree.vue'
import FolderNode from './ChatFolderNode.vue'
import ChatSidebarToolbar from './ChatSidebarToolbar.vue'
import ChatSessionList from './ChatSessionList.vue'
import ChatSidebarSystemControl from './ChatSidebarSystemControl.vue'
import DeleteConversationDialog from './DeleteConversationDialog.vue'
import ShareConversationDialog from './ShareConversationDialog.vue'

// #1804: emit close-mobile so ChatInterface can close the mobile overlay
const emit = defineEmits<{ 'close-mobile': [] }>()

const { t } = useI18n()
const store = useChatStore()
const controller = useChatController()
const folderStore = useFolderStore()

// The session list state and actions (search, selection, rename, share, delete) live in one composable.
const {
  getSessionPreview, searchQuery, filteredSessions,
  selectionMode, sessionSelection, enableSelectionMode, cancelSelection, deleteSelectedSessions,
  showEditModal, editingName, editInput, editSessionName, saveSessionName, cancelEdit,
  showShareDialog, shareTargetSessionId, openShareDialog, handleShareComplete,
  showDeleteDialog, deleteTargetSessionId, deleteFileStats, deleteKBFacts, kbFactsLoading,
  deleteSession, deleteCurrentSession, handleDeleteConfirm, handleDeleteCancel,
} = useChatSidebarSessions()

// GH#8987: folder section state
const showFolders = ref(true)
const showArchived = ref(false)

onMounted(() => {
  folderStore.fetchFolders()
})

function openSession(session: ChatSession): void {
  controller.switchToSession(session.id)
  // #1804: close the mobile overlay after selecting a session
  emit('close-mobile')
}
</script>

<style scoped>
.chat-sidebar {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  block-size: 100%;
  overflow: hidden;
  background: var(--aui-color-surface);
  border-inline-end: 1px solid var(--aui-color-border);
  transition: all 0.3s;
}

.chat-sidebar__content {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-block-size: 0;
  overflow: hidden;
}

.chat-sidebar__history {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--aui-space-2);
  min-block-size: 0;
  padding: var(--aui-space-4) var(--aui-space-4) 0;
  overflow: hidden;
}

.chat-sidebar__heading {
  margin: 0;
  font-size: var(--aui-text-base);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}

.chat-sidebar__list {
  flex: 1;
  min-block-size: 0;
  overflow-y: auto;
  scrollbar-width: thin;
}

.chat-sidebar__actions {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: var(--aui-space-2);
  padding: var(--aui-space-2) 0;
  border-top: 1px solid var(--aui-color-border);
}
</style>
