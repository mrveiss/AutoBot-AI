<template>
  <div class="category-tree">
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i> Loading categories...
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
    const loading = ref(true);

    const loadCategories = async () => {
      loading.value = true;
      try {
        const response = await apiClient.get('/api/knowledge_base/categories');
        const data = await response.json();
        
        if (data.success) {
          categories.value = data.categories;
          emit('loaded', data.categories);
        }
      } catch (error) {
        console.error('Failed to load categories:', error);
      } finally {
        loading.value = false;
      }
    };

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

.loading-state,
.empty-state {
  padding: 20px;
  text-align: center;
  color: #6c757d;
  font-size: 14px;
}

.loading-state i,
.empty-state i {
  margin-right: 8px;
}
</style>