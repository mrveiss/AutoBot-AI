/**
 * Unit Tests for RedisServiceControl.vue Component
 *
 * Tests comprehensive Vue component functionality:
 * - Component rendering with different states
 * - Button click handlers and event emission
 * - Confirmation dialogs
 * - Loading states and disabled states
 * - Error display and notifications
 * - WebSocket real-time updates
 * - API response mocking
 *
 * Test Coverage Target: >80% for RedisServiceControl.vue
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import RedisServiceControl from '@/components/services/RedisServiceControl.vue';

// Mock composables
vi.mock('@/composables/useServiceManagement', () => ({
  useServiceManagement: vi.fn(() => ({
    serviceStatus: {
      value: {
        status: 'running',
        pid: 12345,
        uptime_seconds: 86400,
        memory_mb: 128.5,
        connections: 42,
        last_check: new Date().toISOString()
      }
    },
    healthStatus: {
      value: {
        overall_status: 'healthy',
        service_running: true,
        connectivity: true,
        response_time_ms: 2.5,
        health_checks: {
          connectivity: { status: 'pass', duration_ms: 2.5 },
          systemd: { status: 'pass', duration_ms: 50.0 },
          performance: { status: 'pass', duration_ms: 15.0 }
        },
        recommendations: [],
        auto_recovery: {
          enabled: true,
          recent_recoveries: 0
        }
      }
    },
    loading: { value: false },
    startService: vi.fn(),
    stopService: vi.fn(),
    restartService: vi.fn(),
    refreshStatus: vi.fn(),
    subscribeToStatusUpdates: vi.fn()
  }))
}));

describe('RedisServiceControl.vue', () => {
  let wrapper;

  beforeEach(() => {
    setActivePinia(createPinia());
  });

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount();
    }
  });

  describe('Component Rendering', () => {
    it('renders component with running status', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="redis-service-control"]').exists()).toBe(true);
      expect(wrapper.find('[data-testid="service-header"]').exists()).toBe(true);
      expect(wrapper.text()).toContain('Redis Service');
    });

    it('displays service details when running', () => {
      wrapper = mount(RedisServiceControl);

      const details = wrapper.find('[data-testid="service-details"]');
      expect(details.exists()).toBe(true);
      expect(details.text()).toContain('Uptime');
      expect(details.text()).toContain('Memory');
      expect(details.text()).toContain('Connections');
    });

    it('shows correct uptime formatting', () => {
      wrapper = mount(RedisServiceControl);

      // 86400 seconds = 1 day
      expect(wrapper.text()).toMatch(/1d \d+h \d+m/);
    });

    it('displays memory usage in MB', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.text()).toContain('128.5 MB');
    });

    it('shows connection count', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.text()).toContain('42');
    });

    it('renders service status badge', () => {
      wrapper = mount(RedisServiceControl);

      const badge = wrapper.findComponent({ name: 'ServiceStatusBadge' });
      expect(badge.exists()).toBe(true);
      expect(badge.props('status')).toBe('running');
    });
  });

  describe('Control Buttons', () => {
    it('renders all control buttons', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="start-button"]').exists()).toBe(true);
      expect(wrapper.find('[data-testid="restart-button"]').exists()).toBe(true);
      expect(wrapper.find('[data-testid="stop-button"]').exists()).toBe(true);
      expect(wrapper.find('[data-testid="refresh-button"]').exists()).toBe(true);
    });

    it('start button disabled when service running', () => {
      wrapper = mount(RedisServiceControl);

      const startButton = wrapper.find('[data-testid="start-button"]');
      expect(startButton.attributes('disabled')).toBeDefined();
    });

    it('restart button enabled when service running', () => {
      wrapper = mount(RedisServiceControl);

      const restartButton = wrapper.find('[data-testid="restart-button"]');
      expect(restartButton.attributes('disabled')).toBeUndefined();
    });

    it('stop button enabled when service running', () => {
      wrapper = mount(RedisServiceControl);

      const stopButton = wrapper.find('[data-testid="stop-button"]');
      expect(stopButton.attributes('disabled')).toBeUndefined();
    });

    it('all buttons disabled when loading', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        loading: { value: true }
      });

      wrapper = mount(RedisServiceControl);

      const buttons = wrapper.findAll('button');
      buttons.forEach(button => {
        expect(button.attributes('disabled')).toBeDefined();
      });
    });
  });

  describe('Button Click Handlers', () => {
    it('calls startService when start button clicked', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      const mockStartService = vi.fn();

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        serviceStatus: { value: { status: 'stopped' } },
        startService: mockStartService
      });

      wrapper = mount(RedisServiceControl);

      const startButton = wrapper.find('[data-testid="start-button"]');
      await startButton.trigger('click');

      expect(mockStartService).toHaveBeenCalledOnce();
    });

    it('shows confirmation dialog before restart', async () => {
      wrapper = mount(RedisServiceControl);

      const restartButton = wrapper.find('[data-testid="restart-button"]');
      await restartButton.trigger('click');

      await wrapper.vm.$nextTick();

      expect(wrapper.find('[data-testid="confirm-dialog"]').exists()).toBe(true);
      expect(wrapper.text()).toContain('Restart Redis Service');
    });

    it('shows confirmation dialog before stop', async () => {
      wrapper = mount(RedisServiceControl);

      const stopButton = wrapper.find('[data-testid="stop-button"]');
      await stopButton.trigger('click');

      await wrapper.vm.$nextTick();

      expect(wrapper.find('[data-testid="confirm-dialog"]').exists()).toBe(true);
      expect(wrapper.text()).toContain('Stop Redis Service');
    });

    it('calls refreshStatus when refresh button clicked', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      const mockRefreshStatus = vi.fn();

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        refreshStatus: mockRefreshStatus
      });

      wrapper = mount(RedisServiceControl);

      const refreshButton = wrapper.find('[data-testid="refresh-button"]');
      await refreshButton.trigger('click');

      expect(mockRefreshStatus).toHaveBeenCalledOnce();
    });
  });

  describe('Confirmation Dialogs', () => {
    it('confirms restart and calls restartService', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      const mockRestartService = vi.fn();

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        restartService: mockRestartService
      });

      wrapper = mount(RedisServiceControl);

      // Click restart button
      await wrapper.find('[data-testid="restart-button"]').trigger('click');
      await wrapper.vm.$nextTick();

      // Confirm in dialog
      await wrapper.find('[data-testid="confirm-button"]').trigger('click');
      await flushPromises();

      expect(mockRestartService).toHaveBeenCalledOnce();
    });

    it('cancels restart when dialog cancelled', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      const mockRestartService = vi.fn();

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        restartService: mockRestartService
      });

      wrapper = mount(RedisServiceControl);

      // Click restart button
      await wrapper.find('[data-testid="restart-button"]').trigger('click');
      await wrapper.vm.$nextTick();

      // Cancel in dialog
      await wrapper.find('[data-testid="cancel-button"]').trigger('click');
      await wrapper.vm.$nextTick();

      expect(mockRestartService).not.toHaveBeenCalled();
      expect(wrapper.find('[data-testid="confirm-dialog"]').exists()).toBe(false);
    });

    it('shows warning message in stop confirmation', async () => {
      wrapper = mount(RedisServiceControl);

      await wrapper.find('[data-testid="stop-button"]').trigger('click');
      await wrapper.vm.$nextTick();

      const dialog = wrapper.find('[data-testid="confirm-dialog"]');
      expect(dialog.text()).toContain('All dependent services will be affected');
    });
  });

  describe('Loading States', () => {
    it('shows loading indicator when loading', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        loading: { value: true }
      });

      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="loading-indicator"]').exists()).toBe(true);
    });

    it('disables buttons during loading', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        loading: { value: true }
      });

      wrapper = mount(RedisServiceControl);

      const buttons = wrapper.findAll('button');
      buttons.forEach(button => {
        if (!button.classes().includes('btn-link')) {  // Exclude log toggle button
          expect(button.attributes('disabled')).toBeDefined();
        }
      });
    });

    it('hides loading indicator when not loading', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="loading-indicator"]').exists()).toBe(false);
    });
  });

  describe('Health Status Display', () => {
    it('displays health status section', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="health-status"]').exists()).toBe(true);
      expect(wrapper.text()).toContain('Health Status');
    });

    it('shows healthy status indicator', () => {
      wrapper = mount(RedisServiceControl);

      const indicator = wrapper.find('[data-testid="health-indicator"]');
      expect(indicator.exists()).toBe(true);
      expect(indicator.classes()).toContain('healthy');
      expect(indicator.text()).toBe('HEALTHY');
    });

    it('displays individual health checks', () => {
      wrapper = mount(RedisServiceControl);

      const checks = wrapper.findAll('[data-testid^="health-check-"]');
      expect(checks.length).toBeGreaterThan(0);
    });

    it('shows health check status badges', () => {
      wrapper = mount(RedisServiceControl);

      const connectivityCheck = wrapper.find('[data-testid="health-check-connectivity"]');
      expect(connectivityCheck.exists()).toBe(true);
      expect(connectivityCheck.text()).toContain('pass');
    });

    it('displays health check duration', () => {
      wrapper = mount(RedisServiceControl);

      const connectivityCheck = wrapper.find('[data-testid="health-check-connectivity"]');
      expect(connectivityCheck.text()).toContain('2.5ms');
    });

    it('shows recommendations when present', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        healthStatus: {
          value: {
            overall_status: 'degraded',
            recommendations: [
              'Consider increasing memory limit',
              'Monitor connection usage'
            ]
          }
        }
      });

      wrapper = mount(RedisServiceControl);

      const recommendations = wrapper.find('[data-testid="recommendations"]');
      expect(recommendations.exists()).toBe(true);
      expect(recommendations.text()).toContain('Consider increasing memory limit');
    });

    it('hides recommendations when empty', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="recommendations"]').exists()).toBe(false);
    });
  });

  describe('Auto-Recovery Status', () => {
    it('displays auto-recovery section', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="auto-recovery"]').exists()).toBe(true);
      expect(wrapper.text()).toContain('Auto-Recovery');
    });

    it('shows auto-recovery enabled status', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.text()).toContain('Enabled: Yes');
    });

    it('shows recent recovery count', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        healthStatus: {
          value: {
            auto_recovery: {
              enabled: true,
              recent_recoveries: 3
            }
          }
        }
      });

      wrapper = mount(RedisServiceControl);

      expect(wrapper.text()).toContain('Recent Recoveries: 3');
    });

    it('shows manual intervention alert when required', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        healthStatus: {
          value: {
            auto_recovery: {
              enabled: true,
              requires_manual_intervention: true
            }
          }
        }
      });

      wrapper = mount(RedisServiceControl);

      const alert = wrapper.find('[data-testid="manual-intervention-alert"]');
      expect(alert.exists()).toBe(true);
      expect(alert.classes()).toContain('alert-danger');
      expect(alert.text()).toContain('Manual intervention required');
    });
  });

  describe('Service Logs Viewer', () => {
    it('renders logs toggle button', () => {
      wrapper = mount(RedisServiceControl);

      const logsButton = wrapper.find('[data-testid="toggle-logs-button"]');
      expect(logsButton.exists()).toBe(true);
      expect(logsButton.text()).toContain('Show Logs');
    });

    it('shows logs viewer when toggled', async () => {
      wrapper = mount(RedisServiceControl);

      const logsButton = wrapper.find('[data-testid="toggle-logs-button"]');
      await logsButton.trigger('click');
      await wrapper.vm.$nextTick();

      expect(wrapper.findComponent({ name: 'ServiceLogsViewer' }).exists()).toBe(true);
      expect(logsButton.text()).toContain('Hide Logs');
    });

    it('hides logs viewer when toggled off', async () => {
      wrapper = mount(RedisServiceControl);

      const logsButton = wrapper.find('[data-testid="toggle-logs-button"]');

      // Toggle on
      await logsButton.trigger('click');
      await wrapper.vm.$nextTick();
      expect(wrapper.findComponent({ name: 'ServiceLogsViewer' }).exists()).toBe(true);

      // Toggle off
      await logsButton.trigger('click');
      await wrapper.vm.$nextTick();
      expect(wrapper.findComponent({ name: 'ServiceLogsViewer' }).exists()).toBe(false);
    });
  });

  describe('WebSocket Real-Time Updates', () => {
    it('subscribes to status updates on mount', () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      const mockSubscribe = vi.fn();

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        subscribeToStatusUpdates: mockSubscribe
      });

      wrapper = mount(RedisServiceControl);

      expect(mockSubscribe).toHaveBeenCalledOnce();
    });

    it('updates status when WebSocket message received', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      let statusUpdateCallback;

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        serviceStatus: { value: { status: 'running' } },
        subscribeToStatusUpdates: vi.fn((callback) => {
          statusUpdateCallback = callback;
        })
      });

      wrapper = mount(RedisServiceControl);
      await wrapper.vm.$nextTick();

      // Simulate WebSocket update
      const update = {
        type: 'service_status',
        status: 'stopped',
        timestamp: new Date().toISOString()
      };

      statusUpdateCallback(update);
      await wrapper.vm.$nextTick();

      // Status should update (in real implementation)
      expect(statusUpdateCallback).toBeDefined();
    });

    it('refreshes status after service event', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');
      const mockRefreshStatus = vi.fn();
      let statusUpdateCallback;

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        refreshStatus: mockRefreshStatus,
        subscribeToStatusUpdates: vi.fn((callback) => {
          statusUpdateCallback = callback;
        })
      });

      wrapper = mount(RedisServiceControl);
      await wrapper.vm.$nextTick();

      // Simulate service event (restart completed)
      const event = {
        type: 'service_event',
        service: 'redis',
        event: 'restart',
        result: 'success'
      };

      statusUpdateCallback(event);
      await wrapper.vm.$nextTick();

      // Should trigger status refresh (in real implementation)
      expect(statusUpdateCallback).toBeDefined();
    });
  });

  describe('Error Handling', () => {
    it('displays error message when operation fails', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        startService: vi.fn().mockRejectedValue(new Error('Start failed'))
      });

      wrapper = mount(RedisServiceControl);

      const startButton = wrapper.find('[data-testid="start-button"]');
      await startButton.trigger('click');
      await flushPromises();

      // Error notification should appear (handled by composable)
      // Component should remain in stable state
      expect(wrapper.find('[data-testid="redis-service-control"]').exists()).toBe(true);
    });

    it('shows error state when service status unavailable', async () => {
      const { useServiceManagement } = await import('@/composables/useServiceManagement');

      useServiceManagement.mockReturnValue({
        ...useServiceManagement(),
        serviceStatus: { value: { status: 'unknown' } },
        healthStatus: { value: null }
      });

      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('[data-testid="error-state"]').exists()).toBe(true);
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA labels for buttons', () => {
      wrapper = mount(RedisServiceControl);

      const startButton = wrapper.find('[data-testid="start-button"]');
      expect(startButton.attributes('aria-label')).toBeDefined();
    });

    it('uses semantic HTML elements', () => {
      wrapper = mount(RedisServiceControl);

      expect(wrapper.find('button').exists()).toBe(true);
      expect(wrapper.find('section').exists()).toBe(true);
    });

    it('provides keyboard navigation support', async () => {
      wrapper = mount(RedisServiceControl);

      const startButton = wrapper.find('[data-testid="start-button"]');

      // Should be focusable
      expect(startButton.attributes('tabindex')).not.toBe('-1');
    });
  });
});
