<template>
  <div 
    class="service-item flex items-center justify-between p-2 rounded hover:bg-gray-50 cursor-pointer transition-colors"
    :class="getServiceClass()"
    @click="$emit('click', service)"
  >
    <div class="flex items-center space-x-2 flex-1">
      <!-- Service Status Indicator -->
      <div class="flex-shrink-0">
        <div 
          class="w-2 h-2 rounded-full"
          :class="getStatusDotClass()"
          :title="`${service.name} is ${service.status}`"
        ></div>
      </div>
      
      <!-- Service Name -->
      <span class="text-sm font-medium" :class="getServiceTextClass()">
        {{ service.name }}
      </span>
      
      <!-- Error Indicator -->
      <i 
        v-if="service.status === 'error'" 
        class="fas fa-exclamation-circle text-red-500 text-xs"
        :title="service.error || 'Service error'"
      ></i>
      
      <!-- Warning Indicator -->
      <i 
        v-if="service.status === 'warning'" 
        class="fas fa-exclamation-triangle text-yellow-500 text-xs"
        :title="service.error || 'Service warning'"
      ></i>
    </div>
    
    <!-- Response Time -->
    <div class="flex items-center space-x-2">
      <span 
        v-if="service.responseTime" 
        class="text-xs"
        :class="getResponseTimeClass()"
      >
        {{ service.responseTime }}
      </span>
      
      <!-- Status Badge -->
      <span 
        class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium"
        :class="getStatusBadgeClass()"
      >
        {{ getStatusLabel() }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Service {
  name: string
  status: string
  responseTime?: string
  error?: string
  details?: any
}

const props = defineProps<{
  service: Service
  machineName: string
}>()

const emit = defineEmits<{
  click: [service: Service]
}>()

const getServiceClass = () => {
  if (props.service.status === 'error') {
    return 'bg-red-50 border border-red-200'
  }
  if (props.service.status === 'warning') {
    return 'bg-yellow-50 border border-yellow-200'
  }
  return ''
}

const getStatusDotClass = () => {
  switch (props.service.status) {
    case 'online': return 'bg-green-500 animate-pulse'
    case 'warning': return 'bg-yellow-500'
    case 'error': return 'bg-red-500'
    case 'offline': return 'bg-gray-500'
    default: return 'bg-gray-400'
  }
}

const getServiceTextClass = () => {
  switch (props.service.status) {
    case 'error': return 'text-red-700'
    case 'warning': return 'text-yellow-700'
    case 'offline': return 'text-gray-500'
    default: return 'text-gray-700'
  }
}

const getResponseTimeClass = () => {
  if (props.service.responseTime === 'timeout') {
    return 'text-red-600 font-medium'
  }
  
  const time = parseInt(props.service.responseTime || '0')
  if (time > 500) return 'text-red-600'
  if (time > 200) return 'text-yellow-600'
  return 'text-gray-500'
}

const getStatusBadgeClass = () => {
  switch (props.service.status) {
    case 'online': return 'bg-green-100 text-green-700'
    case 'warning': return 'bg-yellow-100 text-yellow-700'
    case 'error': return 'bg-red-100 text-red-700'
    case 'offline': return 'bg-gray-100 text-gray-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

const getStatusLabel = () => {
  switch (props.service.status) {
    case 'online': return 'UP'
    case 'warning': return 'WARN'
    case 'error': return 'ERR'
    case 'offline': return 'DOWN'
    default: return 'UNK'
  }
}
</script>

<style scoped>
.service-item {
  transition: all 0.2s ease;
}

.service-item:hover {
  transform: translateX(2px);
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
</style>