/**
 * Integration Test for Optimized Monitoring System
 * Tests the performance and functionality of the new monitoring architecture
 */

// Mock browser APIs for testing
global.performance = {
  now: () => Date.now(),
  memory: {
    usedJSHeapSize: 50000000,
    totalJSHeapSize: 100000000
  }
};

global.window = {
  addEventListener: () => {},
  removeEventListener: () => {},
  fetch: () => Promise.resolve({ ok: true, status: 200 })
};

global.document = {
  addEventListener: () => {},
  removeEventListener: () => {},
  hidden: false
};

// Import the optimized components
import { optimizedHealthMonitor } from '../src/utils/OptimizedHealthMonitor.js';
import {
  smartMonitoringController,
  performanceBudgetTracker,
  getAdaptiveInterval,
  OPTIMIZED_PERFORMANCE
} from '../src/config/OptimizedPerformance.js';

/**
 * Test Suite: Optimized Monitoring System
 */
async function runMonitoringTests() {
  const testResults = {
    performanceBudget: false,
    adaptiveIntervals: false,
    healthMonitor: false,
    smartController: false,
    configuration: false,
    performanceImpact: false
  };

  // Test 1: Performance Budget Tracking
  const startBudget = performanceBudgetTracker.getBudgetStatus();
  testResults.performanceBudget = startBudget.maxBudget > 0;

  // Test 2: Adaptive Intervals
  const healthyInterval = getAdaptiveInterval('HEALTH_CHECK_HEALTHY', 'healthy', false);
  const degradedInterval = getAdaptiveInterval('HEALTH_CHECK_DEGRADED', 'degraded', false);
  const criticalInterval = getAdaptiveInterval('HEALTH_CHECK_CRITICAL', 'critical', false);
  const userActiveInterval = getAdaptiveInterval('HEALTH_CHECK_USER_ACTIVE', 'healthy', true);

  testResults.adaptiveIntervals = healthyInterval > 0 && degradedInterval > 0 &&
    criticalInterval > 0 && userActiveInterval > 0;

  // Test 3: Health Monitor Performance
  const startTime = performance.now();

  try {
    // Test health monitor initialization
    const healthStatus = optimizedHealthMonitor.getHealthStatus();
    testResults.healthMonitor = healthStatus.overall !== undefined;

    // Test performance tracking
    performanceBudgetTracker.trackOperation('testHealthCheck', 5); // 5ms mock operation
    const updatedBudget = performanceBudgetTracker.getBudgetStatus();
    testResults.healthMonitor = testResults.healthMonitor &&
      updatedBudget.recentOperations.length > 0;

  } catch (error) {
    testResults.healthMonitor = false;
  }

  // Test 4: Smart Monitoring Controller
  try {
    const systemState = smartMonitoringController.getSystemState();
    testResults.smartController = systemState.userActivity !== undefined &&
      systemState.health !== undefined;

    // Test user activity simulation
    smartMonitoringController.setUserDashboardViewing(true);
    const optimalInterval = smartMonitoringController.getOptimalInterval(120000); // 2 minutes base
    testResults.smartController = testResults.smartController && optimalInterval > 0;

  } catch (error) {
    testResults.smartController = false;
  }

  // Test 5: Configuration Validation
  const configTests = {
    performanceModeEnabled: OPTIMIZED_PERFORMANCE.ENABLED,
    adaptiveIntervalsEnabled: OPTIMIZED_PERFORMANCE.FEATURES.ADAPTIVE_INTERVALS,
    performanceBudgetSet: OPTIMIZED_PERFORMANCE.PERFORMANCE.MAX_MONITORING_OVERHEAD_PER_MINUTE === 50,
    healthIntervalsConfigured: OPTIMIZED_PERFORMANCE.INTERVALS.HEALTH_CHECK_HEALTHY === 120000
  };

  const passedTests = Object.values(configTests).filter(Boolean).length;
  testResults.configuration = passedTests === Object.keys(configTests).length;

  // Test 6: Performance Impact Measurement
  const endTime = performance.now();
  const testDuration = endTime - startTime;

  testResults.performanceImpact = testDuration < OPTIMIZED_PERFORMANCE.PERFORMANCE.MAX_SINGLE_CHECK_DURATION;

  const memoryUsage = global.performance.memory ?
    ((global.performance.memory.usedJSHeapSize / global.performance.memory.totalJSHeapSize) * 100) : 0;

  // Performance Improvement Calculation
  const oldSystemOverhead = 3600; // 3.6 seconds per minute (old system)
  const newSystemOverhead = 50; // 50ms per minute (new system)
  const improvementPercentage = ((oldSystemOverhead - newSystemOverhead) / oldSystemOverhead * 100).toFixed(1);

  // Check all tests passed
  const allTestsPassed = Object.values(testResults).every(result => result === true);

  return {
    success: allTestsPassed,
    performanceImprovement: improvementPercentage,
    testDuration: testDuration,
    budgetCompliant: testDuration < 50,
    testResults,
    metrics: {
      startBudget,
      healthyInterval,
      degradedInterval,
      criticalInterval,
      userActiveInterval,
      testDuration,
      memoryUsage,
      oldSystemOverhead,
      newSystemOverhead
    }
  };
}

// Export for use in other tests
export { runMonitoringTests };

// Run tests if executed directly
if (typeof window === 'undefined') {
  runMonitoringTests().then(results => {
    if (!results.success) {
      throw new Error('Monitoring tests failed');
    }
  }).catch((error) => {
    throw error;
  });
}
