<template>
  <div class="tree-node">
    <div 
      class="node-content"
      :class="{ 
        'selected': isSelected,
        'has-children': hasChildren 
      }"
      @click="handleClick"
      :style="{ paddingLeft: `${level * 20 + 8}px` }"
    >
      <span class="node-icon" v-if="hasChildren">
        <i :class="isExpanded ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
      </span>
      <span class="node-icon" v-else>
        <i class="fas fa-file"></i>
      </span>
      
      <span class="node-label">{{ node.label || nodeKey }}</span>
      
      <span class="node-description" v-if="node.description">
        ({{ node.description }})
      </span>
    </div>
    
    <div v-if="isExpanded && hasChildren" class="children">
      <CategoryTreeNode
        v-for="(childNode, childKey) in node.children"
        :key="childKey"
        :node="childNode"
        :nodeKey="childKey"
        :level="level + 1"
        :parentPath="currentPath"
        :selectedCategory="selectedCategory"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script>
import { ref, computed } from 'vue';

export default {
  name: 'CategoryTreeNode',
  props: {
    node: {
      type: Object,
      required: true
    },
    nodeKey: {
      type: String,
      required: true
    },
    level: {
      type: Number,
      default: 0
    },
    parentPath: {
      type: String,
      default: ''
    },
    selectedCategory: {
      type: String,
      default: ''
    }
  },
  emits: ['select'],
  setup(props, { emit }) {
    const isExpanded = ref(props.level === 0); // Expand first level by default
    
    const hasChildren = computed(() => {
      return props.node.children && Object.keys(props.node.children).length > 0;
    });
    
    const currentPath = computed(() => {
      return props.parentPath ? `${props.parentPath}/${props.nodeKey}` : props.nodeKey;
    });
    
    const isSelected = computed(() => {
      return props.selectedCategory === currentPath.value;
    });
    
    const handleClick = () => {
      if (hasChildren.value) {
        isExpanded.value = !isExpanded.value;
      }
      emit('select', currentPath.value);
    };
    
    return {
      isExpanded,
      hasChildren,
      currentPath,
      isSelected,
      handleClick
    };
  }
};
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.tree-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  padding: var(--spacing-1-5) var(--spacing-2);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--duration-200) var(--ease-in-out);
  margin-bottom: var(--spacing-0-5);
}

.node-content:hover {
  background-color: var(--bg-hover);
}

.node-content.selected {
  background-color: var(--color-primary);
  color: var(--text-on-primary);
}

.node-content.selected:hover {
  background-color: var(--color-primary-hover);
}

.node-icon {
  width: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-right: var(--spacing-1-5);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.node-content.selected .node-icon {
  color: var(--text-on-primary);
}

.node-label {
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
}

.node-description {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-left: var(--spacing-2);
  font-style: italic;
}

.node-content.selected .node-description {
  color: var(--text-on-primary-muted);
}

.children {
  margin-top: var(--spacing-0-5);
}

/* Animation for expansion */
.node-icon i {
  transition: transform var(--duration-200) var(--ease-in-out);
}

.node-content.has-children:hover .node-icon i {
  transform: scale(1.1);
}
</style>