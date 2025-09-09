const { createClient } = require('redis');
const { v4: uuidv4 } = require('uuid');

async function generateInsights() {
  console.log('🧠 Generating knowledge insights from tracked patterns...');
  
  const trackingRedis = createClient({
    socket: { host: '172.16.168.23', port: 6379 },
    database: 10
  });
  await trackingRedis.connect();
  
  const knowledgeRedis = createClient({
    socket: { host: '172.16.168.23', port: 6379 },
    database: 1
  });
  await knowledgeRedis.connect();
  
  // Analyze error patterns
  const allErrors = await trackingRedis.hGetAll('errors:all');
  const errorsByComponent = {};
  
  for (const [errorId, errorData] of Object.entries(allErrors)) {
    const error = JSON.parse(errorData);
    if (!errorsByComponent[error.component]) {
      errorsByComponent[error.component] = [];
    }
    errorsByComponent[error.component].push(error);
  }
  
  // Generate insights for each component with multiple errors
  const insights = [];
  for (const [component, errors] of Object.entries(errorsByComponent)) {
    if (errors.length >= 2) {
      const severities = errors.reduce((acc, e) => {
        acc[e.severity] = (acc[e.severity] || 0) + 1;
        return acc;
      }, {});
      
      const insight = {
        id: `error-pattern-${component}`,
        title: `Recurring ${component.charAt(0).toUpperCase() + component.slice(1)} Errors Detected`,
        content: `Analysis of ${errors.length} errors in ${component} component:

Severity Distribution:
${Object.entries(severities).map(([sev, count]) => `- ${sev}: ${count} errors`).join('\n')}

Sample Error Messages:
${errors.slice(0, 3).map(e => `- ${e.error_message}`).join('\n')}

Recommended Actions:
1. Review error handling in ${component} component
2. Implement better connection retry logic
3. Add circuit breakers for recurring failures
4. Monitor system resources if connection-related`,
        category: 'error_patterns',
        tags: ['error', 'pattern', component, 'recurring'],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        source: 'error_pattern',
        confidence: Math.min(0.95, 0.7 + (errors.length * 0.05)),
        related_tasks: [],
        related_errors: errors.map(e => e.id)
      };
      
      insights.push(insight);
    }
  }
  
  // Analyze task patterns
  const allTasks = await trackingRedis.hGetAll('tasks:all');
  const unfinishedTasks = Object.values(allTasks)
    .map(data => JSON.parse(data))
    .filter(task => task.status !== 'completed');
  
  if (unfinishedTasks.length >= 3) {
    const tasksByType = unfinishedTasks.reduce((acc, task) => {
      let type = 'general';
      if (task.description.toLowerCase().includes('fix') || task.description.toLowerCase().includes('error')) {
        type = 'bug_fix';
      } else if (task.description.toLowerCase().includes('implement') || task.description.toLowerCase().includes('create')) {
        type = 'feature';
      } else if (task.description.toLowerCase().includes('test')) {
        type = 'testing';
      }
      
      if (!acc[type]) acc[type] = [];
      acc[type].push(task);
      return acc;
    }, {});
    
    for (const [taskType, tasks] of Object.entries(tasksByType)) {
      if (tasks.length >= 2) {
        insights.push({
          id: `task-pattern-${taskType}`,
          title: `Multiple ${taskType.replace('_', ' ').toUpperCase()} Tasks Pending`,
          content: `Detected ${tasks.length} unfinished ${taskType} tasks:

${tasks.map(t => `- ${t.description} (${t.status})`).join('\n')}

Recommended Actions:
1. Prioritize completion of related tasks
2. Consider breaking large tasks into smaller parts
3. Allocate dedicated time for ${taskType} work
4. Review blockers preventing task completion`,
          category: 'task_patterns',
          tags: ['task', 'pattern', taskType, 'unfinished'],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          source: 'task_correlation',
          confidence: 0.6 + (tasks.length * 0.05),
          related_tasks: tasks.map(t => t.id),
          related_errors: []
        });
      }
    }
  }
  
  // Store insights in knowledge base
  for (const insight of insights) {
    await knowledgeRedis.hSet('mcp_insights:all', insight.id, JSON.stringify(insight));
    await knowledgeRedis.sAdd(`mcp_insights:category:${insight.category}`, insight.id);
    
    for (const tag of insight.tags) {
      await knowledgeRedis.sAdd(`mcp_insights:tag:${tag}`, insight.id);
    }
    
    // Also store in AutoBot searchable format
    const searchableEntry = {
      id: insight.id,
      title: insight.title,
      content: insight.content,
      metadata: {
        source: 'mcp-autobot-tracker',
        category: insight.category,
        tags: insight.tags,
        confidence: insight.confidence,
        created_at: insight.created_at
      }
    };
    await knowledgeRedis.hSet('knowledge:entries', insight.id, JSON.stringify(searchableEntry));
  }
  
  console.log('✅ Generated', insights.length, 'knowledge insights');
  console.log('\n💡 Insights created:');
  insights.forEach(insight => {
    console.log(`  📊 ${insight.title} (confidence: ${(insight.confidence * 100).toFixed(1)}%)`);
  });
  
  // Show sample insight details
  if (insights.length > 0) {
    console.log('\n📋 Sample Insight Details:');
    console.log('Title:', insights[0].title);
    console.log('Category:', insights[0].category);
    console.log('Tags:', insights[0].tags.join(', '));
    console.log('Content preview:', insights[0].content.substring(0, 200) + '...');
  }
  
  await trackingRedis.quit();
  await knowledgeRedis.quit();
  
  return insights;
}

generateInsights().catch(console.error);