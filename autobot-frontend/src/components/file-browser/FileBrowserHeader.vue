<template>
  <div class="file-browser-header">
    <h2>{{ title || $t('fileBrowser.header.title') }}</h2>

    <!-- Path Navigation -->
    <div class="path-navigation-inline">
      <FilePathNavigation
        :current-path="currentPath"
        @navigate-to-path="$emit('navigate-to-path', $event)"
      />
    </div>

    <div class="file-actions">
      <BaseButton
        variant="outline-solid"
        size="sm"
        @click="$emit('new-folder')"
        :aria-label="$t('fileBrowser.header.newFolder')"
      >
        <Icon name="folder" /> {{ $t('fileBrowser.header.newFolder') }}
      </BaseButton>
      <BaseButton
        variant="outline-solid"
        size="sm"
        @click="$emit('upload')"
        :aria-label="$t('fileBrowser.header.uploadFile')"
      >
        <Icon name="upload" /> {{ $t('fileBrowser.header.uploadFile') }}
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import FilePathNavigation from './FilePathNavigation.vue'

interface Props {
  title?: string
  viewMode: 'tree' | 'list'
  currentPath: string
}

interface Emits {
  (e: 'upload'): void
  (e: 'new-folder'): void
  (e: 'navigate-to-path', path: string): void
}

withDefaults(defineProps<Props>(), {
  title: '',
  currentPath: '/'
})

defineEmits<Emits>()
</script>

<style scoped>
@reference "../../assets/tailwind.css";
.file-browser-header {
  @apply flex flex-wrap items-center gap-4 mb-6 pb-4 border-b border-autobot-border;
}

.file-browser-header h2 {
  @apply text-2xl font-bold text-autobot-text-primary flex-shrink-0;
}

.path-navigation-inline {
  @apply flex items-center gap-3 flex-1 min-w-0;
  flex-basis: 66%;
}

.file-actions {
  @apply flex gap-2 shrink-0 ml-auto;
}

/* Button styling handled by BaseButton component */
</style>
