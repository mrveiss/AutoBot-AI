<template>
  <div class="inline-flex items-center">
    <span
      :class="{
        'bg-green-400': status === 'active' || status === 'healthy',
        'bg-yellow-400': status === 'pending' || status === 'warning',
        'bg-red-400': status === 'error' || status === 'failed',
        'bg-blue-400': status === 'deploying' || status === 'running',
        'bg-gray-400': !status || status === 'unknown',
        'animate-pulse': status === 'deploying' || status === 'running'
      }"
      :title="getStatusText()"
      class="w-2 h-2 rounded-full mr-2"
    ></span>
    <span
      v-if="showText"
      :class="{
        'text-green-700': status === 'active' || status === 'healthy',
        'text-yellow-700': status === 'pending' || status === 'warning',
        'text-red-700': status === 'error' || status === 'failed',
        'text-blue-700': status === 'deploying' || status === 'running',
        'text-gray-700': !status || status === 'unknown'
      }"
      class="text-sm font-medium"
    >
      {{ getStatusText() }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { defineProps } from 'vue'

const props = defineProps<{
  status?: string
  showText?: boolean
}>()

function getStatusText(): string {
  switch (props.status) {
    case 'active':
    case 'healthy':
      return 'Active'
    case 'pending':
      return 'Pending'
    case 'warning':
      return 'Warning'
    case 'error':
      return 'Error'
    case 'failed':
      return 'Failed'
    case 'deploying':
      return 'Deploying'
    case 'running':
      return 'Running'
    case 'success':
      return 'Success'
    default:
      return 'Unknown'
  }
}
</script>
