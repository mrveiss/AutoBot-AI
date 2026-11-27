<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  The Files tab (#22349): header with the folder path, upload and new folder, the folder tree (Full mode only), and the
  file table. Every control is kept; the tree and the view toggle carry `adv`. State and handlers live in
  `useFileBrowserActions`.
-->
<template>
  <div class="file-browser">
    <FileBrowserHeader
      :view-mode="viewMode"
      :current-path="currentPath"
      @upload="triggerFileUpload"
      @new-folder="createNewFolder"
      @navigate-to-path="navigateToPath"
    />

    <FilePreview :show-preview="showPreview" :preview-file="previewFile" @close="closePreview" @download="downloadPreviewFile" />

    <div class="file-content-container">
      <div class="browse-layout" :class="{ 'browse-layout--tree': viewMode === 'tree' }">
        <div v-if="viewMode === 'tree'" class="tree-side adv">
          <FileTreeView
            :directory-tree="directoryTree"
            :selected-path="selectedPath"
            @toggle-node="toggleNode"
            @expand-all="expandAll"
            @collapse-all="collapseAll"
          />
        </div>

        <div class="files-panel">
          <div class="files-header">
            <h3><Icon name="files" /> {{ $t('fileBrowser.browser.contentsOf', { path: selectedPath || '/' }) }}</h3>
            <FileUpload ref="fileUploadRef" class="file-upload-inline" @files-selected="uploadFiles" />
            <div class="file-actions-inline">
              <BaseButton variant="outline" size="sm" :aria-label="$t('fileBrowser.browser.refreshAriaLabel')" data-testid="refresh-files" @click="refreshFiles">
                <Icon name="sync-alt" /> {{ $t('fileBrowser.browser.refresh') }}
              </BaseButton>
              <BaseButton
                variant="outline"
                size="sm"
                class="adv"
                :aria-label="$t('fileBrowser.browser.toggleViewAriaLabel')"
                data-testid="toggle-view"
                @click="toggleView"
              >
                <Icon :name="viewMode === 'tree' ? 'list' : 'folder'" />
                {{ viewMode === 'tree' ? $t('fileBrowser.browser.listView') : $t('fileBrowser.browser.treeView') }}
              </BaseButton>
            </div>
          </div>
          <FileListTable
            :files="sortedFiles"
            :sort-field="sortField"
            :sort-order="sortOrder"
            :current-path="currentPath"
            @sort="sortBy"
            @navigate="navigateToPath"
            @view-file="viewFile"
            @rename-file="renameFile"
            @delete-file="deleteFile"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useFileBrowserActions } from '@/composables/file-browser/useFileBrowserActions'
import FileBrowserHeader from './FileBrowserHeader.vue'
import FileUpload from './FileUpload.vue'
import FilePreview from './FilePreview.vue'
import FileTreeView from './FileTreeView.vue'
import FileListTable from './FileListTable.vue'

const props = withDefaults(defineProps<{ chatContext?: boolean }>(), { chatContext: false })

const fileUploadRef = ref<InstanceType<typeof FileUpload>>()
const {
  directoryTree, previewFile, currentPath, selectedPath, viewMode, sortField, sortOrder, showPreview, sortedFiles,
  refreshFiles, navigateToPath, toggleView, sortBy, uploadFiles, viewFile, deleteFile, renameFile, createNewFolder,
  closePreview, downloadPreviewFile, toggleNode, expandAll, collapseAll,
} = useFileBrowserActions({ chatContext: props.chatContext })

const triggerFileUpload = () => fileUploadRef.value?.triggerFileSelect()

onMounted(() => {
  refreshFiles()
})
</script>

<style scoped>
.file-browser {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--aui-space-6);
  background: var(--aui-color-surface-sunken);
}
.file-content-container {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.browse-layout {
  display: flex;
  flex: 1;
  gap: var(--aui-space-6);
  min-height: 0;
}
.tree-side {
  min-width: 14rem;
}
.files-panel {
  flex: 1;
  min-width: 0;
  overflow: auto;
  background: var(--aui-color-surface-raised);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
}
.files-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--aui-space-4);
  padding: var(--aui-space-4);
  border-bottom: 1px solid var(--aui-color-border);
  background: var(--aui-color-surface-sunken);
}
.files-header h3 {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--aui-space-2);
  font-size: var(--aui-text-lg);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}
.file-upload-inline {
  flex: 1;
  min-width: 0;
}
.file-actions-inline {
  display: flex;
  flex-shrink: 0;
  gap: var(--aui-space-2);
  margin-left: auto;
}
</style>
