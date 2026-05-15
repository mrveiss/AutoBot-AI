// AutoBot Cache Management Utility
// Comprehensive browser cache clearing and management

import { createLogger } from '@/utils/debugUtils';

// Create scoped logger for CacheManager
const logger = createLogger('CacheManager');

export interface CacheStats {
  localStorage: number;
  sessionStorage: number;
  indexedDB: boolean;
  serviceWorker: boolean;
  apiCache: number;
  buildVersion: string;
}

export class CacheManager {
  private static instance: CacheManager;
  private readonly BUILD_VERSION_KEY = 'autobot_build_version';
  private readonly API_CACHE_PREFIX = 'autobot_api_';
  private readonly CONFIG_CACHE_PREFIX = 'autobot_config_';

  private constructor() {}

  public static getInstance(): CacheManager {
    if (!CacheManager.instance) {
      CacheManager.instance = new CacheManager();
    }
    return CacheManager.instance;
  }

  /**
   * Clear all browser caches comprehensively
   */
  public async clearAllCaches(): Promise<void> {

    const clearPromises: Promise<void>[] = [];

    // Clear localStorage
    clearPromises.push(this.clearLocalStorage());

    // Clear sessionStorage
    clearPromises.push(this.clearSessionStorage());

    // Clear IndexedDB
    clearPromises.push(this.clearIndexedDB());

    // Clear service worker caches
    clearPromises.push(this.clearServiceWorkerCaches());

    // Clear API caches
    clearPromises.push(this.clearApiCaches());

    // Wait for all clearing operations
    await Promise.allSettled(clearPromises);

    // Force browser cache refresh
    if ('caches' in window) {
      try {
        const cacheNames = await caches.keys();
        await Promise.all(
          cacheNames.map(name => caches.delete(name))
        );
      } catch (error) {
        logger.warn('Failed to clear browser caches:', error);
      }
    }

  }

  /**
   * Clear localStorage with selective preservation
   */
  public async clearLocalStorage(): Promise<void> {
    try {
      const keysToPreserve = [
        'autobot_user_preferences',
        'autobot_theme_settings'
      ];

      const preservedData: Record<string, string> = {};
      keysToPreserve.forEach(key => {
        const value = localStorage.getItem(key);
        if (value) {
          preservedData[key] = value;
        }
      });

      // Clear everything
      localStorage.clear();

      // Restore preserved data
      Object.entries(preservedData).forEach(([key, value]) => {
        localStorage.setItem(key, value);
      });

    } catch (error) {
      logger.warn('Failed to clear localStorage:', error);
    }
  }

  /**
   * Clear sessionStorage completely
   */
  public async clearSessionStorage(): Promise<void> {
    try {
      sessionStorage.clear();
    } catch (error) {
      logger.warn('Failed to clear sessionStorage:', error);
    }
  }

  /**
   * Clear IndexedDB databases
   */
  public async clearIndexedDB(): Promise<void> {
    if (!('indexedDB' in window)) {
      return;
    }

    try {
      // Get all databases and delete AutoBot related ones
      const databases = await indexedDB.databases();
      const deletePromises = databases
        .filter(db => db.name?.includes('autobot'))
        .map(db => {
          return new Promise<void>((resolve, reject) => {
            const deleteRequest = indexedDB.deleteDatabase(db.name!);
            deleteRequest.onsuccess = () => resolve();
            deleteRequest.onerror = () => reject(deleteRequest.error);
          });
        });

      await Promise.all(deletePromises);
    } catch (error) {
      logger.warn('Failed to clear IndexedDB:', error);
    }
  }

  /**
   * Clear service worker caches
   */
  public async clearServiceWorkerCaches(): Promise<void> {
    if (!('serviceWorker' in navigator)) {
      return;
    }

    try {
      const registration = await navigator.serviceWorker.ready;
      if (registration.active) {
        // Send message to service worker to clear caches
        const messageChannel = new MessageChannel();
        const clearPromise = new Promise<void>((resolve) => {
          messageChannel.port1.onmessage = () => resolve();
        });

        registration.active.postMessage(
          { type: 'CLEAR_CACHE' },
          [messageChannel.port2]
        );

        await clearPromise;
      }
    } catch (error) {
      logger.warn('Failed to clear service worker caches:', error);
    }
  }

  /**
   * Clear API response caches
   */
  public async clearApiCaches(): Promise<void> {
    try {
      // Clear localStorage API caches
      const keys = Object.keys(localStorage);
      keys.forEach(key => {
        if (key.startsWith(this.API_CACHE_PREFIX) || key.startsWith(this.CONFIG_CACHE_PREFIX)) {
          localStorage.removeItem(key);
        }
      });

      // Clear sessionStorage API caches
      const sessionKeys = Object.keys(sessionStorage);
      sessionKeys.forEach(key => {
        if (key.startsWith(this.API_CACHE_PREFIX) || key.startsWith(this.CONFIG_CACHE_PREFIX)) {
          sessionStorage.removeItem(key);
        }
      });

    } catch (error) {
      logger.warn('Failed to clear API caches:', error);
    }
  }

  /**
   * Check if cache clearing is needed (version mismatch)
   */
  public needsCacheClearing(): boolean {
    const currentVersion = import.meta.env.VITE_APP_VERSION || 'dev';
    const storedVersion = localStorage.getItem(this.BUILD_VERSION_KEY);

    if (!storedVersion || storedVersion !== currentVersion) {
      logger.info('Version mismatch detected:', {
        current: currentVersion,
        stored: storedVersion
      });
      return true;
    }

    return false;
  }

  /**
   * Update stored build version
   */
  public updateBuildVersion(): void {
    const currentVersion = import.meta.env.VITE_APP_VERSION || 'dev';
    localStorage.setItem(this.BUILD_VERSION_KEY, currentVersion);
  }

  /**
   * Get cache statistics
   */
  public async getCacheStats(): Promise<CacheStats> {
    const stats: CacheStats = {
      localStorage: this.calculateStorageSize(localStorage),
      sessionStorage: this.calculateStorageSize(sessionStorage),
      indexedDB: 'indexedDB' in window,
      serviceWorker: 'serviceWorker' in navigator,
      apiCache: this.countApiCacheEntries(),
      buildVersion: localStorage.getItem(this.BUILD_VERSION_KEY) || 'unknown'
    };

    return stats;
  }

  /**
   * Calculate storage size in bytes
   */
  private calculateStorageSize(storage: Storage): number {
    let size = 0;
    for (const key in storage) {
      if (storage.hasOwnProperty(key)) {
        size += key.length + (storage[key]?.length || 0);
      }
    }
    return size;
  }

  /**
   * Count API cache entries
   */
  private countApiCacheEntries(): number {
    let count = 0;
    const keys = Object.keys(localStorage);
    keys.forEach(key => {
      if (key.startsWith(this.API_CACHE_PREFIX) || key.startsWith(this.CONFIG_CACHE_PREFIX)) {
        count++;
      }
    });
    return count;
  }

  /**
   * Force hard refresh of the page
   */
  public forceHardRefresh(): void {

    // Clear caches before refresh
    this.clearAllCaches().then(() => {
      // Force hard refresh
      if ('location' in window) {
        window.location.reload();
      }
    });
  }

  /**
   * Initialize cache management on app startup
   */
  public async initialize(): Promise<void> {

    // Check if cache clearing is needed
    if (this.needsCacheClearing()) {
      await this.clearAllCaches();
      this.updateBuildVersion();
    }

    // Prefetch cache stats to trigger any lazy initialization
    await this.getCacheStats();
  }
}

// Export singleton instance
export const cacheManager = CacheManager.getInstance();
