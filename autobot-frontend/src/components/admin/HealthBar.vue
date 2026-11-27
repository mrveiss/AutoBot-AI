<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="health-bar-wrapper" :title="`${label}: ${value.toFixed(1)}%`">
    <span class="hb-label">{{ label }}</span>
    <div class="hb-track" role="progressbar" :aria-valuenow="value" aria-valuemin="0" aria-valuemax="100">
      <div class="hb-fill" :class="fillClass" :style="{ width: `${Math.min(value, 100)}%` }"></div>
    </div>
    <span class="hb-value">{{ value.toFixed(0) }}%</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ label: string; value: number }>()

const fillClass = computed(() => {
  if (props.value >= 90) return 'fill-critical'
  if (props.value >= 70) return 'fill-warning'
  return 'fill-ok'
})
</script>

<style scoped>
.health-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex: 1;
  min-width: 0;
}

.hb-label {
  font-size: 0.68rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.4));
  flex-shrink: 0;
  width: 2rem;
  text-transform: uppercase;
}

.hb-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  overflow: hidden;
}

.hb-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.fill-ok { background: #22c55e; }
.fill-warning { background: #f59e0b; }
.fill-critical { background: #ef4444; }

.hb-value {
  font-size: 0.68rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.4));
  flex-shrink: 0;
  width: 2.5rem;
  text-align: right;
}
</style>
