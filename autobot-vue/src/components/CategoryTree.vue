<template>
  <div class="category-tree">
    <!-- Skeleton loader while loading -->
    <div v-if="loading" class="loading-state">
      <div class="skeleton-tree">
        <div v-for="i in 5" :key="i" class="skeleton-item">
          <div class="skeleton-icon"></div>
          <div class="skeleton-text" :style="{ width: `${60 + (i * 10)}%` }"></div>
        </div>
      </div>
    </div>
    <EmptyState
      v-else-if="Object.keys(categories).length === 0"
      icon="fas fa-folder-open"
      message="No categories available"
    />
    <template v-else>
      <CategoryTreeNode
        v-for="(node, key) in categories"
        :key="key"
        :node="node"
        :nodeKey="key"
        :level="0"
        :selectedCategory="selectedCategory"
        @select="handleSelect"
      />
    </template>
  </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue';
import CategoryTreeNode from './CategoryTreeNode.vue';
import EmptyState from '@/components/ui/EmptyState.vue';
import apiClient from '../utils/ApiClient.js';
import { useAsyncHandler } from '@/composables/useErrorHandler';

export default {
  name: 'CategoryTree',
  components: {
    CategoryTreeNode,
    EmptyState
  },
  props: {
    modelValue: {
      type: String,
      default: ''
    },
    filterCategory: {
      type: String,
      default: null
    }
  },
  emits: ['update:modelValue', 'loaded'],
  setup(props, { emit }) {
    const categories = ref({});
    const selectedCategory = ref(props.modelValue);

    const { execute: loadCategories, loading } = useAsyncHandler(
      async () => {
        // ApiClient.get() returns parsed JSON directly
        return await apiClient.get('/api/knowledge_base/categories');
      },
      {
        onSuccess: (data) => {
          if (data.success || data.categories) {
            categories.value = data.categories || [];
            emit('loaded', data.categories || []);
          }
        },
        logErrors: true,
        errorPrefix: '[CategoryTree]'
      }
    );

    const handleSelect = (categoryPath) => {
      selectedCategory.value = categoryPath;
      emit('update:modelValue', categoryPath);
    };

    // Watch for changes to modelValue prop
    watch(() => props.modelValue, (newValue) => {
      selectedCategory.value = newValue;
    });

    onMounted(() => {
      loadCategories();
    });

    return {
      categories,
      selectedCategory,
      handleSelect,
      loading
    };
  }
};
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.category-tree {
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-2);
  background-color: var(--bg-secondary);
  max-height: 400px;
  overflow-y: auto;
}

/* Scrollbar styling */
.category-tree::-webkit-scrollbar {
  width: 8px;
}

.category-tree::-webkit-scrollbar-track {
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.category-tree::-webkit-scrollbar-thumb {
  background: var(--text-tertiary);
  border-radius: var(--radius-sm);
}

.category-tree::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}

.loading-state {
  padding: var(--spacing-3);
}

.skeleton-tree {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.skeleton-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-icon {
  width: 20px;
  height: 20px;
  background: var(--border-default);
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.skeleton-text {
  height: 16px;
  background: linear-gradient(90deg, var(--border-default) 25%, var(--bg-tertiary) 50%, var(--border-default) 75%);
  background-size: 200% 100%;
  border-radius: var(--radius-sm);
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
