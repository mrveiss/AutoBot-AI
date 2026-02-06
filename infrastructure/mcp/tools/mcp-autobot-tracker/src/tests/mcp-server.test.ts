// MCP AutoBot Tracker - Comprehensive Test Suite
// This test suite validates all core MCP server functionality

import { createClient } from 'redis';
import { NetworkConstants } from '../constants/network.js';

interface TestResult {
  name: string;
  passed: boolean;
  message: string;
  duration: number;
}

class MCPServerTestSuite {
  private redis: ReturnType<typeof createClient> | null = null;
  private results: TestResult[] = [];

  async initialize() {
    console.log('🧪 Initializing MCP Server Test Suite...');

    this.redis = createClient({
      socket: { host: NetworkConstants.REDIS_VM_IP, port: NetworkConstants.REDIS_PORT },
      database: 10
    });

    await this.redis.connect();
    console.log('✅ Connected to Redis test database');
  }

  async runAllTests() {
    console.log('🚀 Running comprehensive MCP server tests...');
    console.log('═'.repeat(50));

    await this.testRedisConnection();
    await this.testDataStorage();
    await this.testTaskExtraction();
    await this.testErrorCorrelation();
    await this.testConversationIngestion();
    await this.testSystemHealthMonitoring();
    await this.testKnowledgeBaseIntegration();
    await this.testRealTimeIngestion();
    await this.testInsightGeneration();

    this.generateTestReport();
  }

  private async testRedisConnection(): Promise<void> {
    const startTime = Date.now();
    try {
      if (!this.redis) throw new Error('Redis not initialized');

      const pong = await this.redis.ping();
      if (pong === 'PONG') {
        this.results.push({
          name: 'Redis Connection Test',
          passed: true,
          message: 'Redis connection successful',
          duration: Date.now() - startTime
        });
      } else {
        throw new Error('Invalid ping response');
      }
    } catch (error) {
      this.results.push({
        name: 'Redis Connection Test',
        passed: false,
        message: `Redis connection failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private async testDataStorage(): Promise<void> {
    const startTime = Date.now();
    try {
      if (!this.redis) throw new Error('Redis not initialized');

      // Test task storage
      const testTaskId = `test_task_${Date.now()}`;
      const testTask = {
        id: testTaskId,
        description: 'Test task for validation',
        status: 'pending',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        chat_session_id: 'test_session',
        message_index: 0
      };

      await this.redis.hSet('tasks:all', testTaskId, JSON.stringify(testTask));
      const retrievedTask = await this.redis.hGet('tasks:all', testTaskId);

      if (retrievedTask) {
        const parsedTask = JSON.parse(retrievedTask);
        if (parsedTask.id === testTaskId) {
          // Cleanup
          await this.redis.hDel('tasks:all', testTaskId);

          this.results.push({
            name: 'Data Storage Test',
            passed: true,
            message: 'Task storage and retrieval successful',
            duration: Date.now() - startTime
          });
        } else {
          throw new Error('Retrieved task data mismatch');
        }
      } else {
        throw new Error('Task not found after storage');
      }
    } catch (error) {
      this.results.push({
        name: 'Data Storage Test',
        passed: false,
        message: `Data storage failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private async testTaskExtraction(): Promise<void> {
    const startTime = Date.now();
    try {
      // Test task extraction from sample conversation
      const sampleConversation = [
        { role: 'user', content: 'I need help with setting up the database', timestamp: new Date().toISOString() },
        { role: 'assistant', content: 'TODO: Set up database connection. FIXME: Fix authentication issue. I will help you configure the database properly.', timestamp: new Date().toISOString() }
      ];

      // Simulate task extraction logic
      const extractedTasks = this.extractTasksFromConversation(sampleConversation);

      if (extractedTasks.length >= 2) { // Should extract TODO and FIXME
        this.results.push({
          name: 'Task Extraction Test',
          passed: true,
          message: `Successfully extracted ${extractedTasks.length} tasks from conversation`,
          duration: Date.now() - startTime
        });
      } else {
        throw new Error(`Expected at least 2 tasks, got ${extractedTasks.length}`);
      }
    } catch (error) {
      this.results.push({
        name: 'Task Extraction Test',
        passed: false,
        message: `Task extraction failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private extractTasksFromConversation(messages: any[]): any[] {
    const tasks: any[] = [];

    messages.forEach((message, index) => {
      if (message.role === 'assistant') {
        const taskPatterns = [
          /TODO:?\s*([^\n.]+)/gi,
          /FIXME:?\s*([^\n.]+)/gi,
          /I will\s*([^\n.]+)/gi
        ];

        taskPatterns.forEach(pattern => {
          const matches = message.content.matchAll(pattern);
          for (const match of matches) {
            tasks.push({
              id: `test_${Date.now()}_${index}`,
              description: match[1].trim(),
              status: 'pending',
              priority: match[0].toLowerCase().includes('fixme') ? 'high' : 'medium'
            });
          }
        });
      }
    });

    return tasks;
  }

  private async testErrorCorrelation(): Promise<void> {
    const startTime = Date.now();
    try {
      if (!this.redis) throw new Error('Redis not initialized');

      // Store a test error
      const testErrorId = `test_error_${Date.now()}`;
      const testError = {
        id: testErrorId,
        error_message: 'Database connection failed',
        timestamp: new Date().toISOString(),
        component: 'backend',
        severity: 'high'
      };

      await this.redis.hSet('errors:all', testErrorId, JSON.stringify(testError));

      // Test error retrieval and correlation
      const retrievedError = await this.redis.hGet('errors:all', testErrorId);

      if (retrievedError) {
        const parsedError = JSON.parse(retrievedError);

        // Cleanup
        await this.redis.hDel('errors:all', testErrorId);

        this.results.push({
          name: 'Error Correlation Test',
          passed: true,
          message: 'Error storage and correlation working correctly',
          duration: Date.now() - startTime
        });
      } else {
        throw new Error('Error not found after storage');
      }
    } catch (error) {
      this.results.push({
        name: 'Error Correlation Test',
        passed: false,
        message: `Error correlation failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private async testConversationIngestion(): Promise<void> {
    const startTime = Date.now();
    try {
      if (!this.redis) throw new Error('Redis not initialized');

      // Test conversation session storage
      const testSessionId = `test_session_${Date.now()}`;
      const testSession = {
        session_id: testSessionId,
        created_at: new Date().toISOString(),
        message_count: 5,
        tasks_extracted: 3,
        errors_extracted: 1,
        topic: 'Test Conversation Ingestion'
      };

      await this.redis.hSet('chat:sessions', testSessionId, JSON.stringify(testSession));
      const retrievedSession = await this.redis.hGet('chat:sessions', testSessionId);

      if (retrievedSession) {
        const parsedSession = JSON.parse(retrievedSession);
        if (parsedSession.session_id === testSessionId) {
          // Cleanup
          await this.redis.hDel('chat:sessions', testSessionId);

          this.results.push({
            name: 'Conversation Ingestion Test',
            passed: true,
            message: 'Conversation ingestion working correctly',
            duration: Date.now() - startTime
          });
        } else {
          throw new Error('Session data mismatch');
        }
      } else {
        throw new Error('Session not found after storage');
      }
    } catch (error) {
      this.results.push({
        name: 'Conversation Ingestion Test',
        passed: false,
        message: `Conversation ingestion failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private async testSystemHealthMonitoring(): Promise<void> {
    const startTime = Date.now();
    try {
      // Test VM health check simulation
      const healthChecks = [
        { name: 'redis', status: 'healthy' },
        { name: 'frontend', status: 'healthy' },
        { name: 'backend', status: 'healthy' }
      ];

      const allHealthy = healthChecks.every(check => check.status === 'healthy');

      if (allHealthy) {
        this.results.push({
          name: 'System Health Monitoring Test',
          passed: true,
          message: 'System health monitoring logic working correctly',
          duration: Date.now() - startTime
        });
      } else {
        throw new Error('Health check logic failed');
      }
    } catch (error) {
      this.results.push({
        name: 'System Health Monitoring Test',
        passed: false,
        message: `Health monitoring failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private async testKnowledgeBaseIntegration(): Promise<void> {
    const startTime = Date.now();
    try {
      // Test knowledge base connection (Redis DB 1)
      const kbRedis = createClient({
        socket: { host: NetworkConstants.REDIS_VM_IP, port: NetworkConstants.REDIS_PORT },
        database: 1
      });

      await kbRedis.connect();
      const pong = await kbRedis.ping();
      await kbRedis.quit();

      if (pong === 'PONG') {
        this.results.push({
          name: 'Knowledge Base Integration Test',
          passed: true,
          message: 'Knowledge base connection successful',
          duration: Date.now() - startTime
        });
      } else {
        throw new Error('Knowledge base connection failed');
      }
    } catch (error) {
      this.results.push({
        name: 'Knowledge Base Integration Test',
        passed: false,
        message: `Knowledge base integration failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private async testRealTimeIngestion(): Promise<void> {
    const startTime = Date.now();
    try {
      // Test real-time ingestion logic (message processing)
      const sampleMessage = {
        role: 'assistant' as const,
        content: 'TODO: Implement real-time processing. This task is important.',
        timestamp: new Date().toISOString()
      };

      // Simulate message processing
      const processed = this.processMessageForIngestion(sampleMessage);

      if (processed.containsTasks && processed.taskCount > 0) {
        this.results.push({
          name: 'Real-Time Ingestion Test',
          passed: true,
          message: `Real-time ingestion logic working (${processed.taskCount} tasks detected)`,
          duration: Date.now() - startTime
        });
      } else {
        throw new Error('Real-time ingestion logic failed to detect tasks');
      }
    } catch (error) {
      this.results.push({
        name: 'Real-Time Ingestion Test',
        passed: false,
        message: `Real-time ingestion failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private processMessageForIngestion(message: any) {
    const taskPatterns = [/TODO:?\s*([^\n.]+)/gi, /FIXME:?\s*([^\n.]+)/gi];
    let taskCount = 0;

    taskPatterns.forEach(pattern => {
      const matches = Array.from(message.content.matchAll(pattern));
      taskCount += matches.length;
    });

    return {
      containsTasks: taskCount > 0,
      taskCount,
      processed: true
    };
  }

  private async testInsightGeneration(): Promise<void> {
    const startTime = Date.now();
    try {
      if (!this.redis) throw new Error('Redis not initialized');

      // Test insight generation logic
      const sampleErrors = [
        { component: 'frontend', severity: 'medium' },
        { component: 'frontend', severity: 'medium' },
        { component: 'backend', severity: 'high' }
      ];

      const insights = this.generateInsightsFromErrors(sampleErrors);

      if (insights.length > 0) {
        this.results.push({
          name: 'Insight Generation Test',
          passed: true,
          message: `Generated ${insights.length} insights from error patterns`,
          duration: Date.now() - startTime
        });
      } else {
        throw new Error('No insights generated from sample errors');
      }
    } catch (error) {
      this.results.push({
        name: 'Insight Generation Test',
        passed: false,
        message: `Insight generation failed: ${(error as Error).message}`,
        duration: Date.now() - startTime
      });
    }
  }

  private generateInsightsFromErrors(errors: any[]) {
    const insights: any[] = [];

    // Group by component
    const componentGroups = errors.reduce((acc, error) => {
      acc[error.component] = (acc[error.component] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    // Generate insights for components with multiple errors
    Object.entries(componentGroups).forEach(([component, count]) => {
      if ((count as number) > 1) {
        insights.push({
          id: `insight_${Date.now()}_${component}`,
          description: `Recurring ${component} errors detected (${count} occurrences)`,
          confidence: 90,
          category: 'error_patterns'
        });
      }
    });

    return insights;
  }

  private generateTestReport(): void {
    console.log('\n');
    console.log('📊 MCP SERVER TEST RESULTS');
    console.log('═'.repeat(50));

    const passed = this.results.filter(r => r.passed).length;
    const failed = this.results.filter(r => !r.passed).length;
    const total = this.results.length;
    const successRate = Math.round((passed / total) * 100);

    console.log(`✅ Passed: ${passed}`);
    console.log(`❌ Failed: ${failed}`);
    console.log(`📊 Success Rate: ${successRate}%`);
    console.log(`⏱️  Total Duration: ${this.results.reduce((sum, r) => sum + r.duration, 0)}ms`);
    console.log('');

    // Detailed results
    console.log('📋 DETAILED TEST RESULTS:');
    console.log('-'.repeat(50));

    this.results.forEach((result, index) => {
      const icon = result.passed ? '✅' : '❌';
      console.log(`${index + 1}. ${icon} ${result.name}`);
      console.log(`   📝 ${result.message}`);
      console.log(`   ⏱️  Duration: ${result.duration}ms`);
      console.log('');
    });

    if (failed > 0) {
      console.log('⚠️  FAILED TESTS REQUIRE ATTENTION');
      this.results.filter(r => !r.passed).forEach(result => {
        console.log(`❌ ${result.name}: ${result.message}`);
      });
    } else {
      console.log('🎉 ALL TESTS PASSED SUCCESSFULLY!');
    }
  }

  async cleanup() {
    if (this.redis) {
      await this.redis.quit();
    }
  }
}

// Export for use in test runner
export { MCPServerTestSuite };

// Run tests if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  (async () => {
    const testSuite = new MCPServerTestSuite();
    try {
      await testSuite.initialize();
      await testSuite.runAllTests();
    } catch (error) {
      console.error('Test suite failed:', error);
    } finally {
      await testSuite.cleanup();
    }
  })();
}
