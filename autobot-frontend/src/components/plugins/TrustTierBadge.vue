<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<!--
  TrustTierBadge Component
  Issue #9049 - Plugin capability system trust tier badges
-->

<template>
  <span :class="['trust-tier-badge', `trust-tier-${tier}`]" :title="tooltipText">
    {{ displayText }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  tier: 'official' | 'verified' | 'community' | 'unverified'
}

const props = defineProps<Props>()

const displayText = computed(() => {
  const textMap = {
    official: 'Official',
    verified: 'Verified',
    community: 'Community',
    unverified: 'Unverified',
  }
  return textMap[props.tier]
})

const tooltipText = computed(() => {
  const tooltipMap = {
    official: 'Built by AutoBot core team — capabilities auto-granted',
    verified: 'Reviewed and approved by AutoBot team — requires operator approval',
    community: 'Community-submitted plugin — requires operator approval',
    unverified: 'Newly uploaded, not yet reviewed — requires operator approval',
  }
  return tooltipMap[props.tier]
})
</script>

<style scoped>
.trust-tier-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  cursor: help;
}

.trust-tier-official {
  background-color: #10b981;
  color: #fff;
}

.trust-tier-verified {
  background-color: #3b82f6;
  color: #fff;
}

.trust-tier-community {
  background-color: #f59e0b;
  color: #fff;
}

.trust-tier-unverified {
  background-color: #ef4444;
  color: #fff;
}
</style>
