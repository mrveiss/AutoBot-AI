#!/usr/bin/env node
/**
 * AutoBot MCP Debug Workflow Example
 * Demonstrates integrated usage of all MCP servers for debugging
 */

const { spawn } = require('child_process');

// Helper function to call MCP server
async function callMCP(server, method, params) {
  return new Promise((resolve, reject) => {
    const request = {
      jsonrpc: "2.0",
      id: Date.now(),
      method: method,
      params: params
    };
    
    const child = spawn(server.command, server.args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, ...server.env }
    });
    
    let response = '';
    
    child.stdout.on('data', (data) => {
      response += data.toString();
    });
    
    child.on('close', () => {
      try {
        const lines = response.split('\n').filter(line => line.trim());
        const jsonResponse = JSON.parse(lines[0]);
        resolve(jsonResponse.result);
      } catch (error) {
        reject(error);
      }
    });
    
    child.stdin.write(JSON.stringify(request));
    child.stdin.end();
  });
}

// MCP Server configurations
const servers = {
  autobot: {
    command: 'node',
    args: ['autobot-mcp-server.js']
  },
  filesystem: {
    command: 'mcp-server-filesystem',
    args: ['/home/kali/Desktop/AutoBot']
  },
  sqlite: {
    command: 'npx',
    args: ['-y', 'mcp-sqlite', 'data/autobot.db']
  },
  puppeteer: {
    command: 'mcp-server-puppeteer'
  }
};

// Example: Debug Frontend Rendering Issue
async function debugFrontendIssue() {
  console.log('🔍 Starting Frontend Debug Workflow...\n');
  
  try {
    // Step 1: Analyze frontend errors
    console.log('1️⃣ Checking frontend console errors...');
    const frontendErrors = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_frontend',
      arguments: {
        action: 'console-errors',
        timeframe: '10m'
      }
    });
    console.log('Frontend errors found:', JSON.parse(frontendErrors.content[0].text).errorCount);
    
    // Step 2: Check API health
    console.log('\n2️⃣ Checking backend API health...');
    const apiHealth = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_backend',
      arguments: {
        action: 'api-health'
      }
    });
    console.log('API Health:', JSON.parse(apiHealth.content[0].text).healthy ? '✅ Healthy' : '❌ Unhealthy');
    
    // Step 3: Analyze WebSocket connections
    console.log('\n3️⃣ Checking WebSocket connections...');
    const wsStatus = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_websockets',
      arguments: {
        action: 'connections'
      }
    });
    console.log('Active WebSocket connections:', JSON.parse(wsStatus.content[0].text).activeConnections);
    
    // Step 4: Log findings to database
    console.log('\n4️⃣ Logging debug session to database...');
    const dbResult = await callMCP(servers.sqlite, 'tools/call', {
      name: 'create_record',
      arguments: {
        table: 'development_log',
        data: {
          project_id: 1,
          log_entry: 'Frontend debug session completed',
          log_level: 'DEBUG',
          details: JSON.stringify({
            errors_found: frontendErrors.content[0].text,
            api_status: apiHealth.content[0].text,
            ws_status: wsStatus.content[0].text
          })
        }
      }
    });
    console.log('Debug session logged successfully!');
    
    // Step 5: Generate recommendations
    console.log('\n5️⃣ Generating recommendations...');
    const errors = JSON.parse(frontendErrors.content[0].text);
    if (errors.errorCount > 0) {
      console.log('\n📋 Recommendations:');
      console.log('- Fix console errors in:', errors.topFiles?.join(', ') || 'Unknown files');
      console.log('- Check API endpoints:', errors.failedEndpoints?.join(', ') || 'None detected');
      console.log('- Review WebSocket stability');
    } else {
      console.log('\n✅ No frontend errors detected!');
    }
    
  } catch (error) {
    console.error('❌ Debug workflow failed:', error.message);
  }
}

// Example: Performance Analysis Workflow
async function analyzePerformance() {
  console.log('\n📊 Starting Performance Analysis...\n');
  
  try {
    // Step 1: Check project structure
    console.log('1️⃣ Analyzing project structure...');
    const projectAnalysis = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_analyze_project',
      arguments: { includeStats: true }
    });
    const project = JSON.parse(projectAnalysis.content[0].text);
    console.log(`Frontend dependencies: ${project.structure.frontend.dependencies}`);
    console.log(`Backend files: ${project.structure.backend.totalFiles}`);
    
    // Step 2: Analyze API performance
    console.log('\n2️⃣ Analyzing API call patterns...');
    const apiAnalysis = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_api_calls',
      arguments: {
        timeframe: '1h',
        includePerformance: true
      }
    });
    console.log('API calls analyzed successfully');
    
    // Step 3: Check memory usage
    console.log('\n3️⃣ Checking backend memory usage...');
    const memoryUsage = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_backend',
      arguments: {
        action: 'memory-usage'
      }
    });
    console.log('Memory analysis completed');
    
    // Step 4: Query historical performance data
    console.log('\n4️⃣ Querying performance history...');
    const perfHistory = await callMCP(servers.sqlite, 'tools/call', {
      name: 'query',
      arguments: {
        sql: `SELECT COUNT(*) as error_count, 
              DATE(timestamp) as date 
              FROM development_log 
              WHERE log_level = 'ERROR' 
              AND timestamp > datetime('now', '-7 days')
              GROUP BY DATE(timestamp)`
      }
    });
    console.log('Historical data retrieved');
    
  } catch (error) {
    console.error('❌ Performance analysis failed:', error.message);
  }
}

// Example: Visual Testing Workflow
async function visualTesting() {
  console.log('\n🎨 Starting Visual Testing Workflow...\n');
  
  try {
    // Step 1: Navigate to application
    console.log('1️⃣ Opening application...');
    await callMCP(servers.puppeteer, 'tools/call', {
      name: 'puppeteer_navigate',
      arguments: {
        url: 'http://127.0.0.1:5173'
      }
    });
    
    // Step 2: Take initial screenshot
    console.log('2️⃣ Capturing initial state...');
    await callMCP(servers.puppeteer, 'tools/call', {
      name: 'puppeteer_screenshot',
      arguments: {
        name: 'initial-state',
        fullPage: true
      }
    });
    
    // Step 3: Interact with UI
    console.log('3️⃣ Testing user interactions...');
    await callMCP(servers.puppeteer, 'tools/call', {
      name: 'puppeteer_fill',
      arguments: {
        selector: '#chat-input',
        value: 'Test message from MCP visual testing'
      }
    });
    
    await callMCP(servers.puppeteer, 'tools/call', {
      name: 'puppeteer_click',
      arguments: {
        selector: 'button[type="submit"]'
      }
    });
    
    // Step 4: Capture result
    console.log('4️⃣ Capturing result state...');
    await callMCP(servers.puppeteer, 'tools/call', {
      name: 'puppeteer_screenshot',
      arguments: {
        name: 'after-interaction',
        fullPage: true
      }
    });
    
    console.log('\n✅ Visual testing completed!');
    
  } catch (error) {
    console.error('❌ Visual testing failed:', error.message);
  }
}

// Main execution
async function main() {
  console.log('🚀 AutoBot MCP Debug Workflow Examples\n');
  console.log('Select a workflow:');
  console.log('1. Debug Frontend Issue');
  console.log('2. Analyze Performance');
  console.log('3. Visual Testing');
  console.log('4. Run All Workflows\n');
  
  const workflow = process.argv[2] || '1';
  
  switch(workflow) {
    case '1':
      await debugFrontendIssue();
      break;
    case '2':
      await analyzePerformance();
      break;
    case '3':
      await visualTesting();
      break;
    case '4':
      await debugFrontendIssue();
      await analyzePerformance();
      await visualTesting();
      break;
    default:
      console.log('Invalid selection. Please choose 1-4.');
  }
  
  console.log('\n🎉 Workflow completed!');
}

// Run the examples
if (require.main === module) {
  main().catch(console.error);
}

module.exports = { debugFrontendIssue, analyzePerformance, visualTesting };