#!/usr/bin/env node

/**
 * AutoBot Custom MCP Server
 * 
 * Provides AutoBot-specific tools for development workflow:
 * - Project analysis and structure inspection
 * - Build system integration
 * - Test execution and reporting  
 * - Configuration management
 * - Docker/deployment operations
 * - Chat history analysis
 * - Knowledge base operations
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { execSync } from 'child_process';
import fs from 'fs/promises';
import path from 'path';

const PROJECT_ROOT = '/home/kali/Desktop/AutoBot';

class AutoBotMCPServer {
  constructor() {
    this.server = new Server(
      {
        name: "autobot-mcp-server",
        version: "1.0.0",
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();
    this.setupErrorHandling();
  }

  setupToolHandlers() {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: "autobot_analyze_project",
            description: "Analyze AutoBot project structure, dependencies, and health",
            inputSchema: {
              type: "object",
              properties: {
                includeStats: {
                  type: "boolean",
                  description: "Include detailed statistics",
                  default: true
                }
              }
            }
          },
          {
            name: "autobot_run_tests",
            description: "Execute AutoBot test suite with reporting",
            inputSchema: {
              type: "object",
              properties: {
                component: {
                  type: "string",
                  enum: ["frontend", "backend", "all"],
                  description: "Which component to test",
                  default: "all"
                },
                coverage: {
                  type: "boolean", 
                  description: "Generate coverage report",
                  default: false
                }
              }
            }
          },
          {
            name: "autobot_build_status",
            description: "Check build status and generate build reports",
            inputSchema: {
              type: "object",
              properties: {
                component: {
                  type: "string",
                  enum: ["frontend", "backend", "docker", "all"],
                  description: "Which component to check",
                  default: "all"
                }
              }
            }
          },
          {
            name: "autobot_chat_analytics",
            description: "Analyze chat history and patterns",
            inputSchema: {
              type: "object",
              properties: {
                days: {
                  type: "number",
                  description: "Number of days to analyze",
                  default: 7
                },
                includeStats: {
                  type: "boolean",
                  description: "Include detailed statistics",
                  default: true
                }
              }
            }
          },
          {
            name: "autobot_knowledge_stats",
            description: "Analyze knowledge base content and statistics",
            inputSchema: {
              type: "object",
              properties: {
                includeContent: {
                  type: "boolean",
                  description: "Include content analysis",
                  default: true
                }
              }
            }
          },
          {
            name: "autobot_docker_status",
            description: "Check Docker containers and compose status",
            inputSchema: {
              type: "object",
              properties: {
                action: {
                  type: "string",
                  enum: ["status", "health", "logs", "restart"],
                  description: "Action to perform",
                  default: "status"
                }
              }
            }
          },
          {
            name: "autobot_debug_frontend",
            description: "Debug AutoBot Vue.js frontend with comprehensive analysis",
            inputSchema: {
              type: "object",
              properties: {
                action: {
                  type: "string",
                  enum: ["console-errors", "network-analysis", "component-tree", "performance", "bundle-analysis"],
                  description: "Type of frontend debugging",
                  default: "console-errors"
                },
                includeStackTrace: {
                  type: "boolean",
                  description: "Include stack traces in error analysis",
                  default: true
                }
              }
            }
          },
          {
            name: "autobot_debug_backend",
            description: "Debug AutoBot Python backend with logs and performance analysis",
            inputSchema: {
              type: "object",
              properties: {
                action: {
                  type: "string",
                  enum: ["logs", "api-health", "db-connections", "memory-usage", "active-sessions"],
                  description: "Type of backend debugging",
                  default: "logs"
                },
                timeframe: {
                  type: "string",
                  enum: ["1h", "4h", "24h", "7d"],
                  description: "Time period for analysis",
                  default: "1h"
                }
              }
            }
          },
          {
            name: "autobot_debug_api_calls",
            description: "Analyze API call patterns, errors, and performance",
            inputSchema: {
              type: "object",
              properties: {
                endpoint: {
                  type: "string",
                  description: "Specific endpoint to analyze (optional)"
                },
                includePayloads: {
                  type: "boolean",
                  description: "Include request/response payloads",
                  default: false
                },
                errorOnly: {
                  type: "boolean",
                  description: "Only show failed API calls",
                  default: false
                }
              }
            }
          },
          {
            name: "autobot_debug_websockets",
            description: "Debug WebSocket connections and message flow",
            inputSchema: {
              type: "object",
              properties: {
                action: {
                  type: "string",
                  enum: ["connections", "messages", "errors", "performance"],
                  description: "WebSocket debugging aspect",
                  default: "connections"
                }
              }
            }
          },
          {
            name: "autobot_debug_logs_analysis",
            description: "Comprehensive log analysis with pattern detection",
            inputSchema: {
              type: "object",
              properties: {
                logLevel: {
                  type: "string",
                  enum: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                  description: "Minimum log level to analyze",
                  default: "WARNING"
                },
                component: {
                  type: "string",
                  enum: ["frontend", "backend", "system", "docker", "all"],
                  description: "Component logs to analyze",
                  default: "all"
                },
                pattern: {
                  type: "string",
                  description: "Specific pattern to search for"
                }
              }
            }
          }
        ]
      };
    });

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          case "autobot_analyze_project":
            return await this.analyzeProject(args);
          case "autobot_run_tests":
            return await this.runTests(args);
          case "autobot_build_status":
            return await this.checkBuildStatus(args);
          case "autobot_chat_analytics":
            return await this.analyzeChatHistory(args);
          case "autobot_knowledge_stats":
            return await this.analyzeKnowledgeBase(args);
          case "autobot_docker_status":
            return await this.checkDockerStatus(args);
          case "autobot_debug_frontend":
            return await this.debugFrontend(args);
          case "autobot_debug_backend":
            return await this.debugBackend(args);
          case "autobot_debug_api_calls":
            return await this.debugApiCalls(args);
          case "autobot_debug_websockets":
            return await this.debugWebsockets(args);
          case "autobot_debug_logs_analysis":
            return await this.debugLogsAnalysis(args);
          default:
            throw new Error(`Unknown tool: ${name}`);
        }
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: `Error executing ${name}: ${error.message}`
            }
          ]
        };
      }
    });
  }

  async analyzeProject(args = {}) {
    const analysis = {
      projectRoot: PROJECT_ROOT,
      timestamp: new Date().toISOString(),
      structure: {},
      dependencies: {},
      health: {}
    };

    try {
      // Analyze frontend
      const frontendPackage = path.join(PROJECT_ROOT, 'autobot-vue/package.json');
      if (await this.fileExists(frontendPackage)) {
        const pkg = JSON.parse(await fs.readFile(frontendPackage, 'utf8'));
        analysis.structure.frontend = {
          name: pkg.name,
          version: pkg.version,
          dependencies: Object.keys(pkg.dependencies || {}).length,
          devDependencies: Object.keys(pkg.devDependencies || {}).length
        };
      }

      // Analyze backend
      const backendFiles = await this.getDirectoryStats(path.join(PROJECT_ROOT, 'backend'));
      analysis.structure.backend = backendFiles;

      // Check configuration files
      const configFiles = ['config/config.yaml', 'CLAUDE.md', 'README.md', 'docker-compose.yml'];
      analysis.structure.config = {};
      for (const file of configFiles) {
        const filePath = path.join(PROJECT_ROOT, file);
        analysis.structure.config[file] = await this.fileExists(filePath);
      }

      // Health checks
      if (args.includeStats) {
        analysis.health.gitStatus = await this.executeCommand('git status --porcelain', { cwd: PROJECT_ROOT });
        analysis.health.diskUsage = await this.executeCommand(`du -sh ${PROJECT_ROOT}`);
      }

      return {
        content: [
          {
            type: "text", 
            text: `# AutoBot Project Analysis\n\n${JSON.stringify(analysis, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Project analysis failed: ${error.message}`);
    }
  }

  async runTests(args = {}) {
    const { component = 'all', coverage = false } = args;
    const results = {
      timestamp: new Date().toISOString(),
      component,
      results: {}
    };

    try {
      if (component === 'frontend' || component === 'all') {
        const frontendDir = path.join(PROJECT_ROOT, 'autobot-vue');
        if (await this.directoryExists(frontendDir)) {
          const testCmd = coverage ? 'npm run test:coverage' : 'npm test';
          results.results.frontend = await this.executeCommand(testCmd, { cwd: frontendDir });
        }
      }

      if (component === 'backend' || component === 'all') {
        // Check for Python tests
        const testCmd = 'python -m pytest tests/ --tb=short -v';
        try {
          results.results.backend = await this.executeCommand(testCmd, { cwd: PROJECT_ROOT });
        } catch (error) {
          results.results.backend = `Backend tests failed: ${error.message}`;
        }
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Test Results\n\n${JSON.stringify(results, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Test execution failed: ${error.message}`);
    }
  }

  async checkBuildStatus(args = {}) {
    const { component = 'all' } = args;
    const status = {
      timestamp: new Date().toISOString(),
      builds: {}
    };

    try {
      if (component === 'frontend' || component === 'all') {
        const frontendDir = path.join(PROJECT_ROOT, 'autobot-vue');
        if (await this.directoryExists(frontendDir)) {
          try {
            status.builds.frontend = await this.executeCommand('npm run build-only', { cwd: frontendDir });
          } catch (error) {
            status.builds.frontend = `Build failed: ${error.message}`;
          }
        }
      }

      if (component === 'docker' || component === 'all') {
        try {
          status.builds.docker = await this.executeCommand('docker-compose config', { cwd: PROJECT_ROOT });
        } catch (error) {
          status.builds.docker = `Docker config check failed: ${error.message}`;
        }
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Build Status\n\n${JSON.stringify(status, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Build status check failed: ${error.message}`);
    }
  }

  async analyzeChatHistory(args = {}) {
    const { days = 7, includeStats = true } = args;
    const analysis = {
      timestamp: new Date().toISOString(),
      period: `${days} days`,
      stats: {}
    };

    try {
      const chatHistoryFile = path.join(PROJECT_ROOT, 'data/chat_history.json');
      if (await this.fileExists(chatHistoryFile)) {
        const content = await fs.readFile(chatHistoryFile, 'utf8');
        const chatData = JSON.parse(content);
        
        if (includeStats) {
          analysis.stats.totalSessions = Object.keys(chatData).length;
          analysis.stats.totalMessages = 0;
          
          for (const session of Object.values(chatData)) {
            if (session.messages) {
              analysis.stats.totalMessages += session.messages.length;
            }
          }
        }
      } else {
        analysis.stats.error = 'Chat history file not found';
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Chat Analytics\n\n${JSON.stringify(analysis, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Chat analytics failed: ${error.message}`);
    }
  }

  async analyzeKnowledgeBase(args = {}) {
    const { includeContent = true } = args;
    const analysis = {
      timestamp: new Date().toISOString(),
      stats: {}
    };

    try {
      const knowledgeDir = path.join(PROJECT_ROOT, 'knowledge_base');
      if (await this.directoryExists(knowledgeDir)) {
        analysis.stats = await this.getDirectoryStats(knowledgeDir);
        
        if (includeContent) {
          analysis.fileTypes = {};
          const files = await fs.readdir(knowledgeDir, { recursive: true });
          for (const file of files) {
            const ext = path.extname(file);
            analysis.fileTypes[ext] = (analysis.fileTypes[ext] || 0) + 1;
          }
        }
      } else {
        analysis.stats.error = 'Knowledge base directory not found';
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Knowledge Base Analysis\n\n${JSON.stringify(analysis, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Knowledge base analysis failed: ${error.message}`);
    }
  }

  async checkDockerStatus(args = {}) {
    const { action = 'status' } = args;
    const result = {
      timestamp: new Date().toISOString(),
      action,
      output: {}
    };

    try {
      switch (action) {
        case 'status':
          result.output.containers = await this.executeCommand('docker ps -a');
          result.output.compose = await this.executeCommand('docker-compose ps', { cwd: PROJECT_ROOT });
          break;
        case 'health':
          result.output.health = await this.executeCommand('docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"');
          break;
        case 'logs':
          result.output.logs = await this.executeCommand('docker-compose logs --tail=50', { cwd: PROJECT_ROOT });
          break;
        default:
          result.output.error = `Unknown action: ${action}`;
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Docker Status\n\n${JSON.stringify(result, null, 2)}`
          }
        ]
      };

    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Docker Status\n\nError: ${error.message}`
          }
        ]
      };
    }
  }

  async debugFrontend(args = {}) {
    const { action = 'console-errors', includeStackTrace = true } = args;
    const result = {
      timestamp: new Date().toISOString(),
      action,
      debug: {}
    };

    try {
      switch (action) {
        case 'console-errors':
          result.debug.browserConsole = await this.executeCommand('cd autobot-vue && npm run build-only 2>&1 | head -50', { cwd: PROJECT_ROOT });
          break;
        case 'network-analysis':
          result.debug.networkRequests = 'Network analysis requires browser session - use Puppeteer MCP server';
          break;
        case 'component-tree':
          const vueFiles = await this.executeCommand('find autobot-vue/src -name "*.vue" -type f | wc -l', { cwd: PROJECT_ROOT });
          result.debug.componentCount = vueFiles;
          result.debug.componentTree = await this.executeCommand('find autobot-vue/src -name "*.vue" -type f | head -20', { cwd: PROJECT_ROOT });
          break;
        case 'performance':
          result.debug.bundleSize = await this.executeCommand('du -sh autobot-vue/dist/', { cwd: PROJECT_ROOT });
          break;
        case 'bundle-analysis':
          result.debug.bundleAnalysis = await this.executeCommand('cd autobot-vue && npm run build-only --analyze', { cwd: PROJECT_ROOT });
          break;
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Frontend Debug\n\n${JSON.stringify(result, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Frontend debugging failed: ${error.message}`);
    }
  }

  async debugBackend(args = {}) {
    const { action = 'logs', timeframe = '1h' } = args;
    const result = {
      timestamp: new Date().toISOString(),
      action,
      timeframe,
      debug: {}
    };

    try {
      switch (action) {
        case 'logs':
          result.debug.recentLogs = await this.executeCommand('tail -50 logs/system.log', { cwd: PROJECT_ROOT });
          result.debug.errorLogs = await this.executeCommand('grep -i error logs/system.log | tail -20', { cwd: PROJECT_ROOT });
          break;
        case 'api-health':
          try {
            result.debug.healthCheck = await this.executeCommand('curl -s http://127.0.0.3:8001/api/system/health');
          } catch (error) {
            result.debug.healthCheck = 'Backend not responding';
          }
          break;
        case 'db-connections':
          result.debug.redisConnection = await this.executeCommand('redis-cli ping 2>/dev/null || echo "Redis not available"');
          break;
        case 'memory-usage':
          result.debug.memoryUsage = await this.executeCommand('ps aux | grep -E "(python|uvicorn)" | head -10');
          break;
        case 'active-sessions':
          result.debug.activeSessions = 'Session info requires database query';
          break;
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Backend Debug\n\n${JSON.stringify(result, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Backend debugging failed: ${error.message}`);
    }
  }

  async debugApiCalls(args = {}) {
    const { endpoint, includePayloads = false, errorOnly = false } = args;
    const result = {
      timestamp: new Date().toISOString(),
      endpoint,
      includePayloads,
      errorOnly,
      analysis: {}
    };

    try {
      // Analyze backend logs for API calls
      let logCommand = 'grep -E "(GET|POST|PUT|DELETE|PATCH)" logs/backend.log';
      if (errorOnly) {
        logCommand += ' | grep -E "(4[0-9][0-9]|5[0-9][0-9])"';
      }
      if (endpoint) {
        logCommand += ` | grep "${endpoint}"`;
      }
      logCommand += ' | tail -20';

      result.analysis.apiCalls = await this.executeCommand(logCommand, { cwd: PROJECT_ROOT });
      
      // Get error patterns
      result.analysis.errorPatterns = await this.executeCommand('grep -E "Error|Exception|Failed" logs/backend.log | tail -10', { cwd: PROJECT_ROOT });

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot API Debug\n\n${JSON.stringify(result, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`API debugging failed: ${error.message}`);
    }
  }

  async debugWebsockets(args = {}) {
    const { action = 'connections' } = args;
    const result = {
      timestamp: new Date().toISOString(),
      action,
      debug: {}
    };

    try {
      switch (action) {
        case 'connections':
          result.debug.activeConnections = await this.executeCommand('netstat -an | grep :8001 | grep ESTABLISHED || echo "No WebSocket connections"');
          break;
        case 'messages':
          result.debug.wsMessages = await this.executeCommand('grep -i websocket logs/backend.log | tail -20 || echo "No WebSocket messages found"', { cwd: PROJECT_ROOT });
          break;
        case 'errors':
          result.debug.wsErrors = await this.executeCommand('grep -i "websocket.*error" logs/backend.log | tail -10 || echo "No WebSocket errors found"', { cwd: PROJECT_ROOT });
          break;
        case 'performance':
          result.debug.wsPerformance = 'WebSocket performance metrics require dedicated monitoring';
          break;
      }

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot WebSocket Debug\n\n${JSON.stringify(result, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`WebSocket debugging failed: ${error.message}`);
    }
  }

  async debugLogsAnalysis(args = {}) {
    const { logLevel = 'WARNING', component = 'all', pattern } = args;
    const result = {
      timestamp: new Date().toISOString(),
      logLevel,
      component,
      pattern,
      analysis: {}
    };

    try {
      let logFiles = [];
      
      switch (component) {
        case 'frontend':
          logFiles = ['logs/frontend.log', 'logs/frontend_runtime.log'];
          break;
        case 'backend':
          logFiles = ['logs/backend.log', 'logs/system.log'];
          break;
        case 'docker':
          result.analysis.dockerLogs = await this.executeCommand('docker-compose logs --tail=50', { cwd: PROJECT_ROOT });
          break;
        case 'all':
          logFiles = ['logs/system.log', 'logs/backend.log', 'logs/frontend.log'];
          break;
      }

      // Analyze each log file
      for (const logFile of logFiles) {
        const filePath = path.join(PROJECT_ROOT, logFile);
        if (await this.fileExists(filePath)) {
          let grepCommand = `grep -i "${logLevel}" ${logFile}`;
          if (pattern) {
            grepCommand += ` | grep -i "${pattern}"`;
          }
          grepCommand += ' | tail -20';

          try {
            result.analysis[logFile] = await this.executeCommand(grepCommand, { cwd: PROJECT_ROOT });
          } catch (error) {
            result.analysis[logFile] = `No ${logLevel} entries found`;
          }
        }
      }

      // Get error frequency analysis
      result.analysis.errorFrequency = await this.executeCommand('grep -i error logs/system.log | cut -d" " -f1-2 | uniq -c | tail -10', { cwd: PROJECT_ROOT });

      return {
        content: [
          {
            type: "text",
            text: `# AutoBot Logs Analysis\n\n${JSON.stringify(result, null, 2)}`
          }
        ]
      };

    } catch (error) {
      throw new Error(`Log analysis failed: ${error.message}`);
    }
  }

  // Utility methods
  async executeCommand(command, options = {}) {
    try {
      const result = execSync(command, { 
        encoding: 'utf8', 
        maxBuffer: 1024 * 1024,
        ...options 
      });
      return result.toString().trim();
    } catch (error) {
      throw new Error(`Command failed: ${command}\n${error.message}`);
    }
  }

  async fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }

  async directoryExists(dirPath) {
    try {
      const stats = await fs.stat(dirPath);
      return stats.isDirectory();
    } catch {
      return false;
    }
  }

  async getDirectoryStats(dirPath) {
    try {
      const files = await fs.readdir(dirPath, { recursive: true });
      return {
        totalFiles: files.length,
        exists: true
      };
    } catch {
      return {
        totalFiles: 0,
        exists: false
      };
    }
  }

  setupErrorHandling() {
    this.server.onerror = (error) => {
      console.error("[MCP Error]", error);
    };

    process.on('SIGINT', async () => {
      await this.server.close();
      process.exit(0);
    });
  }

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("AutoBot MCP Server running on stdio");
  }
}

// Start the server
const server = new AutoBotMCPServer();
server.run().catch(console.error);