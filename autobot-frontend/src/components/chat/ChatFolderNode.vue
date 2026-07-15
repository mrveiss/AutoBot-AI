<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!-- GH#8987: Single folder node in the tree. Recursive for up to 3 levels. -->
<template>
  <div class="folder-node" :style="{ paddingLeft: `${depth * 12}px` }">
    <!-- Folder row -->
    <div
      class="flex items-center gap-1 px-1 py-1 rounded cursor-pointer hover:bg-autobot-bg-secondary group relative text-sm"
      :class="{ 'bg-autobot-bg-secondary': isExpanded }"
      @click="isExpanded = !isExpanded"
    >
      <!-- Expand chevron -->
      <Icon
        :name="isExpanded ? 'chevron-down' : 'chevron-right'"
        class="text-xs text-autobot-text-muted shrink-0 w-3"
      />

      <!-- Folder icon -->
      <Icon
        :name="isExpanded ? 'folder-open' : 'folder'"
        class="text-xs shrink-0"
        :class="folder.pinned ? 'text-electric-500' : 'text-autobot-text-muted'"
      />

      <!-- Folder name or inline edit -->
      <span v-if="!editing" class="flex-1 truncate text-autobot-text-primary text-xs leading-tight">
        {{ folder.name }}
      </span>
      <input
        v-else
        ref="editInput"
        v-model="editName"
        type="text"
        class="flex-1 text-xs px-1 border border-electric-500 rounded bg-autobot-bg-card focus:outline-none"
        @keyup.enter="saveRename"
        @keyup.escape="cancelRename"
        @blur="cancelRename"
        @click.stop
      />

      <!-- Session count badge -->
      <span
        v-if="!editing && totalSessionCount > 0"
        class="text-xs text-autobot-text-muted shrink-0"
      >
        {{ totalSessionCount }}
      </span>

      <!-- Folder actions (on hover) -->
      <div
        v-if="!editing"
        class="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 shrink-0 transition-opacity"
        @click.stop
      >
        <!-- Pin -->
        <button
          class="p-0.5 rounded hover:bg-autobot-bg-card"
          :class="folder.pinned ? 'text-electric-500' : 'text-autobot-text-muted'"
          :title="folder.pinned ? $t('chat.folders.unpin') : $t('chat.folders.pin')"
          @click="folderStore.togglePin(folder.id)"
        >
          <Icon name="thumbtack" class="text-xs" />
        </button>

        <!-- Add sub-folder (only if depth < 2, i.e. max depth 3) -->
        <button
          v-if="depth < 2"
          class="p-0.5 rounded hover:bg-autobot-bg-card text-autobot-text-muted hover:text-autobot-text-secondary"
          :title="$t('chat.folders.addSubfolder')"
          @click="startChildCreate"
        >
          <Icon name="folder-plus" class="text-xs" />
        </button>

        <!-- Rename -->
        <button
          class="p-0.5 rounded hover:bg-autobot-bg-card text-autobot-text-muted hover:text-autobot-text-secondary"
          :title="$t('chat.folders.rename')"
          @click="startRename"
        >
          <Icon name="edit" class="text-xs" />
        </button>

        <!-- Archive / Unarchive -->
        <button
          class="p-0.5 rounded hover:bg-autobot-bg-card text-autobot-text-muted hover:text-autobot-text-secondary"
          :title="folder.archived ? $t('chat.folders.unarchive') : $t('chat.folders.archive')"
          @click="folderStore.toggleArchive(folder.id)"
        >
          <Icon :name="folder.archived ? 'box-open' : 'archive'" class="text-xs" />
        </button>

        <!-- Delete -->
        <button
          class="p-0.5 rounded hover:bg-autobot-bg-card text-red-400 hover:text-red-500"
          :title="$t('common.delete')"
          @click="deleteThisFolder"
        >
          <Icon name="trash" class="text-xs" />
        </button>
      </div>
    </div>

    <!-- Expanded content -->
    <div v-if="isExpanded" class="ms-1">
      <!-- Child folder creation input -->
      <div v-if="creatingChild" class="flex items-center gap-1 ps-4 py-0.5">
        <input
          ref="childInput"
          v-model="childFolderName"
          type="text"
          class="flex-1 text-xs px-2 py-0.5 border border-autobot-border rounded bg-autobot-bg-card focus:outline-none focus:ring-1 focus:ring-electric-500"
          :placeholder="$t('chat.folders.folderName')"
          @keyup.enter="createChildFolder"
          @keyup.escape="cancelChildCreate"
          @blur="cancelChildCreate"
        />
      </div>

      <!-- Child folders (recursive) -->
      <FolderNode
        v-for="child in childFolders"
        :key="child.id"
        :folder="child"
        :depth="depth + 1"
        :sessions="sessions"
        :current-session-id="currentSessionId"
        @session-click="$emit('session-click', $event)"
        @folder-created="$emit('folder-created')"
      />

      <!-- Sessions inside this folder -->
      <div
        v-for="session in folderSessions"
        :key="session.id"
        class="flex items-center gap-1 ps-5 py-1 rounded cursor-pointer hover:bg-autobot-bg-secondary text-xs"
        :class="session.id === currentSessionId ? 'bg-electric-100 text-electric-800' : 'text-autobot-text-secondary'"
        @click="$emit('session-click', session.id)"
      >
        <Icon name="comment-dots" class="text-xs shrink-0 opacity-60" />
        <span class="truncate flex-1">{{ session.title }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import Icon from '@/components/ui/Icon.vue'
import { useFolderStore, type ChatFolder } from '@/stores/useFolderStore'
import type { ChatSession } from '@/stores/useChatStore'

const { t } = useI18n()
const { confirm } = useConfirmDialog()

const props = defineProps<{
  folder: ChatFolder
  depth: number
  sessions: ChatSession[]
  currentSessionId: string | null
}>()

defineEmits<{
  'session-click': [sessionId: string]
  'folder-created': []
}>()

const folderStore = useFolderStore()

const isExpanded = ref(props.folder.pinned)
const editing = ref(false)
const editName = ref('')
const editInput = ref<HTMLInputElement>()
const creatingChild = ref(false)
const childFolderName = ref('')
const childInput = ref<HTMLInputElement>()

const childFolders = computed(() => folderStore.childrenOf(props.folder.id))

const folderSessions = computed(() =>
  props.sessions.filter((s) => props.folder.session_ids.includes(s.id))
)

const totalSessionCount = computed(
  () => props.folder.session_ids.length + childFolders.value.reduce((acc, c) => acc + c.session_ids.length, 0)
)

function startRename() {
  editName.value = props.folder.name
  editing.value = true
  nextTick(() => editInput.value?.focus())
}

async function saveRename() {
  const name = editName.value.trim()
  if (name && name !== props.folder.name) {
    await folderStore.updateFolder(props.folder.id, { name })
  }
  editing.value = false
}

function cancelRename() {
  editing.value = false
}

async function deleteThisFolder() {
  if (!(await confirm({ title: t('common.confirm'), message: t('chat.folders.confirmDelete', { name: props.folder.name }) }))) return
  await folderStore.deleteFolder(props.folder.id)
}

function startChildCreate() {
  isExpanded.value = true
  creatingChild.value = true
  nextTick(() => childInput.value?.focus())
}

async function createChildFolder() {
  const name = childFolderName.value.trim()
  if (name) {
    await folderStore.createFolder({ name, parent_id: props.folder.id })
  }
  childFolderName.value = ''
  creatingChild.value = false
}

function cancelChildCreate() {
  childFolderName.value = ''
  creatingChild.value = false
}
</script>

<!-- Recursive self-reference: using defineComponent name for recursion -->
<script lang="ts">
export default { name: 'FolderNode' }
</script>
