# Advanced Visualizations

**Author**: mrveiss
**Copyright**: (c) 2025 mrveiss
**Issue**: #62 - Enhanced Visualizations

---

## Overview

AutoBot provides a comprehensive suite of advanced visualization components for monitoring, analysis, and system understanding. These components are built with Vue 3 Composition API and TypeScript, offering interactive, real-time visual representations of system state, workflows, and agent activity.

## Available Visualization Components

### 1. Resource Heatmap

**Component**: `ResourceHeatmap.vue`
**Location**: `autobot-vue/src/components/visualizations/ResourceHeatmap.vue`

Displays resource usage patterns over time using ApexCharts heatmap visualization.

#### Features
- **Metrics**: CPU, Memory, Disk, Network I/O
- **Time Ranges**: 1 hour, 6 hours, 24 hours, 7 days
- **Color Coding**: Green (low) to yellow to red (high) intensity
- **Machine Filtering**: View specific VMs in distributed infrastructure
- **Auto-refresh**: Configurable refresh intervals

#### Props
```typescript
interface Props {
  title?: string           // Default: 'Resource Heatmap'
  height?: number          // Default: 300
  refreshInterval?: number // Default: 30000 (30s)
  machine?: string         // Filter by machine IP
}
```

#### Usage
```vue
<template>
  <ResourceHeatmap
    title="CPU Usage Patterns"
    :height="400"
    :refresh-interval="60000"
  />
</template>

<script setup>
import { ResourceHeatmap } from '@/components/visualizations'
</script>
```

---

### 2. Workflow Visualization

**Component**: `WorkflowVisualization.vue`
**Location**: `autobot-vue/src/components/visualizations/WorkflowVisualization.vue`

Interactive workflow execution flowchart with custom SVG rendering.

#### Features
- **Node Types**: Start, End, Action, Task, Decision, Parallel
- **Status Visualization**: Pending, Running, Completed, Failed, Skipped
- **Animated Connections**: Directional flow with particle animation
- **Pan & Zoom**: Full viewport control
- **Node Selection**: Click for detailed information
- **Live Updates**: Real-time status during workflow execution

#### Props
```typescript
interface Props {
  workflowId?: string       // Specific workflow to display
  height?: number           // Default: 500
  refreshInterval?: number  // Default: 5000 (5s)
  showControls?: boolean    // Default: true
}
```

#### Node Types
| Type | Icon | Description |
|------|------|-------------|
| `start` | Circle | Workflow entry point |
| `end` | Double circle | Workflow completion |
| `action` | Rounded rectangle | Standard action node |
| `task` | Rectangle | Task execution |
| `decision` | Diamond | Conditional branching |
| `parallel` | Parallel bars | Concurrent execution |

#### Usage
```vue
<template>
  <WorkflowVisualization
    workflow-id="wf-123"
    :height="600"
  />
</template>

<script setup>
import { WorkflowVisualization } from '@/components/visualizations'
</script>
```

---

### 3. Agent Activity Visualization

**Component**: `AgentActivityVisualization.vue`
**Location**: `autobot-vue/src/components/visualizations/AgentActivityVisualization.vue`

Real-time agent activity monitoring dashboard.

#### Features
- **View Modes**: Grid view, Timeline view
- **Agent Types**: Orchestrator, Worker, Monitor, Analyzer, Executor
- **Status Indicators**: Working, Idle, Error, Paused
- **Live Activity Feed**: Timestamped activity log
- **Metrics Display**: Uptime, success rate, tasks completed
- **Animated Status**: Pulse animations for active agents

#### Props
```typescript
interface Props {
  height?: number           // Default: 400
  refreshInterval?: number  // Default: 5000 (5s)
  showFeed?: boolean        // Default: true
  maxFeedItems?: number     // Default: 50
}
```

#### Agent Status Colors
| Status | Color | Description |
|--------|-------|-------------|
| `working` | Green | Currently executing task |
| `idle` | Gray | Waiting for work |
| `error` | Red | Error state |
| `paused` | Yellow | Manually paused |

#### Usage
```vue
<template>
  <AgentActivityVisualization
    :height="500"
    :show-feed="true"
  />
</template>

<script setup>
import { AgentActivityVisualization } from '@/components/visualizations'
</script>
```

---

### 4. System Architecture Diagram

**Component**: `SystemArchitectureDiagram.vue`
**Location**: `autobot-vue/src/components/visualizations/SystemArchitectureDiagram.vue`

Interactive system architecture visualization showing the distributed AutoBot infrastructure.

#### Features
- **View Modes**: Physical, Logical, Data Flow
- **Detail Levels**: High (all components), Medium (services), Low (overview)
- **Live Status**: Real-time health indicators from monitoring API
- **Pan & Zoom**: Full viewport navigation
- **Mini Map**: Overview navigation
- **Export**: Download as SVG
- **Component Selection**: Click for detailed info panel

#### Props
```typescript
interface Props {
  title?: string           // Default: 'System Architecture'
  height?: number          // Default: 600
  autoRefresh?: boolean    // Default: true
  refreshInterval?: number // Default: 30000 (30s)
}
```

#### Component Categories
| Category | Color | Examples |
|----------|-------|----------|
| Frontend | Purple gradient | Vue.js Frontend, VNC Desktop |
| Backend | Green gradient | FastAPI, WebSocket Server |
| Database | Orange gradient | Redis Stack, SQLite, ChromaDB |
| AI/ML | Violet gradient | LLM Providers, NPU Worker |
| Infrastructure | Indigo gradient | Prometheus, Grafana, Loki |

#### Connection Types
| Type | Style | Description |
|------|-------|-------------|
| `api` | Solid blue | REST API calls |
| `data` | Solid green | Data flow |
| `event` | Dashed orange | Event/WebSocket |

#### Usage
```vue
<template>
  <SystemArchitectureDiagram
    title="AutoBot Infrastructure"
    :height="700"
  />
</template>

<script setup>
import { SystemArchitectureDiagram } from '@/components/visualizations'
</script>
```

---

### 5. Knowledge Graph (Existing)

**Component**: `KnowledgeGraph.vue`
**Location**: `autobot-vue/src/components/knowledge/KnowledgeGraph.vue`

Interactive knowledge graph for entity relationships.

#### Features
- **Layout Modes**: Force-directed, Grid
- **Search & Filter**: By name, type, or observations
- **Depth Control**: 1-3 levels of relationships
- **Pan & Zoom**: Full viewport control
- **Entity Creation**: Add new entities via modal
- **Details Panel**: View entity observations and relations
- **Legend**: Entity type color coding

#### Entity Types
- Conversation, Bug Fix, Feature, Decision
- Task, User Preference, Context
- Learning, Research, Implementation

---

## Custom Dashboard Builder

**View**: `CustomDashboard.vue`
**Location**: `autobot-vue/src/views/CustomDashboard.vue`

Build personalized dashboards with drag-and-drop widgets.

### Features
- **Drag & Drop**: Add widgets from palette
- **Grid Layout**: 3-column responsive grid
- **Widget Configuration**: Per-widget settings
- **Multiple Dashboards**: Create and switch between dashboards
- **Templates**: Pre-configured layouts for common use cases
- **Persistence**: Saved to localStorage
- **Export-Ready**: Dashboard configurations portable

### Available Widget Types
1. Resource Heatmap
2. Workflow Visualization
3. Agent Activity
4. System Architecture
5. System Monitor

### Dashboard Templates
- **Blank**: Start from scratch
- **Monitoring**: System metrics focused
- **Agents**: Agent activity focused
- **Workflows**: Workflow visualization focused

### Usage
Navigate to `/custom-dashboard` or add route:
```typescript
{
  path: '/custom-dashboard',
  name: 'CustomDashboard',
  component: () => import('@/views/CustomDashboard.vue')
}
```

---

## Integration Guide

### Importing Components

```typescript
// Import all visualization components
import {
  ResourceHeatmap,
  WorkflowVisualization,
  AgentActivityVisualization,
  SystemArchitectureDiagram
} from '@/components/visualizations'

// Import individual component
import ResourceHeatmap from '@/components/visualizations/ResourceHeatmap.vue'
```

### Common Patterns

#### Real-time Updates with WebSocket
```typescript
const props = defineProps<{
  refreshInterval?: number
}>()

const { data, isConnected } = useWebSocket('/api/ws/metrics')

watch(data, (newData) => {
  updateVisualization(newData)
})
```

#### Responsive Height
```vue
<template>
  <div class="visualization-wrapper" ref="wrapper">
    <ResourceHeatmap :height="computedHeight" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useElementSize } from '@vueuse/core'

const wrapper = ref(null)
const { height } = useElementSize(wrapper)
const computedHeight = computed(() => Math.max(300, height.value - 50))
</script>
```

---

## Theming

All visualization components use a consistent dark theme with the following color palette:

### Background Colors
- Primary: `#0f172a`
- Secondary: `#1e293b`
- Tertiary: `#334155`

### Text Colors
- Primary: `#f8fafc`
- Secondary: `#e2e8f0`
- Muted: `#94a3b8`

### Accent Colors
- Primary: `#667eea`
- Secondary: `#764ba2`

### Status Colors
- Healthy: `#10b981`
- Warning: `#f59e0b`
- Error: `#ef4444`

---

## Performance Considerations

1. **Lazy Loading**: All visualization components support lazy loading via dynamic imports
2. **Virtual Scrolling**: Large datasets use virtual scrolling where applicable
3. **Debounced Updates**: Real-time data updates are debounced to prevent render thrashing
4. **SVG Optimization**: Complex visualizations use SVG with efficient re-rendering
5. **Worker Offloading**: Heavy calculations can be offloaded to web workers

---

## API Dependencies

| Component | API Endpoints |
|-----------|---------------|
| ResourceHeatmap | `/api/monitoring/metrics/history` |
| WorkflowVisualization | `/api/workflows/{id}`, `/api/workflows/{id}/status` |
| AgentActivityVisualization | `/api/agents`, `/api/agents/activity` |
| SystemArchitectureDiagram | `/api/monitoring/health` |
| KnowledgeGraph | `/api/memory/entities/*` |

---

## Future Enhancements

- [ ] 3D visualization mode for system architecture
- [ ] Timeline scrubbing for historical data
- [ ] Comparison views (side-by-side metrics)
- [ ] Alert overlays on visualizations
- [ ] Export to PDF/PNG
- [ ] Collaborative dashboard sharing
- [ ] Custom color themes

---

## Related Documentation

- [Monitoring API](../api/COMPREHENSIVE_API_DOCUMENTATION.md#monitoring)
- [WebSocket Integration](../developer/WEBSOCKET_INTEGRATION.md)
- [Frontend Development](../developer/PHASE_5_DEVELOPER_SETUP.md)
