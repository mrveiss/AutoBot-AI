# AutoBot Workflow Orchestration API Documentation

## 🔄 Overview

The AutoBot Workflow Orchestration API provides comprehensive multi-agent coordination capabilities, transforming simple chat requests into sophisticated workflows that coordinate research, knowledge management, user approvals, and system operations.

## 🚀 API Endpoints

### Core Workflow Management

#### Execute Workflow
```http
POST /api/workflow/execute
Content-Type: application/json

{
  "user_message": "find tools for network scanning",
  "auto_approve": false
}
```

**Response:**
```json
{
  "type": "workflow_orchestration",
  "workflow_id": "uuid-workflow-id",
  "workflow_response": {
    "message_classification": "complex",
    "workflow_required": true,
    "planned_steps": 8,
    "agents_involved": ["research", "librarian", "orchestrator", "system_commands"],
    "user_approvals_needed": 2,
    "estimated_duration": "3 minutes",
    "workflow_preview": [
      "1. Librarian: Search Knowledge Base",
      "2. Research: Research Tools",
      "3. Orchestrator: Present Tool Options (requires approval)",
      "4. Research: Get Installation Guide",
      "5. Knowledge_Manager: Store Tool Info",
      "6. Orchestrator: Create Install Plan (requires approval)",
      "7. System_Commands: Install Tool",
      "8. System_Commands: Verify Installation"
    ]
  }
}
```

#### List Active Workflows
```http
GET /api/workflow/workflows
```

**Response:**
```json
{
  "workflows": [
    {
      "id": "uuid-workflow-id",
      "status": "in_progress",
      "classification": "complex",
      "steps_completed": 3,
      "total_steps": 8,
      "agents_involved": ["research", "librarian", "orchestrator"],
      "created_at": "2024-01-10T15:30:00Z",
      "estimated_completion": "2024-01-10T15:33:00Z"
    }
  ]
}
```

#### Get Workflow Status
```http
GET /api/workflow/workflow/{workflow_id}/status
```

**Response:**
```json
{
  "id": "uuid-workflow-id",
  "status": "in_progress",
  "classification": "complex",
  "current_step": 4,
  "total_steps": 8,
  "progress_percentage": 50,
  "current_agent": "research",
  "current_action": "Get Installation Guide",
  "steps_completed": [
    {
      "step": 1,
      "agent": "librarian",
      "action": "Search Knowledge Base",
      "status": "completed",
      "duration": "2.1s",
      "result": "Found 3 relevant documents in knowledge base"
    }
  ],
  "pending_approvals": []
}
```

#### Approve Workflow Step
```http
POST /api/workflow/workflow/{workflow_id}/approve
Content-Type: application/json

{
  "step_id": "present_options",
  "approved": true,
  "user_selection": "nmap"
}
```

**Response:**
```json
{
  "status": "approved",
  "workflow_id": "uuid-workflow-id",
  "step_id": "present_options",
  "next_action": "proceeding_to_installation_guide"
}
```

#### Get Pending Approvals
```http
GET /api/workflow/workflow/{workflow_id}/pending_approvals
```

**Response:**
```json
{
  "pending_approvals": [
    {
      "step_id": "present_options",
      "agent": "orchestrator",
      "action": "Present Tool Options",
      "description": "Multiple network scanning tools found. Please select preferred tool.",
      "options": ["nmap", "masscan", "zmap"],
      "timeout": "2024-01-10T15:35:00Z"
    }
  ]
}
```

#### Cancel Workflow
```http
DELETE /api/workflow/workflow/{workflow_id}
```

**Response:**
```json
{
  "status": "cancelled",
  "workflow_id": "uuid-workflow-id",
  "steps_completed": 3,
  "cleanup_status": "completed"
}
```

## 🔧 Integration Patterns

### Frontend Integration

#### Vue.js Service Layer
```javascript
// autobot-vue/src/services/api.js
export const workflowAPI = {
  async executeWorkflow(userMessage, autoApprove = false) {
    return await apiClient.post('/api/workflow/execute', {
      user_message: userMessage,
      auto_approve: autoApprove
    });
  },

  async getActiveWorkflows() {
    return await apiClient.get('/api/workflow/workflows');
  },

  async getWorkflowStatus(workflowId) {
    return await apiClient.get(`/api/workflow/workflow/${workflowId}/status`);
  },

  async approveWorkflowStep(workflowId, stepId, approved, userSelection = null) {
    return await apiClient.post(`/api/workflow/workflow/${workflowId}/approve`, {
      step_id: stepId,
      approved: approved,
      user_selection: userSelection
    });
  }
};
```

#### WebSocket Event Handling
```javascript
// WebSocket workflow events
const handleWorkflowEvent = (eventData) => {
  const eventType = eventData.type;

  switch(eventType) {
    case 'workflow_step_started':
      updateUI(`🔄 Started: ${eventData.payload.description}`);
      break;

    case 'workflow_step_completed':
      updateUI(`✅ Completed: ${eventData.payload.description}`);
      break;

    case 'workflow_approval_required':
      showApprovalModal(eventData.payload.workflow_id, eventData.payload);
      break;

    case 'workflow_completed':
      updateUI(`🎉 Workflow completed! (${eventData.payload.total_steps} steps)`);
      break;

    case 'workflow_failed':
      updateUI(`❌ Workflow failed: ${eventData.payload.error}`);
      break;
  }
};
```

### Backend Integration

#### Custom Agent Implementation
```python
# backend/api/workflow.py - Adding new agent type
async def execute_single_step(workflow_id: str, step: Dict[str, Any], orchestrator):
    agent_type = step["agent_type"]

    if agent_type == "custom_agent":
        # Custom agent implementation
        result = await custom_agent_handler(
            step["action"],
            step["inputs"],
            orchestrator
        )

        # Emit workflow event
        await event_manager.publish("workflow_event", {
            "type": "workflow_step_completed",
            "payload": {
                "workflow_id": workflow_id,
                "step_id": step["id"],
                "agent": agent_type,
                "result": result
            }
        })

        return result
```

#### Request Classification Extension
```python
# src/orchestrator.py - Adding new workflow type
def classify_request_complexity(self, user_message: str) -> TaskComplexity:
    message_lower = user_message.lower()

    # Add custom classification logic
    if "custom_keywords" in message_lower:
        return TaskComplexity.CUSTOM

    # Existing classification logic...
    return self._existing_classification(message_lower)
```

## 🧪 Testing

### API Endpoint Testing
```python
# test_workflow_api.py
import pytest
import asyncio
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_workflow_execution():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/workflow/execute", json={
            "user_message": "find tools for network scanning",
            "auto_approve": False
        })

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "workflow_orchestration"
        assert "workflow_id" in data
```

### End-to-End Testing
```python
# test_complete_system.py
async def test_full_workflow_cycle():
    # 1. Execute workflow
    workflow_result = await execute_workflow("test request")
    workflow_id = workflow_result["workflow_id"]

    # 2. Monitor progress
    while True:
        status = await get_workflow_status(workflow_id)
        if status["status"] in ["completed", "failed"]:
            break
        await asyncio.sleep(1)

    # 3. Verify completion
    assert status["status"] == "completed"
    assert status["steps_completed"] == status["total_steps"]
```

## 🔍 Monitoring and Observability

### Workflow Metrics
- Request classification accuracy
- Average workflow execution time
- Agent coordination efficiency
- User approval response rates
- Error and retry rates

### Logging Integration
```python
# Structured logging for workflow events
logger.info("workflow_started", extra={
    "workflow_id": workflow_id,
    "classification": complexity.value,
    "agents_count": len(agents_involved),
    "estimated_duration": duration
})
```

## 🚨 Error Handling

### Common Error Scenarios
1. **Agent Unavailable** - Graceful fallback to alternative agents
2. **Approval Timeout** - Auto-denial after configured timeout
3. **Step Execution Failure** - Retry logic with exponential backoff
4. **WebSocket Disconnection** - Automatic reconnection with state sync

### Error Response Format
```json
{
  "error": true,
  "error_code": "WORKFLOW_STEP_FAILED",
  "message": "Research agent failed to complete tool search",
  "workflow_id": "uuid-workflow-id",
  "failed_step": 2,
  "recovery_options": ["retry_step", "skip_step", "cancel_workflow"]
}
```

## 🔐 Security Considerations

### Authentication
- All workflow operations require valid session authentication
- User approval steps validate user identity
- System command execution requires elevated permissions

### Input Validation
- User messages sanitized for injection attacks
- Workflow parameters validated against schema
- Agent inputs filtered for malicious content

### Rate Limiting
- Workflow execution rate limited per user
- Concurrent workflow limits enforced
- Resource usage monitoring and throttling

## 📊 Performance Optimization

### Caching Strategies
- Workflow templates cached for common request patterns
- Agent response caching for similar operations
- Knowledge base query result caching

### Async Processing
- Non-blocking workflow step execution
- Background task processing for long-running operations
- Efficient WebSocket connection management

### Resource Management
- Agent pool management and load balancing
- Memory usage optimization for large workflows
- Database connection pooling

---

## 🎯 Best Practices

1. **Always** test workflow changes with `python3 test_workflow_api.py`
2. **Monitor** workflow performance with built-in metrics
3. **Handle** user approvals with appropriate timeouts
4. **Log** all workflow events for debugging and analytics
5. **Validate** all inputs and sanitize user content
6. **Use** WebSocket events for real-time UI updates
7. **Implement** proper error recovery mechanisms
8. **Cache** frequently used workflow patterns
9. **Scale** agent pools based on usage patterns
10. **Document** new workflow types and agent integrations
