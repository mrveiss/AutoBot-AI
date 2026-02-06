#!/usr/bin/env npx tsx
import { AutoBotTracker } from './src/index.js';

async function testIngestion() {
    console.log('🧪 Testing MCP AutoBot Tracker ingestion...');

    const tracker = new AutoBotTracker();
    await tracker.initialize();

    // Test conversation data from the test file
    const testConversation = [
        {
            role: 'user',
            content: 'I need help setting up the Redis connection for AutoBot. The backend keeps timing out.',
            timestamp: '2025-09-09T16:52:00Z'
        },
        {
            role: 'assistant',
            content: 'I will help you configure Redis for the distributed VM architecture. TODO: Check Redis configuration on 172.16.168.23. FIXME: Update connection timeout from 30s to 5s. ERROR: Connection refused on port 6379. The issue appears to be network connectivity.',
            timestamp: '2025-09-09T16:52:30Z'
        }
    ];

    // Test ingestion
    const result = await tracker.ingestChat(testConversation);
    console.log('✅ Ingestion result:', result);

    // Test task retrieval
    const tasks = await tracker.getUnfinishedTasks();
    console.log('📋 Unfinished tasks found:', tasks.tasks?.length || 0);

    // Test error correlation
    const errors = await tracker.getErrorCorrelations();
    console.log('⚠️ Errors tracked:', errors.errors?.length || 0);

    // Test insights
    const insights = await tracker.getInsights();
    console.log('💡 Insights generated:', insights.insights?.length || 0);

    console.log('🎉 MCP tracker validation complete!');
    process.exit(0);
}

testIngestion().catch((error) => {
    console.error('❌ Test failed:', error);
    process.exit(1);
});
