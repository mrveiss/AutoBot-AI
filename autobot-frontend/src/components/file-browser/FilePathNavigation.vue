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
      <input
        v-model="pathInput"
        @keyup.enter="$emit('navigate-to-path', pathInput)"
        :placeholder="$t('fileBrowser.pathNavigation.pathPlaceholder')"
        class="path-field"
      />
      <button @click="$emit('navigate-to-path', pathInput)" class="path-go-btn">
        <Icon name="arrow-right" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Breadcrumb, type BreadcrumbItem } from '@autobot/ui'

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
@reference "../../assets/tailwind.css";
.path-navigation {
  @apply flex flex-wrap items-center gap-4 flex-1 min-w-0;
}

.breadcrumb {
  @apply flex-1 min-w-0;
}

.path-input {
  @apply flex gap-2 flex-shrink-0;
}

.path-field {
  @apply flex-1 px-3 py-2 border border-autobot-border rounded-md focus:outline-none focus:ring-2;
  --tw-ring-color: var(--color-primary);
}

.path-go-btn {
  @apply px-4 py-2 rounded-md focus:outline-none focus:ring-2;
  background: var(--color-primary);
  color: var(--text-inverse);
  --tw-ring-color: var(--color-primary);
}

.path-go-btn:hover {
  filter: brightness(1.1);
}
</style>
