<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  Vision Automation Page

  Self-sufficient wrapper that fetches automation opportunities
  and renders GUIAutomationControls. Issue #777.
-->
<template>
  <GUIAutomationControls
    :opportunities="opportunities"
    :loading="loading"
    @refresh="loadOpportunities"
  />
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { createLogger } from '@/utils/debugUtils';
import GUIAutomationControls from './GUIAutomationControls.vue';
import {
  visionMultimodalApiClient,
  type AutomationOpportunity,
} from '@/utils/VisionMultimodalApiClient';

const logger = createLogger('VisionAutomationPage');

const opportunities = ref<AutomationOpportunity[]>([]);
const loading = ref(false);

const loadOpportunities = async () => {
  loading.value = true;
  try {
    const res = await visionMultimodalApiClient.getAutomationOpportunities();
    if (res.success && res.data) {
      opportunities.value = res.data.opportunities;
    } else {
      logger.warn('Failed to load opportunities:', res.error);
    }
  } catch (err) {
    logger.error('Error loading automation opportunities:', err);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  loadOpportunities();
});
</script>
