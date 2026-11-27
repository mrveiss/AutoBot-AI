<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatFilePanelItem -- one file card of the Chat files panel (#22349): a selection checkbox, the name (or the
  inline rename field), size and age, the "AI generated" badge, the Preview / Download / Delete icon buttons and
  a "More" menu holding Edit, Rename and Duplicate. A right-click on the card opens the same menu. Preview is
  offered only for previewable files and Edit only for editable ones; the caller decides and passes the flags.
  Presentational: it emits intents and keeps only the rename draft.
-->
<template>
  <div
    class="file-item group p-2 bg-autobot-bg-card border rounded-lg transition-all"
    :class="selected ? 'border-autobot-primary bg-autobot-bg-tertiary' : 'border-autobot-border hover:border-autobot-primary'"
    data-testid="file-item"
    @contextmenu.prevent="menuOpen = true"
  >
    <div class="flex items-start gap-2">
      <input
        type="checkbox"
        class="file-item__check mt-1 shrink-0"
        :checked="selected"
        :aria-label="$t('chat.filePanel.selectFile', { name: file.filename })"
        @change="emit('select')"
      />
      <Icon :name="icon" class="shrink-0 text-autobot-text-secondary" />
      <div class="flex-1 min-w-0">
        <div v-if="renaming" class="flex items-center gap-1">
          <BaseInput
            v-model="renameValue"
            size="sm"
            :aria-label="$t('chat.filePanel.rename')"
            data-testid="rename-input"
            @keyup.enter="commitRename"
            @keyup.escape="renaming = false"
          />
          <ChatHeaderIconButton :label="$t('common.save')" icon="check" data-testid="rename-save" @click="commitRename" />
        </div>
        <p v-else class="text-xs font-medium text-autobot-text-primary truncate" :title="file.filename">{{ file.filename }}</p>
        <div class="flex items-center gap-2 mt-0.5 text-xs text-autobot-text-secondary">
          <span>{{ sizeLabel }}</span>
          <span aria-hidden="true">&middot;</span>
          <span>{{ formatTimeAgo(file.upload_timestamp) }}</span>
        </div>
        <BaseBadge v-if="file.file_type === 'generated'" variant="primary" size="sm" class="mt-1" data-testid="ai-badge">
          {{ $t('chat.filePanel.aiGenerated') }}
        </BaseBadge>
      </div>
      <div class="file-item__actions flex items-center shrink-0">
        <ChatHeaderIconButton
          v-if="previewable"
          :label="$t('chat.filePanel.previewFile', { name: file.filename })"
          icon="eye"
          data-testid="action-preview"
          @click="emit('preview')"
        />
        <ChatHeaderIconButton
          :label="$t('chat.filePanel.downloadFile', { name: file.filename })"
          icon="download"
          data-testid="action-download"
          @click="emit('download')"
        />
        <ChatHeaderIconButton
          :label="$t('chat.filePanel.deleteFile', { name: file.filename })"
          icon="trash"
          icon-class="text-autobot-error"
          data-testid="action-delete"
          @click="emit('delete')"
        />
        <BaseDropdownMenu v-model:open="menuOpen" :items="menuItems" size="sm" align="end" @select="onMenuSelect">
          <template #trigger>
            <BaseButton
              variant="ghost"
              size="sm"
              class="min-w-11 min-h-11 sm:min-w-8 sm:min-h-8"
              :aria-label="$t('chat.filePanel.moreActions', { name: file.filename })"
              data-testid="action-more"
            >
              <Icon name="ellipsis-h" />
            </BaseButton>
          </template>
        </BaseDropdownMenu>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton, BaseDropdownMenu, BaseInput, createRecencyFormatter } from '@autobot/ui'
import type { MenuItem } from '@autobot/ui'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import ChatHeaderIconButton from '@/components/chat/ChatHeaderIconButton.vue'
import type { ConversationFile } from '@/composables/useConversationFiles'

const props = defineProps<{
  file: ConversationFile
  selected: boolean
  icon: IconName
  sizeLabel: string
  previewable: boolean
  editable: boolean
}>()
const emit = defineEmits<{
  select: []
  preview: []
  download: []
  delete: []
  edit: []
  rename: [name: string]
  duplicate: []
}>()

const { t, locale } = useI18n()
const formatTimeAgo = createRecencyFormatter({ justNow: () => t('common.justNow'), locale: () => locale.value, invalidText: '—' })

const menuOpen = ref(false)
const renaming = ref(false)
const renameValue = ref('')

const menuItems = computed<MenuItem[]>(() => [
  ...(props.editable ? [{ key: 'edit', label: t('common.edit') }] : []),
  { key: 'rename', label: t('chat.filePanel.rename') },
  { key: 'duplicate', label: t('chat.filePanel.duplicate') },
])

function onMenuSelect(key: string): void {
  if (key === 'edit') emit('edit')
  else if (key === 'duplicate') emit('duplicate')
  else if (key === 'rename') {
    renameValue.value = props.file.filename
    renaming.value = true
  }
}

function commitRename(): void {
  const name = renameValue.value.trim()
  if (!name) return
  renaming.value = false
  emit('rename', name)
}
</script>

<style scoped>
.file-item {
  animation: slideInFromRight 0.2s ease-out;
}
.file-item__check {
  accent-color: var(--aui-color-primary);
}
.file-item__actions {
  opacity: 0;
  transition: opacity var(--aui-transition);
}
.file-item:hover .file-item__actions,
.file-item:focus-within .file-item__actions {
  opacity: 1;
}
@keyframes slideInFromRight {
  from {
    opacity: 0;
    transform: translateX(10px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .file-item {
    animation: none;
  }
}
</style>
