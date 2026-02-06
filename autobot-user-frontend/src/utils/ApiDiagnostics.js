/**
 * API Diagnostics Tool - Comprehensive API endpoint testing and verification
 * This tool helps diagnose API connectivity issues and verifies endpoint functionality
 */

import apiClient from './ApiClient.js';
import apiMapper from './ApiEndpointMapper.js';

class ApiDiagnostics {
  constructor() {
    this.testResults = new Map();
    this.backendStatus = 'unknown';
    this.criticalEndpoints = [
      '/api/system/health',
      '/api/chat',
      '/api/chats',
      '/api/settings/',
      '/api/prompts/',
      '/api/knowledge_base/search'
    ];
  }

  /**
   * Run comprehensive API diagnostics
   */
  async runComprehensiveDiagnostics() {

    const results = {
      timestamp: new Date().toISOString(),
      backendConnectivity: await this.checkBackendConnectivity(),
      endpointTests: await this.testCriticalEndpoints(),
      mappingValidation: this.validateApiMappings(),
      recommendations: []
    };

    // Generate recommendations based on results
    results.recommendations = this.generateRecommendations(results);

    return results;
  }

  /**
   * Check basic backend connectivity
   */
  async checkBackendConnectivity() {

    const connectivity = {
      baseUrl: apiClient.getBaseUrl(),
      reachable: false,
      responseTime: null,
      error: null
    };

    try {
      const startTime = performance.now();

      // Try to use ApiClient's hello method first
      try {
        const response = await apiClient.get('/api/hello');
        connectivity.responseTime = Math.round(performance.now() - startTime);
        connectivity.reachable = true;
        connectivity.status = response.status;

        if (response.data) {
          connectivity.message = response.data.message;
        }
      } catch (_helloError) {
        // Fallback to health endpoint
        await apiClient.getSystemHealth();
        connectivity.responseTime = Math.round(performance.now() - startTime);
        connectivity.reachable = true;
        connectivity.alternativeEndpoint = '/api/system/health';
        connectivity.status = 200;
      }

    } catch (error) {
      connectivity.error = error.message;
      connectivity.reachable = false;
      connectivity.responseTime = Math.round(performance.now() - startTime);
    }

    this.backendStatus = connectivity.reachable ? 'online' : 'offline';
    return connectivity;
  }

  /**
   * Test critical API endpoints
   */
  async testCriticalEndpoints() {

    const endpointResults = [];

    for (const endpoint of this.criticalEndpoints) {

      const testResult = {
        endpoint,
        method: 'GET',
        success: false,
        responseTime: null,
        status: null,
        error: null,
        cached: false
      };

      try {
        const startTime = performance.now();
        const response = await apiClient.get(endpoint);
        testResult.responseTime = Math.round(performance.now() - startTime);
        testResult.success = true;
        testResult.status = response.status || 200;
        testResult.cached = response.headers && response.headers.get('x-cache') === 'hit';

        // ApiClient already parses JSON, so we can access data directly
        if (response.data) {
          testResult.dataKeys = Object.keys(response.data).slice(0, 5); // First 5 keys for verification
        } else if (response.message) {
          testResult.dataKeys = ['message'];
        }

      } catch (error) {
        testResult.error = error.message;
        testResult.success = false;

        // Additional error classification
        if (error.message.includes('timeout')) {
          testResult.errorType = 'timeout';
        } else if (error.message.includes('Network error')) {
          testResult.errorType = 'network';
        } else if (error.message.includes('HTTP 404')) {
          testResult.errorType = 'not_found';
        } else if (error.message.includes('HTTP 500')) {
          testResult.errorType = 'server_error';
        } else {
          testResult.errorType = 'unknown';
        }
      }

      endpointResults.push(testResult);
    }

    return endpointResults;
  }

  /**
   * Validate API mappings against actual endpoints
   */
  validateApiMappings() {

    const validation = {
      totalMappings: 0,
      validMappings: 0,
      invalidMappings: 0,
      issues: []
    };

    const mappingReport = apiMapper.generateMappingReport();
    validation.totalMappings = mappingReport.mappings.length;

    // Check each mapping
    for (const mapping of mappingReport.mappings) {
      let hasValidEndpoints = false;

      for (const endpoint of mapping.endpoints) {
        if (this.isValidEndpoint(endpoint)) {
          hasValidEndpoints = true;
        } else {
          validation.issues.push({
            component: mapping.component,
            endpoint,
            issue: 'Endpoint pattern may not match actual API'
          });
        }
      }

      if (hasValidEndpoints) {
        validation.validMappings++;
      } else {
        validation.invalidMappings++;
        validation.issues.push({
          component: mapping.component,
          issue: 'No valid endpoints found for component'
        });
      }
    }

    return validation;
  }

  /**
   * Check if an endpoint pattern is valid
   */
  isValidEndpoint(endpoint) {
    // Basic validation - check if it looks like a valid API endpoint
    if (!endpoint.startsWith('/api/')) return false;
    if (endpoint === '*') return true; // Wildcard is valid

    // Check against known valid patterns
    const validPatterns = [
      /^\/api\/[a-z_-]+$/,                    // /api/endpoint
      /^\/api\/[a-z_-]+\/[a-z_-]+$/,         // /api/category/endpoint
      /^\/api\/[a-z_-]+\/\{[a-z_]+\}$/,      // /api/endpoint/{param}
      /^\/api\/[a-z_-]+\/[a-z_-]+\/\{[a-z_]+\}$/ // /api/category/endpoint/{param}
    ];

    return validPatterns.some(pattern => pattern.test(endpoint));
  }

  /**
   * Generate recommendations based on diagnostic results
   */
  generateRecommendations(results) {
    const recommendations = [];

    // Backend connectivity recommendations
    if (!results.backendConnectivity.reachable) {
      recommendations.push({
        priority: 'critical',
        category: 'connectivity',
        issue: 'Backend server is not reachable',
        recommendation: 'Start the backend server using ./run_agent.sh',
        command: './run_agent.sh'
      });
    } else if (results.backendConnectivity.responseTime > 2000) {
      recommendations.push({
        priority: 'medium',
        category: 'performance',
        issue: `Slow backend response time: ${results.backendConnectivity.responseTime}ms`,
        recommendation: 'Check backend server performance and resources'
      });
    }

    // Endpoint-specific recommendations
    const failedEndpoints = results.endpointTests.filter(test => !test.success);

    if (failedEndpoints.length > 0) {
      const criticalFailures = failedEndpoints.filter(test =>
        ['chat', 'chats', 'settings', 'system'].some(critical =>
          test.endpoint.includes(critical)
        )
      );

      if (criticalFailures.length > 0) {
        recommendations.push({
          priority: 'high',
          category: 'functionality',
          issue: `Critical endpoints failing: ${criticalFailures.map(f => f.endpoint).join(', ')}`,
          recommendation: 'Check backend API implementation for missing routes'
        });
      }

      // Timeout-specific recommendations
      const timeoutFailures = failedEndpoints.filter(test => test.errorType === 'timeout');
      if (timeoutFailures.length > 0) {
        recommendations.push({
          priority: 'medium',
          category: 'performance',
          issue: `Endpoints timing out: ${timeoutFailures.map(f => f.endpoint).join(', ')}`,
          recommendation: 'Increase timeout values or optimize backend endpoint performance'
        });
      }

      // 404 Not Found recommendations
      const notFoundFailures = failedEndpoints.filter(test => test.errorType === 'not_found');
      if (notFoundFailures.length > 0) {
        recommendations.push({
          priority: 'high',
          category: 'configuration',
          issue: `Endpoints not found: ${notFoundFailures.map(f => f.endpoint).join(', ')}`,
          recommendation: 'Verify backend API routes are properly registered'
        });
      }
    }

    // Mapping validation recommendations
    if (results.mappingValidation.invalidMappings > 0) {
      recommendations.push({
        priority: 'low',
        category: 'documentation',
        issue: `${results.mappingValidation.invalidMappings} invalid API mappings found`,
        recommendation: 'Update API mapping documentation to match actual endpoints'
      });
    }

    // Cache performance recommendations
    const cachedTests = results.endpointTests.filter(test => test.cached);
    if (cachedTests.length === 0 && results.endpointTests.some(test => test.success)) {
      recommendations.push({
        priority: 'low',
        category: 'performance',
        issue: 'No API responses are being cached',
        recommendation: 'Verify API client caching is working correctly'
      });
    }

    return recommendations;
  }

  /**
   * Test a specific component's API integration
   */
  async testComponentIntegration(componentName) {

    const endpoints = apiMapper.getEndpointsForComponent(componentName);
    const functions = apiMapper.getFunctionsForComponent(componentName);

    const componentTest = {
      component: componentName,
      endpoints,
      functions,
      endpointTests: []
    };

    // Test each endpoint used by this component
    for (const endpoint of endpoints) {
      if (endpoint === '*') continue; // Skip wildcard endpoints

      try {
        const startTime = performance.now();
        const response = await apiClient.get(endpoint);
        const responseTime = Math.round(performance.now() - startTime);

        componentTest.endpointTests.push({
          endpoint,
          success: true,
          responseTime,
          status: response.status || 200
        });

      } catch (error) {
        componentTest.endpointTests.push({
          endpoint,
          success: false,
          error: error.message
        });
      }
    }

    return componentTest;
  }

  /**
   * Generate a quick health report
   */
  async quickHealthCheck() {

    const health = {
      overall: 'unknown',
      backend: 'unknown',
      criticalEndpoints: 'unknown',
      timestamp: new Date().toISOString()
    };

    try {
      // Test basic connectivity
      const connectivity = await this.checkBackendConnectivity();
      health.backend = connectivity.reachable ? 'healthy' : 'unhealthy';

      // Test a few critical endpoints quickly
      const criticalTests = await Promise.allSettled([
        apiClient.getSystemHealth().catch(e => ({ error: e.message })),
        apiClient.getChatList().catch(e => ({ error: e.message })),
        apiClient.getSettings().catch(e => ({ error: e.message }))
      ]);

      const successfulTests = criticalTests.filter(result =>
        result.status === 'fulfilled' && !result.value.error
      );

      health.criticalEndpoints = successfulTests.length >= 2 ? 'healthy' : 'unhealthy';

      // Overall health
      if (health.backend === 'healthy' && health.criticalEndpoints === 'healthy') {
        health.overall = 'healthy';
      } else if (health.backend === 'healthy') {
        health.overall = 'degraded';
      } else {
        health.overall = 'unhealthy';
      }

    } catch (error) {
      health.overall = 'unhealthy';
      health.error = error.message;
    }

    return health;
  }

  /**
   * Export diagnostic results for sharing or debugging
   */
  exportDiagnostics(results, format = 'json') {
    switch (format) {
      case 'json':
        return JSON.stringify(results, null, 2);

      case 'text':
        let text = '=== API Diagnostics Report ===\n\n';
        text += `Timestamp: ${results.timestamp}\n`;
        text += `Backend Status: ${results.backendConnectivity.reachable ? 'Online' : 'Offline'}\n`;
        text += `Response Time: ${results.backendConnectivity.responseTime || 'N/A'}ms\n\n`;

        text += '=== Endpoint Tests ===\n';
        for (const test of results.endpointTests) {
          text += `${test.endpoint}: ${test.success ? 'PASS' : 'FAIL'}`;
          if (test.error) text += ` (${test.error})`;
          text += '\n';
        }

        text += '\n=== Recommendations ===\n';
        for (const rec of results.recommendations) {
          text += `[${rec.priority.toUpperCase()}] ${rec.issue}\n`;
          text += `  → ${rec.recommendation}\n\n`;
        }

        return text;

      default:
        return results;
    }
  }
}

// Create singleton instance
const apiDiagnostics = new ApiDiagnostics();

// Make available globally for debugging
if (typeof window !== 'undefined') {
  window.apiDiagnostics = apiDiagnostics;
  window.runApiDiagnostics = () => apiDiagnostics.runComprehensiveDiagnostics();
  window.quickApiHealth = () => apiDiagnostics.quickHealthCheck();
  window.testComponentApi = (component) => apiDiagnostics.testComponentIntegration(component);
}

export default apiDiagnostics;
