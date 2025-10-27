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
    <div v-else-if="Object.keys(categories).length === 0" class="empty-state">
      <i class="fas fa-folder-open"></i> No categories available
    </div>
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
import apiClient from '../utils/ApiClient.js';
import { useAsyncHandler } from '@/composables/useErrorHandler';

export default {
  name: 'CategoryTree',
  components: {
    CategoryTreeNode
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
        const response = await apiClient.get('/api/knowledge_base/categories');
        // Handle both Response object and already-parsed JSON
        const data = typeof response.json === 'function' ? await response.json() : response;
        return data;
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
.category-tree {
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 8px;
  background-color: #f8f9fa;
  max-height: 400px;
  overflow-y: auto;
}

/* Scrollbar styling */
.category-tree::-webkit-scrollbar {
  width: 8px;
}

.category-tree::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.category-tree::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 4px;
}

.category-tree::-webkit-scrollbar-thumb:hover {
  background: #555;
}

.loading-state {
  padding: 12px;
}

.skeleton-tree {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-item {
  display: flex;
  align-items: center;
  gap: 8px;
  animation: pulse 1.5s ease-in-out infinite;
}

.skeleton-icon {
  width: 20px;
  height: 20px;
  background: #e0e0e0;
  border-radius: 4px;
  flex-shrink: 0;
}

.skeleton-text {
  height: 16px;
  background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
  background-size: 200% 100%;
  border-radius: 4px;
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

.empty-state {
  padding: 20px;
  text-align: center;
  color: #6c757d;
  font-size: 14px;
}

.empty-state i {
  margin-right: 8px;
}
</style>
