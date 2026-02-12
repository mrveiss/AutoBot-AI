# AutoBot Troubleshooting Index

**Quick Navigation** | [By Component](#by-component) | [By Symptom](#by-symptom) | [By Severity](#by-severity) | [All Guides](#all-guides)

---

## 🔍 Quick Search

**Having an issue?** Use this symptom-to-guide mapping:

| Symptom | Guide | Severity |
|---------|-------|----------|
| Port not accessible / Connection refused | [NPU Worker Port Not Accessible](guides/npu-worker-port-not-accessible.md) | High |
| 404 / 401 API errors | [Frontend API Calls 404/401 Errors](guides/frontend-api-calls-404-401-errors.md) | High |
| ModuleNotFoundError / ImportError | [Stale Import Paths](guides/stale-import-paths-after-refactor.md) | High |
| Ansible role not found | [Ansible Role Deployment Failures](guides/ansible-role-deployment-failures.md) | High |
| Tool results appear instantly | [LLM Streaming Fake Tool Results](guides/llm-streaming-fake-tool-results.md) | Medium |
| Backend API unresponsive | [Comprehensive Guide §1](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#1-backend-api-unresponsive) | Critical |
| VM communication failure | [Comprehensive Guide §2](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#2-vm-communication-failures) | Critical |
| Redis connection failure | [Comprehensive Guide §3](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#3-redis-database-failures) | Critical |
| Multi-modal AI failure | [Comprehensive Guide §4](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#4-multi-modal-ai-processing-failures) | High |
| Knowledge base search error | [Comprehensive Guide §5](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#5-knowledge-base-search-failures) | High |
| Frontend connection timeout | [Comprehensive Guide §6](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#6-frontend-connection-issues) | High |
| Terminal command timeout | [Comprehensive Guide §7](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#7-terminal-command-execution-issues) | Medium |
| Browser automation failure | [Comprehensive Guide §8](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#8-browser-service-automation-failures) | Medium |
| File upload failure | [Comprehensive Guide §9](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#9-file-upload--management-issues) | Medium |
| Performance degradation | [Comprehensive Guide §10](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#10-performance-optimization-issues) | Low |

---

## By Component

### 🔧 Infrastructure

| Issue | Guide | Issue # |
|-------|-------|---------|
| NPU worker port not accessible | [Guide](guides/npu-worker-port-not-accessible.md) | #851 |
| Ansible role deployment failures | [Guide](guides/ansible-role-deployment-failures.md) | #807, #837 |
| VM communication breakdown | [Comprehensive §2](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#2-vm-communication-failures) | - |

### 🔙 Backend

| Issue | Guide | Issue # |
|-------|-------|---------|
| API unresponsive | [Comprehensive §1](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#1-backend-api-unresponsive) | - |
| Stale import paths after refactoring | [Guide](guides/stale-import-paths-after-refactor.md) | #806 |
| LLM streaming hallucinations | [Guide](guides/llm-streaming-fake-tool-results.md) | #727 |
| Redis connection failures | [Comprehensive §3](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#3-redis-database-failures) | - |

### 🎨 Frontend

| Issue | Guide | Issue # |
|-------|-------|---------|
| API calls return 404/401 errors | [Guide](guides/frontend-api-calls-404-401-errors.md) | #810, #822 |
| Frontend connection issues | [Comprehensive §6](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#6-frontend-connection-issues) | - |

### 🤖 AI / ML

| Issue | Guide | Issue # |
|-------|-------|---------|
| Multi-modal AI processing failures | [Comprehensive §4](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#4-multi-modal-ai-processing-failures) | - |
| Knowledge base search errors | [Comprehensive §5](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#5-knowledge-base-search-failures) | - |

### 🌐 Browser / Terminal

| Issue | Guide | Issue # |
|-------|-------|---------|
| Terminal command timeouts | [Comprehensive §7](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#7-terminal-command-execution-issues) | - |
| Browser automation failures | [Comprehensive §8](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#8-browser-service-automation-failures) | - |

---

## By Symptom

### Connection / Network Issues
- [NPU Worker Port Not Accessible](guides/npu-worker-port-not-accessible.md)
- [Frontend API 404/401 Errors](guides/frontend-api-calls-404-401-errors.md)
- [VM Communication Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#2-vm-communication-failures)
- [Redis Connection Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#3-redis-database-failures)

### Import / Module Errors
- [Stale Import Paths](guides/stale-import-paths-after-refactor.md)
- `ModuleNotFoundError: No module named 'src.xxx'`
- `ImportError: cannot import name 'xxx'`

### Deployment / Configuration Issues
- [Ansible Role Deployment Failures](guides/ansible-role-deployment-failures.md)
- Role not found
- Duplicate role warnings
- Venv Python mismatch

### API / Service Issues
- [Backend API Unresponsive](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#1-backend-api-unresponsive)
- [Frontend API Errors](guides/frontend-api-calls-404-401-errors.md)
- Port conflicts
- CORS errors

### AI / LLM Issues
- [LLM Streaming Fake Results](guides/llm-streaming-fake-tool-results.md)
- [Multi-Modal AI Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#4-multi-modal-ai-processing-failures)
- [Knowledge Base Search Errors](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#5-knowledge-base-search-failures)

---

## By Severity

### 🔥 Critical (System Down)
1. [Backend API Unresponsive](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#1-backend-api-unresponsive)
2. [VM Communication Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#2-vm-communication-failures)
3. [Redis Database Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#3-redis-database-failures)

### ⚠️ High Priority (Degraded Performance)
4. [NPU Worker Port Not Accessible](guides/npu-worker-port-not-accessible.md)
5. [Frontend API 404/401 Errors](guides/frontend-api-calls-404-401-errors.md)
6. [Stale Import Paths](guides/stale-import-paths-after-refactor.md)
7. [Ansible Deployment Failures](guides/ansible-role-deployment-failures.md)
8. [Multi-Modal AI Processing Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#4-multi-modal-ai-processing-failures)
9. [Knowledge Base Search Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#5-knowledge-base-search-failures)
10. [Frontend Connection Issues](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#6-frontend-connection-issues)

### 📝 Medium Priority (Feature Impact)
11. [LLM Streaming Fake Results](guides/llm-streaming-fake-tool-results.md)
12. [Terminal Command Timeouts](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#7-terminal-command-execution-issues)
13. [Browser Automation Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#8-browser-service-automation-failures)
14. [File Upload Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#9-file-upload--management-issues)

### ℹ️ Low Priority (Minor Impact)
15. [Performance Optimization](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#10-performance-optimization-issues)

---

## All Guides

### Detailed Guides (New)
1. [NPU Worker Port Not Accessible](guides/npu-worker-port-not-accessible.md) - #851
2. [Frontend API Calls 404/401 Errors](guides/frontend-api-calls-404-401-errors.md) - #810, #822
3. [Stale Import Paths After Refactoring](guides/stale-import-paths-after-refactor.md) - #806
4. [Ansible Role Deployment Failures](guides/ansible-role-deployment-failures.md) - #807, #837
5. [LLM Streaming Fake Tool Results](guides/llm-streaming-fake-tool-results.md) - #727

### Comprehensive Guide (Existing)
6. [Backend API Unresponsive](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#1-backend-api-unresponsive)
7. [VM Communication Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#2-vm-communication-failures)
8. [Redis Database Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#3-redis-database-failures)
9. [Multi-Modal AI Processing Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#4-multi-modal-ai-processing-failures)
10. [Knowledge Base Search Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#5-knowledge-base-search-failures)
11. [Frontend Connection Issues](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#6-frontend-connection-issues)
12. [Terminal Command Execution Issues](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#7-terminal-command-execution-issues)
13. [Browser Service Automation Failures](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#8-browser-service-automation-failures)
14. [File Upload & Management Issues](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#9-file-upload--management-issues)
15. [Performance Optimization Issues](COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md#10-performance-optimization-issues)

### Reference Documents
- [Guide Template](guides/GUIDE_TEMPLATE.md) - Template for creating new guides
- [Knowledge Manager Categories](KNOWLEDGE_MANAGER_CATEGORIES.md)
- [User Guide: Troubleshooting](../user-guide/04-troubleshooting.md)

---

## Quick Diagnostic Commands

Before diving into specific guides, run these diagnostic commands:

```bash
# 1. Overall system health
bash run_autobot.sh --status

# 2. Service connectivity
python3 scripts/health_check_comprehensive.py

# 3. Recent errors
tail -f logs/autobot.log | grep -i error

# 4. VM network
ping -c 3 172.16.168.19  # SLM
ping -c 3 172.16.168.21  # Frontend
ping -c 3 172.16.168.22  # NPU
ping -c 3 172.16.168.23  # Redis
ping -c 3 172.16.168.24  # AI Stack
ping -c 3 172.16.168.25  # Browser

# 5. Critical services
curl -s http://127.0.0.1:8001/api/health | jq .
redis-cli -h 172.16.168.23 ping
```

---

## Contributing

To add a new troubleshooting guide:

1. Use the [guide template](guides/GUIDE_TEMPLATE.md)
2. Create `docs/troubleshooting/guides/your-issue-name.md`
3. Add entry to this INDEX.md in all relevant sections
4. Link from error messages if applicable
5. Test all commands and verification steps

---

**Last Updated**: 2026-02-12
**Total Guides**: 15 (10 comprehensive + 5 detailed)
