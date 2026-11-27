<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="path-navigation">
    <!-- Breadcrumb Navigation: the kit trail (#17563); the last part is the current folder -->
    <Breadcrumb
      class="breadcrumb"
      :items="crumbs"
      :label="$t('common.breadcrumb')"
      @select="$emit('navigate-to-path', pathForCrumb($event))"
    >
      <template #item="{ item, index }">
        <Icon v-if="index === 0" name="home" /> {{ item.label }}
      </template>
      <template #separator><Icon name="chevron-right" /></template>
    </Breadcrumb>

    <!-- Path Input -->
    <div class="path-input">
      <BaseInput
        v-model="pathInput"
        size="sm"
        class="path-field"
        :aria-label="$t('fileBrowser.pathNavigation.pathLabel')"
        :placeholder="$t('fileBrowser.pathNavigation.pathPlaceholder')"
        data-testid="path-input"
        @keyup.enter="$emit('navigate-to-path', pathInput)"
      />
      <BaseButton
        variant="primary"
        size="sm"
        :aria-label="$t('fileBrowser.header.goToPath')"
        data-testid="path-go"
        @click="$emit('navigate-to-path', pathInput)"
      >
        <Icon name="arrow-right" />
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseInput, Breadcrumb, type BreadcrumbItem } from '@autobot/ui'

interface Props {
  currentPath: string
}

interface Emits {
  (e: 'navigate-to-path', path: string): void
}

const props = defineProps<Props>()
defineEmits<Emits>()
const { t } = useI18n()

// Local state for path input
const pathInput = ref(props.currentPath)

// Watch for external path changes
watch(() => props.currentPath, (newPath) => {
  pathInput.value = newPath
})

// Computed properties
const pathParts = computed(() => {
  return props.currentPath.split('/').filter(part => part)
})

// Home, then one crumb per path part; every crumb but the current folder navigates
const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('fileBrowser.pathNavigation.home'), selectable: true },
  ...pathParts.value.map((part) => ({ label: part, selectable: true })),
])

// Crumb 0 is home; crumb n is the path through part n
const pathForCrumb = (index: number): string => '/' + pathParts.value.slice(0, index).join('/')
</script>

<style scoped>
.path-navigation {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--aui-space-4);
  min-width: 0;
}
.breadcrumb {
  flex: 1;
  min-width: 0;
}
.path-input {
  display: flex;
  flex-shrink: 0;
  gap: var(--aui-space-2);
}
</style>
