#!/usr/bin/env node
/**
 * AutoBot MCP Health Monitor
 * Continuously monitors system health using MCP tools
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

// Configuration
const MONITOR_INTERVAL = 60000; // Check every minute
const ALERT_THRESHOLD = {
  frontendErrors: 10,
  apiResponseTime: 1000, // ms
  memoryUsage: 80, // percent
  websocketErrors: 5
};

// ANSI color codes
const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m'
};

// MCP Server configurations
const servers = {
  autobot: {
    command: 'node',
    args: [path.join(__dirname, '..', '.mcp', 'autobot-mcp-server.js')]
  },
  sqlite: {
    command: 'npx',
    args: ['-y', 'mcp-sqlite', path.join(__dirname, '..', 'data', 'autobot.db')]
  }
};

// Helper to call MCP server
async function callMCP(server, method, params) {
  return new Promise((resolve, reject) => {
    const request = {
      jsonrpc: "2.0",
      id: Date.now(),
      method: method,
      params: params
    };

    const child = spawn(server.command, server.args, {
      stdio: ['pipe', 'pipe', 'pipe']
    });

    let response = '';
    let error = '';

    child.stdout.on('data', (data) => {
      response += data.toString();
    });

    child.stderr.on('data', (data) => {
      error += data.toString();
    });

    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`MCP server exited with code ${code}: ${error}`));
        return;
      }

      try {
        // Parse response (filter out server messages)
        const lines = response.split('\n').filter(line => line.trim().startsWith('{'));
        if (lines.length > 0) {
          const jsonResponse = JSON.parse(lines[0]);
          resolve(jsonResponse.result);
        } else {
          reject(new Error('No valid JSON response'));
        }
      } catch (err) {
        reject(err);
      }
    });

    child.stdin.write(JSON.stringify(request));
    child.stdin.end();
  });
}

// Monitor functions
async function checkFrontendHealth() {
  try {
    const result = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_frontend',
      arguments: {
        action: 'console-errors',
        timeframe: '5m'
      }
    });

    const data = JSON.parse(result.content[0].text);
    return {
      healthy: data.errorCount < ALERT_THRESHOLD.frontendErrors,
      errorCount: data.errorCount,
      topErrors: data.errors?.slice(0, 3) || []
    };
  } catch (error) {
    return { healthy: false, error: error.message };
  }
}

async function checkBackendHealth() {
  try {
    const result = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_backend',
      arguments: {
        action: 'api-health'
      }
    });

    const data = JSON.parse(result.content[0].text);
    return {
      healthy: data.healthy === true,
      status: data.status || 'unknown',
      issues: data.issues || []
    };
  } catch (error) {
    return { healthy: false, error: error.message };
  }
}

async function checkAPIPerformance() {
  try {
    const result = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_api_calls',
      arguments: {
        timeframe: '5m',
        includePerformance: true
      }
    });

    const data = JSON.parse(result.content[0].text);
    return {
      healthy: (data.avgResponseTime || 0) < ALERT_THRESHOLD.apiResponseTime,
      avgResponseTime: data.avgResponseTime || 0,
      totalCalls: data.totalCalls || 0,
      errorRate: data.errorRate || 0
    };
  } catch (error) {
    return { healthy: false, error: error.message };
  }
}

async function checkWebSocketHealth() {
  try {
    const result = await callMCP(servers.autobot, 'tools/call', {
      name: 'autobot_debug_websockets',
      arguments: {
        action: 'errors',
        timeframe: '5m'
      }
    });

    const data = JSON.parse(result.content[0].text);
    return {
      healthy: (data.errorCount || 0) < ALERT_THRESHOLD.websocketErrors,
      errorCount: data.errorCount || 0,
      activeConnections: data.activeConnections || 0
    };
  } catch (error) {
    return { healthy: false, error: error.message };
  }
}

async function logHealthCheck(results) {
  try {
    await callMCP(servers.sqlite, 'tools/call', {
      name: 'create_record',
      arguments: {
        table: 'development_log',
        data: {
          project_id: 1,
          log_entry: 'Automated health check',
          log_level: results.allHealthy ? 'INFO' : 'WARNING',
          details: JSON.stringify({
            timestamp: new Date().toISOString(),
            results: results
          })
        }
      }
    });
  } catch (error) {
    console.error('Failed to log health check:', error.message);
  }
}

// Main monitoring loop
async function runHealthCheck() {
  console.log(`\n${colors.blue}🏥 Running Health Check - ${new Date().toLocaleTimeString()}${colors.reset}`);
  console.log('=' .repeat(50));

  const results = {
    frontend: await checkFrontendHealth(),
    backend: await checkBackendHealth(),
    api: await checkAPIPerformance(),
    websocket: await checkWebSocketHealth()
  };

  results.allHealthy = results.frontend.healthy &&
                       results.backend.healthy &&
                       results.api.healthy &&
                       results.websocket.healthy;

  // Display results
  console.log(`\n${colors.blue}Frontend:${colors.reset}`);
  if (results.frontend.healthy) {
    console.log(`  ${colors.green}✓ Healthy${colors.reset} - ${results.frontend.errorCount} errors`);
  } else {
    console.log(`  ${colors.red}✗ Issues Detected${colors.reset} - ${results.frontend.errorCount} errors`);
    results.frontend.topErrors?.forEach(err => {
      console.log(`    - ${err.message || err}`);
    });
  }

  console.log(`\n${colors.blue}Backend:${colors.reset}`);
  if (results.backend.healthy) {
    console.log(`  ${colors.green}✓ Healthy${colors.reset}`);
  } else {
    console.log(`  ${colors.red}✗ Issues Detected${colors.reset}`);
    results.backend.issues?.forEach(issue => {
      console.log(`    - ${issue}`);
    });
  }

  console.log(`\n${colors.blue}API Performance:${colors.reset}`);
  if (results.api.healthy) {
    console.log(`  ${colors.green}✓ Healthy${colors.reset} - Avg: ${results.api.avgResponseTime}ms`);
  } else {
    console.log(`  ${colors.red}✗ Slow Response${colors.reset} - Avg: ${results.api.avgResponseTime}ms`);
  }
  console.log(`  Total Calls: ${results.api.totalCalls}, Error Rate: ${results.api.errorRate}%`);

  console.log(`\n${colors.blue}WebSocket:${colors.reset}`);
  if (results.websocket.healthy) {
    console.log(`  ${colors.green}✓ Healthy${colors.reset} - ${results.websocket.activeConnections} active connections`);
  } else {
    console.log(`  ${colors.red}✗ Errors Detected${colors.reset} - ${results.websocket.errorCount} errors`);
  }

  // Overall status
  console.log(`\n${colors.blue}Overall Status:${colors.reset}`);
  if (results.allHealthy) {
    console.log(`  ${colors.green}✅ All Systems Operational${colors.reset}`);
  } else {
    console.log(`  ${colors.yellow}⚠️  Issues Detected - Check logs for details${colors.reset}`);
  }

  // Log to database
  await logHealthCheck(results);

  // Write to file for external monitoring
  const statusFile = path.join(__dirname, '..', 'data', 'health_status.json');
  fs.writeFileSync(statusFile, JSON.stringify({
    timestamp: new Date().toISOString(),
    healthy: results.allHealthy,
    details: results
  }, null, 2));

  return results;
}

// Alert function
function sendAlert(message) {
  console.log(`\n${colors.red}🚨 ALERT: ${message}${colors.reset}`);
  // In production, this could send email, Slack notification, etc.
}

// Main monitoring function
async function startMonitoring() {
  console.log(`${colors.blue}🚀 AutoBot MCP Health Monitor Started${colors.reset}`);
  console.log(`Checking every ${MONITOR_INTERVAL / 1000} seconds...`);
  console.log(`Press Ctrl+C to stop\n`);

  // Initial check
  await runHealthCheck();

  // Set up interval
  const interval = setInterval(async () => {
    const results = await runHealthCheck();

    // Check for critical issues
    if (!results.allHealthy) {
      if (!results.backend.healthy) {
        sendAlert('Backend API is down!');
      }
      if (results.frontend.errorCount > ALERT_THRESHOLD.frontendErrors * 2) {
        sendAlert(`Critical frontend errors: ${results.frontend.errorCount}`);
      }
      if (results.api.avgResponseTime > ALERT_THRESHOLD.apiResponseTime * 2) {
        sendAlert(`Severe API performance degradation: ${results.api.avgResponseTime}ms`);
      }
    }
  }, MONITOR_INTERVAL);

  // Graceful shutdown
  process.on('SIGINT', () => {
    console.log(`\n${colors.yellow}Stopping health monitor...${colors.reset}`);
    clearInterval(interval);
    process.exit(0);
  });
}

// Command line interface
if (require.main === module) {
  const command = process.argv[2];

  switch (command) {
    case 'once':
      // Run single health check
      runHealthCheck().then(() => {
        console.log(`\n${colors.green}Health check complete${colors.reset}`);
        process.exit(0);
      }).catch(error => {
        console.error(`${colors.red}Health check failed:${colors.reset}`, error);
        process.exit(1);
      });
      break;

    case 'monitor':
    default:
      // Start continuous monitoring
      startMonitoring().catch(error => {
        console.error(`${colors.red}Monitor failed to start:${colors.reset}`, error);
        process.exit(1);
      });
      break;
  }
}

module.exports = { runHealthCheck, checkFrontendHealth, checkBackendHealth };
