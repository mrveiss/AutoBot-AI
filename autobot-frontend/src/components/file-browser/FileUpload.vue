<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="file-upload-section">
    <div class="file-upload-inline-wrapper">
      <label for="visible-file-input" class="file-input-label">
        <Icon name="cloud-upload-alt" />
        {{ $t('fileBrowser.upload.dragAndDrop') }}
      </label>

      <!-- Visible file input -->
      <input
        id="visible-file-input"
        ref="visibleFileInput"
        type="file"
        @change="handleFileSelected"
        class="visible-file-input"
        data-testid="visible-file-upload-input"
        :aria-label="$t('fileBrowser.upload.visibleInputAriaLabel')"
        multiple
      />
    </div>

    <!-- Hidden file input for programmatic access -->
    <input
      ref="hiddenFileInput"
      type="file"
      style="display: none"
      @change="handleFileSelected"
      data-testid="file-upload-input"
      :aria-label="$t('fileBrowser.upload.hiddenInputAriaLabel')"
      multiple
    />
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref } from 'vue'

interface Emits {
  (e: 'files-selected', files: FileList): void
}

const emit = defineEmits<Emits>()

// Template refs
const visibleFileInput = ref<HTMLInputElement>()
const hiddenFileInput = ref<HTMLInputElement>()

// Methods
const handleFileSelected = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    emit('files-selected', target.files)
  }
}

const triggerFileSelect = () => {
  hiddenFileInput.value?.click()
}

// Expose methods for parent component
defineExpose({
  triggerFileSelect
})
</script>

<style scoped>
.file-upload-section {
  padding: 0 var(--aui-space-2);
  border: 1px dashed var(--aui-color-border);
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-surface);
  transition: border-color var(--aui-transition);
}
.file-upload-section:hover,
.file-upload-section:focus-within {
  border-color: var(--aui-color-primary);
}
.file-upload-inline-wrapper {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--aui-space-1);
}
.file-input-label {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--aui-space-2);
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  color: var(--aui-color-text-muted);
  cursor: pointer;
}
.visible-file-input {
  flex: 1;
  min-width: 150px;
  font-size: var(--aui-text-sm);
  color: var(--aui-color-text-muted);
}
.visible-file-input::file-selector-button {
  margin-right: var(--aui-space-2);
  padding: var(--aui-space-1) var(--aui-space-3);
  border: 0;
  border-radius: var(--aui-radius-md);
  background: var(--aui-color-primary);
  color: var(--aui-color-primary-contrast);
  font-size: var(--aui-text-sm);
  font-weight: var(--aui-font-weight-medium);
  cursor: pointer;
}
.visible-file-input::file-selector-button:hover {
  background: var(--aui-color-primary-hover);
}
</style>
