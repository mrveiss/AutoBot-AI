import { createClient } from 'redis';
import { v4 as uuidv4 } from 'uuid';
import * as fs from 'fs/promises';
import * as path from 'path';
import { Tail } from 'tail';
import { exec } from 'child_process';
import { promisify } from 'util';
import { NetworkConstants, HealthCheckEndpoints } from './constants/network.js';
import { PathConstants } from './constants/paths.js';

const execAsync = promisify(exec);

interface LogConfig {
  name: string;
  path: string;
  component: string;
  patterns: {
    error: RegExp[];
    warning: RegExp[];
    task: RegExp[];
    completion: RegExp[];
  };
}

export class BackgroundMonitor {
  public redis: ReturnType<typeof createClient> | null = null;
  private logWatchers: Map<string, any> = new Map();
  private dockerLogProcesses: Map<string, any> = new Map();
  private isRunning = false;

  // AutoBot log configurations
  private logConfigs: LogConfig[] = [
    {
      name: 'backend',
      path: PathConstants.BACKEND_LOG,
      component: 'backend',
      patterns: {
        error: [
          /ERROR\s*[\|\:]?\s*(.+)/gi,
          /Exception\s*[\|\:]?\s*(.+)/gi,
          /Traceback\s*(.+)/gi,
          /Failed\s*[\|\:]?\s*(.+)/gi,
          /❌\s*(.+)/gi,
        ],
        warning: [
          /WARNING\s*[\|\:]?\s*(.+)/gi,
          /WARN\s*[\|\:]?\s*(.+)/gi,
          /⚠️\s*(.+)/gi,
        ],
        task: [
          /TODO\s*[\|\:]?\s*(.+)/gi,
          /FIXME\s*[\|\:]?\s*(.+)/gi,
          /TASK\s*[\|\:]?\s*(.+)/gi,
          /need to\s+(.+)/gi,
          /should\s+(.+)/gi,
        ],
        completion: [
          /✅\s*(.+)/gi,
          /SUCCESS\s*[\|\:]?\s*(.+)/gi,
          /Completed\s*[\|\:]?\s*(.+)/gi,
          /done\s*[\|\:]?\s*(.+)/gi,
        ],
      },
    },
    {
      name: 'frontend',
      path: PathConstants.FRONTEND_LOG,
      component: 'frontend',
      patterns: {
        error: [
          /ERROR\s*(.+)/gi,
          /\[ERROR\]\s*(.+)/gi,
          /console\.error\s*(.+)/gi,
          /Failed to\s*(.+)/gi,
        ],
        warning: [
          /WARNING\s*(.+)/gi,
          /\[WARN\]\s*(.+)/gi,
          /console\.warn\s*(.+)/gi,
        ],
        task: [
          /TODO\s*(.+)/gi,
          /FIXME\s*(.+)/gi,
        ],
        completion: [
          /SUCCESS\s*(.+)/gi,
          /Built\s*(.+)/gi,
        ],
      },
    },
    {
      name: 'redis',
      path: PathConstants.REDIS_LOG,
      component: 'redis',
      patterns: {
        error: [
          /\# WARNING\s*(.+)/gi,
          /\# ERROR\s*(.+)/gi,
          /Connection refused\s*(.+)/gi,
        ],
        warning: [
          /\# Warning\s*(.+)/gi,
        ],
        task: [],
        completion: [
          /Ready to accept connections/gi,
          /DB saved/gi,
        ],
      },
    },
  ];

  // Docker services to monitor
  private dockerServices = [
    'autobot-backend',
    'autobot-frontend',
    'autobot-redis',
    'autobot-ai-stack',
    'autobot-npu-worker',
    'autobot-browser',
  ];

  constructor(private redisConfig: any) {}

  async start() {
    console.error('[BackgroundMonitor] Starting background monitoring...');

    // Connect to Redis
    this.redis = createClient(this.redisConfig);
    this.redis.on('error', (err) => console.error('Redis Error:', err));
    await this.redis.connect();

    this.isRunning = true;

    // Start log file monitoring
    await this.startLogFileMonitoring();

    // Start Docker log monitoring
    await this.startVMHealthMonitoring();

    // Start periodic system checks
    this.startPeriodicChecks();

    console.error('[BackgroundMonitor] All monitoring systems active');
  }

  async stop() {
    console.error('[BackgroundMonitor] Stopping monitoring...');
    this.isRunning = false;

    // Stop log watchers
    for (const [name, watcher] of this.logWatchers) {
      watcher.unwatch();
    }
    this.logWatchers.clear();

    // Stop Docker processes
    for (const [name, process] of this.dockerLogProcesses) {
      process.kill();
    }
    this.dockerLogProcesses.clear();

    if (this.redis) {
      await this.redis.quit();
    }
  }

  private async startLogFileMonitoring() {
    for (const config of this.logConfigs) {
      try {
        // Check if log file exists
        await fs.access(config.path);

        console.error(`[BackgroundMonitor] Monitoring ${config.name} at ${config.path}`);

        const watcher = new Tail(config.path, {
          fromBeginning: false,
          follow: true,
          logger: console,
        });

        watcher.on('line', (line: string) => {
          this.processLogLine(config, line);
        });

        watcher.on('error', (error: any) => {
          console.error(`[BackgroundMonitor] Error watching ${config.name}:`, error);
        });

        this.logWatchers.set(config.name, watcher);

      } catch (error) {
        console.error(`[BackgroundMonitor] Cannot access log file ${config.path}:`, error);

        // Try to create parent directory
        try {
          await fs.mkdir(path.dirname(config.path), { recursive: true });
          await fs.writeFile(config.path, `# Log file created by BackgroundMonitor\n`);
          console.error(`[BackgroundMonitor] Created log file ${config.path}`);

          // Retry monitoring after creation
          setTimeout(() => this.startLogFileMonitoring(), 5000);
        } catch (createError) {
          console.error(`[BackgroundMonitor] Cannot create log file ${config.path}:`, createError);
        }
      }
    }
  }

  private async startVMHealthMonitoring() {
    console.error('[BackgroundMonitor] Starting VM health monitoring for distributed architecture...');

    // VM health endpoints for distributed AutoBot architecture
    const vmHealthChecks = [
      { name: 'frontend', url: HealthCheckEndpoints.FRONTEND, component: 'frontend' },
      { name: 'npu-worker', url: HealthCheckEndpoints.NPU_WORKER, component: 'npu-worker' },
      { name: 'redis', url: HealthCheckEndpoints.REDIS, component: 'redis', type: 'redis' },
      { name: 'ai-stack', url: HealthCheckEndpoints.AI_STACK, component: 'ai-stack' },
      { name: 'browser', url: HealthCheckEndpoints.BROWSER, component: 'browser' },
      { name: 'backend', url: HealthCheckEndpoints.BACKEND, component: 'backend' }
    ];

    for (const vm of vmHealthChecks) {
      try {
        if (vm.type === 'redis') {
          // Special Redis health check using Redis PING
          const { createClient } = await import('redis');
          const testRedis = createClient({
            socket: { host: NetworkConstants.REDIS_VM_IP, port: NetworkConstants.REDIS_PORT, connectTimeout: 3000 },
          });
          await testRedis.connect();
          const pong = await testRedis.ping();
          await testRedis.quit();

          if (pong === 'PONG') {
            console.error(`[BackgroundMonitor] VM ${vm.name} (${vm.url}): HEALTHY`);
          } else {
            console.error(`[BackgroundMonitor] VM ${vm.name} (${vm.url}): UNHEALTHY (ping failed)`);
            await this.recordVMHealthIssue(vm.name, vm.component, 'PING_FAILED');
          }
        } else {
          // Standard HTTP health check
          const curlCommand = `timeout 5 curl -s -o /dev/null -w "%{http_code}" ${vm.url}`;
          const { stdout } = await execAsync(curlCommand);
          const statusCode = stdout.trim();

          if (statusCode === '200') {
            console.error(`[BackgroundMonitor] VM ${vm.name} (${vm.url}): HEALTHY`);
          } else {
            console.error(`[BackgroundMonitor] VM ${vm.name} (${vm.url}): UNHEALTHY (${statusCode})`);
            await this.recordVMHealthIssue(vm.name, vm.component, statusCode);
          }
        }
      } catch (error) {
        console.error(`[BackgroundMonitor] VM ${vm.name} health check failed:`, (error as Error).message);
        await this.recordVMHealthIssue(vm.name, vm.component, 'CONNECTION_FAILED');
      }
    }
  }

  private async recordVMHealthIssue(vmName: string, component: string, status: string) {
    if (this.redis) {
      const errorEntry = {
        id: uuidv4(),
        timestamp: new Date().toISOString(),
        error_message: `VM ${vmName} health check failed: ${status}`,
        component: component,
        severity: status === 'CONNECTION_FAILED' ? 'high' : 'medium',
        source: 'vm_health_monitor',
        vm_name: vmName,
        status: status
      };

      await this.redis.hSet('errors:all', errorEntry.id, JSON.stringify(errorEntry));
      await this.redis.lPush('errors:recent', errorEntry.id);
      await this.redis.lTrim('errors:recent', 0, 999);
    }
  }

  private startPeriodicChecks() {
    // Run system health checks every 5 minutes
    const interval = setInterval(async () => {
      if (!this.isRunning) {
        clearInterval(interval);
        return;
      }

      await this.performSystemHealthCheck();
      await this.cleanupOldData();
      await this.generatePeriodicReport();
    }, 5 * 60 * 1000); // 5 minutes
  }

  private async processLogLine(config: LogConfig, line: string) {
    if (!this.redis) return;

    const timestamp = new Date().toISOString();

    // Check for errors
    for (const pattern of config.patterns.error) {
      const match = pattern.exec(line);
      if (match) {
        const error = {
          id: uuidv4(),
          error_message: match[1] || match[0],
          full_log_line: line,
          timestamp,
          component: config.component,
          severity: this.determineSeverity(line),
          source: 'log_file',
          log_file: config.path,
        };

        await this.redis.hSet('errors:all', error.id, JSON.stringify(error));
        await this.redis.lPush('errors:recent', error.id);
        await this.redis.lTrim('errors:recent', 0, 999); // Keep last 1000 errors

        console.error(`[BackgroundMonitor] Error detected in ${config.name}: ${error.error_message}`);
        break;
      }
    }

    // Check for warnings
    for (const pattern of config.patterns.warning) {
      const match = pattern.exec(line);
      if (match) {
        const warning = {
          id: uuidv4(),
          message: match[1] || match[0],
          full_log_line: line,
          timestamp,
          component: config.component,
          source: 'log_file',
          log_file: config.path,
        };

        await this.redis.hSet('warnings:all', warning.id, JSON.stringify(warning));
        await this.redis.lPush('warnings:recent', warning.id);
        await this.redis.lTrim('warnings:recent', 0, 499); // Keep last 500 warnings
        break;
      }
    }

    // Check for task indicators
    for (const pattern of config.patterns.task) {
      const match = pattern.exec(line);
      if (match) {
        const task = {
          id: uuidv4(),
          description: match[1] || match[0],
          status: 'pending',
          created_at: timestamp,
          updated_at: timestamp,
          source: 'log_file',
          component: config.component,
          log_file: config.path,
          full_log_line: line,
        };

        await this.redis.hSet('tasks:all', task.id, JSON.stringify(task));
        await this.redis.lPush('tasks:from_logs', task.id);
        console.error(`[BackgroundMonitor] Task detected in ${config.name}: ${task.description}`);
        break;
      }
    }

    // Check for completion indicators
    for (const pattern of config.patterns.completion) {
      const match = pattern.exec(line);
      if (match) {
        await this.markRelatedTasksComplete(match[1] || match[0], config.component);
        break;
      }
    }
  }

  private async processDockerLogLine(service: string, line: string) {
    if (!this.redis) return;

    // Similar processing to log files but with Docker context
    const component = service.replace('autobot-', '');
    const timestamp = new Date().toISOString();

    // Docker-specific error patterns
    const errorPatterns = [
      /ERROR\s*(.+)/gi,
      /Exception\s*(.+)/gi,
      /Fatal\s*(.+)/gi,
      /Critical\s*(.+)/gi,
      /failed\s*(.+)/gi,
    ];

    for (const pattern of errorPatterns) {
      const match = pattern.exec(line);
      if (match) {
        const error = {
          id: uuidv4(),
          error_message: match[1] || match[0],
          full_log_line: line,
          timestamp,
          component,
          severity: this.determineSeverity(line),
          source: 'docker_logs',
          service_name: service,
        };

        await this.redis.hSet('errors:all', error.id, JSON.stringify(error));
        await this.redis.lPush('errors:recent', error.id);
        await this.redis.lTrim('errors:recent', 0, 999);

        console.error(`[BackgroundMonitor] Docker error in ${service}: ${error.error_message}`);
        break;
      }
    }

    // Store raw docker logs for analysis
    await this.redis.lPush(`docker_logs:${service}`, JSON.stringify({
      timestamp,
      line,
      service,
    }));
    await this.redis.lTrim(`docker_logs:${service}`, 0, 1999); // Keep last 2000 lines per service
  }

  private determineSeverity(line: string): 'low' | 'medium' | 'high' | 'critical' {
    const criticalKeywords = /critical|fatal|emergency|panic/i;
    const highKeywords = /error|exception|failed|failure/i;
    const mediumKeywords = /warning|warn|deprecated/i;

    if (criticalKeywords.test(line)) return 'critical';
    if (highKeywords.test(line)) return 'high';
    if (mediumKeywords.test(line)) return 'medium';
    return 'low';
  }

  private async markRelatedTasksComplete(completionMessage: string, component: string) {
    if (!this.redis) return;

    // Get all pending/in-progress tasks for this component
    const allTasks = await this.redis.hGetAll('tasks:all');

    for (const [taskId, taskData] of Object.entries(allTasks)) {
      const task = JSON.parse(taskData);

      if (task.component === component &&
          (task.status === 'pending' || task.status === 'in_progress')) {

        // Use basic string similarity to match tasks with completion messages
        if (this.isRelatedMessage(task.description, completionMessage)) {
          task.status = 'completed';
          task.updated_at = new Date().toISOString();
          task.completion_message = completionMessage;

          await this.redis.hSet('tasks:all', taskId, JSON.stringify(task));
          console.error(`[BackgroundMonitor] Marked task as completed: ${task.description}`);
        }
      }
    }
  }

  private isRelatedMessage(taskDescription: string, completionMessage: string): boolean {
    // Simple keyword matching - could be enhanced with NLP
    const taskWords = taskDescription.toLowerCase().split(/\s+/);
    const completionWords = completionMessage.toLowerCase().split(/\s+/);

    let matches = 0;
    for (const word of taskWords) {
      if (word.length > 3 && completionWords.includes(word)) {
        matches++;
      }
    }

    return matches >= 2; // Require at least 2 matching words
  }

  private async performSystemHealthCheck() {
    if (!this.redis) return;

    console.error('[BackgroundMonitor] Performing system health check...');

    const healthData = {
      timestamp: new Date().toISOString(),
      services: {} as Record<string, any>,
      system: {} as Record<string, any>,
    };

    // Check VM services for distributed architecture
    const vmServices = [
      { name: 'frontend', url: HealthCheckEndpoints.FRONTEND },
      { name: 'npu-worker', url: HealthCheckEndpoints.NPU_WORKER },
      { name: 'redis', url: HealthCheckEndpoints.REDIS, type: 'redis' },
      { name: 'ai-stack', url: HealthCheckEndpoints.AI_STACK },
      { name: 'browser', url: HealthCheckEndpoints.BROWSER },
      { name: 'backend', url: HealthCheckEndpoints.BACKEND }
    ];

    for (const vm of vmServices) {
      try {
        if (vm.type === 'redis') {
          // Redis health check using PING
          const { createClient } = await import('redis');
          const testRedis = createClient({
            socket: { host: NetworkConstants.REDIS_VM_IP, port: NetworkConstants.REDIS_PORT, connectTimeout: 3000 },
          });
          await testRedis.connect();
          const pong = await testRedis.ping();
          await testRedis.quit();

          healthData.services[vm.name] = {
            status: pong === 'PONG' ? 'healthy' : 'unhealthy',
            healthy: pong === 'PONG',
            url: vm.url,
            ping_response: pong
          };
        } else {
          // HTTP health check
          const curlCommand = `timeout 3 curl -s -o /dev/null -w "%{http_code}" ${vm.url}`;
          const { stdout } = await execAsync(curlCommand);
          const statusCode = stdout.trim();
          healthData.services[vm.name] = {
            status: statusCode === '200' ? 'healthy' : 'unhealthy',
            healthy: statusCode === '200',
            url: vm.url,
            status_code: statusCode
          };
        }
      } catch (error) {
        healthData.services[vm.name] = {
          status: 'connection_failed',
          healthy: false,
          url: vm.url,
          error: (error as Error).message,
        };
      }
    }

    // Check disk space
    try {
      const { stdout } = await execAsync(`df -h ${PathConstants.PROJECT_ROOT}`);
      const diskInfo = stdout.split('\n')[1].split(/\s+/);
      healthData.system.disk = {
        usage: diskInfo[4],
        available: diskInfo[3],
      };
    } catch (error) {
      healthData.system.disk = { error: (error as Error).message };
    }

    // Check memory usage
    try {
      const { stdout } = await execAsync('free -m');
      const memInfo = stdout.split('\n')[1].split(/\s+/);
      healthData.system.memory = {
        total: memInfo[1],
        used: memInfo[2],
        free: memInfo[3],
      };
    } catch (error) {
      healthData.system.memory = { error: (error as Error).message };
    }

    await this.redis.hSet('system:health_checks', healthData.timestamp, JSON.stringify(healthData));

    // Alert on critical issues
    const unhealthyServices = Object.entries(healthData.services)
      .filter(([name, data]: [string, any]) => !data.healthy);

    if (unhealthyServices.length > 0) {
      const alert = {
        id: uuidv4(),
        type: 'system_health',
        severity: 'high',
        message: `Unhealthy services detected: ${unhealthyServices.map(([name]) => name).join(', ')}`,
        timestamp: healthData.timestamp,
        details: unhealthyServices,
      };

      await this.redis.hSet('alerts:all', alert.id, JSON.stringify(alert));
      await this.redis.lPush('alerts:recent', alert.id);
      console.error(`[BackgroundMonitor] ALERT: ${alert.message}`);
    }
  }

  private async cleanupOldData() {
    if (!this.redis) return;

    // Clean up old errors (keep last 30 days)
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();

    const allErrors = await this.redis.hGetAll('errors:all');
    for (const [errorId, errorData] of Object.entries(allErrors)) {
      const error = JSON.parse(errorData);
      if (error.timestamp < thirtyDaysAgo) {
        await this.redis.hDel('errors:all', errorId);
      }
    }

    // Clean up old warnings (keep last 7 days)
    const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

    const allWarnings = await this.redis.hGetAll('warnings:all');
    for (const [warningId, warningData] of Object.entries(allWarnings)) {
      const warning = JSON.parse(warningData);
      if (warning.timestamp < sevenDaysAgo) {
        await this.redis.hDel('warnings:all', warningId);
      }
    }

    console.error('[BackgroundMonitor] Cleaned up old monitoring data');
  }

  private async generatePeriodicReport() {
    if (!this.redis) return;

    const report = {
      timestamp: new Date().toISOString(),
      period: 'last_5_minutes',
      summary: {} as Record<string, any>,
    };

    // Get recent errors
    const recentErrors = await this.redis.lRange('errors:recent', 0, 49); // Last 50
    report.summary.recent_errors = recentErrors.length;

    // Get recent warnings
    const recentWarnings = await this.redis.lRange('warnings:recent', 0, 49);
    report.summary.recent_warnings = recentWarnings.length;

    // Get unfinished tasks
    const allTasks = await this.redis.hGetAll('tasks:all');
    const unfinishedTasks = Object.values(allTasks)
      .map(data => JSON.parse(data))
      .filter(task => task.status !== 'completed').length;
    report.summary.unfinished_tasks = unfinishedTasks;

    await this.redis.hSet('reports:periodic', report.timestamp, JSON.stringify(report));

    // Keep only last 100 reports
    const reportKeys = await this.redis.hKeys('reports:periodic');
    if (reportKeys.length > 100) {
      const sortedKeys = reportKeys.sort();
      for (let i = 0; i < sortedKeys.length - 100; i++) {
        await this.redis.hDel('reports:periodic', sortedKeys[i]);
      }
    }

    console.error(`[BackgroundMonitor] Periodic report: ${recentErrors.length} errors, ${recentWarnings.length} warnings, ${unfinishedTasks} unfinished tasks`);
  }

  // Public API for external queries
  async getRecentActivity(minutes: number = 60) {
    if (!this.redis) return null;

    const cutoff = new Date(Date.now() - minutes * 60 * 1000).toISOString();

    const recentErrors: any[] = [];
    const recentWarnings: any[] = [];
    const recentTasks: any[] = [];

    // Get recent errors
    const errorIds = await this.redis.lRange('errors:recent', 0, -1);
    for (const id of errorIds) {
      const errorData = await this.redis.hGet('errors:all', id);
      if (errorData) {
        const error = JSON.parse(errorData);
        if (error.timestamp > cutoff) {
          recentErrors.push(error);
        }
      }
    }

    // Get recent warnings
    const warningIds = await this.redis.lRange('warnings:recent', 0, -1);
    for (const id of warningIds) {
      const warningData = await this.redis.hGet('warnings:all', id);
      if (warningData) {
        const warning = JSON.parse(warningData);
        if (warning.timestamp > cutoff) {
          recentWarnings.push(warning);
        }
      }
    }

    // Get recent tasks
    const taskIds = await this.redis.lRange('tasks:from_logs', 0, -1);
    for (const id of taskIds) {
      const taskData = await this.redis.hGet('tasks:all', id);
      if (taskData) {
        const task = JSON.parse(taskData);
        if (task.created_at > cutoff) {
          recentTasks.push(task);
        }
      }
    }

    return {
      period_minutes: minutes,
      errors: recentErrors,
      warnings: recentWarnings,
      tasks: recentTasks,
      summary: {
        total_errors: recentErrors.length,
        total_warnings: recentWarnings.length,
        total_tasks: recentTasks.length,
      },
    };
  }
}
