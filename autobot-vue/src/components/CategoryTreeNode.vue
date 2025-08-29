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
.tree-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s ease;
  margin-bottom: 2px;
}

.node-content:hover {
  background-color: #e9ecef;
}

.node-content.selected {
  background-color: #007bff;
  color: white;
}

.node-content.selected:hover {
  background-color: #0056b3;
}

.node-icon {
  width: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-right: 6px;
  font-size: 12px;
  color: #6c757d;
}

.node-content.selected .node-icon {
  color: white;
}

.node-label {
  font-weight: 500;
  font-size: 14px;
}

.node-description {
  font-size: 12px;
  color: #6c757d;
  margin-left: 8px;
  font-style: italic;
}

.node-content.selected .node-description {
  color: rgba(255, 255, 255, 0.8);
}

.children {
  margin-top: 2px;
}

/* Animation for expansion */
.node-icon i {
  transition: transform 0.2s ease;
}

.node-content.has-children:hover .node-icon i {
  transform: scale(1.1);
}
</style>