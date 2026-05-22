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
@reference "../../assets/tailwind.css";
.file-upload-section {
  @apply mb-6 p-0 border-2 border-dashed border-autobot-border rounded-lg bg-autobot-bg-secondary hover:border-autobot-border transition-colors;
}

.file-upload-inline-wrapper {
  @apply flex items-center flex-wrap;
}

.file-input-label {
  @apply flex items-center gap-2 text-autobot-text-secondary font-medium cursor-pointer text-sm flex-shrink-0;
}

.file-input-label:hover {
  @apply text-autobot-text-primary;
}

.visible-file-input {
  @apply flex-1 min-w-[150px] text-sm text-autobot-text-muted py-0 file:mr-2 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-medium;
}

.visible-file-input::file-selector-button {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.visible-file-input:hover::file-selector-button {
  filter: brightness(1.1);
}

/* Drag and drop styling */
.file-upload-section.drag-over {
  border-color: var(--color-primary);
  background: var(--color-info-bg);
}
</style>
