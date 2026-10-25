<template>
  <div id="app" class="h-screen bg-autobot-bg-primary flex flex-col overflow-hidden">
    <!-- Skip links: the shared kit's SkipLink, which moves focus (#17565) -->
    <template v-if="showAuthChrome">
      <SkipLink :label="$t('nav.skipToContent')" />
      <!-- #navigation is display:none below lg, so its skip link is too -->
      <span class="hidden lg:inline"><SkipLink target="#navigation" :label="$t('nav.skipToNavigation')" /></span>
    </template>

    <!-- Header: hidden on public routes such as login (#901) -->
    <AppHeader
      v-if="showAuthChrome"
      @open-profile="showProfileModal = true"
      @open-status="showSystemStatus = true"
    />

    <!-- System Status panel, on the kit BaseModal (#18240) -->
    <SystemStatusModal />

    <!-- Profile Modal (Issue #950) -->
    <ProfileModal
      :is-open="showProfileModal"
      @close="showProfileModal = false"
    />

    <!-- Telemetry Consent Modal (Issue #9035) -->
    <!-- Gated behind authentication (#12334): the consent prompt persists its
         choice via authenticated endpoints, so mounting it on the login/
         unauthenticated route overlaid the Sign In form and 401'd, re-nagging
         forever. Defer until after successful login. -->
    <TelemetryConsentModal v-if="userStore.isAuthenticated" />

    <!-- System Status Notifications (limit to last 5 to prevent teleport accumulation) -->
    <SystemStatusNotification
      v-for="notif in (appStore?.systemNotifications || []).filter(n => n.visible).slice(-5)"
      :key="`notification-${notif.id}`"
      :visible="notif.visible"
      :severity="notif.severity"
      :title="notif.title"
      :message="notif.message"
      :status-details="notif.statusDetails"
      :allow-dismiss="true"
      :show-details="notif.statusDetails ? true : false"
      :auto-hide="0"
      @dismiss="() => appStore?.removeSystemNotification(notif.id)"
      @expired="() => appStore?.removeSystemNotification(notif.id)"
      @hide="() => appStore?.removeSystemNotification(notif.id)"
      @remove="() => appStore?.removeSystemNotification(notif.id)"
    />

    <!-- CAPTCHA Human-in-the-Loop Notification (Issue #206) -->
    <CaptchaNotification />

    <!-- Toast Notifications Container (Issue #502) -->
    <ToastContainer />

    <!-- Host Selection Dialog for Agent SSH Actions -->
    <HostSelectionDialog
      :show="hostSelectionState.showDialog"
      :command="hostSelectionState.pendingRequest?.command"
      :purpose="hostSelectionState.pendingRequest?.purpose"
      :request-id="hostSelectionState.pendingRequest?.requestId"
      @selected="onHostSelected"
      @cancelled="onHostSelectionCancelled"
      @close="onHostSelectionClose"
    />

    <!-- Offline mode banner — #3275 -->
    <OfflineBanner />

    <!-- Main Content Area with Router -->
    <main id="main-content" class="flex-1 min-h-0 overflow-hidden" role="main">
      <LoadingBoundary
        :loading="isLoading"
        :on-retry="clearAllCaches"
        :timeout-ms="15000"
        @loading-timeout="handleLoadingTimeout"
        class="h-full"
      >
        <!-- Use router-view for all content to enable proper sub-routing -->
        <ErrorBoundary>
          <router-view class="h-full" />
        </ErrorBoundary>
      </LoadingBoundary>
    </main>

    <!-- TASK 16: About link relocated into the profile dropdown (desktop) and
         the mobile nav panel. The page-bottom footer link was removed. -->
  </div>

  <!-- Issue #729: RUM Dashboard moved to slm-admin -->
  <!-- ElevationDialog removed: feature not yet implemented (#920) -->

  <!-- Global confirm dialog (#6092) -->
  <ConfirmDialog />

  <!-- Global command palette — opened via Ctrl/Cmd+K (#8989) -->
  <CommandPalette ref="commandPaletteRef" />
</template>

<script lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, provide } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useAppStore } from '@/stores/useAppStore'
import { useUserStore } from '@/stores/useUserStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useRuntimeFeaturesStore } from '@/stores/useRuntimeFeaturesStore'
import { useSystemStatus } from '@/composables/useSystemStatus'
import { SYSTEM_STATUS_KEY } from '@/composables/systemStatusContext'
import { useHostSelection, type InfrastructureHost } from '@/composables/useHostSelection';
import { useGlobalShortcuts } from '@/composables/useGlobalShortcuts'
import AppHeader from '@/components/layout/AppHeader.vue'
import SystemStatusModal from '@/components/layout/SystemStatusModal.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import { SkipLink } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'
import { cacheBuster } from '@/utils/CacheBuster.js';
import { healthMonitor } from '@/utils/HealthMonitor.js';
import { useBackendHealthNotice } from '@/composables/useBackendHealthNotice';
import { initializeNotificationBridge } from '@/utils/notificationBridge';
import { smartMonitoringController, getAdaptiveInterval } from '@/config/OptimizedPerformance.js';
import { clearAllSystemNotifications, resetHealthMonitor } from '@/utils/ClearNotifications.js';
import SystemStatusNotification from '@/components/ui/SystemStatusNotification.vue';
import CaptchaNotification from '@/components/research/CaptchaNotification.vue';
import ToastContainer from '@/components/ui/ToastContainer.vue';
import HostSelectionDialog from '@/components/ui/HostSelectionDialog.vue';
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue';
import LoadingBoundary from '@/components/ui/LoadingBoundary.vue';
import ProfileModal from '@/components/profile/ProfileModal.vue';
import ErrorBoundary from '@/components/common/ErrorBoundary.vue'
import OfflineBanner from '@/components/ui/OfflineBanner.vue';
import TelemetryConsentModal from '@/components/modals/TelemetryConsentModal.vue';

const logger = createLogger('App');

export default {
  name: 'App',

  components: {
    SystemStatusNotification,
    OfflineBanner,
    CaptchaNotification,
    ToastContainer,
    HostSelectionDialog,
    ConfirmDialog,
    LoadingBoundary,
    ProfileModal,
    ErrorBoundary,
    AppHeader,
    SystemStatusModal,
    CommandPalette,
    SkipLink,
    TelemetryConsentModal,
  },

  setup() {
    const { t } = useI18n()

    // Store references
    const appStore = useAppStore();
    const backendHealthNotice = useBackendHealthNotice(appStore, t, () => ({
      consecutiveFailures: healthMonitor.consecutiveFailures?.backend ?? 0,
      error: healthMonitor.lastBackendError,
    }));
    const userStore = useUserStore();
    const chatStore = useChatStore();
    const knowledgeStore = useKnowledgeStore();
    // #10502: runtime (deployment) feature flags from /api/frontend-config,
    // used to gate the Company OS nav item when the deployment lacks the
    // PostgreSQL company mode.
    const runtimeFeaturesStore = useRuntimeFeaturesStore();
    const router = useRouter();
    const route = useRoute();

    // Initialize user preferences system (Issue #753)
    import('@/composables/usePreferences').then(({ usePreferences }) => {
      const prefs = usePreferences();
      logger.debug('User preferences system initialized');

      // Cross-device language sync: load stored language from backend after login (#1675)
      let handledSignIns = 0
      watch(
        () => userStore.isAuthenticated,
        async (authenticated) => {
          if (authenticated) {
            // A login() since the last pass is a fresh sign-in; anything else is a
            // session restore, which keeps the device's mode and variant (#18240).
            const freshSignIn = userStore.signInCount > handledSignIns;
            handledSignIns = userStore.signInCount;
            await prefs.loadLanguageFromBackend();
            // Cross-device appearance sync: pull stored theme/accent/density (#8988)
            await prefs.loadAppearanceFromBackend({ freshSignIn });
          }
        },
        { immediate: true }
      );
    });

    // ONE status instance for the shell: the header dot, the profile-menu item
    // and the status panel inject it (useSystemStatus keeps per-call state).
    const systemStatusApi = useSystemStatus()
    provide(SYSTEM_STATUS_KEY, systemStatusApi)
    const { showSystemStatus, refreshSystemStatus, updateSystemStatus } = systemStatusApi

    // Host selection composable for agent SSH actions
    const {
      showDialog: hostSelectionShowDialog,
      pendingRequest: hostSelectionPendingRequest,
      handleHostSelected,
      handleDialogCancelled,
      handleDialogClose
    } = useHostSelection()

    // Create reactive state object for host selection
    const hostSelectionState = computed(() => ({
      showDialog: hostSelectionShowDialog.value,
      pendingRequest: hostSelectionPendingRequest.value
    }))

    // Host selection event handlers
    const onHostSelected = (result: { host: InfrastructureHost; rememberChoice: boolean }) => {
      handleHostSelected(result)
    }

    const onHostSelectionCancelled = () => {
      handleDialogCancelled()
    }

    const onHostSelectionClose = () => {
      handleDialogClose()
    }

    const showProfileModal = ref(false);

    // Global keyboard shortcuts (#8989)
    const commandPaletteRef = ref<InstanceType<typeof CommandPalette> | null>(null)
    useGlobalShortcuts({ commandPaletteRef })

    let notificationCleanup: number | null = null;

    // Computed properties
    const isLoading = computed(() => appStore?.isLoading || false);
    const hasErrors = computed(() => false); // No errors property in store
    const isPublicRoute = computed(() => !!route.meta.isPublic);
    const showAuthChrome = computed(() => userStore.isAuthenticated && !isPublicRoute.value);

    // Methods
    const clearAllCaches = async () => {
      try {
        // Clear all stores
        if (appStore && typeof appStore.clearAllNotifications === 'function') {
          appStore.clearAllNotifications();
        }
        if (chatStore && typeof chatStore.clearAllSessions === 'function') {
          chatStore.clearAllSessions();
        }
        // Knowledge store doesn't have clearCache method
        // Clear by refreshing stats
        if (knowledgeStore && typeof knowledgeStore.refreshStats === 'function') {
          await knowledgeStore.refreshStats();
        }

        // Reload the page
        window.location.reload();
      } catch (error) {
        logger.error('Error clearing caches:', error);
      }
    };

    const handleGlobalError = (error: Error) => {
      logger.error('Global error:', error);
      if (appStore && typeof appStore.addSystemNotification === 'function') {
        appStore.addSystemNotification({
          severity: 'error',
          title: t('nav.applicationError'),
          message: error.message || t('nav.unexpectedError')
        });
      }
    };

    // Named handlers for global error listeners (#2849)
    const handleWindowError = (event: ErrorEvent) => {
      handleGlobalError(event.error || event);
    };
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      handleGlobalError(event.reason);
    };

    // Unified loading event handlers
    const handleLoadingComplete = () => {
      logger.debug('Loading completed successfully');
      if (appStore && typeof appStore.setLoading === 'function') {
        appStore.setLoading(false);
      }
    };

    const handleLoadingError = (error: string | Error) => {
      logger.error('Loading error:', error);
      handleGlobalError(error instanceof Error ? error : new Error(String(error)));
    };

    const handleLoadingTimeout = () => {
      logger.warn('Loading timed out - continuing with available content');
      if (appStore && typeof appStore.addSystemNotification === 'function') {
        appStore.addSystemNotification({
          severity: 'warning',
          title: t('nav.loadingTimeout'),
          message: t('nav.loadingTimeoutMessage')
        });
      }
    };

    // OPTIMIZED: Intelligent system health monitoring
    const startOptimizedHealthCheck = () => {
      logger.debug('Starting optimized health monitoring system...');

      // Listen for health changes from optimized monitor
      healthMonitor.onHealthChange((healthData) => {
        // Update app store with health status
        if (appStore && typeof appStore.setBackendStatus === 'function') {
          const backendStatus = healthData.status.backend;
          const statusClass = backendStatus === 'healthy' ? 'success' : backendStatus === 'degraded' ? 'warning' : 'error';
          appStore.setBackendStatus({ class: statusClass });
        }
        // #16253: a degraded or critical backend raises one notice with its status details.
        backendHealthNotice.onHealthChange(healthData);

        // Update smart monitoring controller (filter out 'unknown' state)
        const healthState = healthData.status.overall;
        if (healthState !== 'unknown') {
          smartMonitoringController.setSystemHealth(healthState);
        }
      });

      logger.debug('Optimized health monitoring initialized');
    };

    // OPTIMIZED: Smart notification cleanup with adaptive intervals
    const startOptimizedNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
      }

      // Use adaptive interval based on system state
      const cleanupInterval = getAdaptiveInterval('NOTIFICATION_CLEANUP', 'healthy', false);

      notificationCleanup = window.setInterval(() => {
        if (appStore && appStore.systemNotifications && appStore.systemNotifications.length > 5) {
          logger.debug('Cleaning up excessive notifications:', appStore.systemNotifications.length);
          // Keep only the last 5 notifications
          const recentNotifications = appStore.systemNotifications.slice(-5);
          appStore.systemNotifications.splice(0, appStore.systemNotifications.length, ...recentNotifications);
        }
      }, cleanupInterval);

      logger.debug(`Notification cleanup scheduled every ${Math.round(cleanupInterval/60000)} minutes`);
    };

    const stopOptimizedNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
        notificationCleanup = null;
      }
    };

    // Router event monitoring - OPTIMIZED: Event-driven instead of polling
    const setupRouterMonitoring = () => {
      // Monitor router navigation events
      router.afterEach((to, from) => {
        logger.debug(`Navigation: ${from.path} → ${to.path}`);

        // Update user activity in smart monitoring controller
        smartMonitoringController.userActivity.lastActivity = Date.now();
        smartMonitoringController.userActivity.isActive = true;
      });

      // Monitor router errors
      router.onError((error) => {
        logger.error('Router error:', error);
        handleGlobalError(error);
      });
    };

    // Lifecycle hooks
    onMounted(async () => {
      logger.debug('Initializing optimized AutoBot application...');

      // #10502: load deployment feature flags (e.g. company_os_enabled) so the
      // nav rail can hide modules unavailable in this deployment mode.
      void runtimeFeaturesStore.load();

      // Set up global error handling (#2849: use named handlers for cleanup)
      window.addEventListener('error', handleWindowError);
      window.addEventListener('unhandledrejection', handleUnhandledRejection);

      // CRITICAL FIX: Clear any stuck system notifications on startup
      logger.debug('Clearing stuck system notifications on startup...');
      clearAllSystemNotifications();
      resetHealthMonitor();

      // Initialize notification bridge for ErrorHandler integration (Issue #502)
      initializeNotificationBridge();
      logger.debug('NotificationBridge initialized for ErrorHandler integration');

      // OPTIMIZED: Initialize new performance-aware systems
      try {
        // Initialize cache buster
        if (cacheBuster && typeof cacheBuster.initialize === 'function') {
          cacheBuster.initialize();
        }

        // OPTIMIZED: Start optimized health monitoring
        startOptimizedHealthCheck();

        // FIXED: Use useSystemStatus composable's refresh method
        logger.debug('Initializing system status with composable...');
        try {
          await refreshSystemStatus();
          updateSystemStatus();
        } catch (statusError) {
          logger.warn('System status initialization failed, but Vue app will continue:', statusError);
          // Don't throw - let Vue app mount successfully
        }

        // OPTIMIZED: Setup router monitoring (event-driven)
        setupRouterMonitoring();

        logger.debug('Optimized monitoring systems initialized successfully');

      } catch (error) {
        logger.error('Error initializing optimized systems:', error);
        // Don't let initialization errors prevent app mounting
      }

      // OPTIMIZED: Start adaptive notification cleanup
      startOptimizedNotificationCleanup();

      // Set loading to false once initialization is complete
      if (appStore && typeof appStore.setLoading === 'function') {
        appStore.setLoading(false);
      }

      logger.debug('Optimized AutoBot initialized - monitoring restored with <50ms performance budget');
    });

    onUnmounted(() => {
      logger.debug('Cleaning up optimized monitoring systems...');

      // Clean up listeners (#2849: remove all event listeners added in onMounted)
      window.removeEventListener('error', handleWindowError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
      stopOptimizedNotificationCleanup();

      // Destroy optimized health monitor
      if (healthMonitor && typeof healthMonitor.destroy === 'function') {
        healthMonitor.destroy();
      }
    });

    return {
      // Store references
      appStore,
      userStore,
      chatStore,
      knowledgeStore,

      // Reactive data
      commandPaletteRef,
      showProfileModal,
      showSystemStatus,

      // Computed
      isLoading,
      hasErrors,
      isPublicRoute,
      showAuthChrome,

      // Methods
      clearAllCaches,
      handleGlobalError,

      // Unified loading handlers
      handleLoadingComplete,
      handleLoadingError,
      handleLoadingTimeout,

      // Host selection (for agent SSH actions)
      hostSelectionState,
      onHostSelected,
      onHostSelectionCancelled,
      onHostSelectionClose,
    };
  }
};
</script>
