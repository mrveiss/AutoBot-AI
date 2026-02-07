import { createClient } from 'redis';

interface KnowledgeEntry {
  id: string;
  title: string;
  content: string;
  category: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  source: 'chat_analysis' | 'error_pattern' | 'task_correlation' | 'system_insight';
  confidence: number;
  related_tasks: string[];
  related_errors: string[];
}

export class KnowledgeIntegration {
  private redis: ReturnType<typeof createClient> | null = null;

  constructor(private redisConfig: any) {}

  async connect() {
    // Connect to AutoBot's knowledge base database (DB 1)
    this.redis = createClient({
      ...this.redisConfig,
      database: 1, // AutoBot's knowledge database
    });
    this.redis.on('error', (err) => console.error('Knowledge Redis Error:', err));
    await this.redis.connect();
    console.error('Connected to AutoBot knowledge base (DB 1)');
  }

  async disconnect() {
    if (this.redis) {
      await this.redis.quit();
    }
  }

  // Analyze patterns and generate knowledge entries
  async analyzeAndGenerateKnowledge() {
    if (!this.redis) throw new Error('Knowledge integration not connected');

    console.error('[KnowledgeIntegration] Starting pattern analysis...');

    const insights: KnowledgeEntry[] = [];

    // Analyze error patterns
    const errorPatterns = await this.analyzeErrorPatterns();
    insights.push(...errorPatterns);

    // Analyze task patterns
    const taskPatterns = await this.analyzeTaskPatterns();
    insights.push(...taskPatterns);

    // Analyze system behavior patterns
    const systemPatterns = await this.analyzeSystemPatterns();
    insights.push(...systemPatterns);

    // Store insights in knowledge base
    for (const insight of insights) {
      await this.storeKnowledgeEntry(insight);
    }

    console.error(`[KnowledgeIntegration] Generated ${insights.length} knowledge entries`);
    return insights;
  }

  private async analyzeErrorPatterns(): Promise<KnowledgeEntry[]> {
    // Get tracking Redis connection (DB 10)
    const trackingRedis = createClient({
      ...this.redisConfig,
      database: 10,
    });
    await trackingRedis.connect();

    try {
      const insights: KnowledgeEntry[] = [];
      const allErrors = await trackingRedis.hGetAll('errors:all');

      // Group errors by component and message patterns
      const errorGroups: Record<string, any[]> = {};

      for (const [errorId, errorData] of Object.entries(allErrors)) {
        const error = JSON.parse(errorData);
        const key = `${error.component}:${this.extractErrorType(error.error_message)}`;

        if (!errorGroups[key]) {
          errorGroups[key] = [];
        }
        errorGroups[key].push(error);
      }

      // Generate insights for frequent error patterns
      for (const [pattern, errors] of Object.entries(errorGroups)) {
        if (errors.length >= 3) { // Pattern with 3+ occurrences
          const [component, errorType] = pattern.split(':');

          insights.push({
            id: `error-pattern-${pattern.replace(/[^a-zA-Z0-9]/g, '-')}`,
            title: `Recurring ${errorType} Error in ${component}`,
            content: this.generateErrorPatternAnalysis(errors),
            category: 'error_patterns',
            tags: ['error', 'pattern', component, errorType],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            source: 'error_pattern',
            confidence: this.calculateConfidence(errors.length, 'error'),
            related_tasks: this.extractRelatedTasks(errors),
            related_errors: errors.map(e => e.id),
          });
        }
      }

      return insights;
    } finally {
      await trackingRedis.quit();
    }
  }

  private async analyzeTaskPatterns(): Promise<KnowledgeEntry[]> {
    const trackingRedis = createClient({
      ...this.redisConfig,
      database: 10,
    });
    await trackingRedis.connect();

    try {
      const insights: KnowledgeEntry[] = [];
      const allTasks = await trackingRedis.hGetAll('tasks:all');

      // Analyze task completion patterns
      const tasksByComponent: Record<string, any[]> = {};
      const unfinishedByType: Record<string, any[]> = {};

      for (const [taskId, taskData] of Object.entries(allTasks)) {
        const task = JSON.parse(taskData);

        // Group by component
        if (!tasksByComponent[task.component]) {
          tasksByComponent[task.component] = [];
        }
        tasksByComponent[task.component].push(task);

        // Group unfinished tasks by type
        if (task.status !== 'completed') {
          const taskType = this.categorizeTask(task.description);
          if (!unfinishedByType[taskType]) {
            unfinishedByType[taskType] = [];
          }
          unfinishedByType[taskType].push(task);
        }
      }

      // Generate insights for unfinished task patterns
      for (const [taskType, tasks] of Object.entries(unfinishedByType)) {
        if (tasks.length >= 2) {
          insights.push({
            id: `task-pattern-${taskType}`,
            title: `Recurring ${taskType} Tasks Need Attention`,
            content: this.generateTaskPatternAnalysis(tasks, taskType),
            category: 'task_patterns',
            tags: ['task', 'pattern', taskType, 'unfinished'],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            source: 'task_correlation',
            confidence: this.calculateConfidence(tasks.length, 'task'),
            related_tasks: tasks.map(t => t.id),
            related_errors: tasks.flatMap(t => t.error_correlations || []),
          });
        }
      }

      return insights;
    } finally {
      await trackingRedis.quit();
    }
  }

  private async analyzeSystemPatterns(): Promise<KnowledgeEntry[]> {
    const trackingRedis = createClient({
      ...this.redisConfig,
      database: 10,
    });
    await trackingRedis.connect();

    try {
      const insights: KnowledgeEntry[] = [];

      // Get recent health checks
      const healthChecks = await trackingRedis.hGetAll('system:health_checks');
      const healthData = Object.values(healthChecks)
        .map(data => JSON.parse(data))
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, 20); // Last 20 health checks

      // Analyze service stability
      const serviceHealth = this.analyzeServiceHealth(healthData);
      if (serviceHealth.unstableServices.length > 0) {
        insights.push({
          id: 'system-stability-issues',
          title: 'Service Stability Issues Detected',
          content: this.generateServiceStabilityAnalysis(serviceHealth),
          category: 'system_insights',
          tags: ['system', 'stability', 'services', 'health'],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          source: 'system_insight',
          confidence: this.calculateConfidence(serviceHealth.unstableServices.length, 'system'),
          related_tasks: [],
          related_errors: [],
        });
      }

      // Analyze resource usage patterns
      const resourcePatterns = this.analyzeResourcePatterns(healthData);
      if (resourcePatterns.issues.length > 0) {
        insights.push({
          id: 'resource-usage-patterns',
          title: 'Resource Usage Patterns Identified',
          content: this.generateResourceAnalysis(resourcePatterns),
          category: 'system_insights',
          tags: ['system', 'resources', 'memory', 'disk'],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          source: 'system_insight',
          confidence: this.calculateConfidence(resourcePatterns.issues.length, 'system'),
          related_tasks: [],
          related_errors: [],
        });
      }

      return insights;
    } finally {
      await trackingRedis.quit();
    }
  }

  private async storeKnowledgeEntry(entry: KnowledgeEntry) {
    if (!this.redis) return;

    // Store in AutoBot's knowledge base format
    await this.redis.hSet('mcp_insights:all', entry.id, JSON.stringify(entry));

    // Add to category index
    await this.redis.sAdd(`mcp_insights:category:${entry.category}`, entry.id);

    // Add to tag indexes
    for (const tag of entry.tags) {
      await this.redis.sAdd(`mcp_insights:tag:${tag}`, entry.id);
    }

    // Create searchable text entry for AutoBot's search system
    const searchableEntry = {
      id: entry.id,
      title: entry.title,
      content: entry.content,
      metadata: {
        source: 'mcp-autobot-tracker',
        category: entry.category,
        tags: entry.tags,
        confidence: entry.confidence,
        created_at: entry.created_at,
      },
    };

    await this.redis.hSet('knowledge:entries', entry.id, JSON.stringify(searchableEntry));

    console.error(`[KnowledgeIntegration] Stored knowledge entry: ${entry.title}`);
  }

  // Helper methods
  private extractErrorType(errorMessage: string): string {
    if (/connection|timeout|refused/i.test(errorMessage)) return 'connection';
    if (/import|module|not found/i.test(errorMessage)) return 'import';
    if (/permission|access|forbidden/i.test(errorMessage)) return 'permission';
    if (/memory|out of/i.test(errorMessage)) return 'memory';
    if (/disk|space|full/i.test(errorMessage)) return 'disk';
    if (/database|redis|sql/i.test(errorMessage)) return 'database';
    return 'general';
  }

  private categorizeTask(description: string): string {
    if (/fix|error|bug|issue/i.test(description)) return 'bug_fix';
    if (/implement|create|add|new/i.test(description)) return 'feature';
    if (/update|upgrade|modify/i.test(description)) return 'update';
    if (/test|testing|spec/i.test(description)) return 'testing';
    if (/deploy|deployment|build/i.test(description)) return 'deployment';
    if (/config|configuration|setup/i.test(description)) return 'configuration';
    return 'general';
  }

  private calculateConfidence(count: number, type: 'error' | 'task' | 'system'): number {
    const baseConfidence = {
      error: 0.7,
      task: 0.6,
      system: 0.8,
    };

    return Math.min(0.95, baseConfidence[type] + (count * 0.05));
  }

  private extractRelatedTasks(errors: any[]): string[] {
    return [...new Set(errors.flatMap(e => e.correlated_tasks || []))];
  }

  private generateErrorPatternAnalysis(errors: any[]): string {
    const totalErrors = errors.length;
    const timeRange = this.getTimeRange(errors);
    const components = [...new Set(errors.map(e => e.component))];
    const severities = errors.reduce((acc, e) => {
      acc[e.severity] = (acc[e.severity] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return `## Error Pattern Analysis

**Pattern Summary:**
- Total occurrences: ${totalErrors}
- Time range: ${timeRange}
- Affected components: ${components.join(', ')}
- Severity distribution: ${Object.entries(severities)
  .map(([sev, count]) => `${sev}: ${count}`)
  .join(', ')}

**Recommended Actions:**
1. Review error handling in affected components
2. Implement better error logging and monitoring
3. Consider adding circuit breakers for recurring failures
4. Review system resources if memory/disk related

**Sample Error Messages:**
${errors.slice(0, 3).map(e => `- ${e.error_message}`).join('\n')}

This pattern suggests a systemic issue that requires investigation and resolution.`;
  }

  private generateTaskPatternAnalysis(tasks: any[], taskType: string): string {
    const totalTasks = tasks.length;
    const timeRange = this.getTimeRange(tasks, 'created_at');
    const components = [...new Set(tasks.map(t => t.component).filter(Boolean))];

    return `## Unfinished Task Pattern Analysis

**Pattern Summary:**
- Task type: ${taskType}
- Unfinished count: ${totalTasks}
- Time range: ${timeRange}
- Affected components: ${components.length > 0 ? components.join(', ') : 'Various'}

**Task Examples:**
${tasks.slice(0, 5).map(t => `- ${t.description} (${t.status})`).join('\n')}

**Recommended Actions:**
1. Prioritize completion of these related tasks
2. Investigate common blockers for this task type
3. Consider breaking large tasks into smaller parts
4. Review resource allocation for affected components

This pattern indicates recurring work that may benefit from systematic attention.`;
  }

  private generateServiceStabilityAnalysis(serviceHealth: any): string {
    return `## Service Stability Analysis

**Unstable Services:**
${serviceHealth.unstableServices.map((s: any) =>
  `- **${s.name}**: ${s.failureRate}% failure rate (${s.failures}/${s.total} checks)`
).join('\n')}

**Recommended Actions:**
1. Investigate root causes of service instability
2. Review service configuration and resource limits
3. Implement better health checks and recovery mechanisms
4. Consider service redundancy for critical components

**Health Check Period:** ${serviceHealth.period}
**Total Checks:** ${serviceHealth.totalChecks}`;
  }

  private generateResourceAnalysis(resourcePatterns: any): string {
    return `## Resource Usage Analysis

**Issues Identified:**
${resourcePatterns.issues.map((issue: any) => `- **${issue.type}**: ${issue.description}`).join('\n')}

**Trends:**
${resourcePatterns.trends.map((trend: any) => `- **${trend.metric}**: ${trend.direction} trend`).join('\n')}

**Recommended Actions:**
1. Monitor resource usage more closely
2. Consider scaling resources if usage is consistently high
3. Implement alerts for resource thresholds
4. Review application efficiency and optimization opportunities

**Analysis Period:** ${resourcePatterns.period}`;
  }

  private analyzeServiceHealth(healthData: any[]): any {
    const serviceStats: Record<string, { total: number; failures: number }> = {};

    for (const health of healthData) {
      for (const [serviceName, serviceData] of Object.entries(health.services || {})) {
        if (!serviceStats[serviceName]) {
          serviceStats[serviceName] = { total: 0, failures: 0 };
        }
        serviceStats[serviceName].total++;
        if (!(serviceData as any).healthy) {
          serviceStats[serviceName].failures++;
        }
      }
    }

    const unstableServices = Object.entries(serviceStats)
      .filter(([_, stats]) => stats.failures > 0)
      .map(([name, stats]) => ({
        name,
        failures: stats.failures,
        total: stats.total,
        failureRate: ((stats.failures / stats.total) * 100).toFixed(1),
      }))
      .filter(service => parseFloat(service.failureRate) >= 10); // 10% or more failure rate

    return {
      unstableServices,
      totalChecks: healthData.length,
      period: this.getTimeRange(healthData),
    };
  }

  private analyzeResourcePatterns(healthData: any[]): any {
    const issues: any[] = [];
    const trends: any[] = [];

    // Simple resource analysis
    const latestHealth = healthData[0];
    if (latestHealth?.system?.disk?.usage) {
      const diskUsage = parseInt(latestHealth.system.disk.usage.replace('%', ''));
      if (diskUsage > 80) {
        issues.push({
          type: 'disk_space',
          description: `High disk usage detected: ${diskUsage}%`,
        });
      }
    }

    return {
      issues,
      trends,
      period: this.getTimeRange(healthData),
    };
  }

  private getTimeRange(items: any[], timeField: string = 'timestamp'): string {
    if (items.length === 0) return 'No data';

    const times = items.map(item => new Date(item[timeField]).getTime()).sort();
    const start = new Date(times[0]);
    const end = new Date(times[times.length - 1]);

    if (start.getTime() === end.getTime()) {
      return start.toISOString().split('T')[0];
    }

    return `${start.toISOString().split('T')[0]} to ${end.toISOString().split('T')[0]}`;
  }

  // Public API for querying insights
  async getInsights(category?: string, tags?: string[]): Promise<KnowledgeEntry[]> {
    if (!this.redis) return [];

    let insightIds: string[];

    if (category) {
      insightIds = await this.redis.sMembers(`mcp_insights:category:${category}`);
    } else if (tags && tags.length > 0) {
      // Get intersection of all tag sets
      const tagSets = await Promise.all(
        tags.map(tag => this.redis!.sMembers(`mcp_insights:tag:${tag}`))
      );
      insightIds = tagSets.reduce((intersection, set) =>
        intersection.filter(id => set.includes(id))
      );
    } else {
      const allInsights = await this.redis.hGetAll('mcp_insights:all');
      insightIds = Object.keys(allInsights);
    }

    const insights: KnowledgeEntry[] = [];
    for (const id of insightIds) {
      const data = await this.redis.hGet('mcp_insights:all', id);
      if (data) {
        insights.push(JSON.parse(data));
      }
    }

    return insights.sort((a, b) =>
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    );
  }
}
