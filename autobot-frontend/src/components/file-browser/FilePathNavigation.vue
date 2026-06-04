<template>
  <div class="path-navigation">
    <!-- Breadcrumb Navigation -->
    <div class="breadcrumb">
      <button @click="$emit('navigate-to-path', '/')" class="breadcrumb-item" type="button">
        <Icon name="home" /> {{ $t('fileBrowser.pathNavigation.home') }}
      </button>
      <span v-for="(part, index) in pathParts" :key="index" class="breadcrumb-item">
        <Icon name="chevron-right" class="breadcrumb-separator" />
        <button @click="$emit('navigate-to-path', getPathUpTo(index))" class="clickable" type="button">
          {{ part }}
        </button>
      </span>
    </div>

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

interface Props {
  currentPath: string
}

interface Emits {
  (e: 'navigate-to-path', path: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

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

// Methods
const getPathUpTo = (index: number): string => {
  const parts = pathParts.value.slice(0, index + 1)
  return '/' + parts.join('/')
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";
.path-navigation {
  @apply flex flex-wrap items-center gap-4 flex-1 min-w-0;
}

.breadcrumb {
  @apply flex items-center flex-wrap gap-1 flex-1 min-w-0;
}

.breadcrumb-item {
  @apply flex items-center text-sm bg-none border-none cursor-pointer hover:underline p-0;
  color: var(--text-link);
  font: inherit;
}

.breadcrumb-item:hover {
  color: var(--text-link-hover);
}

.breadcrumb-item .clickable {
  @apply cursor-pointer hover:underline bg-none border-none p-0;
  color: var(--text-link);
  font: inherit;
}

.breadcrumb-item .clickable:hover {
  color: var(--text-link-hover);
}

.breadcrumb-separator {
  @apply text-autobot-text-muted mx-1;
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
