<template>
  <PageHeader class="file-browser-header" :title="title || $t('fileBrowser.header.title')" :level="2">
    <template #actions>
      <BaseButton
        variant="outline"
        size="sm"
        @click="$emit('new-folder')"
        :aria-label="$t('fileBrowser.header.newFolder')"
      >
        <Icon name="folder" /> {{ $t('fileBrowser.header.newFolder') }}
      </BaseButton>
      <BaseButton
        variant="outline"
        size="sm"
        @click="$emit('upload')"
        :aria-label="$t('fileBrowser.header.uploadFile')"
      >
        <Icon name="upload" /> {{ $t('fileBrowser.header.uploadFile') }}
      </BaseButton>
    </template>

    <!-- Path Navigation -->
    <div class="path-navigation-inline">
      <FilePathNavigation
        :current-path="currentPath"
        @navigate-to-path="$emit('navigate-to-path', $event)"
      />
    </div>
  </PageHeader>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { BaseButton, PageHeader } from '@autobot/ui'
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
  @apply mb-6;
}

.path-navigation-inline {
  @apply flex items-center gap-3 flex-1 min-w-0;
}
</style>
