# LLM-as-Judge Framework Documentation

## Overview

The AutoBot LLM-as-Judge framework provides a comprehensive system for automated decision making, quality assessment, and risk evaluation throughout the application. This framework implements transparent, explainable AI decision-making to improve system reliability, security, and user experience.

## Architecture

### Core Components

1. **BaseLLMJudge** - Abstract base class for all judges
2. **WorkflowStepJudge** - Evaluates workflow steps before execution
3. **AgentResponseJudge** - Assesses agent response quality and effectiveness
4. **MultiAgentArbitrator** - Coordinates decisions between multiple agents
5. **SecurityRiskJudge** - Evaluates security risks and command safety

### Key Design Principles

- **Transparent Reasoning**: All decisions include detailed reasoning and evidence
- **Multi-Criteria Evaluation**: Each judgment evaluates multiple dimensions
- **Context-Aware Decisions**: Judges consider execution context and user needs
- **Explainable AI**: Clear explanations for trust and debugging
- **Feedback Loops**: Performance tracking for continuous improvement

## Judge Types and Use Cases

### 1. WorkflowStepJudge

**Purpose**: Evaluates workflow steps before execution to ensure safety, quality, and effectiveness.

**Evaluation Criteria**:
- Safety: Risk assessment and potential for harm
- Quality: Likelihood of successful execution
- Relevance: Alignment with workflow goals
- Feasibility: Technical possibility of execution
- Efficiency: Resource utilization and performance
- Compliance: Adherence to policies and best practices

**Integration Points**:
- Workflow automation API (`/api/workflow_automation/`)
- Pre-execution step validation
- Automated workflow systems

**Example Usage**:
```python
from src.judges.workflow_step_judge import WorkflowStepJudge

judge = WorkflowStepJudge()
judgment = await judge.evaluate_workflow_step(
    step_data={
        "step_id": "update_system",
        "command": "sudo apt update",
        "description": "Update package repositories",
        "risk_level": "low"
    },
    workflow_context={
        "workflow_name": "System Update",
        "current_step_index": 0,
        "total_steps": 4
    },
    user_context={
        "permissions": ["admin"],
        "experience_level": "advanced",
        "environment": "production"
    }
)

if judgment.recommendation == "APPROVE":
    # Execute step
    pass
else:
    # Handle rejection or request user confirmation
    pass
```

### 2. AgentResponseJudge

**Purpose**: Evaluates agent response quality, relevance, and effectiveness.

**Evaluation Criteria**:
- Relevance: How well the response addresses the request
- Accuracy: Correctness and reliability of information
- Completeness: Thoroughness in addressing the request
- Quality: Overall excellence of the response
- Consistency: Internal coherence and alignment
- Efficiency: Appropriateness and resource utilization

**Integration Points**:
- Chat API response validation
- Multi-agent response comparison
- Quality assurance systems
- User satisfaction tracking

**Example Usage**:
```python
from src.judges.agent_response_judge import AgentResponseJudge

judge = AgentResponseJudge()
judgment = await judge.evaluate_agent_response(
    request={"query": "How do I install Docker?"},
    response={
        "content": "To install Docker, run: curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh",
        "confidence": 0.95
    },
    agent_type="terminal",
    context={"user_os": "ubuntu", "experience": "beginner"}
)

quality_score = judgment.overall_score
recommendations = judgment.improvement_suggestions
```

### 3. MultiAgentArbitrator

**Purpose**: Coordinates decisions between multiple agents and resolves conflicts.

**Key Features**:
- Response comparison and ranking
- Conflict detection and resolution
- Consensus building
- Agent performance evaluation

**Integration Points**:
- Multi-agent chat systems
- Response selection mechanisms
- Agent coordination workflows

**Example Usage**:
```python
from src.judges.multi_agent_arbitrator import MultiAgentArbitrator

arbitrator = MultiAgentArbitrator()

# Compare multiple agent responses
judgment = await arbitrator.arbitrate_agent_responses(
    user_request={"query": "Best way to optimize database performance?"},
    agent_responses=[
        {"agent": "database_expert", "response": "Use indexing and query optimization"},
        {"agent": "general_assistant", "response": "Consider using a faster database engine"}
    ],
    agent_types=["database_expert", "general_assistant"],
    context={"database_type": "postgresql", "performance_issues": ["slow_queries"]}
)

best_response = judgment.alternatives_considered[0]
```

### 4. SecurityRiskJudge

**Purpose**: Evaluates security risks, command safety, and compliance.

**Risk Assessment Areas**:
- Command safety evaluation
- File access risk assessment
- Network operation security
- Privilege escalation detection
- Data exposure prevention

**Integration Points**:
- Terminal command validation
- File system access control
- Network operation approval
- Security compliance checking

**Example Usage**:
```python
from src.judges.security_risk_judge import SecurityRiskJudge

judge = SecurityRiskJudge()

# Evaluate command security
judgment = await judge.evaluate_command_security(
    command="sudo rm -rf /tmp/cache",
    context={
        "working_directory": "/home/user",
        "user": "developer",
        "session_type": "interactive"
    },
    user_permissions=["sudo"],
    environment="development"
)

if judgment.overall_score > 0.7:
    # Command is safe to execute
    pass
else:
    # Command requires additional approval or is blocked
    pass
```

## API Integration

### Workflow Automation

The framework is integrated into the workflow automation system to evaluate steps before execution:

**Endpoint**: `/api/workflow_automation/`

**Integration Flow**:
1. Workflow step created
2. Step evaluated by WorkflowStepJudge and SecurityRiskJudge
3. Decision made based on combined evaluation
4. Step approved, rejected, or requires user confirmation

### Validation Dashboard

**Endpoints**:
- `/api/validation_dashboard/judge_workflow_step` - Evaluate workflow steps
- `/api/validation_dashboard/judge_agent_response` - Evaluate agent responses
- `/api/validation_dashboard/judge_status` - Get judge performance metrics

**Example API Usage**:
```bash
# Evaluate a workflow step
curl -X POST "http://localhost:8000/api/validation_dashboard/judge_workflow_step" \
  -H "Content-Type: application/json" \
  -d '{
    "step_data": {
      "step_id": "install_package",
      "command": "sudo apt install -y python3-pip",
      "description": "Install Python package manager"
    },
    "workflow_context": {
      "workflow_name": "Development Setup",
      "current_step_index": 2
    },
    "user_context": {
      "permissions": ["admin"],
      "environment": "development"
    }
  }'

# Response
{
  "status": "success",
  "judgment": {
    "overall_score": 0.85,
    "recommendation": "APPROVE",
    "confidence": "high",
    "reasoning": "Command is safe for development environment with proper permissions",
    "criterion_scores": [
      {
        "dimension": "safety",
        "score": 0.9,
        "reasoning": "Low risk package installation command"
      }
    ],
    "improvement_suggestions": []
  }
}
```

## Configuration and Customization

### Judge Configuration

Judges can be configured with custom thresholds and parameters:

```python
# Custom thresholds
workflow_judge = WorkflowStepJudge()
workflow_judge.safety_threshold = 0.8  # Higher safety requirement
workflow_judge.quality_threshold = 0.7  # Higher quality requirement

security_judge = SecurityRiskJudge()
security_judge.block_threshold = 0.6  # More restrictive blocking
```

### Adding Custom Judges

To create a custom judge:

1. Inherit from `BaseLLMJudge`
2. Implement `_prepare_judgment_prompt()` method
3. Define evaluation criteria and context
4. Add to integration points

```python
from src.judges import BaseLLMJudge, JudgmentDimension

class CustomJudge(BaseLLMJudge):
    def __init__(self):
        super().__init__("custom_judge")

    async def _prepare_judgment_prompt(self, subject, criteria, context, alternatives=None, **kwargs):
        # Implement custom prompt logic
        return "Evaluate this custom scenario..."

    def _get_system_prompt(self):
        return "You are an expert in custom evaluation..."
```

## Performance and Monitoring

### Metrics Tracking

All judges track performance metrics:
- Total judgments made
- Average processing time
- Recommendation distribution
- Average confidence levels

### Performance Optimization

- **Caching**: Repeated evaluations can be cached
- **Async Processing**: All judges support async operations
- **Batch Evaluation**: Multiple items can be evaluated together
- **Context Reuse**: Common context can be shared across evaluations

### Monitoring Integration

```python
# Get judge performance metrics
metrics = judge.get_performance_metrics()
print(f"Total judgments: {metrics['total_judgments']}")
print(f"Average score: {metrics['average_score']}")
print(f"Processing time: {metrics['average_processing_time_ms']}ms")
```

## Testing and Validation

### Unit Tests

Located in `/tests/judges/`:
- `test_workflow_step_judge.py`
- `test_agent_response_judge.py`
- `test_multi_agent_arbitrator.py`
- `test_security_risk_judge.py`

### Integration Tests

- End-to-end workflow evaluation
- API endpoint testing
- Performance benchmarking
- Error handling validation

### Example Test

```python
import pytest
from src.judges.workflow_step_judge import WorkflowStepJudge

@pytest.mark.asyncio
async def test_workflow_step_evaluation():
    judge = WorkflowStepJudge()

    step_data = {
        "step_id": "test_step",
        "command": "echo 'hello'",
        "description": "Test command"
    }

    judgment = await judge.evaluate_workflow_step(
        step_data, {}, {"permissions": ["user"]}
    )

    assert judgment.overall_score > 0.8
    assert judgment.recommendation == "APPROVE"
```

## Best Practices

### Implementation Guidelines

1. **Clear Prompts**: Write detailed, specific evaluation prompts
2. **Consistent Scoring**: Use standardized 0.0-1.0 scoring scales
3. **Evidence-Based**: Provide specific evidence for all scores
4. **Context Awareness**: Consider user, environment, and system context
5. **Error Handling**: Gracefully handle evaluation failures
6. **Performance**: Optimize for response time and resource usage

### Security Considerations

1. **Input Validation**: Validate all input data before evaluation
2. **Prompt Injection**: Protect against malicious prompt injection
3. **Access Control**: Ensure judges have appropriate system access
4. **Audit Logging**: Log all judgment decisions for audit trails
5. **Fallback Behavior**: Define safe fallback when judges fail

### Usage Patterns

1. **Pre-execution Validation**: Evaluate before taking actions
2. **Quality Assurance**: Continuous monitoring of outputs
3. **User Assistance**: Help users understand system decisions
4. **Risk Management**: Identify and mitigate potential risks
5. **Performance Optimization**: Use judgments to improve system performance

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed
2. **LLM Interface Issues**: Verify LLM interface is properly configured
3. **Performance Problems**: Check for prompt optimization opportunities
4. **Inconsistent Results**: Review prompt clarity and evaluation criteria

### Debug Mode

Enable debug logging for detailed judgment information:

```python
import logging
logging.getLogger("src.judges").setLevel(logging.DEBUG)
```

### Error Recovery

All judges implement graceful error recovery:
- Default to safe decisions on errors
- Provide meaningful error messages
- Continue operation when possible
- Log errors for analysis

## Future Enhancements

### Planned Features

1. **Learning Integration**: Feedback-based improvement
2. **Custom Criteria**: User-defined evaluation dimensions
3. **Batch Processing**: Efficient bulk evaluations
4. **Real-time Monitoring**: Live judgment tracking
5. **Advanced Analytics**: Judgment pattern analysis

### Extension Points

1. **Custom Judges**: Domain-specific evaluation logic
2. **External Integration**: Third-party risk assessment tools
3. **Machine Learning**: Automated prompt optimization
4. **Compliance Frameworks**: Industry-specific compliance checking

## Conclusion

The AutoBot LLM-as-Judge framework provides a robust foundation for automated decision making throughout the system. By implementing transparent, explainable AI evaluation, it enhances system safety, security, and user experience while maintaining flexibility for customization and extension.

For additional support or questions, refer to the implementation files in `/src/judges/` or contact the development team.
