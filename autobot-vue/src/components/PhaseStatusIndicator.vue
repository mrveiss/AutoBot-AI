<template>
  <div class="phase-status-indicator">
    <!-- Compact header view -->
    <div class="phase-header" @click="toggleExpanded" tabindex="0" @keyup.enter="$event.target.click()" @keyup.space="$event.target.click()">
      <div class="phase-info">
        <span class="phase-name">{{ currentPhase?.name || 'Loading...' }}</span>
        <div class="phase-progress">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: `${(projectStatus?.overall_completion || 0) * 100}%` }"
            ></div>
          </div>
          <span class="progress-text">{{ ((projectStatus?.overall_completion || 0) * 100).toFixed(1) }}%</span>
        </div>
      </div>
      <button class="toggle-btn" :class="{ expanded: isExpanded }" aria-label="Expand">
        <i class="fas fa-chevron-down"></i>
      </button>
    </div>

    <!-- Expanded detailed view -->
    <div v-if="isExpanded" class="phase-details">
      <div class="validation-summary">
        <div class="summary-item">
          <i class="fas fa-tasks"></i>
          <span>{{ projectStatus?.completed_phases || 0 }}/{{ projectStatus?.total_phases || 0 }} Phases Complete</span>
        </div>
        <div class="summary-item">
          <i class="fas fa-clock"></i>
          <span>Last validated: {{ formatDate(lastValidated) }}</span>
        </div>
        <div class="summary-item">
          <i class="fas fa-rocket"></i>
          <span>Next: {{ nextPhase?.name || 'All complete' }}</span>
        </div>
      </div>

      <!-- Current phase capabilities -->
      <div v-if="currentPhaseDetails" class="current-phase">
        <h4>{{ currentPhaseDetails.name }} Progress</h4>
        <div class="capabilities-grid">
          <div
            v-for="capability in currentPhaseCapabilities"
            :key="capability.name"
            class="capability-item"
            :class="getCapabilityStatus(capability)"
          >
            <i :class="getCapabilityIcon(capability)"></i>
            <span class="capability-name">{{ capability.name }}</span>
            <span class="capability-description">{{ capability.description }}</span>
          </div>
        </div>
      </div>

      <!-- All phases overview -->
      <div class="phases-overview">
        <h4>All Phases</h4>
        <div class="phases-grid">
          <div
            v-for="(phase, phaseId) in allPhases"
            :key="phaseId"
            class="phase-card"
            :class="getPhaseStatus(phase)"
          >
            <div class="phase-card-header">
              <i :class="getPhaseIcon(phase)"></i>
              <span class="phase-card-name">{{ phase.name }}</span>
            </div>
            <div class="phase-card-progress">
              <div class="mini-progress-bar">
                <div
                  class="mini-progress-fill"
                  :style="{ width: `${phase.completion * 100}%` }"
                ></div>
              </div>
              <span class="mini-progress-text">{{ (phase.completion * 100).toFixed(0) }}%</span>
            </div>
            <div class="phase-card-capabilities">
              {{ phase.implemented_capabilities }}/{{ phase.capabilities }} ready
            </div>
          </div>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="phase-actions">
        <BaseButton variant="primary" @click="refreshStatus" :disabled="isLoading">
          <i class="fas fa-sync" :class="{ 'fa-spin': isLoading }"></i>
          Refresh Status
        </BaseButton>
        <BaseButton variant="secondary" @click="runValidation" :disabled="isValidating">
          <i class="fas fa-check-circle" :class="{ 'fa-spin': isValidating }"></i>
          Run Validation
        </BaseButton>
        <BaseButton variant="info" @click="showReport">
          <i class="fas fa-file-alt"></i>
          View Report
        </BaseButton>
      </div>
    </div>

    <!-- Validation Report Modal -->
    <BaseModal
      v-model="showReportModal"
      title="Project Validation Report"
      size="large"
      scrollable
    >
      <pre class="validation-report">{{ validationReport }}</pre>
    </BaseModal>
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue';
import { apiService } from '../services/api';
import { formatDateTime } from '@/utils/formatHelpers';
import BaseButton from '@/components/base/BaseButton.vue';
import BaseModal from '@/components/ui/BaseModal.vue';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('PhaseStatusIndicator');

export default {
  name: 'PhaseStatusIndicator',
  components: {
    BaseButton,
    BaseModal
  },
  setup() {
    const isExpanded = ref(false);
    const isLoading = ref(false);
    const isValidating = ref(false);
    const showReportModal = ref(false);
    const projectStatus = ref(null);
    const allPhases = ref({});
    const detailedPhases = ref({}); // Stores detailed phase info with capabilities
    const validationReport = ref('');
    const lastValidated = ref(null);

    const currentPhase = computed(() => {
      if (!projectStatus.value) return null;
      return allPhases.value[projectStatus.value.current_phase];
    });

    const currentPhaseDetails = computed(() => {
      if (!projectStatus.value) return null;
      return allPhases.value[projectStatus.value.current_phase];
    });

    const currentPhaseCapabilities = computed(() => {
      // Fetch real capabilities from detailed phases API
      if (!projectStatus.value) return [];

      const currentPhaseName = projectStatus.value.current_phase;
      const phaseDetails = detailedPhases.value[currentPhaseName];

      if (phaseDetails && Array.isArray(phaseDetails.capabilities)) {
        // Return real capability data from API
        return phaseDetails.capabilities.map(cap => ({
          name: cap.name,
          description: cap.description || `Capability: ${cap.name}`,
          implemented: cap.implemented
        }));
      }

      // Return empty array if no capabilities loaded yet
      return [];
    });

    const nextPhase = computed(() => {
      if (!projectStatus.value?.next_suggested_phase) return null;
      return allPhases.value[projectStatus.value.next_suggested_phase] || null;
    });

    const toggleExpanded = () => {
      isExpanded.value = !isExpanded.value;
    };

    const loadDetailedPhases = async () => {
      // Issue #552: Fixed path - backend uses /api/project-state/project/phases
      try {
        const response = await apiService.get('/api/project-state/project/phases');
        if (response && response.phases) {
          // Store detailed phase info with capabilities
          detailedPhases.value = response.phases;
          logger.debug('Loaded detailed phases with capabilities:', Object.keys(response.phases));
        }
      } catch (error) {
        logger.warn('Failed to load detailed phases:', error.message);
        // Keep detailedPhases empty - computed property will return empty array
        detailedPhases.value = {};
      }
    };

    const refreshStatus = async () => {
      isLoading.value = true;
      try {
        // Issue #552: Fixed path - backend uses /api/project-state/project/status
        const response = await apiService.get('/api/project-state/project/status');
        // API response doesn't have a 'data' wrapper, it's the direct response
        if (response && response.current_phase) {
          projectStatus.value = response;
          allPhases.value = response.phases;
          lastValidated.value = new Date();
          // Load detailed phases with real capability data
          await loadDetailedPhases();
        }
      } catch (error) {
        logger.warn('Project status API not available:', error.message);
        // Clear data when API unavailable - no mock fallback per Issue #450
        projectStatus.value = null;
        allPhases.value = {};
        detailedPhases.value = {};
      } finally {
        isLoading.value = false;
      }
    };

    const runValidation = async () => {
      isValidating.value = true;
      try {
        // Issue #552: Fixed path - backend uses /api/project-state/project/validate
        await apiService.post('/api/project-state/project/validate');
        await refreshStatus(); // Refresh after validation
      } catch (error) {
        logger.error('Failed to run validation:', error);
      } finally {
        isValidating.value = false;
      }
    };

    const showReport = async () => {
      try {
        // Issue #552: Fixed path - backend uses /api/project-state/project/report
        const response = await apiService.get('/api/project-state/project/report');
        if (response.data.success) {
          validationReport.value = response.data.report;
          showReportModal.value = true;
        }
      } catch (error) {
        logger.error('Failed to load validation report:', error);
      }
    };

    const closeReport = () => {
      showReportModal.value = false;
    };

    const formatDate = (date) => {
      if (!date) return 'Never';
      return formatDateTime(date);
    };

    const getPhaseStatus = (phase) => {
      if (phase.is_completed) return 'phase-completed';
      if (phase.is_active) return 'phase-active';
      return 'phase-inactive';
    };

    const getPhaseIcon = (phase) => {
      if (phase.is_completed) return 'fas fa-check-circle';
      if (phase.is_active) return 'fas fa-play-circle';
      return 'fas fa-circle';
    };

    const getCapabilityStatus = (capability) => {
      return capability.implemented ? 'capability-implemented' : 'capability-pending';
    };

    const getCapabilityIcon = (capability) => {
      return capability.implemented ? 'fas fa-check' : 'fas fa-clock';
    };

    onMounted(() => {
      refreshStatus();
    });

    return {
      isExpanded,
      isLoading,
      isValidating,
      showReportModal,
      projectStatus,
      allPhases,
      validationReport,
      lastValidated,
      currentPhase,
      currentPhaseDetails,
      currentPhaseCapabilities,
      nextPhase,
      toggleExpanded,
      refreshStatus,
      runValidation,
      showReport,
      closeReport,
      formatDate,
      getPhaseStatus,
      getPhaseIcon,
      getCapabilityStatus,
      getCapabilityIcon
    };
  }
};
</script>

<style scoped>
.phase-status-indicator {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
  overflow: hidden;
}

.phase-header {
  padding: var(--spacing-3) var(--spacing-4);
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--chart-purple) 100%);
  color: var(--text-on-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  transition: all var(--duration-300) var(--ease-in-out);
}

.phase-header:hover {
  background: linear-gradient(135deg, var(--color-primary-hover) 0%, var(--chart-purple) 100%);
}

.phase-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.phase-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
}

.phase-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.progress-bar {
  width: 200px;
  height: 6px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--chart-green-light);
  transition: width var(--duration-500) var(--ease-in-out);
}

.progress-text {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  min-width: 45px;
}

.toggle-btn {
  background: none;
  border: none;
  color: var(--text-on-primary);
  font-size: var(--text-base);
  cursor: pointer;
  transition: transform var(--duration-300) var(--ease-in-out);
  padding: var(--spacing-1);
}

.toggle-btn.expanded {
  transform: rotate(180deg);
}

.phase-details {
  padding: var(--spacing-4);
  background: var(--bg-card);
}

.validation-summary {
  display: flex;
  gap: var(--spacing-6);
  margin-bottom: var(--spacing-5);
  flex-wrap: wrap;
}

.summary-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.summary-item i {
  color: var(--text-tertiary);
}

.current-phase h4 {
  margin: 0 0 var(--spacing-3) 0;
  color: var(--text-primary);
  font-size: var(--text-base);
}

.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-5);
}

.capability-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
  transition: all var(--duration-200) var(--ease-in-out);
}

.capability-item.capability-implemented {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.capability-item.capability-pending {
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
}

.capability-name {
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
}

.capability-description {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  grid-column: 2 / -1;
  margin-left: var(--spacing-6);
}

.phases-overview h4 {
  margin: var(--spacing-5) 0 var(--spacing-3) 0;
  color: var(--text-primary);
  font-size: var(--text-base);
}

.phases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-5);
}

.phase-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-3);
  transition: all var(--duration-200) var(--ease-in-out);
}

.phase-card.phase-completed {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.phase-card.phase-active {
  background: var(--color-info-bg);
  border-color: var(--color-info-light);
  box-shadow: 0 0 0 1px var(--color-info-light);
}

.phase-card.phase-inactive {
  background: var(--bg-tertiary);
  border-color: var(--border-default);
}

.phase-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-2);
}

.phase-card-header i.fa-check-circle {
  color: var(--color-success);
}

.phase-card-header i.fa-play-circle {
  color: var(--color-info);
}

.phase-card-header i.fa-circle {
  color: var(--text-tertiary);
}

.phase-card-name {
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.phase-card-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-1);
}

.mini-progress-bar {
  flex: 1;
  height: 4px;
  background: var(--border-subtle);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: var(--color-info);
  transition: width var(--duration-500) var(--ease-in-out);
}

.phase-card.phase-completed .mini-progress-fill {
  background: var(--color-success);
}

.mini-progress-text {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  min-width: 30px;
}

.phase-card-capabilities {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.phase-actions {
  display: flex;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.validation-report {
  background: var(--bg-secondary);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
  white-space: pre-wrap;
  margin: 0;
}

@media (max-width: 768px) {
  .validation-summary {
    flex-direction: column;
    gap: var(--spacing-3);
  }

  .capabilities-grid {
    grid-template-columns: 1fr;
  }

  .phases-grid {
    grid-template-columns: 1fr;
  }

  .phase-actions {
    flex-direction: column;
  }

  .btn {
    width: 100%;
    justify-content: center;
  }
}
</style>