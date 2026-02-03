# AutoBot MCP Tools and Agent Collaboration Reference Guide

This document serves as the comprehensive reference for all available MCP (Model Context Protocol) tools and agent collaboration capabilities in the AutoBot platform. All agents MUST be aware of these tools and collaboration patterns.

## 🧩 Available MCP Server Tools

### 1. Memory Management (`mcp__memory__*`)
**Purpose**: Persistent knowledge graph for tracking patterns, configurations, and historical insights
**Tools Available:**
- `mcp__memory__create_entities` - Create multiple entities with observations
- `mcp__memory__create_relations` - Create relationships between entities
- `mcp__memory__add_observations` - Add new observations to existing entities
- `mcp__memory__delete_entities` - Remove entities and relations
- `mcp__memory__delete_observations` - Remove specific observations
- `mcp__memory__delete_relations` - Remove specific relationships
- `mcp__memory__read_graph` - Read entire knowledge graph
- `mcp__memory__search_nodes` - Search entities by query
- `mcp__memory__open_nodes` - Retrieve specific entities by name

**Best Practices:**
- Track successful patterns, configurations, and solutions
- Create entities for components, services, and architectural patterns
- Use relations to map dependencies and interactions
- Add observations for performance metrics, errors, and fixes

### 2. Sequential Thinking (`mcp__sequential-thinking__*`)
**Purpose**: Systematic multi-step problem analysis and decision making
**Tools Available:**
- `mcp__sequential-thinking__sequentialthinking` - Dynamic thinking process with revision capabilities

**Best Practices:**
- Use for complex debugging and architectural analysis
- Allows revision and branching of thought processes
- Generates verified solutions through iterative thinking
- Excellent for systematic troubleshooting

### 3. Structured Thinking (`mcp__structured-thinking__*`)
**Purpose**: Chain of Thought framework for 3-4 step systematic analysis
**Tools Available:**
- `mcp__structured-thinking__chain_of_thought` - Structured problem-solving framework

**Best Practices:**
- Use for architectural decisions and design patterns
- 3-4 step methodology for consistent analysis
- Hypothesis generation and verification
- Agent selection and command coordination

### 4. Task Management (`mcp__shrimp-task-manager__*`)
**Purpose**: Advanced AI-powered task planning, analysis, and coordination
**Tools Available:**
- `mcp__shrimp-task-manager__plan_task` - Task planning guidance
- `mcp__shrimp-task-manager__analyze_task` - Deep requirement analysis
- `mcp__shrimp-task-manager__reflect_task` - Critical review and optimization
- `mcp__shrimp-task-manager__split_tasks` - Break complex tasks into subtasks
- `mcp__shrimp-task-manager__list_tasks` - Task status tracking
- `mcp__shrimp-task-manager__execute_task` - Task execution guidance
- `mcp__shrimp-task-manager__verify_task` - Task completion verification
- `mcp__shrimp-task-manager__delete_task` - Remove incomplete tasks
- `mcp__shrimp-task-manager__clear_all_tasks` - Reset task system
- `mcp__shrimp-task-manager__update_task` - Modify task content
- `mcp__shrimp-task-manager__query_task` - Search and filter tasks
- `mcp__shrimp-task-manager__get_task_detail` - Retrieve complete task info
- `mcp__shrimp-task-manager__process_thought` - Advanced thinking workflows
- `mcp__shrimp-task-manager__init_project_rules` - Initialize project standards
- `mcp__shrimp-task-manager__research_mode` - Specialized research workflows

**Best Practices:**
- Use for complex multi-step feature implementations
- Break down large tasks into manageable subtasks
- Track dependencies and execution order
- Coordinate between multiple agents

### 5. File System Operations (`mcp__filesystem__*`)
**Purpose**: Advanced file and directory operations
**Tools Available:**
- `mcp__filesystem__read_text_file` - Read text files with encoding support
- `mcp__filesystem__read_media_file` - Read binary/media files
- `mcp__filesystem__read_multiple_files` - Batch file reading
- `mcp__filesystem__write_file` - Write files with proper encoding
- `mcp__filesystem__edit_file` - Line-based file editing
- `mcp__filesystem__create_directory` - Directory creation
- `mcp__filesystem__list_directory` - Directory listing
- `mcp__filesystem__list_directory_with_sizes` - Directory listing with size info
- `mcp__filesystem__directory_tree` - Recursive tree structure
- `mcp__filesystem__move_file` - Move/rename operations
- `mcp__filesystem__search_files` - Recursive file search
- `mcp__filesystem__get_file_info` - File metadata
- `mcp__filesystem__list_allowed_directories` - Available directory paths

**Best Practices:**
- Use for complex file operations beyond basic Read/Write
- Batch operations for efficiency
- Directory tree analysis for architecture understanding
- File search for pattern matching across codebase

### 6. Context7 Documentation (`mcp__context7__*`)
**Purpose**: Up-to-date library documentation and API references
**Tools Available:**
- `mcp__context7__resolve-library-id` - Find library identifiers
- `mcp__context7__get-library-docs` - Fetch current documentation

**Best Practices:**
- Always resolve library ID before fetching docs
- Use for current framework versions and API changes
- Excellent for modern framework integration
- Check before implementing new dependencies

### 7. Browser Automation (`mcp__puppeteer__*` / `mcp__playwright-*`)
**Purpose**: Automated browser testing and web interaction
**Tools Available:**
**Puppeteer:**
- `mcp__puppeteer__puppeteer_navigate` - Navigate to URLs
- `mcp__puppeteer__puppeteer_screenshot` - Take screenshots
- `mcp__puppeteer__puppeteer_click` - Click elements
- `mcp__puppeteer__puppeteer_fill` - Fill forms
- `mcp__puppeteer__puppeteer_select` - Select options
- `mcp__puppeteer__puppeteer_hover` - Hover elements
- `mcp__puppeteer__puppeteer_evaluate` - Execute JavaScript

**Playwright (Advanced):**
- Complete browser automation suite with advanced features
- Multiple browser engines (Chromium, Firefox, WebKit)
- Advanced testing workflows and code generation
- HTTP request/response testing
- File uploads and form handling

**Playwright (Microsoft):**
- Microsoft-optimized Playwright implementation
- Accessibility-focused automation
- Enterprise-grade browser testing

**Best Practices:**
- Use for E2E testing and UI validation
- Automate complex user workflows
- Cross-browser compatibility testing
- Web scraping and data extraction

### 8. Mobile Testing (`mcp__mobile-simulator__*`)
**Purpose**: Mobile device simulation and testing
**Tools Available:**
- `mcp__mobile-simulator__mobile_use_default_device` - Use default device
- `mcp__mobile-simulator__mobile_list_available_devices` - List devices
- `mcp__mobile-simulator__mobile_use_device` - Select specific device
- `mcp__mobile-simulator__mobile_list_apps` - List installed apps
- `mcp__mobile-simulator__mobile_launch_app` - Launch applications
- `mcp__mobile-simulator__mobile_terminate_app` - Stop applications
- `mcp__mobile-simulator__mobile_get_screen_size` - Screen dimensions
- `mcp__mobile-simulator__mobile_click_on_screen_at_coordinates` - Tap screen
- `mcp__mobile-simulator__mobile_long_press_on_screen_at_coordinates` - Long press
- `mcp__mobile-simulator__mobile_list_elements_on_screen` - UI elements
- `mcp__mobile-simulator__mobile_press_button` - Hardware buttons
- `mcp__mobile-simulator__mobile_open_url` - Open browser URLs
- `mcp__mobile-simulator__swipe_on_screen` - Swipe gestures
- `mcp__mobile-simulator__mobile_type_keys` - Text input
- `mcp__mobile-simulator__mobile_save_screenshot` - Save screenshots
- `mcp__mobile-simulator__mobile_take_screenshot` - Take screenshots
- `mcp__mobile-simulator__mobile_set_orientation` - Device rotation
- `mcp__mobile-simulator__mobile_get_orientation` - Current orientation

**Best Practices:**
- Use for mobile app testing and validation
- Test responsive designs across devices
- Automate mobile user workflows
- Cross-platform mobile compatibility

### 9. IDE Integration (`mcp__ide__*`)
**Purpose**: Development environment integration
**Tools Available:**
- `mcp__ide__getDiagnostics` - Language server diagnostics
- `mcp__ide__executeCode` - Code execution in Jupyter kernel

**Best Practices:**
- Use for code quality analysis
- Real-time error detection
- Interactive code testing and validation

## 🤝 Agent Collaboration Framework

### Agent Specializations and Collaboration Patterns

#### Core Development Team
**Frontend Engineer** ↔ **Backend Engineer** ↔ **Database Engineer**
- Share MCP memory for API contracts and data schemas
- Use task manager for coordinated feature development
- Sequential thinking for complex integrations

#### Quality Assurance Team
**Code Reviewer** → **Security Auditor** → **Testing Engineer**
- Memory sharing for known patterns and vulnerabilities
- Task manager for systematic review workflows
- Structured thinking for quality gates

#### AI and Performance Team  
**AI/ML Engineer** ↔ **Performance Engineer** ↔ **Multimodal Engineer**
- Memory tracking for optimization patterns and benchmarks
- Task coordination for complex AI pipeline development
- Sequential thinking for performance bottleneck analysis

#### Architecture and Infrastructure
**Systems Architect** ↔ **DevOps Engineer** → **Documentation Engineer**
- Memory for architectural decisions and deployment patterns
- Task planning for infrastructure changes
- Structured thinking for system design decisions

#### Planning and Management
**Project Manager** ↔ **Project Task Planner** → **PRD Writer**
- Task manager integration for project coordination
- Memory for successful project patterns
- Structured thinking for planning decisions

### Cross-Agent Communication Patterns

#### 1. Memory-Driven Collaboration
```markdown
Agent A creates entity: "API_Authentication_Pattern"
Agent A adds observation: "JWT implementation successful with Redis session store"
Agent B searches memory: "authentication patterns"
Agent B finds: Previous successful patterns and common pitfalls
Agent B uses knowledge: Implements consistent authentication
```

#### 2. Task-Coordinated Development
```markdown
Systems Architect: Splits complex feature into subtasks
Frontend Engineer: Takes UI subtasks, updates progress
Backend Engineer: Takes API subtasks, notes dependencies
Testing Engineer: Takes testing subtasks, validates completion
```

#### 3. Sequential Problem Solving
```markdown
Issue identified → Code Reviewer analyzes → Security Auditor checks → Performance Engineer optimizes → Documentation Engineer records
Each agent uses sequential thinking for their analysis
Memory updated with findings and solutions
```

## 🛠️ MCP Tool Integration Patterns

### Pattern 1: Investigation and Analysis
1. **mcp__sequential-thinking** - Systematic problem analysis
2. **mcp__filesystem** - Code exploration and pattern identification
3. **mcp__memory** - Historical pattern and solution lookup
4. **Context7** - Current best practice validation

### Pattern 2: Development Workflow
1. **mcp__shrimp-task-manager** - Task planning and coordination
2. **mcp__filesystem** - Code implementation and file operations
3. **mcp__puppeteer/playwright** - Testing and validation
4. **mcp__memory** - Pattern and solution storage

### Pattern 3: Quality Assurance
1. **mcp__structured-thinking** - Systematic quality analysis
2. **mcp__ide** - Code diagnostics and quality metrics
3. **mcp__memory** - Known issue and solution patterns
4. **mcp__shrimp-task-manager** - Quality improvement task tracking

### Pattern 4: Architecture and Design
1. **mcp__sequential-thinking** - Complex architectural analysis
2. **mcp__structured-thinking** - Design decision framework
3. **mcp__memory** - Architectural pattern storage
4. **Context7** - Current framework and tool documentation

## 🎯 Agent-Specific MCP Recommendations

### For All Agents:
- **MUST have access to**: `mcp__memory__*`, `mcp__filesystem__*`, basic thinking tools
- **SHOULD have access to**: `mcp__shrimp-task-manager__*` for complex work
- **MAY have access to**: Specialized tools based on domain (browser automation, mobile testing, etc.)

### High-Priority Updates Needed:
1. **Frontend Engineer**: Missing mobile simulator, playwright advanced tools
2. **Security Auditor**: Missing memory tools, task management, browser automation
3. **Performance Engineer**: Missing mobile testing, IDE integration
4. **Testing Engineer**: Missing mobile simulator, all playwright variants
5. **Documentation Engineer**: Missing context7, structured thinking
6. **DevOps Engineer**: Missing mobile testing, browser automation
7. **Database Engineer**: Missing browser testing tools
8. **Project Manager**: Missing technical MCP tools for better coordination
9. **Multimodal Engineer**: Missing browser automation for UI testing
10. **Systems Architect**: Missing mobile and browser testing capabilities

### Medium-Priority Updates:
- Add collaboration patterns to all agent descriptions
- Include cross-agent communication examples
- Add MCP tool usage best practices
- Include memory sharing patterns

## 📋 Implementation Checklist

### Phase 1: Core Tool Access (High Priority)
- [ ] Update all agents with complete MCP tool lists
- [ ] Add memory management tools to all agents
- [ ] Add task management tools to development agents
- [ ] Add filesystem tools where missing

### Phase 2: Specialized Tool Distribution (Medium Priority)
- [ ] Add browser automation to testing and quality agents
- [ ] Add mobile testing to frontend and testing agents
- [ ] Add IDE integration to development agents
- [ ] Add context7 to all documentation-related agents

### Phase 3: Collaboration Framework (High Priority)
- [ ] Add cross-agent communication patterns
- [ ] Include memory sharing examples
- [ ] Add task coordination patterns
- [ ] Include escalation and handoff procedures

### Phase 4: Documentation and Training (Medium Priority)
- [ ] Update agent descriptions with collaboration patterns
- [ ] Add MCP tool usage examples
- [ ] Include best practices for each tool category
- [ ] Create quick reference for common patterns

## 🔄 Maintenance and Updates

This reference guide should be updated when:
- New MCP servers are added to the platform
- Agent specializations change or expand
- New collaboration patterns are identified
- Tool capabilities are enhanced or deprecated

**Last Updated**: 2025-01-12
**Next Review**: When new MCP servers are deployed or agent roles change significantly