<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- GH#8987: Recursive folder tree shown in ChatSidebar.
     Supports create / rename / delete / pin / nest (max 3 levels).
     Sessions are displayed under their folder; drag-assign via session context menu. -->
<template>
  <div class="folder-tree">
    <!-- Root-level folders -->
    <FolderNode
      v-for="folder in folderStore.rootFolders"
      :key="folder.id"
      :folder="folder"
      :depth="0"
      :sessions="sessions"
      :current-session-id="currentSessionId"
      @session-click="$emit('session-click', $event)"
      @folder-created="onFolderCreated"
    />

    <!-- Create root folder button -->
    <button
      v-if="!creatingRoot"
      class="mt-1 flex items-center gap-1 w-full text-xs text-autobot-text-muted hover:text-autobot-text-secondary px-1 py-1 rounded transition-colors"
      @click="creatingRoot = true"
    >
      <Icon name="folder-plus" class="text-xs" />
      {{ $t('chat.folders.newFolder') }}
    </button>
    <div v-else class="mt-1 flex items-center gap-1">
      <input
        ref="rootInput"
        v-model="rootFolderName"
        type="text"
        class="flex-1 text-xs px-2 py-1 border border-autobot-border rounded bg-autobot-bg-card focus:outline-none focus:ring-1 focus:ring-electric-500"
        :placeholder="$t('chat.folders.folderName')"
        @keyup.enter="createRootFolder"
        @keyup.escape="cancelRootCreate"
        @blur="cancelRootCreate"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import FolderNode from './ChatFolderNode.vue'
import { useFolderStore } from '@/stores/useFolderStore'
import type { ChatSession } from '@/stores/useChatStore'

const { t } = useI18n()

defineProps<{
  sessions: ChatSession[]
  currentSessionId: string | null
}>()

defineEmits<{
  'session-click': [sessionId: string]
}>()

const folderStore = useFolderStore()

const creatingRoot = ref(false)
const rootFolderName = ref('')
const rootInput = ref<HTMLInputElement>()

function onFolderCreated() {
  // nothing needed — store updates reactively
}

async function createRootFolder() {
  const name = rootFolderName.value.trim()
  if (!name) {
    creatingRoot.value = false
    return
  }
  await folderStore.createFolder({ name, parent_id: null })
  rootFolderName.value = ''
  creatingRoot.value = false
}

function cancelRootCreate() {
  rootFolderName.value = ''
  creatingRoot.value = false
}

watch(creatingRoot, async (v) => {
  if (v) {
    await nextTick()
    rootInput.value?.focus()
  }
})
</script>

