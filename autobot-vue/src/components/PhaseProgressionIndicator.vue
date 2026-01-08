<template>
  <div class="phase-progression-container">
    <!-- Main Phase Status Header -->
    <div class="phase-header">
      <h2 class="phase-title">
        <i class="fas fa-rocket"></i>
        System Phase Status (On-Demand)
      </h2>
      <div class="header-controls">
        <BaseButton
          variant="outline"
          @click="loadPhaseData"
          :disabled="loading"
          class="load-validation-btn"
        >
          <i class="fas fa-play" v-if="!loading"></i>
          <i class="fas fa-spinner fa-spin" v-else></i>
          {{ loading ? 'Loading...' : 'Load Validation Data' }}
        </BaseButton>
        <div class="overall-maturity" v-if="phases.length > 0">
          <span class="maturity-label">System Maturity:</span>
          <div class="maturity-bar">
            <div
              class="maturity-fill"
              :style="{ width: `${systemMaturity}%` }"
              :class="getMaturityClass(systemMaturity)"
            ></div>
          </div>
          <span class="maturity-percentage">{{ systemMaturity }}%</span>
        </div>
      </div>
    </div>

    <!-- Error State -->
    <div v-if="hasLoadError && !loading" class="error-notice">
      <div class="error-content">
        <i class="fas fa-exclamation-triangle"></i>
        <h3>Phase validation temporarily unavailable</h3>
        <p>The validation system is currently not accessible, but the application continues to work normally.</p>
        <BaseButton
          variant="warning"
          @click="retryLoad"
          class="retry-button"
        >
          <i class="fas fa-redo"></i>
          Retry
        </BaseButton>
      </div>
    </div>

    <!-- No Data State -->
    <EmptyState
      v-if="phases.length === 0 && !loading && !hasLoadError"
      icon="fas fa-info-circle"
      title="Phase Validation Ready"
      message="Click 'Load Validation Data' above to run on-demand system validation and see detailed phase requirements."
    >
      <p class="performance-note">Validation is now on-demand to improve system performance</p>
    </EmptyState>

    <!-- Phase Grid -->
    <div v-if="!hasLoadError && phases.length > 0" class="phases-grid">
      <div
        v-for="phase in phases"
        :key="phase.name"
        class="phase-card"
        :class="getPhaseCardClass(phase)"
      >
        <!-- Phase Header -->
        <div class="phase-card-header">
          <div class="phase-icon">
            <i :class="getPhaseIcon(phase)"></i>
          </div>
          <div class="phase-info">
            <h3 class="phase-name">{{ phase.name }}</h3>
            <span class="phase-status" :class="getStatusClass(phase.status)">
              {{ formatStatus(phase.status) }}
            </span>
          </div>
          <div class="phase-completion">
            {{ phase.completion_percentage }}%
          </div>
        </div>

        <!-- Progress Bar -->
        <div class="progress-container">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: `${phase.completion_percentage}%` }"
              :class="getProgressClass(phase.completion_percentage)"
            ></div>
          </div>
        </div>

        <!-- Phase Details -->
        <div class="phase-details" v-if="showDetails">
          <!-- Phase Description -->
          <div v-if="phase.description" class="phase-description">
            <h4><i class="fas fa-info-circle"></i> Phase Description:</h4>
            <p>{{ phase.description }}</p>
          </div>

          <!-- Acceptance Criteria -->
          <div v-if="phase.acceptance_criteria" class="criteria-section">
            <h4><i class="fas fa-check-square"></i> Acceptance Criteria:</h4>
            <ul class="criteria-list">
              <li v-for="criteria in phase.acceptance_criteria" :key="criteria" class="acceptance-criteria-item">
                <i class="fas fa-chevron-right icon-info"></i>
                {{ criteria }}
              </li>
            </ul>
          </div>

          <!-- Functional Requirements -->
          <div v-if="phase.functional_requirements" class="criteria-section">
            <h4><i class="fas fa-cog"></i> Functional Requirements:</h4>
            <ul class="criteria-list">
              <li v-for="requirement in phase.functional_requirements" :key="requirement" class="functional-req-item">
                <i class="fas fa-chevron-right icon-purple"></i>
                {{ requirement }}
              </li>
            </ul>
          </div>

          <div class="validation-criteria" v-if="phase.validation_details">
            <h4><i class="fas fa-clipboard-check"></i> Validation Results:</h4>

            <!-- Files Check -->
            <div v-if="phase.validation_details.files_check" class="criteria-section">
              <h4><i class="fas fa-file-code"></i> Required Files:</h4>
              <ul class="criteria-list">
                <li v-for="file in phase.validation_details.files_check.details" :key="file.file"
                    :class="file.exists ? 'criteria-pass' : 'criteria-fail'">
                  <i :class="file.exists ? 'fas fa-check icon-success' : 'fas fa-times icon-error'"></i>
                  {{ file.file }}
                </li>
              </ul>
            </div>

            <!-- Directories Check -->
            <div v-if="phase.validation_details.directories_check" class="criteria-section">
              <h4><i class="fas fa-folder"></i> Required Directories:</h4>
              <ul class="criteria-list">
                <li v-for="dir in phase.validation_details.directories_check.details" :key="dir.directory"
                    :class="dir.exists ? 'criteria-pass' : 'criteria-fail'">
                  <i :class="dir.exists ? 'fas fa-check icon-success' : 'fas fa-times icon-error'"></i>
                  {{ dir.directory }}
                </li>
              </ul>
            </div>

            <!-- Endpoints Check -->
            <div v-if="phase.validation_details.endpoints_check" class="criteria-section">
              <h4><i class="fas fa-plug"></i> API Endpoints:</h4>
              <ul class="criteria-list">
                <li v-for="endpoint in phase.validation_details.endpoints_check.details" :key="endpoint.endpoint"
                    :class="endpoint.accessible ? 'criteria-pass' : 'criteria-fail'">
                  <i :class="endpoint.accessible ? 'fas fa-check icon-success' : 'fas fa-times icon-error'"></i>
                  {{ endpoint.endpoint }}
                  <span v-if="endpoint.response_time" class="response-time">({{ endpoint.response_time }}ms)</span>
                </li>
              </ul>
            </div>

            <!-- Services Check -->
            <div v-if="phase.validation_details.services_check" class="criteria-section">
              <h4><i class="fas fa-server"></i> Required Services:</h4>
              <ul class="criteria-list">
                <li v-for="service in phase.validation_details.services_check.details" :key="service.service"
                    :class="service.running ? 'criteria-pass' : 'criteria-fail'">
                  <i :class="service.running ? 'fas fa-check icon-success' : 'fas fa-times icon-error'"></i>
                  {{ service.service }}
                  <span class="service-status">({{ service.status }})</span>
                </li>
              </ul>
            </div>

            <!-- Performance Metrics -->
            <div v-if="phase.validation_details.performance_check" class="criteria-section">
              <h4><i class="fas fa-tachometer-alt"></i> Performance Metrics:</h4>
              <ul class="criteria-list">
                <li v-for="(metric, key) in phase.validation_details.performance_check.details" :key="key"
                    :class="metric.passed ? 'criteria-pass' : 'criteria-fail'">
                  <i :class="metric.passed ? 'fas fa-check icon-success' : 'fas fa-times icon-error'"></i>
                  {{ key }}: {{ metric.current }}{{ metric.unit }}
                  <span class="metric-threshold">({{ metric.passed ? 'passed' : 'failed' }} threshold: {{ metric.threshold }}{{ metric.unit }})</span>
                </li>
              </ul>
            </div>

            <!-- Security Features -->
            <div v-if="phase.validation_details.security_check" class="criteria-section">
              <h4><i class="fas fa-shield-alt"></i> Security Features:</h4>
              <ul class="criteria-list">
                <li v-for="feature in phase.validation_details.security_check.details" :key="feature.feature"
                    :class="feature.enabled ? 'criteria-pass' : 'criteria-fail'">
                  <i :class="feature.enabled ? 'fas fa-check icon-success' : 'fas fa-times icon-error'"></i>
                  {{ feature.feature }}
                </li>
              </ul>
            </div>

            <!-- UI Features -->
            <div v-if="phase.validation_details.ui_check" class="criteria-section">
              <h4><i class="fas fa-desktop"></i> UI Features:</h4>
              <ul class="criteria-list">
                <li v-for="feature in phase.validation_details.ui_check.details" :key="feature.feature"
                    :class="feature.available ? 'criteria-pass' : 'criteria-fail'">
                  <i :class="feature.available ? 'fas fa-check icon-success' : 'fas fa-times icon-error'"></i>
                  {{ feature.feature }}
                </li>
              </ul>
            </div>
          </div>

          <!-- Capabilities (if available) -->
          <div class="capabilities" v-if="phase.capabilities_unlocked?.length">
            <strong>Capabilities:</strong>
            <div class="capability-tags">
              <span
                v-for="capability in phase.capabilities_unlocked"
                :key="capability"
                class="capability-tag"
              >
                {{ capability }}
              </span>
            </div>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="phase-actions" v-if="canManagePhases">
          <BaseButton
            v-if="canTriggerProgression(phase)"
            variant="primary"
            size="sm"
            @click="triggerProgression(phase.name)"
            :disabled="progressionInProgress"
            class="btn-progression"
          >
            <i class="fas fa-play"></i>
            Progress
          </BaseButton>

          <BaseButton
            variant="success"
            size="sm"
            @click="validatePhase(phase.name)"
            :disabled="validationInProgress"
            class="btn-validate"
          >
            <i class="fas fa-check-circle"></i>
            Validate
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- Progression History -->
    <div class="progression-history" v-if="progressionHistory?.length">
      <h3>
        <i class="fas fa-history"></i>
        Recent Progressions
      </h3>
      <div class="history-timeline">
        <div
          v-for="item in progressionHistory.slice(-5)"
          :key="item.timestamp"
          class="history-item"
        >
          <div class="history-icon">
            <i class="fas fa-arrow-right icon-info"></i>
          </div>
          <div class="history-content">
            <strong>{{ item.phase }}</strong>
            <span class="history-status" :class="getStatusClass(item.status)">
              {{ formatStatus(item.status) }}
            </span>
            <div class="history-time">
              {{ formatTime(item.timestamp) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Auto-Progression Controls -->
    <div class="auto-progression-controls">
      <div class="control-header">
        <h3>
          <i class="fas fa-cog"></i>
          Auto-Progression Settings
        </h3>
      </div>

      <div class="controls-grid">
        <div class="control-item">
          <label class="switch">
            <input
              type="checkbox"
              v-model="autoProgressionEnabled"
              @change="updateAutoProgression"
            >
            <span class="slider"></span>
          </label>
          <span class="control-label">Auto-Progression Enabled</span>
        </div>

        <BaseButton
          variant="primary"
          @click="runFullValidation"
          :disabled="validationInProgress"
          class="btn-full-validation"
        >
          <i class="fas fa-play-circle"></i>
          Run Full System Validation
        </BaseButton>

        <BaseButton
          variant="success"
          @click="triggerAutoProgression"
          :disabled="progressionInProgress || !autoProgressionEnabled"
          class="btn-auto-progression"
        >
          <i class="fas fa-forward"></i>
          Trigger Auto-Progression
        </BaseButton>
      </div>
    </div>

    <!-- Loading Overlays -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner">
        <i class="fas fa-spinner fa-spin"></i>
        <span>{{ loadingMessage }}</span>
      </div>
    </div>
  </div>
</template>

<script>
import { apiRequest } from '@/config/api.js';
import EmptyState from '@/components/ui/EmptyState.vue';
import BaseButton from '@/components/base/BaseButton.vue';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('PhaseProgressionIndicator');

export default {
  name: 'PhaseProgressionIndicator',
  components: {
    EmptyState,
    BaseButton
  },

  data() {
    return {
      phases: [],
      systemMaturity: 0,
      progressionHistory: [],
      autoProgressionEnabled: true,
      loading: false,
      loadingMessage: '',
      validationInProgress: false,
      progressionInProgress: false,
      showDetails: true,
      canManagePhases: true,
      refreshInterval: null,
      hasLoadError: false
    }
  },

  mounted() {
    // Only load data on explicit user request - no automatic loading
    // this.loadPhaseData();  // Commented out - load only on demand
  },

  beforeUnmount() {
    // No auto-refresh to stop
    // this.stopAutoRefresh();  // Commented out
  },

  methods: {
    async loadPhaseData() {
      this.loading = true;
      this.loadingMessage = 'Loading phase data...';

      try {
        // Load phase status
        const phasesData = await apiRequest('/api/phases/status');
        this.phases = phasesData.phases || [];
        this.systemMaturity = phasesData.system_maturity || 0;
        this.autoProgressionEnabled = phasesData.auto_progression_enabled || false;

        // Try to get validation data for better phase info
        try {
          const validationData = await apiRequest('/api/validation-dashboard/report');
          if (validationData.status === 'success' && validationData.report) {
            this.systemMaturity = validationData.report.system_overview.overall_maturity;
            // Map validation data to phase format
            this.phases = validationData.report.phase_details.map(phase => ({
              name: phase.display_name,
              completion_percentage: phase.completion_percentage,
              status: phase.completion_percentage >= 95 ? 'complete' :
                     phase.completion_percentage >= 75 ? 'mostly_complete' :
                     phase.completion_percentage >= 50 ? 'in_progress' : 'incomplete',
              auto_progression: true,
              capabilities_unlocked: [],
              prerequisites: [],
              next_phases: []
            }));
          }
        } catch (error) {
          // Could not load validation data, using phase status data
        }

        // Calculate overall system maturity
        if (this.phases.length > 0) {
          const totalCompletion = this.phases.reduce((sum, phase) => sum + phase.completion_percentage, 0);
          this.systemMaturity = Math.round(totalCompletion / this.phases.length);
        }

      } catch (error) {
        // Silently handle validation service unavailability
        this.phases = [];
        this.systemMaturity = 0;
        this.autoProgressionEnabled = false;
        this.hasLoadError = true;

        // Only log in development mode
        if (import.meta.env.DEV) {
          logger.debug('Validation service unavailable:', error.message);
        }
      } finally{
        this.loading = false;
      }
    },

    async runFullValidation() {
      this.validationInProgress = true;
      this.loading = true;
      this.loadingMessage = 'Running comprehensive system validation...';

      try {
        const result = await apiRequest('/api/phases/validation/full');
        this.$emit('validation-complete', result);

        // Refresh phase data
        await this.loadPhaseData();

        this.$emit('success', 'System validation completed successfully');
      } catch (error) {
        logger.error('Validation failed:', error);
        this.$emit('error', 'System validation failed');
      } finally {
        this.validationInProgress = false;
        this.loading = false;
      }
    },

    async triggerAutoProgression() {
      this.progressionInProgress = true;
      this.loading = true;
      this.loadingMessage = 'Executing automated progression...';

      try {
        await apiRequest('/api/phases/progression/auto', {
          method: 'POST'
        });

        this.$emit('success', 'Auto-progression started successfully');

        // Wait a bit for progression to complete, then refresh
        setTimeout(async () => {
          await this.loadPhaseData();
        }, 3000);
      } catch (error) {
        logger.error('Auto-progression failed:', error);
        this.$emit('error', 'Auto-progression failed');
      } finally {
        this.progressionInProgress = false;
        this.loading = false;
      }
    },

    async triggerProgression(phaseName) {
      this.progressionInProgress = true;
      this.loading = true;
      this.loadingMessage = `Progressing to ${phaseName}...`;

      try {
        await apiRequest('/api/phases/progression/manual', {
          method: 'POST',
          body: JSON.stringify({
            phase_name: phaseName,
            user_id: 'web_ui',
            trigger: 'user_request'
          })
        });

        this.$emit('success', `Successfully progressed to ${phaseName}`);
        await this.loadPhaseData();
      } catch (error) {
        logger.error('Manual progression failed:', error);
        this.$emit('error', `Failed to progress to ${phaseName}: ${error.message}`);
      } finally {
        this.progressionInProgress = false;
        this.loading = false;
      }
    },

    async validatePhase(phaseName) {
      this.validationInProgress = true;
      this.loadingMessage = `Validating ${phaseName}...`;

      try {
        const result = await apiRequest('/api/phases/validation/run', {
          method: 'POST',
          body: JSON.stringify({
            phases: [phaseName],
            include_details: true
          })
        });

        this.$emit('phase-validated', { phase: phaseName, result });
        await this.loadPhaseData();
      } catch (error) {
        logger.error('Phase validation failed:', error);
        this.$emit('error', `Validation failed for ${phaseName}`);
      } finally {
        this.validationInProgress = false;
      }
    },

    async updateAutoProgression() {
      try {
        await apiRequest('/api/phases/config/update', {
          method: 'POST',
          body: JSON.stringify({
            auto_progression_enabled: this.autoProgressionEnabled
          })
        });

        this.$emit('success', `Auto-progression ${this.autoProgressionEnabled ? 'enabled' : 'disabled'}`);
      } catch (error) {
        logger.error('Failed to update auto-progression setting:', error);
        // Revert the toggle
        this.autoProgressionEnabled = !this.autoProgressionEnabled;
      }
    },

    async retryLoad() {
      this.hasLoadError = false;
      await this.loadPhaseData();
    },

    // Auto-refresh disabled - validation is now on-demand only
    // startAutoRefresh() {
    //   this.refreshInterval = setInterval(() => {
    //     this.loadPhaseData();
    //   }, 30000); // Refresh every 30 seconds
    // },

    // stopAutoRefresh() {
    //   if (this.refreshInterval) {
    //     clearInterval(this.refreshInterval);
    //   }
    // },

    // Helper methods
    getPhaseCardClass(phase) {
      return [
        'phase-card-status',
        phase.status === 'complete' ? 'phase-complete' :
        phase.status === 'mostly_complete' ? 'phase-mostly-complete' :
        phase.status === 'in_progress' ? 'phase-in-progress' : 'phase-incomplete'
      ];
    },

    getPhaseIcon(phase) {
      const icons = {
        'Phase 1: Core Infrastructure': 'fas fa-server',
        'Phase 2: Knowledge Base and Memory': 'fas fa-database',
        'Phase 3: LLM Integration': 'fas fa-brain',
        'Phase 4: Security and Authentication': 'fas fa-shield-alt',
        'Phase 5: Performance Optimization': 'fas fa-tachometer-alt',
        'Phase 6: Monitoring and Alerting': 'fas fa-chart-line',
        'Phase 7: Frontend and UI': 'fas fa-desktop',
        'Phase 8: Agent Orchestration': 'fas fa-sitemap',
        'Advanced AI Features': 'fas fa-robot',
        'Phase 10: Production Readiness': 'fas fa-cloud'
      };

      return icons[phase.name] || 'fas fa-cog';
    },

    getStatusClass(status) {
      const classes = {
        'complete': 'status-complete',
        'mostly_complete': 'status-mostly-complete',
        'in_progress': 'status-in-progress',
        'incomplete': 'status-incomplete',
        'promoted': 'status-complete',
        'eligible': 'status-in-progress',
        'blocked': 'status-incomplete'
      };

      return classes[status] || 'status-unknown';
    },

    getProgressClass(percentage) {
      if (percentage >= 95) return 'progress-complete';
      if (percentage >= 75) return 'progress-mostly-complete';
      if (percentage >= 50) return 'progress-in-progress';
      return 'progress-incomplete';
    },

    getMaturityClass(maturity) {
      if (maturity >= 95) return 'maturity-production';
      if (maturity >= 80) return 'maturity-beta';
      if (maturity >= 50) return 'maturity-alpha';
      return 'maturity-development';
    },

    formatStatus(status) {
      return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    },

    formatTime(timestamp) {
      return new Date(timestamp).toLocaleString();
    },

    canTriggerProgression(phase) {
      return phase.completion_percentage < 95 && phase.auto_progression;
    },

    isPrerequisiteMet(prerequisite) {
      const prereqPhase = this.phases.find(p => p.name === prerequisite);
      return prereqPhase ? prereqPhase.completion_percentage >= 95 : false;
    }
  }
}
</script>

<style scoped>
/**
 * PhaseProgressionIndicator.vue - Migrated to Design Tokens
 * Issue #704: CSS Design System - Centralized Theming
 * All hardcoded colors replaced with CSS custom properties from design-tokens.css
 */

.phase-progression-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-5);
  font-family: var(--font-sans);
}

.phase-header {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--chart-purple) 100%);
  color: var(--text-on-primary);
  padding: var(--spacing-5);
  border-radius: var(--radius-xl);
  margin-bottom: var(--spacing-5);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-5);
}

/* Button styling handled by BaseButton component */

.performance-note {
  font-size: var(--text-sm);
  font-style: italic;
  color: var(--color-success) !important;
}

.phase-title {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  font-size: var(--text-2xl);
}

.overall-maturity {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  min-width: 300px;
}

.maturity-bar {
  width: 200px;
  height: 20px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.maturity-fill {
  height: 100%;
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-xl);
}

.maturity-production {
  background: linear-gradient(90deg, var(--color-success) 0%, var(--color-success-hover) 100%);
}

.maturity-beta {
  background: linear-gradient(90deg, var(--color-info) 0%, var(--color-info-dark) 100%);
}

.maturity-alpha {
  background: linear-gradient(90deg, var(--color-warning) 0%, var(--color-warning-hover) 100%);
}

.maturity-development {
  background: linear-gradient(90deg, var(--color-error) 0%, var(--color-error-hover) 100%);
}

.error-notice {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-lg);
  margin: var(--spacing-5) 0;
  padding: var(--spacing-5);
  text-align: center;
}

.phase-description {
  background: var(--bg-secondary);
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
  border-left: 4px solid var(--color-info);
}

.phase-description h4 {
  margin: 0 0 var(--spacing-2) 0;
  font-size: var(--text-base);
  color: var(--color-info-dark);
}

.phase-description p {
  margin: 0;
  color: var(--text-secondary);
  font-style: italic;
}

.acceptance-criteria-item {
  color: var(--color-info-dark);
  margin: var(--spacing-1) 0;
  padding: var(--spacing-1);
  background: var(--color-info-bg);
  border-radius: var(--radius-default);
}

.functional-req-item {
  color: var(--chart-purple);
  margin: var(--spacing-1) 0;
  padding: var(--spacing-1);
  background: var(--chart-purple-bg);
  border-radius: var(--radius-default);
}

.error-content {
  max-width: 500px;
  margin: 0 auto;
}

.error-content i {
  font-size: var(--text-4xl);
  color: var(--color-warning);
  margin-bottom: var(--spacing-2-5);
}

.error-content h3 {
  color: var(--color-warning-dark);
  margin: var(--spacing-2-5) 0;
  font-size: var(--text-xl);
}

.error-content p {
  color: var(--color-warning-dark);
  margin-bottom: var(--spacing-4);
}

/* Button styling handled by BaseButton component */

.phases-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-5);
  margin-bottom: var(--spacing-8);
}

.phase-card {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  padding: var(--spacing-5);
  box-shadow: var(--shadow-md);
  border-left: 4px solid var(--border-default);
  transition: var(--transition-all);
}

.phase-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.phase-complete {
  border-left-color: var(--color-success);
}

.phase-mostly-complete {
  border-left-color: var(--color-info);
}

.phase-in-progress {
  border-left-color: var(--color-warning);
}

.phase-incomplete {
  border-left-color: var(--color-error);
}

.phase-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.phase-icon {
  font-size: var(--text-2xl);
  color: var(--text-tertiary);
}

.phase-info {
  flex: 1;
}

.phase-name {
  margin: 0 0 var(--spacing-1) 0;
  font-size: var(--text-lg);
  color: var(--text-primary);
}

.phase-status {
  font-size: var(--text-sm);
  padding: 2px var(--spacing-2);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
}

.status-complete {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.status-mostly-complete {
  background: var(--color-info-bg);
  color: var(--color-info-dark);
}

.status-in-progress {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.status-incomplete {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.phase-completion {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.progress-container {
  margin: var(--spacing-4) 0;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--border-default);
  border-radius: var(--radius-default);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  transition: width var(--duration-300) var(--ease-out);
  border-radius: var(--radius-default);
}

.progress-complete {
  background: linear-gradient(90deg, var(--color-success) 0%, var(--color-success-hover) 100%);
}

.progress-mostly-complete {
  background: linear-gradient(90deg, var(--color-info) 0%, var(--color-info-dark) 100%);
}

.progress-in-progress {
  background: linear-gradient(90deg, var(--color-warning) 0%, var(--color-warning-hover) 100%);
}

.progress-incomplete {
  background: linear-gradient(90deg, var(--color-error) 0%, var(--color-error-hover) 100%);
}

.phase-details {
  margin: var(--spacing-4) 0;
  font-size: var(--text-sm);
  color: var(--text-tertiary);
}

.validation-criteria {
  margin-top: var(--spacing-2-5);
}

.criteria-section {
  margin-bottom: var(--spacing-4);
  padding: var(--spacing-2-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--border-default);
}

.criteria-section h4 {
  margin: 0 0 var(--spacing-2) 0;
  font-size: var(--text-sm);
  color: var(--text-primary);
  font-weight: var(--font-semibold);
}

.criteria-section h4 i {
  margin-right: var(--spacing-1);
  width: 14px;
}

.criteria-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.criteria-list li {
  display: flex;
  align-items: center;
  padding: 3px 0;
  font-size: var(--text-xs);
}

.criteria-list li i {
  margin-right: var(--spacing-2);
  width: 12px;
  font-size: 0.75rem;
}

.criteria-pass {
  color: var(--color-success-hover);
}

.criteria-fail {
  color: var(--color-error-hover);
}

.response-time {
  margin-left: var(--spacing-1);
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-style: italic;
}

.service-status {
  margin-left: var(--spacing-1);
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-style: italic;
}

.metric-threshold {
  margin-left: var(--spacing-1);
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-style: italic;
}

.capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
  margin-top: var(--spacing-1);
}

.capability-tag {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  padding: 2px var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
}

.prereq-list,
.next-phases-list {
  margin: var(--spacing-1) 0;
  padding-left: var(--spacing-5);
}

.phase-actions {
  display: flex;
  gap: var(--spacing-2-5);
  margin-top: var(--spacing-4);
}

/* Button styling handled by BaseButton component */

.progression-history {
  background: var(--bg-card);
  padding: var(--spacing-5);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  margin-bottom: var(--spacing-5);
}

.progression-history h3 {
  margin: 0 0 var(--spacing-4) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  color: var(--text-primary);
}

.history-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2-5);
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-2-5);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.history-icon {
  font-size: var(--text-xl);
}

.history-content {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.history-status {
  padding: 2px var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
}

.history-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-left: auto;
}

.auto-progression-controls {
  background: var(--bg-card);
  padding: var(--spacing-5);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
}

.control-header h3 {
  margin: 0 0 var(--spacing-5) 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  color: var(--text-primary);
}

.controls-grid {
  display: grid;
  grid-template-columns: auto 1fr 1fr;
  gap: var(--spacing-5);
  align-items: center;
}

.control-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
}

.switch {
  position: relative;
  display: inline-block;
  width: 60px;
  height: 34px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--border-default);
  transition: var(--duration-300);
  border-radius: var(--radius-full);
}

.slider:before {
  position: absolute;
  content: "";
  height: 26px;
  width: 26px;
  left: 4px;
  bottom: 4px;
  background-color: var(--text-on-primary);
  transition: var(--duration-300);
  border-radius: var(--radius-full);
}

input:checked + .slider {
  background-color: var(--color-info);
}

input:checked + .slider:before {
  transform: translateX(26px);
}

/* Button styling handled by BaseButton component */

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.loading-spinner {
  background: var(--bg-card);
  padding: var(--spacing-8);
  border-radius: var(--radius-xl);
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-4);
}

.loading-spinner i {
  font-size: var(--text-4xl);
  color: var(--color-info);
}

/* Icon color utility classes using design tokens */
.icon-success {
  color: var(--color-success);
}

.icon-error {
  color: var(--color-error);
}

.icon-info {
  color: var(--color-info);
}

.icon-purple {
  color: var(--chart-purple);
}
</style>
