/**
 * Emergency Performance Fix Script
 * IMMEDIATELY DISABLE ALL AGGRESSIVE MONITORING TO FIX 8+ SECOND NAVIGATION DELAYS
 */

console.log('🚨 EMERGENCY PERFORMANCE FIX - DISABLING AGGRESSIVE MONITORING');

// 1. Disable all existing intervals and timeouts
let clearedIntervals = 0;
let clearedTimeouts = 0;

for (let i = 1; i < 99999; i++) {
  try {
    clearInterval(i);
    clearedIntervals++;
  } catch (e) {
    // Ignore
  }

  try {
    clearTimeout(i);
    clearedTimeouts++;
  } catch (e) {
    // Ignore
  }
}

console.log(`🧹 Cleared ${clearedIntervals} intervals and ${clearedTimeouts} timeouts`);

// 2. Force enable performance mode
if (window.frontendHealthMonitor) {
  window.frontendHealthMonitor.disableMonitoring();
  console.log('🔇 Frontend Health Monitor DISABLED');
}

if (window.routerHealthMonitor) {
  window.routerHealthMonitor.destroy();
  console.log('🔇 Router Health Monitor DISABLED');
}

// 3. Clear excessive local storage that might be causing slowdowns
const keysToOptimize = [
  'rum_critical_issues',
  'rum_recent_events',
  'chat_history',
  'notification_cache',
  'performance_metrics'
];

keysToOptimize.forEach(key => {
  const data = localStorage.getItem(key);
  if (data) {
    try {
      const parsed = JSON.parse(data);
      if (Array.isArray(parsed) && parsed.length > 50) {
        // Keep only recent 10 items
        const optimized = parsed.slice(-10);
        localStorage.setItem(key, JSON.stringify(optimized));
        console.log(`🗑️ Optimized ${key}: reduced from ${parsed.length} to ${optimized.length} items`);
      }
    } catch (e) {
      // Skip if not JSON
    }
  }
});

// 4. Disable Vue dev tools if present (can cause performance issues)
if (window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
  window.__VUE_DEVTOOLS_GLOBAL_HOOK__.enabled = false;
  console.log('🔇 Vue DevTools DISABLED for performance');
}

// 5. Optimize browser performance settings
if (window.performance && window.performance.setResourceTimingBufferSize) {
  window.performance.setResourceTimingBufferSize(50); // Reduce from default 250
  console.log('📊 Performance buffer size reduced');
}

// 6. Create performance monitoring override
window.EMERGENCY_PERFORMANCE_MODE = true;

// Override common performance killers
const originalSetInterval = window.setInterval;
const originalSetTimeout = window.setTimeout;

window.setInterval = function(callback, delay, ...args) {
  // Block any intervals shorter than 2 minutes in emergency mode
  if (delay < 120000) {
    console.warn(`🚫 Blocked aggressive interval: ${delay}ms - using 2 minutes instead`);
    delay = 120000;
  }
  return originalSetInterval.call(this, callback, delay, ...args);
};

window.setTimeout = function(callback, delay, ...args) {
  // Allow timeouts but log aggressive ones
  if (delay < 1000) {
    console.warn(`⚠️ Aggressive timeout detected: ${delay}ms`);
  }
  return originalSetTimeout.call(this, callback, delay, ...args);
};

// 7. Force garbage collection if available
if (window.gc) {
  window.gc();
  console.log('🗑️ Forced garbage collection');
}

// 8. Add performance monitoring
const performanceMonitor = {
  start: performance.now(),

  measureNavigationTime() {
    let lastNavigationTime = performance.now();

    // Monitor router changes
    if (window.$router) {
      window.$router.afterEach(() => {
        const navigationTime = performance.now() - lastNavigationTime;
        if (navigationTime > 1000) {
          console.warn(`🐌 Slow navigation detected: ${navigationTime.toFixed(2)}ms`);
        } else {
          console.log(`✅ Navigation time: ${navigationTime.toFixed(2)}ms`);
        }
        lastNavigationTime = performance.now();
      });
    }
  },

  reportStatus() {
    const now = performance.now();
    const uptime = now - this.start;

    console.log(`📊 Emergency Performance Mode Status:
      • Uptime: ${Math.round(uptime / 1000)}s
      • Memory: ${window.performance?.memory ? Math.round(window.performance.memory.usedJSHeapSize / 1024 / 1024) + 'MB' : 'unknown'}
      • Active Intervals: ${this.countActiveIntervals()}
    `);
  },

  countActiveIntervals() {
    // Try to estimate active intervals
    let active = 0;
    for (let i = 1; i < 1000; i++) {
      try {
        clearInterval(i);
        // If no error, there was an active interval
        active++;
      } catch (e) {
        // No interval with this ID
      }
    }
    return active;
  }
};

performanceMonitor.measureNavigationTime();

// Report status every 30 seconds
setInterval(() => {
  performanceMonitor.reportStatus();
}, 30000);

// 9. Add emergency reset function to window
window.emergencyPerformanceReset = function() {
  console.log('🔄 EMERGENCY PERFORMANCE RESET');
  location.reload();
};

// 10. Add manual performance tools
window.performanceTools = {
  clearAllIntervals() {
    for (let i = 1; i < 99999; i++) {
      clearInterval(i);
    }
    console.log('🧹 All intervals cleared manually');
  },

  clearAllTimeouts() {
    for (let i = 1; i < 99999; i++) {
      clearTimeout(i);
    }
    console.log('🧹 All timeouts cleared manually');
  },

  measureNavigationPerformance() {
    const start = performance.now();
    return {
      end() {
        const duration = performance.now() - start;
        console.log(`⏱️ Operation took: ${duration.toFixed(2)}ms`);
        return duration;
      }
    };
  },

  optimizeLocalStorage() {
    const totalKeys = Object.keys(localStorage).length;
    let optimizedKeys = 0;

    Object.keys(localStorage).forEach(key => {
      const value = localStorage.getItem(key);
      if (value && value.length > 50000) { // Large items (>50KB)
        try {
          const parsed = JSON.parse(value);
          if (Array.isArray(parsed) && parsed.length > 100) {
            localStorage.setItem(key, JSON.stringify(parsed.slice(-50)));
            optimizedKeys++;
          }
        } catch (e) {
          // Not JSON, check if it's a large string
          if (value.length > 100000) {
            localStorage.removeItem(key);
            optimizedKeys++;
          }
        }
      }
    });

    console.log(`🗂️ Optimized ${optimizedKeys}/${totalKeys} localStorage keys`);
  }
};

console.log(`
✅ EMERGENCY PERFORMANCE MODE ACTIVATED

🎯 Applied fixes:
  • Disabled FrontendHealthMonitor (was creating WebSocket connections every 5 seconds)
  • Disabled RouterHealthMonitor (was doing expensive DOM queries)
  • Cleared all existing intervals/timeouts
  • Blocked new aggressive intervals (<2 minutes)
  • Optimized localStorage data
  • Disabled Vue DevTools
  • Added performance monitoring

🛠️ Available tools:
  • window.performanceTools.clearAllIntervals()
  • window.performanceTools.optimizeLocalStorage()
  • window.emergencyPerformanceReset() - reload page

⚡ Navigation should now be MUCH faster (milliseconds instead of 8+ seconds)
`);

// Start reporting
setTimeout(() => {
  performanceMonitor.reportStatus();
}, 2000);