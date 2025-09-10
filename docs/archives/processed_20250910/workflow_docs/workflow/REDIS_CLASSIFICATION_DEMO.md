# Redis-Based Workflow Classification System

## 🎯 Problem Solved

**Before**: Keywords hardcoded in source code
**After**: Dynamic keywords and rules stored in Redis database

## 🚀 Key Improvements

### 1. **Dynamic Configuration**
- Keywords stored in Redis, not source code
- Rules can be updated without code changes
- Real-time classification updates

### 2. **Better Maintainability**
- Centralized keyword management
- Easy addition of new categories
- Version control for classification logic

### 3. **Scalability**
- Support for complex classification rules
- Priority-based rule evaluation
- Extensible architecture

## 📊 System Overview

### Redis Storage Structure
```
autobot:workflow:classification:keywords
{
  "security": ["scan", "vulnerabilities", "penetration", "exploit", ...],
  "network": ["network", "port", "firewall", "tcp", "udp", ...],
  "research": ["find", "search", "tools", "best", "recommend", ...],
  "install": ["install", "setup", "configure", "deploy", ...]
}

autobot:workflow:classification:rules
{
  "security_network": {
    "condition": "any_security AND any_network",
    "complexity": "complex",
    "priority": 100
  },
  "multiple_research": {
    "condition": "research >= 2 OR has_tools",
    "complexity": "complex",
    "priority": 90
  }
}
```

### Classification Logic
1. **Extract keywords** from user message
2. **Count matches** per category
3. **Evaluate rules** by priority order
4. **Return complexity** level (simple/research/install/complex)

## 🛠️ Usage Examples

### Managing Keywords
```bash
# Show current statistics
python3 manage_classification.py

# Add security keywords via CLI
python3 src/workflow_classifier.py add-keyword --category security --keyword "malware"

# Test classification
python3 src/workflow_classifier.py test --message "I need to scan my network"
```

### Programmatic Usage
```python
from src.workflow_classifier import WorkflowClassifier

classifier = WorkflowClassifier()

# Test classification
complexity = classifier.classify_request("I need to scan my network for vulnerabilities")
# Returns: TaskComplexity.COMPLEX

# Add keywords dynamically
classifier.add_keywords("security", ["pentest", "audit", "compliance"])
```

## 📈 Current Statistics

After initialization:
- **6 Categories**: research, install, complex, security, network, system
- **43 Keywords**: Comprehensive coverage of workflow triggers
- **5 Rules**: Priority-based classification logic

## 🎮 Demo Results

### Test Cases
```bash
$ python3 src/workflow_classifier.py test --message "I need to scan my network for security vulnerabilities"
Classification: complex

$ python3 src/workflow_classifier.py test --message "What is 2+2?"
Classification: simple

$ python3 src/workflow_classifier.py test --message "How do I install Docker?"
Classification: install

$ python3 src/workflow_classifier.py test --message "Find Python libraries"
Classification: research
```

### Integration with Orchestrator
```python
# Old way (hardcoded)
if "security" in message and "network" in message:
    return TaskComplexity.COMPLEX

# New way (Redis-based)
classifier = WorkflowClassifier(redis_client)
return classifier.classify_request(message)
```

## 🔧 Management Interface

Interactive CLI tool: `manage_classification.py`

Features:
- Add keywords to any category
- Test message classification
- View statistics and current keywords
- Bulk operations for common scenarios

## 🚀 Benefits Achieved

1. **No Code Changes**: Add keywords without touching source code
2. **Real-time Updates**: Classification changes apply immediately
3. **Better Accuracy**: More comprehensive keyword coverage
4. **Easy Maintenance**: Centralized configuration management
5. **Extensibility**: Simple to add new categories and rules

## 📊 Impact on Workflow Orchestration

The message "I need to scan my network for security vulnerabilities" now correctly triggers:
- **Classification**: COMPLEX
- **Workflow**: 8-step multi-agent orchestration
- **Agents**: Research, KB Librarian, System Commands, Orchestrator
- **Result**: Intelligent coordination instead of generic response

**Status**: Redis-based classification system fully operational! 🎉
