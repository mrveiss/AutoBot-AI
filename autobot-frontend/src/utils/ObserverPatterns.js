/**
 * Observer Pattern Replacements for setTimeout/setInterval
 * Replaces time-based delays with event-driven and state-based patterns
 */

import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for ObserverPatterns
const logger = createLogger('ObserverPatterns');

class EventObserver {
  constructor() {
    this.observers = new Map();
    this.eventQueue = [];
    this.isProcessing = false;
  }

  /**
   * Subscribe to events with callback
   */
  subscribe(eventType, callback) {
    if (!this.observers.has(eventType)) {
      this.observers.set(eventType, new Set());
    }

    const observerSet = this.observers.get(eventType);
    observerSet.add(callback);


    // Return unsubscribe function
    return () => {
      observerSet.delete(callback);
      if (observerSet.size === 0) {
        this.observers.delete(eventType);
      }
    };
  }

  /**
   * Emit event to all subscribers
   */
  emit(eventType, data = null) {
    const observers = this.observers.get(eventType);
    if (!observers || observers.size === 0) {
      return;
    }


    // Execute callbacks immediately for synchronous events
    for (const callback of observers) {
      try {
        callback(data);
      } catch (error) {
        logger.error(`[EventObserver] Error in callback for '${eventType}':`, error);
      }
    }
  }

  /**
   * Get number of observers for event type
   */
  getObserverCount(eventType) {
    const observers = this.observers.get(eventType);
    return observers ? observers.size : 0;
  }
}

class StateObserver {
  constructor() {
    this.state = new Map();
    this.watchers = new Map();
    this.computedProperties = new Map();
  }

  /**
   * Set state value and notify watchers
   */
  setState(key, value) {
    const oldValue = this.state.get(key);

    // Only update if value changed
    if (oldValue !== value) {
      this.state.set(key, value);
      this.notifyWatchers(key, value, oldValue);

    }
  }

  /**
   * Get state value
   */
  getState(key) {
    return this.state.get(key);
  }

  /**
   * Watch state changes
   */
  watch(key, callback) {
    if (!this.watchers.has(key)) {
      this.watchers.set(key, new Set());
    }

    const watcherSet = this.watchers.get(key);
    watcherSet.add(callback);


    // Return unwatch function
    return () => {
      watcherSet.delete(callback);
      if (watcherSet.size === 0) {
        this.watchers.delete(key);
      }
    };
  }

  /**
   * Notify all watchers of state change
   */
  notifyWatchers(key, newValue, oldValue) {
    const watchers = this.watchers.get(key);
    if (!watchers) return;

    for (const callback of watchers) {
      try {
        callback(newValue, oldValue, key);
      } catch (error) {
        logger.error(`[StateObserver] Error in watcher for '${key}':`, error);
      }
    }

    // Update computed properties that depend on this key
    this.updateComputedProperties(key);
  }

  /**
   * Define computed property based on other state
   */
  computed(computedKey, dependencies, computeFn) {
    this.computedProperties.set(computedKey, {
      dependencies,
      computeFn,
      cachedValue: undefined,
      isValid: false
    });

    // Watch all dependencies
    dependencies.forEach(dep => {
      this.watch(dep, () => {
        this.invalidateComputed(computedKey);
      });
    });

  }

  /**
   * Get computed property value
   */
  getComputed(computedKey) {
    const computed = this.computedProperties.get(computedKey);
    if (!computed) return undefined;

    if (!computed.isValid) {
      // Recompute value
      const dependencyValues = computed.dependencies.map(dep => this.getState(dep));
      computed.cachedValue = computed.computeFn(...dependencyValues);
      computed.isValid = true;

    }

    return computed.cachedValue;
  }

  /**
   * Invalidate computed property
   */
  invalidateComputed(computedKey) {
    const computed = this.computedProperties.get(computedKey);
    if (computed) {
      computed.isValid = false;
    }
  }

  /**
   * Update computed properties that depend on changed key
   */
  updateComputedProperties(changedKey) {
    for (const [computedKey, computed] of this.computedProperties.entries()) {
      if (computed.dependencies.includes(changedKey)) {
        this.invalidateComputed(computedKey);
      }
    }
  }
}

class ConditionWaiter {
  constructor() {
    this.conditions = new Map();
    this.checkInterval = null;
  }

  /**
   * Wait for condition to be true - replaces setTimeout polling
   */
  waitFor(conditionName, checkFunction, options = {}) {
    const {
      immediate = true,
      checkInterval = 100,
      onConditionMet,
      onConditionChanged
    } = options;

    return new Promise((resolve, reject) => {
      const conditionData = {
        checkFunction,
        resolve,
        reject,
        onConditionMet,
        onConditionChanged,
        lastResult: null
      };

      this.conditions.set(conditionName, conditionData);


      // Check immediately if requested
      if (immediate) {
        this.checkCondition(conditionName);
      }

      // Start checking if not already running
      if (!this.checkInterval) {
        this.startChecking(checkInterval);
      }
    });
  }

  /**
   * Check single condition
   */
  checkCondition(conditionName) {
    const condition = this.conditions.get(conditionName);
    if (!condition) return;

    try {
      const result = condition.checkFunction();
      const changed = result !== condition.lastResult;
      condition.lastResult = result;

      if (changed && condition.onConditionChanged) {
        condition.onConditionChanged(result);
      }

      if (result) {

        if (condition.onConditionMet) {
          condition.onConditionMet();
        }

        condition.resolve(result);
        this.conditions.delete(conditionName);

        // Stop checking if no more conditions
        if (this.conditions.size === 0) {
          this.stopChecking();
        }
      }
    } catch (error) {
      logger.error(`[ConditionWaiter] Error checking condition '${conditionName}':`, error);
      condition.reject(error);
      this.conditions.delete(conditionName);

      if (this.conditions.size === 0) {
        this.stopChecking();
      }
    }
  }

  /**
   * Start periodic checking
   */
  startChecking(interval) {
    if (this.checkInterval) return;


    this.checkInterval = setInterval(() => {
      for (const conditionName of this.conditions.keys()) {
        this.checkCondition(conditionName);
      }
    }, interval);
  }

  /**
   * Stop periodic checking
   */
  stopChecking() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
    }
  }

  /**
   * Cancel waiting for specific condition
   */
  cancel(conditionName) {
    const condition = this.conditions.get(conditionName);
    if (condition) {
      condition.reject(new Error(`Condition '${conditionName}' was cancelled`));
      this.conditions.delete(conditionName);

      if (this.conditions.size === 0) {
        this.stopChecking();
      }
    }
  }

  /**
   * Cancel all conditions
   */
  cancelAll() {
    for (const [_conditionName, condition] of this.conditions.entries()) {
      condition.reject(new Error('All conditions cancelled'));
    }

    this.conditions.clear();
    this.stopChecking();
  }
}

class ResourceMonitor {
  constructor() {
    this.resources = new Map();
    this.subscribers = new Map();
  }

  /**
   * Monitor resource availability
   */
  monitor(resourceName, checkFunction, options = {}) {
    const {
      checkInterval = 1000,
      onAvailable,
      onUnavailable,
      onStateChange
    } = options;

    const resourceData = {
      checkFunction,
      lastState: null,
      isAvailable: false,
      onAvailable,
      onUnavailable,
      onStateChange,
      checkInterval
    };

    this.resources.set(resourceName, resourceData);

    // Start monitoring
    this.startMonitoring(resourceName);


    return () => this.stopMonitoring(resourceName);
  }

  /**
   * Start monitoring specific resource
   */
  startMonitoring(resourceName) {
    const resource = this.resources.get(resourceName);
    if (!resource) return;

    // Check immediately
    this.checkResource(resourceName);

    // Set up periodic checking
    const interval = setInterval(() => {
      this.checkResource(resourceName);
    }, resource.checkInterval);

    resource.interval = interval;
  }

  /**
   * Stop monitoring resource
   */
  stopMonitoring(resourceName) {
    const resource = this.resources.get(resourceName);
    if (resource?.interval) {
      clearInterval(resource.interval);
    }

    this.resources.delete(resourceName);
  }

  /**
   * Check single resource
   */
  async checkResource(resourceName) {
    const resource = this.resources.get(resourceName);
    if (!resource) return;

    try {
      const isAvailable = await resource.checkFunction();
      const stateChanged = isAvailable !== resource.lastState;

      if (stateChanged) {
        resource.lastState = isAvailable;
        resource.isAvailable = isAvailable;


        if (resource.onStateChange) {
          resource.onStateChange(isAvailable);
        }

        if (isAvailable && resource.onAvailable) {
          resource.onAvailable();
        } else if (!isAvailable && resource.onUnavailable) {
          resource.onUnavailable();
        }
      }
    } catch (error) {
      logger.error(`[ResourceMonitor] Error checking resource '${resourceName}':`, error);

      if (resource.lastState !== false) {
        resource.lastState = false;
        resource.isAvailable = false;

        if (resource.onUnavailable) {
          resource.onUnavailable();
        }
      }
    }
  }

  /**
   * Get current resource state
   */
  getResourceState(resourceName) {
    const resource = this.resources.get(resourceName);
    return resource ? resource.isAvailable : null;
  }
}

// Global instances
export const eventObserver = new EventObserver();
export const stateObserver = new StateObserver();
export const conditionWaiter = new ConditionWaiter();
export const resourceMonitor = new ResourceMonitor();

// Convenience functions to replace common setTimeout patterns

/**
 * Replace setTimeout with condition waiting
 */
export function waitForCondition(checkFn, options = {}) {
  const conditionName = `condition_${Date.now()}_${Math.random()}`;
  return conditionWaiter.waitFor(conditionName, checkFn, options);
}

/**
 * Replace setInterval with resource monitoring
 */
export function monitorResource(resourceName, checkFn, options = {}) {
  return resourceMonitor.monitor(resourceName, checkFn, options);
}

/**
 * Replace setTimeout delay with immediate execution based on state
 */
export function executeWhenReady(stateName, callback) {
  const currentValue = stateObserver.getState(stateName);

  if (currentValue) {
    // Execute immediately
    callback(currentValue);
  } else {
    // Wait for state to become truthy
    const unwatch = stateObserver.watch(stateName, (newValue) => {
      if (newValue) {
        callback(newValue);
        unwatch(); // One-time execution
      }
    });
  }
}

/**
 * Replace polling with event emission
 */
export function emitWhenReady(eventName, checkFn, data = null) {
  if (checkFn()) {
    eventObserver.emit(eventName, data);
  } else {
    // Wait for condition and then emit
    waitForCondition(checkFn).then(() => {
      eventObserver.emit(eventName, data);
    });
  }
}

export default {
  eventObserver,
  stateObserver,
  conditionWaiter,
  resourceMonitor,
  waitForCondition,
  monitorResource,
  executeWhenReady,
  emitWhenReady
};
