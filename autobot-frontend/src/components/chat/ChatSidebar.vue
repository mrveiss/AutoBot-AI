<template>
  <div
    class="flex h-full shrink-0 flex-col overflow-hidden border-e border-[var(--aui-color-border)] bg-[var(--aui-color-surface)] transition-all duration-300"
    :class="{ 'w-12': store.sidebarCollapsed, 'w-[16.25rem]': !store.sidebarCollapsed }"
  >
    <!-- Toggle Button row: desktop collapse toggle + mobile close button (#1804) -->
    <div class="flex shrink-0 items-center border-b border-[var(--aui-color-border)]">
      <BaseButton
        variant="ghost"
        class="hidden flex-1 p-3 lg:flex"
        @click="controller.toggleSidebar()"
        :aria-label="store.sidebarCollapsed ? $t('chat.sidebar.expandSidebar') : $t('chat.sidebar.collapseSidebar')"
      >
        <Icon :name="store.sidebarCollapsed ? 'chevron-right' : 'chevron-left'" />
      </BaseButton>
      <!-- Mobile header: close button only. The section headings below are the accessible headings (#5456). -->
      <div class="flex w-full items-center justify-end px-3 py-2 lg:hidden">
        <BaseButton variant="ghost" class="p-2" @click="emit('close-mobile')" :aria-label="$t('common.close')">
          <Icon name="times" />
        </BaseButton>
      </div>
    </div>

    <!-- v-show, not v-if: a reload started in System Control must survive collapsing and expanding the sidebar. -->
    <div v-show="!store.sidebarCollapsed" class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <!-- Mockup order: toolbar (New chat, Select, More, Search), Folders, Chat History, rows -->
      <div class="px-3 pt-4">
        <ChatSidebarToolbar
          v-model:search="searchQuery"
          :selection-mode="selectionMode"
          :selected-count="sessionSelection.selectedCount.value"
          :has-current-session="!!store.currentSessionId"
          @new-chat="controller.createNewSession()"
          @toggle-selection="selectionMode ? cancelSelection() : enableSelectionMode()"
          @delete-selected="deleteSelectedSessions()"
          @reset-chat="controller.resetCurrentChat()"
          @delete-chat="deleteCurrentSession()"
          @refresh="controller.loadChatSessions()"
        />
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3 [scrollbar-width:thin]">
        <!-- Folders Section (GH#8987) -->
        <section v-if="folderStore.folders.length > 0">
          <div class="mx-2.5 mb-1.5 mt-4 flex items-center justify-between">
            <h3 class="m-0 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-[var(--aui-color-text-muted)]">
              {{ $t('chat.folders.folders') }}
            </h3>
            <BaseButton
              variant="ghost"
              size="xs"
              :aria-expanded="showFolders"
              :aria-label="$t('chat.folders.folders')"
              @click="showFolders = !showFolders"
            >
              <Icon :name="showFolders ? 'chevron-down' : 'chevron-right'" class="text-xs" />
            </BaseButton>
          </div>
          <ChatFolderTree
            v-if="showFolders"
            :sessions="filteredSessions"
            :current-session-id="store.currentSessionId"
            @session-click="(id) => controller.switchToSession(id)"
          />

          <!-- GH#8987: Archived folders (hidden by default, chats remain searchable) -->
          <div v-if="folderStore.archivedFolders.length > 0" class="mt-2 border-t border-[var(--aui-color-border)] pt-2">
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

        <ChatUnassignedGroup
          :sessions="unassignedSessions"
          :companies="companies"
          :title-of="(s) => s.title || getSessionPreview(s)"
          @open="openSession"
          @assign="assignToCompany"
        />

        <section>
          <h3 class="mx-2.5 mb-1.5 mt-4 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-[var(--aui-color-text-muted)]">
            {{ $t('chat.sidebar.chatHistory') }}
          </h3>
          <ChatSessionList
            :sessions="filteredSessions"
            :total-count="store.sessions.filter((s) => !s.unassigned).length"
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
        </section>
      </div>

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
    :preview-failed="deletePreviewFailed"
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
      data-autofocus
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
import { useChatCompanyScope } from '@/composables/chat/useChatCompanyScope'
import ChatFolderTree from './ChatFolderTree.vue'
import FolderNode from './ChatFolderNode.vue'
import ChatSidebarToolbar from './ChatSidebarToolbar.vue'
import ChatUnassignedGroup from './ChatUnassignedGroup.vue'
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
  getSessionPreview, searchQuery, filteredSessions, unassignedSessions,
  selectionMode, sessionSelection, enableSelectionMode, cancelSelection, deleteSelectedSessions,
  showEditModal, editingName, editSessionName, saveSessionName, cancelEdit,
  showShareDialog, shareTargetSessionId, openShareDialog, handleShareComplete,
  showDeleteDialog, deleteTargetSessionId, deleteFileStats, deleteKBFacts, kbFactsLoading, deletePreviewFailed,
  deleteSession, deleteCurrentSession, handleDeleteConfirm, handleDeleteCancel,
} = useChatSidebarSessions()

// #21997: the list follows the active company; a person assigns each Unassigned chat.
const { companies, assignToCompany } = useChatCompanyScope()

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
