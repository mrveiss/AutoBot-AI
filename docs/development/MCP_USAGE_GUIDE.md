# 🚀 MCP Usage Guide for AutoBot Development

This guide demonstrates how to leverage all available MCP (Model Context Protocol) servers for effective development and debugging in the AutoBot project.

## 📋 Available MCP Servers

### 1. **Filesystem MCP Server** 
**Purpose:** Advanced file operations across the codebase
**Key Tools:**
- `read_file` - Read file contents with syntax highlighting
- `read_multiple_files` - Batch read operations  
- `write_file` - Create/update files
- `list_directory` - Explore project structure
- `search_files` - Find files by pattern
- `get_file_info` - File metadata and stats
- `list_allowed_directories` - View accessible paths

**Example Development Workflow:**
```javascript
// Find all Vue components with specific patterns
mcp.filesystem.search_files({
  path: "/home/kali/Desktop/AutoBot/autobot-vue",
  pattern: "*.vue",
  excludePatterns: ["node_modules/**"]
})

// Read multiple related files simultaneously
mcp.filesystem.read_multiple_files({
  paths: [
    "src/components/ChatInterface.vue",
    "src/utils/ApiClient.js",
    "src/services/ChatService.js"
  ]
})
```

### 2. **AutoBot Custom MCP Server**
**Purpose:** Project-specific development and debugging tools
**Development Tools:**
- `autobot_analyze_project` - Complete project health analysis
- `autobot_run_tests` - Execute test suites with detailed reporting
- `autobot_build_status` - Check build configuration and status
- `autobot_docker_status` - Monitor Docker containers

**Debugging Tools:**
- `autobot_debug_frontend` - Vue.js debugging (console errors, network, components)
- `autobot_debug_backend` - Python backend debugging (logs, API health, memory)
- `autobot_debug_api_calls` - API endpoint analysis with error patterns
- `autobot_debug_websockets` - WebSocket connection debugging
- `autobot_debug_logs_analysis` - Pattern-based log analysis

**Example Debug Session:**
```javascript
// Comprehensive frontend debugging
mcp.autobot.autobot_debug_frontend({
  action: "console-errors",
  timeframe: "10m"
})

// API call pattern analysis
mcp.autobot.autobot_debug_api_calls({
  endpoint: "/api/workflow/execute",
  timeframe: "1h",
  includeErrors: true
})

// Backend performance analysis
mcp.autobot.autobot_debug_backend({
  action: "memory-usage",
  includeProcesses: true
})
```

### 3. **Puppeteer MCP Server**
**Purpose:** Browser automation for frontend testing
**Key Tools:**
- `puppeteer_navigate` - Navigate to URLs
- `puppeteer_screenshot` - Capture visual states
- `puppeteer_click` - Interact with elements
- `puppeteer_fill` - Fill form inputs
- `puppeteer_evaluate` - Execute JavaScript in browser

**Example Frontend Testing:**
```javascript
// Test chat interface workflow
mcp.puppeteer.puppeteer_navigate({
  url: "http://127.0.0.1:5173"
})

mcp.puppeteer.puppeteer_screenshot({
  name: "initial-load",
  fullPage: true
})

mcp.puppeteer.puppeteer_fill({
  selector: "#chat-input",
  value: "Test message from MCP"
})

mcp.puppeteer.puppeteer_click({
  selector: "button[type='submit']"
})

// Verify response rendering
mcp.puppeteer.puppeteer_evaluate({
  script: `
    const messages = document.querySelectorAll('.message');
    return {
      messageCount: messages.length,
      lastMessage: messages[messages.length - 1]?.textContent
    };
  `
})
```

### 4. **SQLite MCP Server**
**Purpose:** Database operations for development tracking
**Key Tools:**
- `query` - Execute SQL queries
- `create_record` - Insert development logs
- `read_records` - Query project data
- `update_records` - Update task status

**Example Development Tracking:**
```javascript
// Log development milestone
mcp.sqlite.create_record({
  table: "development_log",
  data: {
    project_id: 1,
    log_entry: "Implemented MCP debugging infrastructure",
    log_level: "SUCCESS",
    details: JSON.stringify({
      servers_configured: 6,
      tools_available: 45
    })
  }
})

// Query recent debugging sessions
mcp.sqlite.query({
  sql: `
    SELECT * FROM development_log 
    WHERE log_level IN ('ERROR', 'DEBUG') 
    AND timestamp > datetime('now', '-1 day')
    ORDER BY timestamp DESC
  `
})
```

### 5. **GitHub MCP Server** (Requires GITHUB_PAT)
**Purpose:** Repository management and collaboration
**Key Tools:**
- Repository operations (browse, search code)
- Issue/PR management
- Workflow monitoring
- Code review automation

**Example GitHub Integration:**
```javascript
// Search for similar issues
mcp.github.search_issues({
  query: "ResearchAgent constructor error",
  state: "all"
})

// Create issue for tracking
mcp.github.create_issue({
  title: "MCP Integration Complete",
  body: "All 6 MCP servers configured and operational",
  labels: ["enhancement", "infrastructure"]
})
```

### 6. **Sequential Thinking MCP Server**
**Purpose:** Complex problem-solving workflows
**Key Tool:**
- `sequential_thinking` - Multi-step analytical reasoning

**Example Problem Solving:**
```javascript
mcp.sequential.sequential_thinking({
  query: "Analyze the AutoBot frontend architecture and suggest performance optimizations considering the current MVC implementation, API client patterns, and Vue 3 composition API usage"
})
```

## 🔧 Integrated Development Workflows

### **1. Debugging a Frontend Issue**
```javascript
// Step 1: Analyze frontend errors
const frontendErrors = await mcp.autobot.autobot_debug_frontend({
  action: "console-errors"
});

// Step 2: Check related API calls
const apiCalls = await mcp.autobot.autobot_debug_api_calls({
  endpoint: frontendErrors.problematicEndpoint
});

// Step 3: Visual debugging with Puppeteer
await mcp.puppeteer.puppeteer_navigate({ url: "http://127.0.0.1:5173" });
await mcp.puppeteer.puppeteer_screenshot({ name: "error-state" });

// Step 4: Log findings to database
await mcp.sqlite.create_record({
  table: "debug_sessions",
  data: {
    issue: "Frontend rendering error",
    findings: JSON.stringify({ frontendErrors, apiCalls }),
    resolution: "Pending"
  }
});
```

### **2. Backend Performance Investigation**
```javascript
// Step 1: Analyze backend health
const health = await mcp.autobot.autobot_debug_backend({
  action: "api-health"
});

// Step 2: Check memory usage
const memory = await mcp.autobot.autobot_debug_backend({
  action: "memory-usage"
});

// Step 3: Analyze logs for patterns
const logs = await mcp.autobot.autobot_debug_logs_analysis({
  logLevel: "ERROR",
  pattern: "timeout|memory|exception"
});

// Step 4: Use sequential thinking for root cause
const analysis = await mcp.sequential.sequential_thinking({
  query: `Given these symptoms: ${JSON.stringify({ health, memory, logs })}, 
          identify the root cause and suggest optimizations`
});
```

### **3. Full-Stack Feature Development**
```javascript
// Step 1: Analyze project structure
const project = await mcp.autobot.autobot_analyze_project();

// Step 2: Read related files
const files = await mcp.filesystem.read_multiple_files({
  paths: [
    "src/components/NewFeature.vue",
    "backend/api/new_feature.py",
    "src/agents/feature_agent.py"
  ]
});

// Step 3: Run tests
const tests = await mcp.autobot.autobot_run_tests({
  pattern: "**/test_new_feature*.py"
});

// Step 4: Visual testing
await mcp.puppeteer.puppeteer_navigate({ url: "http://127.0.0.1:5173/new-feature" });
const screenshot = await mcp.puppeteer.puppeteer_screenshot({ fullPage: true });

// Step 5: Document in database
await mcp.sqlite.create_record({
  table: "features",
  data: {
    name: "New Feature",
    status: "implemented",
    test_results: JSON.stringify(tests)
  }
});
```

## 📊 Best Practices

### **1. Batch Operations**
Use MCP servers for batch operations to improve efficiency:
```javascript
// Read multiple files in one call
const files = await mcp.filesystem.read_multiple_files({
  paths: relatedFiles
});

// Execute multiple debug checks
const [frontend, backend, websockets] = await Promise.all([
  mcp.autobot.autobot_debug_frontend({ action: "network-analysis" }),
  mcp.autobot.autobot_debug_backend({ action: "logs" }),
  mcp.autobot.autobot_debug_websockets({ action: "connections" })
]);
```

### **2. Progressive Debugging**
Start broad and narrow down:
```javascript
// 1. Project-wide analysis
const overview = await mcp.autobot.autobot_analyze_project();

// 2. Component-specific debugging
if (overview.frontend.errors > 0) {
  const frontendDebug = await mcp.autobot.autobot_debug_frontend({
    action: "component-tree"
  });
}

// 3. Targeted file investigation
const problematicFile = await mcp.filesystem.read_file({
  path: frontendDebug.errorSource
});
```

### **3. Documentation and Tracking**
Always document findings:
```javascript
// Track debugging session
await mcp.sqlite.create_record({
  table: "debug_sessions",
  data: {
    timestamp: new Date().toISOString(),
    issue_description: "WebSocket connection drops",
    mcp_tools_used: ["autobot_debug_websockets", "autobot_debug_backend"],
    findings: debugResults,
    resolution: "Increased timeout values"
  }
});
```

## 🎯 Quick Reference

### **For Frontend Issues:**
1. `autobot_debug_frontend` - Console errors, network, components
2. `puppeteer_*` tools - Visual testing and interaction
3. `filesystem` tools - Read Vue components and services

### **For Backend Issues:**
1. `autobot_debug_backend` - Logs, health, memory
2. `autobot_debug_api_calls` - API endpoint analysis
3. `filesystem` tools - Read Python modules

### **For Integration Issues:**
1. `autobot_debug_websockets` - Real-time connection debugging
2. `autobot_debug_logs_analysis` - Cross-component log patterns
3. `sequential_thinking` - Complex problem analysis

### **For Development Tracking:**
1. `sqlite` tools - Log progress, track issues
2. `autobot_analyze_project` - Project health monitoring
3. `github` tools - Repository management (when configured)

## 🚀 Advanced Techniques

### **1. Automated Error Detection**
```javascript
// Set up periodic health checks
setInterval(async () => {
  const health = await mcp.autobot.autobot_debug_backend({ action: "api-health" });
  if (!health.healthy) {
    await mcp.sqlite.create_record({
      table: "alerts",
      data: {
        type: "health_check_failed",
        details: JSON.stringify(health)
      }
    });
  }
}, 60000); // Every minute
```

### **2. Performance Profiling**
```javascript
// Profile API endpoints
const endpoints = ["/api/chat", "/api/workflow", "/api/knowledge"];
const profiles = await Promise.all(
  endpoints.map(endpoint => 
    mcp.autobot.autobot_debug_api_calls({
      endpoint,
      timeframe: "1h",
      includePerformance: true
    })
  )
);
```

### **3. Automated Testing Pipeline**
```javascript
// Full test suite with visual validation
const pipeline = async () => {
  // 1. Run backend tests
  const backendTests = await mcp.autobot.autobot_run_tests({ pattern: "backend/**" });
  
  // 2. Run frontend tests
  const frontendTests = await mcp.autobot.autobot_run_tests({ pattern: "frontend/**" });
  
  // 3. Visual regression testing
  await mcp.puppeteer.puppeteer_navigate({ url: "http://127.0.0.1:5173" });
  const screenshots = await captureAllViews();
  
  // 4. Log results
  await mcp.sqlite.create_record({
    table: "test_runs",
    data: {
      timestamp: new Date().toISOString(),
      backend_results: JSON.stringify(backendTests),
      frontend_results: JSON.stringify(frontendTests),
      visual_tests: JSON.stringify(screenshots)
    }
  });
};
```

---

**Remember:** The MCP servers are designed to work together. Combine their capabilities for comprehensive development and debugging workflows that leverage the full power of the AutoBot infrastructure.