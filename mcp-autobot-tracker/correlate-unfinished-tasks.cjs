const { createClient } = require('redis');
const { v4: uuidv4 } = require('uuid');

class ConversationTaskCorrelator {
  constructor() {
    this.redis = null;
    this.allTasks = [];
    this.allSessions = [];
    this.unfinishedTasks = [];
    this.systemInsights = [];
  }

  async initialize() {
    console.log('🔄 Initializing MCP AutoBot Tracker correlation analysis...');
    this.redis = createClient({
      socket: { host: '172.16.168.23', port: 6379 },
      database: 10
    });
    await this.redis.connect();
    console.log('✅ Connected to MCP tracking database');
  }

  async loadAllConversationData() {
    console.log('📊 Loading all conversation data from MCP tracker...');
    
    // Load all chat sessions
    const sessionKeys = await this.redis.hKeys('chat:sessions');
    console.log(`📚 Found ${sessionKeys.length} conversation sessions`);
    
    for (const sessionId of sessionKeys) {
      const sessionData = await this.redis.hGet('chat:sessions', sessionId);
      if (sessionData) {
        const session = JSON.parse(sessionData);
        this.allSessions.push(session);
        
        // Load tasks for this session
        const sessionTaskIds = await this.redis.sMembers(`chat:${sessionId}:tasks`);
        for (const taskId of sessionTaskIds) {
          const taskData = await this.redis.hGet('tasks:all', taskId);
          if (taskData) {
            const task = JSON.parse(taskData);
            task.session_info = {
              session_id: sessionId,
              topic: session.topic,
              created_at: session.created_at
            };
            this.allTasks.push(task);
          }
        }
      }
    }

    console.log(`📋 Loaded ${this.allTasks.length} total tasks from all conversations`);
  }

  async loadSystemInsights() {
    console.log('🧠 Loading system insights and error patterns...');
    
    // Load recent insights
    const insightIds = await this.redis.lRange('insights:recent', 0, -1);
    
    for (const insightId of insightIds) {
      const insightData = await this.redis.hGet('insights:all', insightId);
      if (insightData) {
        this.systemInsights.push(JSON.parse(insightData));
      }
    }
    
    console.log(`💡 Loaded ${this.systemInsights.length} system insights`);
  }

  categorizeAndAnalyzeTasks() {
    console.log('🔍 Categorizing and analyzing all tasks...');
    
    const taskStats = {
      total: this.allTasks.length,
      completed: 0,
      pending: 0,
      in_progress: 0,
      high_priority: 0,
      medium_priority: 0,
      low_priority: 0
    };

    const tasksByComponent = {};
    const tasksBySession = {};

    this.allTasks.forEach(task => {
      // Update stats
      taskStats[task.status] = (taskStats[task.status] || 0) + 1;
      taskStats[task.priority + '_priority'] = (taskStats[task.priority + '_priority'] || 0) + 1;
      
      // Group by component
      if (!tasksByComponent[task.component]) {
        tasksByComponent[task.component] = { total: 0, completed: 0, pending: 0, in_progress: 0, tasks: [] };
      }
      tasksByComponent[task.component].total++;
      tasksByComponent[task.component][task.status]++;
      tasksByComponent[task.component].tasks.push(task);
      
      // Group by session
      const sessionId = task.session_info?.session_id || 'unknown';
      if (!tasksBySession[sessionId]) {
        tasksBySession[sessionId] = { tasks: [], topic: task.session_info?.topic || 'Unknown' };
      }
      tasksBySession[sessionId].tasks.push(task);
      
      // Collect unfinished tasks
      if (task.status === 'pending' || task.status === 'in_progress') {
        this.unfinishedTasks.push(task);
      }
    });

    this.taskStats = taskStats;
    this.tasksByComponent = tasksByComponent;
    this.tasksBySession = tasksBySession;
    
    console.log(`🎯 Found ${this.unfinishedTasks.length} unfinished tasks`);
  }

  prioritizeUnfinishedTasks() {
    console.log('⚡ Prioritizing unfinished tasks by importance and dependencies...');
    
    // Sort by priority (high -> medium -> low) and then by creation date
    this.unfinishedTasks.sort((a, b) => {
      const priorityOrder = { high: 3, medium: 2, low: 1 };
      const priorityDiff = priorityOrder[b.priority] - priorityOrder[a.priority];
      
      if (priorityDiff !== 0) return priorityDiff;
      
      // If same priority, sort by creation date (oldest first)
      return new Date(a.created_at) - new Date(b.created_at);
    });

    // Identify dependencies and blockers
    const dependencyPatterns = [
      { pattern: /redis|database|connection/, component: 'infrastructure', blocking: true },
      { pattern: /backend|api|server/, component: 'backend', blocking: true },
      { pattern: /frontend|ui|interface/, component: 'frontend', blocking: false },
      { pattern: /test|validation|verification/, component: 'testing', blocking: false },
      { pattern: /docker|container|deployment/, component: 'deployment', blocking: true },
      { pattern: /security|auth|permission/, component: 'security', blocking: true }
    ];

    this.unfinishedTasks.forEach(task => {
      task.analysis = {
        is_blocker: false,
        component_type: 'other',
        estimated_effort: 'medium',
        dependencies: []
      };

      dependencyPatterns.forEach(pattern => {
        if (pattern.pattern.test(task.description.toLowerCase())) {
          task.analysis.is_blocker = pattern.blocking;
          task.analysis.component_type = pattern.component;
        }
      });

      // Estimate effort based on description length and complexity keywords
      const complexityKeywords = ['integration', 'refactor', 'redesign', 'implement', 'create', 'build'];
      const simpleKeywords = ['fix', 'update', 'add', 'configure', 'enable'];
      
      const hasComplexity = complexityKeywords.some(keyword => 
        task.description.toLowerCase().includes(keyword)
      );
      const hasSimple = simpleKeywords.some(keyword => 
        task.description.toLowerCase().includes(keyword)
      );

      if (hasComplexity && task.description.length > 50) {
        task.analysis.estimated_effort = 'high';
      } else if (hasSimple && task.description.length < 30) {
        task.analysis.estimated_effort = 'low';
      }
    });
  }

  async correlateWithCurrentSystemStatus() {
    console.log('🔗 Correlating unfinished tasks with current system status...');
    
    // Get recent system health data
    const recentErrors = await this.redis.lRange('errors:recent', 0, 19);
    const activeIssues = [];
    
    for (const errorId of recentErrors) {
      const errorData = await this.redis.hGet('errors:all', errorId);
      if (errorData) {
        const error = JSON.parse(errorData);
        // Only include errors from last 24 hours
        const errorTime = new Date(error.timestamp);
        const now = new Date();
        if ((now - errorTime) < 24 * 60 * 60 * 1000) {
          activeIssues.push(error);
        }
      }
    }

    // Correlate tasks with active issues
    this.unfinishedTasks.forEach(task => {
      const relatedErrors = activeIssues.filter(error => {
        const taskKeywords = task.description.toLowerCase().split(/\s+/);
        const errorKeywords = error.error_message.toLowerCase().split(/\s+/);
        
        return taskKeywords.some(keyword => 
          errorKeywords.some(errorWord => 
            errorWord.includes(keyword) || keyword.includes(errorWord)
          )
        );
      });
      
      if (relatedErrors.length > 0) {
        task.analysis.active_issues = relatedErrors.length;
        task.analysis.urgent = true;
        task.priority = 'high'; // Upgrade priority if there are active issues
      }
    });

    console.log(`🚨 Found ${activeIssues.length} active system issues in last 24 hours`);
  }

  generateComprehensiveReport() {
    console.log('📊 Generating comprehensive unfinished tasks report...');
    console.log('');
    console.log('═'.repeat(80));
    console.log('🎯 MCP AUTOBOT TRACKER - UNFINISHED TASKS CORRELATION ANALYSIS');
    console.log('═'.repeat(80));
    console.log('');

    // Overall statistics
    console.log('📈 OVERALL TASK STATISTICS:');
    console.log('-'.repeat(40));
    console.log(`📋 Total Tasks Tracked: ${this.taskStats.total}`);
    console.log(`✅ Completed: ${this.taskStats.completed} (${Math.round((this.taskStats.completed / this.taskStats.total) * 100)}%)`);
    console.log(`⏳ Pending: ${this.taskStats.pending}`);
    console.log(`🔄 In Progress: ${this.taskStats.in_progress}`);
    console.log(`⚠️  Unfinished: ${this.unfinishedTasks.length} (${Math.round((this.unfinishedTasks.length / this.taskStats.total) * 100)}%)`);
    console.log('');

    // Priority breakdown
    console.log('🎯 PRIORITY BREAKDOWN:');
    console.log('-'.repeat(25));
    console.log(`🔴 High Priority: ${this.taskStats.high_priority}`);
    console.log(`🟡 Medium Priority: ${this.taskStats.medium_priority}`);
    console.log(`🟢 Low Priority: ${this.taskStats.low_priority}`);
    console.log('');

    // Component analysis
    console.log('🏗️  TASKS BY COMPONENT:');
    console.log('-'.repeat(30));
    Object.entries(this.tasksByComponent)
      .sort(([,a], [,b]) => (b.pending + b.in_progress) - (a.pending + a.in_progress))
      .slice(0, 8)
      .forEach(([component, data]) => {
        const unfinishedCount = data.pending + data.in_progress;
        const completionRate = Math.round((data.completed / data.total) * 100);
        console.log(`  📦 ${component}: ${unfinishedCount} unfinished / ${data.total} total (${completionRate}% complete)`);
      });
    console.log('');

    // Session analysis
    console.log('💬 TASKS BY CONVERSATION SESSION:');
    console.log('-'.repeat(40));
    Object.entries(this.tasksBySession)
      .sort(([,a], [,b]) => b.tasks.length - a.tasks.length)
      .slice(0, 5)
      .forEach(([sessionId, data]) => {
        const unfinished = data.tasks.filter(t => t.status !== 'completed').length;
        console.log(`  🗣️  ${data.topic.substring(0, 50)}...`);
        console.log(`      Session: ${sessionId.substring(0, 20)}...`);
        console.log(`      Tasks: ${unfinished} unfinished / ${data.tasks.length} total`);
        console.log('');
      });

    // Top priority unfinished tasks
    console.log('🚨 TOP PRIORITY UNFINISHED TASKS:');
    console.log('═'.repeat(50));
    
    const topTasks = this.unfinishedTasks
      .filter(task => task.analysis?.urgent || task.priority === 'high')
      .slice(0, 10);

    if (topTasks.length === 0) {
      console.log('🎉 No high-priority unfinished tasks found!');
    } else {
      topTasks.forEach((task, index) => {
        console.log(`${index + 1}. [${task.status.toUpperCase()}] ${task.description}`);
        console.log(`   📅 Created: ${new Date(task.created_at).toLocaleDateString()}`);
        console.log(`   🎯 Priority: ${task.priority} | Component: ${task.component}`);
        console.log(`   💪 Effort: ${task.analysis?.estimated_effort || 'unknown'}`);
        if (task.analysis?.active_issues) {
          console.log(`   🚨 Active Issues: ${task.analysis.active_issues} related errors detected`);
        }
        if (task.analysis?.is_blocker) {
          console.log('   🚫 BLOCKING OTHER WORK');
        }
        console.log(`   📍 Session: ${task.session_info?.topic || 'Unknown'}`);
        console.log('');
      });
    }

    // All unfinished tasks by category
    console.log('📋 ALL UNFINISHED TASKS BY CATEGORY:');
    console.log('═'.repeat(45));

    const tasksByType = {};
    this.unfinishedTasks.forEach(task => {
      const type = task.analysis?.component_type || 'other';
      if (!tasksByType[type]) tasksByType[type] = [];
      tasksByType[type].push(task);
    });

    Object.entries(tasksByType)
      .sort(([,a], [,b]) => b.length - a.length)
      .forEach(([type, tasks]) => {
        console.log(`\n🔧 ${type.toUpperCase()} (${tasks.length} tasks):`);
        tasks.slice(0, 5).forEach(task => {
          const urgentFlag = task.analysis?.urgent ? '🚨' : '';
          const blockerFlag = task.analysis?.is_blocker ? '🚫' : '';
          console.log(`  ${urgentFlag}${blockerFlag} [${task.priority}] ${task.description.substring(0, 70)}...`);
        });
        if (tasks.length > 5) {
          console.log(`  ... and ${tasks.length - 5} more ${type} tasks`);
        }
      });

    // Recommendations
    console.log('\n');
    console.log('🎯 ACTIONABLE RECOMMENDATIONS:');
    console.log('═'.repeat(35));

    const blockers = this.unfinishedTasks.filter(task => task.analysis?.is_blocker);
    const urgent = this.unfinishedTasks.filter(task => task.analysis?.urgent);
    const quickWins = this.unfinishedTasks.filter(task => task.analysis?.estimated_effort === 'low');

    if (blockers.length > 0) {
      console.log(`🚫 PRIORITY 1: Address ${blockers.length} blocking tasks first`);
      console.log('   These are preventing other work from proceeding');
    }

    if (urgent.length > 0) {
      console.log(`🚨 PRIORITY 2: Fix ${urgent.length} urgent issues with active system problems`);
      console.log('   These have current errors or failures affecting the system');
    }

    if (quickWins.length > 0) {
      console.log(`⚡ PRIORITY 3: Complete ${quickWins.length} quick wins for momentum`);
      console.log('   These are low-effort tasks that can be done quickly');
    }

    const remainingTasks = this.unfinishedTasks.length - blockers.length - urgent.length - quickWins.length;
    if (remainingTasks > 0) {
      console.log(`📋 PRIORITY 4: Plan work for remaining ${remainingTasks} tasks`);
      console.log('   These can be scheduled based on capacity and dependencies');
    }

    console.log('');
    console.log('💡 INSIGHTS FROM SYSTEM MONITORING:');
    console.log('-'.repeat(40));
    this.systemInsights.slice(0, 3).forEach((insight, index) => {
      console.log(`${index + 1}. ${insight.description || insight.insight}`);
      console.log(`   Confidence: ${insight.confidence || 'N/A'}%`);
      console.log('');
    });

    console.log('═'.repeat(80));
    console.log('🎉 CORRELATION ANALYSIS COMPLETE');
    console.log('═'.repeat(80));
  }

  async storeAnalysisResults() {
    console.log('💾 Storing correlation analysis results...');
    
    const analysisResult = {
      id: uuidv4(),
      timestamp: new Date().toISOString(),
      analysis_type: 'unfinished_tasks_correlation',
      summary: {
        total_tasks: this.taskStats.total,
        unfinished_tasks: this.unfinishedTasks.length,
        completion_rate: Math.round((this.taskStats.completed / this.taskStats.total) * 100),
        high_priority_unfinished: this.unfinishedTasks.filter(t => t.priority === 'high').length,
        urgent_tasks: this.unfinishedTasks.filter(t => t.analysis?.urgent).length,
        blocking_tasks: this.unfinishedTasks.filter(t => t.analysis?.is_blocker).length
      },
      unfinished_tasks: this.unfinishedTasks.map(task => ({
        id: task.id,
        description: task.description,
        priority: task.priority,
        status: task.status,
        component: task.component,
        estimated_effort: task.analysis?.estimated_effort,
        is_urgent: task.analysis?.urgent || false,
        is_blocker: task.analysis?.is_blocker || false,
        active_issues: task.analysis?.active_issues || 0
      })),
      recommendations: {
        immediate_blockers: this.unfinishedTasks.filter(t => t.analysis?.is_blocker).length,
        urgent_fixes: this.unfinishedTasks.filter(t => t.analysis?.urgent).length,
        quick_wins: this.unfinishedTasks.filter(t => t.analysis?.estimated_effort === 'low').length
      }
    };

    await this.redis.hSet('analyses:all', analysisResult.id, JSON.stringify(analysisResult));
    await this.redis.lPush('analyses:correlation', analysisResult.id);
    await this.redis.lTrim('analyses:correlation', 0, 49);

    console.log('✅ Analysis results stored in MCP tracker');
  }

  async cleanup() {
    if (this.redis) {
      await this.redis.quit();
    }
  }
}

async function correlateAllUnfinishedTasks() {
  const correlator = new ConversationTaskCorrelator();
  
  try {
    await correlator.initialize();
    await correlator.loadAllConversationData();
    await correlator.loadSystemInsights();
    correlator.categorizeAndAnalyzeTasks();
    correlator.prioritizeUnfinishedTasks();
    await correlator.correlateWithCurrentSystemStatus();
    correlator.generateComprehensiveReport();
    await correlator.storeAnalysisResults();
    
  } catch (error) {
    console.error('❌ Error during correlation analysis:', error);
  } finally {
    await correlator.cleanup();
  }
}

correlateAllUnfinishedTasks().catch(console.error);