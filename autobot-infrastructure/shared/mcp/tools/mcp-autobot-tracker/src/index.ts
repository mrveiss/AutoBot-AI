#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
  Tool,
} from '@modelcontextprotocol/sdk/types.js';
import { createClient } from 'redis';
import { v4 as uuidv4 } from 'uuid';
import * as chrono from 'chrono-node';
import natural from 'natural';
import { z } from 'zod';
import { BackgroundMonitor } from './background-monitor.js';
import { KnowledgeIntegration } from './knowledge-integration.js';
import { RealTimeIngestion } from './real-time-ingestion.js';
import { NetworkConstants } from './constants/network.js';

// Redis configuration - using AutoBot's Redis instance
const REDIS_CONFIG = {
  socket: {
    host: NetworkConstants.REDIS_VM_IP,
    port: NetworkConstants.REDIS_PORT,
  },
  database: 10, // Using DB 10 for MCP tracking
};

// Schema definitions
const ChatMessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string(),
  timestamp: z.string().optional(),
  tool_calls: z.array(z.any()).optional(),
});

const TaskSchema = z.object({
  id: z.string(),
  description: z.string(),
  status: z.enum(['pending', 'in_progress', 'completed', 'failed', 'blocked']),
  created_at: z.string(),
  updated_at: z.string(),
  chat_session_id: z.string(),
  message_index: z.number(),
  dependencies: z.array(z.string()).optional(),
  error_correlations: z.array(z.string()).optional(),
  context: z.record(z.any()).optional(),
});

const ErrorSchema = z.object({
  id: z.string(),
  error_message: z.string(),
  stack_trace: z.string().optional(),
  timestamp: z.string(),
  component: z.string(),
  severity: z.enum(['low', 'medium', 'high', 'critical']),
  correlated_tasks: z.array(z.string()).optional(),
});

class AutoBotTracker {
  public redis: ReturnType<typeof createClient> | null = null;
  private tokenizer: any;
  private tfidf: any;

  constructor() {
    this.tokenizer = new natural.WordTokenizer();
    this.tfidf = new natural.TfIdf();
  }

  async connect() {
    this.redis = createClient(REDIS_CONFIG);
    this.redis.on('error', (err) => console.error('Redis Client Error', err));
    await this.redis.connect();
    console.error('Connected to Redis DB 10 for MCP tracking');
  }

  async disconnect() {
    if (this.redis) {
      await this.redis.quit();
    }
  }

  // Ingest a Claude chat conversation
  async ingestChat(sessionId: string, messages: any[]) {
    if (!this.redis) throw new Error('Redis not connected');

    const tasks: any[] = [];
    const errors: any[] = [];

    for (let i = 0; i < messages.length; i++) {
      const message = messages[i];

      // Extract tasks from messages
      const extractedTasks = this.extractTasks(message.content, sessionId, i);
      tasks.push(...extractedTasks);

      // Extract errors from messages
      const extractedErrors = this.extractErrors(message.content);
      errors.push(...extractedErrors);

      // Store message
      await this.redis.hSet(
        `chat:${sessionId}:messages`,
        i.toString(),
        JSON.stringify(message)
      );
    }

    // Store extracted tasks
    for (const task of tasks) {
      await this.redis.hSet(
        `tasks:all`,
        task.id,
        JSON.stringify(task)
      );
      await this.redis.sAdd(`chat:${sessionId}:tasks`, task.id);
    }

    // Store extracted errors
    for (const error of errors) {
      await this.redis.hSet(
        `errors:all`,
        error.id,
        JSON.stringify(error)
      );
      await this.redis.sAdd(`chat:${sessionId}:errors`, error.id);
    }

    // Correlate tasks with errors
    await this.correlateTasksAndErrors(tasks, errors);

    return {
      session_id: sessionId,
      message_count: messages.length,
      tasks_extracted: tasks.length,
      errors_extracted: errors.length,
    };
  }

  // Extract tasks from message content
  private extractTasks(content: string, sessionId: string, messageIndex: number): any[] {
    const tasks: any[] = [];

    // Patterns for identifying tasks
    const taskPatterns = [
      /(?:TODO|FIXME|TASK|FIX|IMPLEMENT|CREATE|UPDATE|REFACTOR):\s*(.+?)(?:\n|$)/gi,
      /(?:need to|should|must|have to|going to|will)\s+(.+?)(?:\.|,|\n|$)/gi,
      /(?:^\d+\.\s+)(.+?)(?:\n|$)/gm, // Numbered lists
      /(?:^[-*]\s+)(.+?)(?:\n|$)/gm, // Bullet points
      /\[ \]\s+(.+?)(?:\n|$)/g, // Unchecked checkboxes
    ];

    const extractedDescriptions = new Set<string>();

    for (const pattern of taskPatterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        const description = match[1].trim();
        if (description.length > 10 && description.length < 500) {
          extractedDescriptions.add(description);
        }
      }
    }

    // Analyze task completion status from content
    const completionIndicators = {
      completed: /(?:done|completed|fixed|resolved|implemented|✓|✅)/i,
      failed: /(?:failed|error|couldn't|can't|unable|blocked)/i,
      in_progress: /(?:working on|implementing|fixing|updating|creating)/i,
    };

    for (const description of extractedDescriptions) {
      let status: 'pending' | 'in_progress' | 'completed' | 'failed' = 'pending';

      for (const [statusKey, pattern] of Object.entries(completionIndicators)) {
        if (pattern.test(description)) {
          status = statusKey as any;
          break;
        }
      }

      tasks.push({
        id: uuidv4(),
        description,
        status,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        chat_session_id: sessionId,
        message_index: messageIndex,
      });
    }

    return tasks;
  }

  // Extract errors from message content
  private extractErrors(content: string): any[] {
    const errors: any[] = [];

    // Patterns for identifying errors
    const errorPatterns = [
      /(?:error|exception|traceback|failed):\s*(.+?)(?:\n|$)/gi,
      /(?:Error|Exception|Failed)\s+(.+?)(?:\n|at\s|$)/g,
      /\[ERROR\]\s*(.+?)(?:\n|$)/g,
      /❌\s*(.+?)(?:\n|$)/g,
    ];

    const extractedErrors = new Set<string>();

    for (const pattern of errorPatterns) {
      let match;
      while ((match = pattern.exec(content)) !== null) {
        extractedErrors.add(match[1].trim());
      }
    }

    // Identify component from error context
    const componentPatterns = {
      backend: /(?:backend|api|fastapi|uvicorn|python)/i,
      frontend: /(?:frontend|vue|vite|npm|node|javascript)/i,
      redis: /(?:redis|cache|database)/i,
      docker: /(?:docker|container|compose)/i,
      llm: /(?:llm|ollama|openai|model)/i,
      knowledge: /(?:knowledge|kb|vector|embedding)/i,
    };

    for (const errorMsg of extractedErrors) {
      let component = 'unknown';
      let severity: 'low' | 'medium' | 'high' | 'critical' = 'medium';

      // Detect component
      for (const [comp, pattern] of Object.entries(componentPatterns)) {
        if (pattern.test(errorMsg)) {
          component = comp;
          break;
        }
      }

      // Detect severity
      if (/(?:critical|fatal|emergency)/i.test(errorMsg)) {
        severity = 'critical';
      } else if (/(?:error|exception|failed)/i.test(errorMsg)) {
        severity = 'high';
      } else if (/(?:warning|warn)/i.test(errorMsg)) {
        severity = 'medium';
      } else {
        severity = 'low';
      }

      errors.push({
        id: uuidv4(),
        error_message: errorMsg,
        timestamp: new Date().toISOString(),
        component,
        severity,
      });
    }

    return errors;
  }

  // Correlate tasks with errors using TF-IDF similarity
  private async correlateTasksAndErrors(tasks: any[], errors: any[]) {
    if (!this.redis || tasks.length === 0 || errors.length === 0) return;

    // Build TF-IDF documents
    const documents: string[] = [];
    tasks.forEach(task => {
      this.tfidf.addDocument(task.description);
      documents.push(task.description);
    });

    // Find correlations
    for (const error of errors) {
      const correlatedTasks: string[] = [];

      this.tfidf.tfidfs(error.error_message, (i: number, measure: number) => {
        if (measure > 0.3) { // Threshold for correlation
          correlatedTasks.push(tasks[i].id);
        }
      });

      if (correlatedTasks.length > 0) {
        error.correlated_tasks = correlatedTasks;

        // Update tasks with error correlations
        for (const taskId of correlatedTasks) {
          const task = tasks.find(t => t.id === taskId);
          if (task) {
            task.error_correlations = task.error_correlations || [];
            task.error_correlations.push(error.id);
          }
        }
      }
    }

    // Update Redis with correlations
    for (const task of tasks) {
      if (task.error_correlations) {
        await this.redis.hSet(
          `tasks:all`,
          task.id,
          JSON.stringify(task)
        );
      }
    }

    for (const error of errors) {
      if (error.correlated_tasks) {
        await this.redis.hSet(
          `errors:all`,
          error.id,
          JSON.stringify(error)
        );
      }
    }
  }

  // Get unfinished tasks
  async getUnfinishedTasks(sessionId?: string) {
    if (!this.redis) throw new Error('Redis not connected');

    let taskIds: string[];

    if (sessionId) {
      taskIds = await this.redis.sMembers(`chat:${sessionId}:tasks`);
    } else {
      const allTasks = await this.redis.hGetAll('tasks:all');
      taskIds = Object.keys(allTasks);
    }

    const unfinishedTasks: any[] = [];

    for (const taskId of taskIds) {
      const taskData = await this.redis.hGet('tasks:all', taskId);
      if (taskData) {
        const task = JSON.parse(taskData);
        if (task.status !== 'completed') {
          unfinishedTasks.push(task);
        }
      }
    }

    return unfinishedTasks;
  }

  // Get errors with correlations
  async getErrorsWithCorrelations(component?: string, severity?: string) {
    if (!this.redis) throw new Error('Redis not connected');

    const allErrors = await this.redis.hGetAll('errors:all');
    const errors: any[] = [];

    for (const [errorId, errorData] of Object.entries(allErrors)) {
      const error = JSON.parse(errorData);

      // Filter by component and severity if provided
      if (component && error.component !== component) continue;
      if (severity && error.severity !== severity) continue;

      // Get correlated tasks
      if (error.correlated_tasks) {
        const tasks = [];
        for (const taskId of error.correlated_tasks) {
          const taskData = await this.redis.hGet('tasks:all', taskId);
          if (taskData) {
            tasks.push(JSON.parse(taskData));
          }
        }
        error.correlated_task_details = tasks;
      }

      errors.push(error);
    }

    return errors;
  }

  // Generate summary report
  async generateSummaryReport() {
    if (!this.redis) throw new Error('Redis not connected');

    const allTasks = await this.redis.hGetAll('tasks:all');
    const allErrors = await this.redis.hGetAll('errors:all');

    const taskStats = {
      total: 0,
      pending: 0,
      in_progress: 0,
      completed: 0,
      failed: 0,
      blocked: 0,
    };

    const errorStats = {
      total: 0,
      by_component: {} as Record<string, number>,
      by_severity: {
        low: 0,
        medium: 0,
        high: 0,
        critical: 0,
      },
    };

    // Process tasks
    for (const taskData of Object.values(allTasks)) {
      const task = JSON.parse(taskData);
      taskStats.total++;
      taskStats[task.status as keyof typeof taskStats]++;
    }

    // Process errors
    for (const errorData of Object.values(allErrors)) {
      const error = JSON.parse(errorData);
      errorStats.total++;
      errorStats.by_severity[error.severity as keyof typeof errorStats.by_severity]++;
      errorStats.by_component[error.component] = (errorStats.by_component[error.component] || 0) + 1;
    }

    // Find most problematic areas
    const problemAreas = Object.entries(errorStats.by_component)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([component, count]) => ({ component, error_count: count }));

    return {
      task_statistics: taskStats,
      error_statistics: errorStats,
      problem_areas: problemAreas,
      completion_rate: taskStats.total > 0
        ? ((taskStats.completed / taskStats.total) * 100).toFixed(2) + '%'
        : '0%',
      critical_errors: errorStats.by_severity.critical,
      unfinished_tasks: taskStats.total - taskStats.completed,
    };
  }
}

// Initialize MCP Server and Background Monitor
const tracker = new AutoBotTracker();
const backgroundMonitor = new BackgroundMonitor(REDIS_CONFIG);
const knowledgeIntegration = new KnowledgeIntegration(REDIS_CONFIG);
const realTimeIngestion = new RealTimeIngestion();
const server = new Server(
  {
    name: 'mcp-autobot-tracker',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
      resources: {},
    },
  }
);

// Define tools
const tools: Tool[] = [
  {
    name: 'ingest_chat',
    description: 'Ingest a Claude chat conversation for tracking',
    inputSchema: {
      type: 'object',
      properties: {
        session_id: {
          type: 'string',
          description: 'Unique identifier for the chat session',
        },
        messages: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              role: { type: 'string' },
              content: { type: 'string' },
              timestamp: { type: 'string' },
            },
            required: ['role', 'content'],
          },
          description: 'Array of chat messages',
        },
      },
      required: ['session_id', 'messages'],
    },
  },
  {
    name: 'get_unfinished_tasks',
    description: 'Get all unfinished tasks from tracked conversations',
    inputSchema: {
      type: 'object',
      properties: {
        session_id: {
          type: 'string',
          description: 'Optional session ID to filter tasks',
        },
      },
    },
  },
  {
    name: 'get_errors_with_correlations',
    description: 'Get errors with their correlated tasks',
    inputSchema: {
      type: 'object',
      properties: {
        component: {
          type: 'string',
          description: 'Filter by component (backend, frontend, redis, etc.)',
        },
        severity: {
          type: 'string',
          enum: ['low', 'medium', 'high', 'critical'],
          description: 'Filter by severity level',
        },
      },
    },
  },
  {
    name: 'generate_summary_report',
    description: 'Generate a comprehensive summary report of all tracked data',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'get_recent_activity',
    description: 'Get recent errors, warnings, and tasks from background monitoring',
    inputSchema: {
      type: 'object',
      properties: {
        minutes: {
          type: 'number',
          description: 'Number of minutes to look back (default: 60)',
        },
      },
    },
  },
  {
    name: 'get_system_health',
    description: 'Get current system health status',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'analyze_and_generate_knowledge',
    description: 'Analyze patterns and generate knowledge insights for AutoBot',
    inputSchema: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'get_insights',
    description: 'Get generated knowledge insights',
    inputSchema: {
      type: 'object',
      properties: {
        category: {
          type: 'string',
          description: 'Filter by category (error_patterns, task_patterns, system_insights)',
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'Filter by tags',
        },
      },
    },
  },
  {
    name: 'update_task_status',
    description: 'Update the status of a tracked task',
    inputSchema: {
      type: 'object',
      properties: {
        task_id: {
          type: 'string',
          description: 'ID of the task to update',
        },
        status: {
          type: 'string',
          enum: ['pending', 'in_progress', 'completed', 'failed', 'blocked'],
          description: 'New status for the task',
        },
        notes: {
          type: 'string',
          description: 'Optional notes about the status change',
        },
      },
      required: ['task_id', 'status'],
    },
  },
];

// Handle tool requests
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'ingest_chat': {
        const result = await tracker.ingestChat(
          (args as any).session_id,
          (args as any).messages
        );
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(result, null, 2),
            },
          ],
        };
      }

      case 'get_unfinished_tasks': {
        const tasks = await tracker.getUnfinishedTasks((args as any).session_id);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(tasks, null, 2),
            },
          ],
        };
      }

      case 'get_errors_with_correlations': {
        const errors = await tracker.getErrorsWithCorrelations(
          (args as any).component,
          (args as any).severity
        );
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(errors, null, 2),
            },
          ],
        };
      }

      case 'generate_summary_report': {
        const report = await tracker.generateSummaryReport();
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(report, null, 2),
            },
          ],
        };
      }

      case 'update_task_status': {
        if (!tracker.redis) throw new Error('Redis not connected');

        const taskData = await tracker.redis!.hGet('tasks:all', (args as any).task_id);
        if (!taskData) {
          throw new Error(`Task ${(args as any).task_id} not found`);
        }

        const task = JSON.parse(taskData);
        task.status = (args as any).status;
        task.updated_at = new Date().toISOString();
        if ((args as any).notes) {
          task.notes = task.notes || [];
          task.notes.push({
            timestamp: new Date().toISOString(),
            note: (args as any).notes,
          });
        }

        await tracker.redis!.hSet('tasks:all', (args as any).task_id, JSON.stringify(task));

        return {
          content: [
            {
              type: 'text',
              text: `Task ${(args as any).task_id} updated to status: ${(args as any).status}`,
            },
          ],
        };
      }

      case 'get_recent_activity': {
        const activity = await backgroundMonitor.getRecentActivity((args as any).minutes || 60);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(activity, null, 2),
            },
          ],
        };
      }

      case 'get_system_health': {
        if (!backgroundMonitor.redis) {
          throw new Error('Background monitor not connected');
        }

        // Get latest health check
        const healthKeys = await backgroundMonitor.redis!.hKeys('system:health_checks');
        if (healthKeys.length === 0) {
          throw new Error('No health checks available');
        }

        const latestKey = healthKeys.sort().pop();
        const healthData = await backgroundMonitor.redis!.hGet('system:health_checks', latestKey!);

        return {
          content: [
            {
              type: 'text',
              text: healthData || 'No health data available',
            },
          ],
        };
      }

      case 'analyze_and_generate_knowledge': {
        const insights = await knowledgeIntegration.analyzeAndGenerateKnowledge();
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({
                generated_insights: insights.length,
                insights: insights.slice(0, 5), // Show first 5
                message: `Generated ${insights.length} knowledge insights from patterns`,
              }, null, 2),
            },
          ],
        };
      }

      case 'get_insights': {
        const insights = await knowledgeIntegration.getInsights((args as any).category, (args as any).tags);
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(insights, null, 2),
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    return {
      content: [
        {
          type: 'text',
          text: `Error: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

// Handle resource requests
server.setRequestHandler(ListResourcesRequestSchema, async () => ({
  resources: [
    {
      uri: 'autobot://unfinished-tasks',
      name: 'Unfinished Tasks',
      description: 'All unfinished tasks from tracked conversations',
      mimeType: 'application/json',
    },
    {
      uri: 'autobot://error-correlations',
      name: 'Error Correlations',
      description: 'Errors with their correlated tasks',
      mimeType: 'application/json',
    },
    {
      uri: 'autobot://summary-report',
      name: 'Summary Report',
      description: 'Comprehensive summary of tracked data',
      mimeType: 'application/json',
    },
    {
      uri: 'autobot://recent-activity',
      name: 'Recent Activity',
      description: 'Recent errors, warnings, and tasks from monitoring',
      mimeType: 'application/json',
    },
    {
      uri: 'autobot://system-health',
      name: 'System Health',
      description: 'Current system health status',
      mimeType: 'application/json',
    },
  ],
}));

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const { uri } = request.params;

  try {
    switch (uri) {
      case 'autobot://unfinished-tasks': {
        const tasks = await tracker.getUnfinishedTasks();
        return {
          contents: [
            {
              uri,
              mimeType: 'application/json',
              text: JSON.stringify(tasks, null, 2),
            },
          ],
        };
      }

      case 'autobot://error-correlations': {
        const errors = await tracker.getErrorsWithCorrelations();
        return {
          contents: [
            {
              uri,
              mimeType: 'application/json',
              text: JSON.stringify(errors, null, 2),
            },
          ],
        };
      }

      case 'autobot://summary-report': {
        const report = await tracker.generateSummaryReport();
        return {
          contents: [
            {
              uri,
              mimeType: 'application/json',
              text: JSON.stringify(report, null, 2),
            },
          ],
        };
      }

      case 'autobot://recent-activity': {
        const activity = await backgroundMonitor.getRecentActivity(60);
        return {
          contents: [
            {
              uri,
              mimeType: 'application/json',
              text: JSON.stringify(activity, null, 2),
            },
          ],
        };
      }

      case 'autobot://system-health': {
        if (!backgroundMonitor.redis) {
          throw new Error('Background monitor not connected');
        }

        const healthKeys = await backgroundMonitor.redis!.hKeys('system:health_checks');
        const latestKey = healthKeys.sort().pop();
        const healthData = latestKey
          ? await backgroundMonitor.redis.hGet('system:health_checks', latestKey)
          : null;

        return {
          contents: [
            {
              uri,
              mimeType: 'application/json',
              text: healthData || '{"error": "No health data available"}',
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown resource: ${uri}`);
    }
  } catch (error: any) {
    throw new Error(`Failed to read resource: ${error.message}`);
  }
});

// Start the server
async function main() {
  try {
    await tracker.connect();
    console.error('AutoBot Tracker MCP Server starting...');

    // Start background monitoring
    await backgroundMonitor.start();
    console.error('Background monitoring started');

    // Connect knowledge integration
    await knowledgeIntegration.connect();
    console.error('Knowledge integration connected');

    // Start real-time ingestion
    await realTimeIngestion.initialize();
    console.error('Real-time conversation ingestion started');

    const transport = new StdioServerTransport();
    await server.connect(transport);

    console.error('AutoBot Tracker MCP Server running with full integration');

    // Schedule periodic knowledge analysis (every 30 minutes)
    setInterval(async () => {
      try {
        console.error('[Scheduler] Running periodic knowledge analysis...');
        await knowledgeIntegration.analyzeAndGenerateKnowledge();
      } catch (error) {
        console.error('[Scheduler] Error in periodic analysis:', error);
      }
    }, 30 * 60 * 1000); // 30 minutes

  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Handle shutdown
process.on('SIGINT', async () => {
  console.error('Shutting down...');
  await backgroundMonitor.stop();
  await knowledgeIntegration.disconnect();
  await realTimeIngestion.shutdown();
  await tracker.disconnect();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.error('SIGTERM received, shutting down...');
  await backgroundMonitor.stop();
  await knowledgeIntegration.disconnect();
  await realTimeIngestion.shutdown();
  await tracker.disconnect();
  process.exit(0);
});

main();
