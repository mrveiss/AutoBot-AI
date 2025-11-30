/**
 * ConfigTester - Test harness for AppConfig service
 * Used to validate all service URLs are working correctly
 */

import appConfig from './AppConfig.js';
import { createLogger } from '@/utils/debugUtils';

const logger = createLogger('ConfigTester');

export class ConfigTester {
  constructor() {
    this.results = {};
  }

  /**
   * Test all service URL resolution
   */
  async testAllServiceUrls() {
    logger.debug('Testing all service URL resolution...');
    
    const services = [
      'backend',
      'redis', 
      'vnc_desktop',
      'vnc_terminal',
      'vnc_playwright',
      'npu_worker',
      'ollama',
      'playwright'
    ];

    const results = {};
    
    for (const service of services) {
      try {
        const startTime = Date.now();
        const url = await appConfig.getServiceUrl(service);
        const endTime = Date.now();
        
        results[service] = {
          success: true,
          url: url,
          responseTime: endTime - startTime
        };
        
        logger.debug(`✅ ${service}: ${url} (${endTime - startTime}ms)`);
      } catch (error) {
        results[service] = {
          success: false,
          error: error.message,
          responseTime: null
        };
        
        logger.debug(`❌ ${service}: ${error.message}`);
      }
    }

    this.results.serviceUrls = results;
    return results;
  }

  /**
   * Test VNC URL generation with different options
   */
  async testVncUrls() {
    logger.debug('Testing VNC URL generation...');
    
    const vncTypes = ['desktop', 'terminal', 'playwright'];
    const results = {};
    
    for (const type of vncTypes) {
      try {
        const startTime = Date.now();
        
        // Test default options
        const defaultUrl = await appConfig.getVncUrl(type);
        
        // Test custom options
        const customUrl = await appConfig.getVncUrl(type, {
          quality: '6',
          compression: '5',
          extraParams: { test: 'custom' }
        });
        
        const endTime = Date.now();
        
        results[type] = {
          success: true,
          defaultUrl: defaultUrl,
          customUrl: customUrl,
          responseTime: endTime - startTime
        };
        
        logger.debug(`✅ VNC ${type}:`);
        logger.debug(`   Default: ${defaultUrl}`);
        logger.debug(`   Custom:  ${customUrl}`);
        logger.debug(`   Time: ${endTime - startTime}ms`);
        
      } catch (error) {
        results[type] = {
          success: false,
          error: error.message
        };
        
        logger.debug(`❌ VNC ${type}: ${error.message}`);
      }
    }

    this.results.vncUrls = results;
    return results;
  }

  /**
   * Test API URL generation with cache busting
   */
  async testApiUrls() {
    logger.debug('Testing API URL generation...');
    
    const endpoints = [
      '/api/health',
      '/api/chat/chats',
      '/api/knowledge_base/stats',
      '/api/settings'
    ];
    
    const results = {};
    
    for (const endpoint of endpoints) {
      try {
        const startTime = Date.now();
        
        // Test default cache busting
        const defaultUrl = await appConfig.getApiUrl(endpoint);
        
        // Test without cache busting
        const noCacheUrl = await appConfig.getApiUrl(endpoint, { cacheBust: false });
        
        const endTime = Date.now();
        
        results[endpoint] = {
          success: true,
          defaultUrl: defaultUrl,
          noCacheUrl: noCacheUrl,
          responseTime: endTime - startTime
        };
        
        logger.debug(`✅ API ${endpoint}:`);
        logger.debug(`   With cache bust: ${defaultUrl}`);
        logger.debug(`   No cache bust:   ${noCacheUrl}`);
        
      } catch (error) {
        results[endpoint] = {
          success: false,
          error: error.message
        };
        
        logger.debug(`❌ API ${endpoint}: ${error.message}`);
      }
    }

    this.results.apiUrls = results;
    return results;
  }

  /**
   * Test configuration value retrieval
   */
  testConfigValues() {
    logger.debug('Testing configuration value retrieval...');
    
    const testPaths = [
      'api.timeout',
      'features.enableDebug', 
      'features.enableRum',
      'environment.isDev',
      'services.backend.host',
      'nonexistent.path'
    ];
    
    const results = {};
    
    testPaths.forEach(path => {
      try {
        const value = appConfig.get(path);
        results[path] = {
          success: true,
          value: value,
          type: typeof value
        };
        
        logger.debug(`✅ Config ${path}: ${JSON.stringify(value)} (${typeof value})`);
      } catch (error) {
        results[path] = {
          success: false,
          error: error.message
        };
        
        logger.debug(`❌ Config ${path}: ${error.message}`);
      }
    });

    this.results.configValues = results;
    return results;
  }

  /**
   * Test feature flags
   */
  testFeatureFlags() {
    logger.debug('Testing feature flags...');
    
    const features = [
      'enableDebug',
      'enableRum', 
      'enableWebSockets',
      'enableVncDesktop',
      'enableNpuWorker',
      'nonexistentFeature'
    ];
    
    const results = {};
    
    features.forEach(feature => {
      try {
        const enabled = appConfig.isFeatureEnabled(feature);
        results[feature] = {
          success: true,
          enabled: enabled
        };
        
        logger.debug(`✅ Feature ${feature}: ${enabled ? 'ENABLED' : 'DISABLED'}`);
      } catch (error) {
        results[feature] = {
          success: false,
          error: error.message
        };
        
        logger.debug(`❌ Feature ${feature}: ${error.message}`);
      }
    });

    this.results.featureFlags = results;
    return results;
  }

  /**
   * Run all tests
   */
  async runAllTests() {
    logger.debug('🧪 Running comprehensive configuration tests...');
    
    const startTime = Date.now();
    
    try {
      await this.testAllServiceUrls();
      
      await this.testVncUrls();
      
      await this.testApiUrls();
      
      this.testConfigValues();
      
      this.testFeatureFlags();
      
      const endTime = Date.now();
      
      logger.debug(`✅ All tests completed in ${endTime - startTime}ms`);
      logger.debug('📊 Test results:', this.results);
      
      return {
        success: true,
        totalTime: endTime - startTime,
        results: this.results
      };
      
    } catch (error) {
      logger.error('❌ Test suite failed:', error);
      return {
        success: false,
        error: error.message,
        results: this.results
      };
    }
  }

  /**
   * Get test summary
   */
  getSummary() {
    const summary = {
      totalTests: 0,
      passedTests: 0,
      failedTests: 0,
      services: {}
    };

    Object.keys(this.results).forEach(category => {
      const categoryResults = this.results[category];
      Object.keys(categoryResults).forEach(test => {
        summary.totalTests++;
        if (categoryResults[test].success) {
          summary.passedTests++;
        } else {
          summary.failedTests++;
        }
      });
      
      summary.services[category] = {
        total: Object.keys(categoryResults).length,
        passed: Object.values(categoryResults).filter(r => r.success).length,
        failed: Object.values(categoryResults).filter(r => !r.success).length
      };
    });

    return summary;
  }
}

// Export singleton instance
export const configTester = new ConfigTester();

// Auto-run tests in development mode
if (import.meta.env.DEV && typeof window !== 'undefined') {
  // Run tests after a short delay to ensure DOM is ready
  setTimeout(() => {
    if (window.location.search.includes('test-config')) {
      configTester.runAllTests();
    }
  }, 1000);
}

export default configTester;