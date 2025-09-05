/**
 * API Endpoint Mapper - Comprehensive mapping of GUI elements to API endpoints
 * This creates a centralized registry of which frontend components/functions use which backend endpoints
 */

class ApiEndpointMapper {
  constructor() {
    this.mappings = new Map();
    this.reverseMappings = new Map(); // endpoint -> components
    this.usageStats = new Map();
    this.setupMappings();
  }

  setupMappings() {
    // Define comprehensive mappings between frontend components/functions and their API endpoints
    this.registerMapping({
      component: 'App.vue',
      functions: ['mounted', 'checkHealth', 'loadUserData'],
      endpoints: ['/api/system/health', '/api/user/profile'],
      description: 'Main app initialization and health checks'
    });

    this.registerMapping({
      component: 'ChatInterface.vue',
      functions: [
        'sendMessage', 'getChatHistory', 'createNewChat', 'deleteChat',
        'saveChatMessages', 'loadChatList', 'resetChat'
      ],
      endpoints: [
        '/api/chat',
        '/api/chat/chats',
        '/api/chat/chats/new',
        '/api/chat/chats/{chat_id}',
        '/api/chat/chats/{chat_id}/save',
        '/api/chat/chats/{chat_id}/reset',
        '/api/reset'
      ],
      description: 'All chat-related operations'
    });

    this.registerMapping({
      component: 'KnowledgeManager.vue',
      functions: [
        'performSearch', 'searchKnowledge', 'addTextToKnowledge', 'addUrlToKnowledge',
        'addFileToKnowledge', 'exportKnowledge', 'cleanupKnowledge', 'getKnowledgeStats',
        'getDetailedKnowledgeStats', 'loadKnowledgeEntries'
      ],
      endpoints: [
        '/api/knowledge_base/search',
        '/api/knowledge_base/add_text',
        '/api/knowledge_base/add_url',
        '/api/knowledge_base/add_file',
        '/api/knowledge_base/export',
        '/api/knowledge_base/cleanup',
        '/api/knowledge_base/stats',
        '/api/knowledge_base/detailed_stats',
        '/api/knowledge_base/entries'
      ],
      description: 'Knowledge base management and search functionality'
    });

    this.registerMapping({
      component: 'SettingsPanel.vue',
      functions: [
        'loadSettingsFromBackend', 'saveSettings', 'getSettings', 'saveBackendSettings',
        'loadPrompts', 'savePrompt', 'revertPrompt', 'loadModels'
      ],
      endpoints: [
        '/api/settings/',
        '/api/settings/config',
        '/api/settings/backend',
        '/api/prompts/',
        '/api/prompts/{prompt_id}',
        '/api/prompts/{prompt_id}/revert',
        '/api/llm/models',
        '/api/llm/status/comprehensive'
      ],
      description: 'Settings configuration and prompt management'
    });

    this.registerMapping({
      component: 'SystemMonitor.vue',
      functions: [
        'checkHealth', 'getSystemMetrics', 'getPerformanceData',
        'loadSystemStats', 'refreshMetrics'
      ],
      endpoints: [
        '/api/system/health',
        '/api/system/health/{component}',
        '/api/system/metrics',
        '/api/system/info',
        '/api/metrics/{metric_type}'
      ],
      description: 'System health and performance monitoring'
    });

    this.registerMapping({
      component: 'SecretsManager.vue',
      functions: [
        'loadSecrets', 'saveSecret', 'deleteSecret', 'updateSecret',
        'getChatSecrets', 'transferSecrets', 'cleanupSecrets'
      ],
      endpoints: [
        '/api/secrets',
        '/api/secrets/{secret_id}',
        '/api/secrets/chat/{chat_id}',
        '/api/secrets/chat/{chat_id}/cleanup'
      ],
      description: 'Secrets and credentials management'
    });

    this.registerMapping({
      component: 'FileBrowser.vue',
      functions: [
        'listFiles', 'uploadFile', 'downloadFile', 'deleteFile',
        'viewFile', 'createDirectory', 'getFileStats'
      ],
      endpoints: [
        '/api/files/list',
        '/api/files/upload',
        '/api/files/download/{path}',
        '/api/files/delete',
        '/api/files/view/{path}',
        '/api/files/create_directory',
        '/api/files/stats'
      ],
      description: 'File system operations and management'
    });

    this.registerMapping({
      component: 'TerminalWindow.vue',
      functions: [
        'executeCommand', 'createSession', 'getSession', 'deleteSession',
        'sendInput', 'getSessionHistory'
      ],
      endpoints: [
        '/api/terminal/execute',
        '/api/terminal/sessions',
        '/api/terminal/sessions/{session_id}',
        '/api/terminal/consolidated/sessions',
        '/api/terminal/consolidated/sessions/{session_id}/input'
      ],
      description: 'Terminal command execution and session management'
    });

    this.registerMapping({
      component: 'WorkflowApproval.vue',
      functions: [
        'getWorkflows', 'approveWorkflow', 'rejectWorkflow', 'getWorkflowStatus',
        'executeWorkflow', 'getPendingApprovals'
      ],
      endpoints: [
        '/api/workflow',
        '/api/workflow/{workflow_id}',
        '/api/workflow/{workflow_id}/status',
        '/api/workflow/{workflow_id}/approve',
        '/api/workflow/{workflow_id}/pending_approvals',
        '/api/workflow_automation/start_workflow/{workflow_id}'
      ],
      description: 'Workflow orchestration and approval processes'
    });

    this.registerMapping({
      component: 'ValidationDashboard.vue',
      functions: [
        'loadValidationData', 'runValidation', 'getValidationResults',
        'exportValidationReport'
      ],
      endpoints: [
        '/api/validation-dashboard/data',
        '/api/validation-dashboard/run',
        '/api/validation-dashboard/results',
        '/api/validation-dashboard/export'
      ],
      description: 'System validation and testing dashboard'
    });

    this.registerMapping({
      component: 'RumDashboard.vue',
      functions: [
        'getRumData', 'getPerformanceMetrics', 'getUserJourneys',
        'getErrorLogs', 'exportRumReport'
      ],
      endpoints: [
        '/api/rum/data',
        '/api/rum/metrics',
        '/api/rum/journeys',
        '/api/errors/logs',
        '/api/rum/export'
      ],
      description: 'Real User Monitoring and analytics'
    });

    this.registerMapping({
      component: 'VoiceInterface.vue',
      functions: [
        'startRecording', 'stopRecording', 'processVoice',
        'getVoiceSettings', 'updateVoiceSettings'
      ],
      endpoints: [
        '/api/voice/record',
        '/api/voice/process',
        '/api/voice/settings'
      ],
      description: 'Voice recognition and processing'
    });

    // Core API Client utility mappings
    this.registerMapping({
      component: 'ApiClient.js',
      functions: [
        'request', 'get', 'post', 'put', 'delete',
        'testConnection', 'getApiStatus', 'batchRequest'
      ],
      endpoints: ['*'], // ApiClient can call any endpoint
      description: 'Core API communication layer'
    });

    // Navigation and routing mappings
    this.registerMapping({
      component: 'Navigation',
      functions: ['updateRoute', 'checkTabAccess'],
      endpoints: ['/api/system/health', '/api/user/permissions'],
      description: 'Navigation state and access control'
    });
  }

  /**
   * Register a mapping between frontend component and backend endpoints
   */
  registerMapping({ component, functions = [], endpoints = [], description = '' }) {
    const mapping = {
      component,
      functions,
      endpoints,
      description,
      registeredAt: new Date().toISOString()
    };

    // Store in main mapping
    this.mappings.set(component, mapping);

    // Create reverse mappings (endpoint -> components)
    endpoints.forEach(endpoint => {
      if (!this.reverseMappings.has(endpoint)) {
        this.reverseMappings.set(endpoint, new Set());
      }
      this.reverseMappings.get(endpoint).add(component);
    });

    console.debug(`Registered mapping: ${component} -> ${endpoints.join(', ')}`);
  }

  /**
   * Find which components use a specific endpoint
   */
  getComponentsForEndpoint(endpoint) {
    // Handle parameterized endpoints
    const components = new Set();

    for (const [registeredEndpoint, componentSet] of this.reverseMappings.entries()) {
      if (this.endpointMatches(endpoint, registeredEndpoint)) {
        componentSet.forEach(comp => components.add(comp));
      }
    }

    return Array.from(components);
  }

  /**
   * Get all endpoints used by a specific component
   */
  getEndpointsForComponent(component) {
    const mapping = this.mappings.get(component);
    return mapping ? mapping.endpoints : [];
  }

  /**
   * Get all functions in a component that use APIs
   */
  getFunctionsForComponent(component) {
    const mapping = this.mappings.get(component);
    return mapping ? mapping.functions : [];
  }

  /**
   * Check if an endpoint pattern matches a specific endpoint
   */
  endpointMatches(actualEndpoint, patternEndpoint) {
    if (patternEndpoint === '*') return true;
    if (actualEndpoint === patternEndpoint) return true;

    // Handle parameterized endpoints like /api/chats/{chat_id}
    const pattern = patternEndpoint.replace(/\{[^}]+\}/g, '[^/]+');
    const regex = new RegExp(`^${pattern}$`);
    return regex.test(actualEndpoint);
  }

  /**
   * Track API usage for analytics
   */
  recordUsage(component, endpoint, method = 'GET') {
    const key = `${component}:${endpoint}:${method}`;
    const current = this.usageStats.get(key) || { count: 0, lastUsed: null };

    this.usageStats.set(key, {
      count: current.count + 1,
      lastUsed: new Date().toISOString(),
      component,
      endpoint,
      method
    });
  }

  /**
   * Get comprehensive mapping report
   */
  generateMappingReport() {
    const report = {
      totalComponents: this.mappings.size,
      totalEndpoints: this.reverseMappings.size,
      mappings: [],
      orphanedEndpoints: [], // Endpoints not mapped to any component
      unusedComponents: [], // Components without API mappings
      usage: Array.from(this.usageStats.entries()).map(([key, stats]) => ({
        key,
        ...stats
      }))
    };

    // Build detailed mappings
    for (const [component, mapping] of this.mappings.entries()) {
      report.mappings.push({
        component,
        functionsCount: mapping.functions.length,
        endpointsCount: mapping.endpoints.length,
        description: mapping.description,
        endpoints: mapping.endpoints,
        functions: mapping.functions
      });
    }

    return report;
  }

  /**
   * Validate that all GUI elements have corresponding API endpoints
   */
  validateMappings() {
    const issues = [];

    // Check for missing endpoints
    for (const [component, mapping] of this.mappings.entries()) {
      if (mapping.endpoints.length === 0) {
        issues.push({
          type: 'missing_endpoints',
          component,
          message: `Component ${component} has no API endpoints mapped`
        });
      }

      if (mapping.functions.length === 0) {
        issues.push({
          type: 'missing_functions',
          component,
          message: `Component ${component} has no API functions mapped`
        });
      }
    }

    return issues;
  }

  /**
   * Find potential API endpoint duplications or conflicts
   */
  findEndpointConflicts() {
    const conflicts = [];
    const endpointGroups = new Map();

    // Group similar endpoints
    for (const endpoint of this.reverseMappings.keys()) {
      const baseEndpoint = endpoint.replace(/\{[^}]+\}/g, '{param}');
      if (!endpointGroups.has(baseEndpoint)) {
        endpointGroups.set(baseEndpoint, []);
      }
      endpointGroups.get(baseEndpoint).push(endpoint);
    }

    // Find potential conflicts
    for (const [baseEndpoint, endpoints] of endpointGroups.entries()) {
      if (endpoints.length > 1) {
        conflicts.push({
          basePattern: baseEndpoint,
          variations: endpoints,
          components: endpoints.map(ep => this.getComponentsForEndpoint(ep)).flat()
        });
      }
    }

    return conflicts;
  }

  /**
   * Get mapping information for debugging
   */
  debug(component = null) {
    if (component) {
      const mapping = this.mappings.get(component);
      if (mapping) {
        console.table({
          Component: component,
          Functions: mapping.functions.join(', '),
          Endpoints: mapping.endpoints.join(', '),
          Description: mapping.description
        });
      } else {
        console.warn(`No mapping found for component: ${component}`);
      }
    } else {
      console.log('=== API Endpoint Mappings ===');
      for (const [component, mapping] of this.mappings.entries()) {
        console.group(component);
        console.log('Functions:', mapping.functions);
        console.log('Endpoints:', mapping.endpoints);
        console.log('Description:', mapping.description);
        console.groupEnd();
      }
    }
  }

  /**
   * Export mappings for documentation or analysis
   */
  exportMappings(format = 'json') {
    const data = this.generateMappingReport();

    switch (format) {
      case 'json':
        return JSON.stringify(data, null, 2);

      case 'csv':
        let csv = 'Component,Function,Endpoint,Description\n';
        for (const mapping of data.mappings) {
          for (const func of mapping.functions) {
            for (const endpoint of mapping.endpoints) {
              csv += `"${mapping.component}","${func}","${endpoint}","${mapping.description}"\n`;
            }
          }
        }
        return csv;

      case 'markdown':
        let md = '# API Endpoint Mappings\n\n';
        for (const mapping of data.mappings) {
          md += `## ${mapping.component}\n`;
          md += `${mapping.description}\n\n`;
          md += `**Functions:** ${mapping.functions.join(', ')}\n\n`;
          md += `**Endpoints:**\n`;
          for (const endpoint of mapping.endpoints) {
            md += `- \`${endpoint}\`\n`;
          }
          md += '\n';
        }
        return md;

      default:
        return data;
    }
  }
}

// Create singleton instance
const apiMapper = new ApiEndpointMapper();

// Make available globally for debugging
if (typeof window !== 'undefined') {
  window.apiMapper = apiMapper;
  window.debugApiMappings = (component) => apiMapper.debug(component);
  window.validateApiMappings = () => apiMapper.validateMappings();
  window.exportApiMappings = (format) => apiMapper.exportMappings(format);
}

export default apiMapper;
