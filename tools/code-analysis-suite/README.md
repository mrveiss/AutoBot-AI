# AutoBot Code Analysis Suite

A comprehensive code quality analysis system with Redis caching and NPU acceleration support.

## 🎯 Overview

The Code Analysis Suite provides enterprise-grade code quality monitoring with 9 specialized analyzers supporting both backend and frontend technologies:

- **Code Duplication Analyzer** - Finds duplicate code blocks using AST and embedding similarity
- **Environment Variable Analyzer** - Identifies hardcoded configurations that should be externalized
- **Performance Analyzer** - Detects memory leaks, blocking calls, and performance bottlenecks
- **Security Analyzer** - Scans for security vulnerabilities with CWE classifications
- **API Consistency Analyzer** - Ensures consistent API design patterns across frameworks
- **Testing Coverage Analyzer** - Identifies test coverage gaps and missing test patterns
- **Architectural Pattern Analyzer** - Analyzes design patterns and architectural quality
- **Frontend Analyzer** - JavaScript, TypeScript, Vue, React, Angular code analysis
- **Automated Fix Generator** - Generates specific code fixes with confidence scoring

## 🚀 Quick Start

### Prerequisites

```bash
# Install Redis (required for caching)
sudo apt install redis-server
# or
docker run -d -p 6379:6379 redis:alpine

# Install Python dependencies
pip install redis aioredis numpy scikit-learn chromadb
```

### Basic Usage

```bash
# Run individual analyzers
python scripts/analyze_duplicates.py
python scripts/analyze_security.py
python scripts/analyze_performance.py
python scripts/analyze_frontend.py      # NEW: Frontend analysis

# Run comprehensive analysis
python scripts/analyze_code_quality.py

# Generate automated fixes
python scripts/generate_automated_corrections.py
```

## 📊 Analyzers Overview

### 1. Code Duplication Analyzer
- **Purpose**: Find and eliminate duplicate code blocks
- **Output**: Similarity clusters, refactoring suggestions, lines saved
- **Script**: `scripts/analyze_duplicates.py`

### 2. Environment Variable Analyzer
- **Purpose**: Identify hardcoded values that should be configuration
- **Output**: Hardcoded URLs, API keys, file paths, network addresses
- **Script**: `scripts/analyze_env_vars.py`

### 3. Performance Analyzer
- **Purpose**: Detect performance issues and memory leaks
- **Output**: Memory leaks, blocking calls, inefficient loops, database issues
- **Script**: `scripts/analyze_performance.py`

### 4. Security Analyzer
- **Purpose**: Find security vulnerabilities with CWE classifications
- **Output**: SQL injection, XSS, weak crypto, hardcoded secrets
- **Script**: `scripts/analyze_security.py`

### 5. API Consistency Analyzer
- **Purpose**: Ensure consistent API design across endpoints
- **Output**: Naming inconsistencies, response format issues, auth patterns
- **Script**: `scripts/analyze_api_consistency.py`

### 6. Testing Coverage Analyzer
- **Purpose**: Identify test coverage gaps and missing tests
- **Output**: Untested functions, missing edge cases, integration tests
- **Script**: `scripts/analyze_testing_coverage.py`

### 7. Architectural Pattern Analyzer
- **Purpose**: Analyze design patterns and architectural quality
- **Output**: Pattern detection, coupling/cohesion metrics, architectural issues
- **Script**: `scripts/analyze_architecture.py`

### 8. Frontend Analyzer
- **Purpose**: Analyze JavaScript, TypeScript, Vue, React, Angular code
- **Output**: Framework detection, XSS vulnerabilities, performance issues, accessibility gaps
- **Script**: `scripts/analyze_frontend.py`

### 9. Automated Fix Generator
- **Purpose**: Generate specific code fixes with confidence scoring
- **Output**: Automated patches, fix recommendations, risk assessments
- **Script**: `scripts/generate_automated_fixes.py`

## 🔧 Configuration

### Redis Configuration
```python
# Default Redis connection
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

# Configure in src/config.py or environment variables
export REDIS_URL="redis://localhost:6379/0"
```

### NPU Support (Optional)
```bash
# Install OpenVINO for Intel NPU acceleration
pip install openvino
```

## 📋 Detailed Usage

### Running Individual Analyzers

```bash
# Security analysis
python scripts/analyze_security.py
# Output: Security vulnerabilities with CWE classifications

# Performance analysis
python scripts/analyze_performance.py  
# Output: Memory leaks, blocking calls, database issues

# Code duplication analysis
python scripts/analyze_duplicates.py
# Output: Duplicate code groups with similarity scores
```

### Comprehensive Analysis

```bash
# Full code quality dashboard
python scripts/analyze_code_quality.py
# Output: 
# - Overall quality score (0-100)
# - Issue breakdown by category
# - Technical debt calculations
# - Priority recommendations
```

### Automated Fix Generation

```bash
# Generate fixes for detected issues
python scripts/generate_automated_corrections.py
# Output:
# - Specific code fixes with confidence scores
# - Git-style patches ready to apply
# - Risk assessment for each fix
```

## 📊 Output Examples

### Quality Score Breakdown
```
Overall Quality Score: 87.2/100

Individual Scores:
- Security: 95/100 🟢 EXCELLENT
- Performance: 82/100 🟡 GOOD  
- Architecture: 78/100 🟡 GOOD
- Test Coverage: 65/100 🟠 NEEDS IMPROVEMENT
```

### Issue Prioritization
```
🚨 Critical Issues (5):
1. SQL Injection in auth.py:42
2. Memory leak in file_handler.py:128
3. Hardcoded API key in config.py:15

⚠️ High Priority Issues (12):
1. Blocking call in async function
2. Missing error handling
```

### Automated Fixes
```
✅ 23 fixes can be applied automatically
🔍 8 fixes require manual review

Security Fix Example:
- File: src/database.py:45
- Issue: SQL injection vulnerability
- Fix: Replace string formatting with parameterized query
- Confidence: 95%
- Risk: Low
```

## 🏗️ Architecture

### System Design
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Redis Cache  │    │  Analysis Engine │    │  NPU Processor  │
│   (Results)    │◄───│  (Coordination)  │◄───│  (Optional)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │  Security   │ │ Performance │ │ Architecture│
            │  Analyzer   │ │  Analyzer   │ │   Analyzer  │
            └─────────────┘ └─────────────┘ └─────────────┘
```

### Data Flow
1. **Input**: Source code files (Python focus)
2. **Processing**: Parallel analysis with Redis caching
3. **Analysis**: AST parsing, pattern matching, ML similarity
4. **Output**: Structured reports with actionable insights
5. **Fixes**: Automated patch generation with confidence scoring

## 📈 Integration

### CI/CD Integration
```yaml
# .github/workflows/code-quality.yml
name: Code Quality Analysis
on: [push, pull_request]

jobs:
  quality:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v2
      - name: Run Code Analysis
        run: |
          pip install -r code-analysis-suite/requirements.txt
          python code-analysis-suite/scripts/analyze_code_quality.py
          # Fail if quality score < 80
          if [ $(jq '.overall_quality_score' comprehensive_quality_report.json) -lt 80 ]; then
            exit 1
          fi
```

### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: code-quality-check
        name: Code Quality Check
        entry: python code-analysis-suite/scripts/analyze_code_quality.py --quick
        language: system
        pass_filenames: false
```

## 🔍 Advanced Usage

### Custom Analysis Patterns
```python
# Add custom security patterns
from code_analysis_suite.src.security_analyzer import SecurityAnalyzer

analyzer = SecurityAnalyzer()
analyzer.security_patterns['custom_vulnerability'] = [
    (r'dangerous_function\(.*\)', 'Custom vulnerability pattern', 'CWE-XXX')
]
```

### Batch Processing
```python
# Analyze multiple projects
projects = ['project1/', 'project2/', 'project3/']
for project in projects:
    results = await analyzer.analyze_security(project)
    print(f"{project}: {results['metrics']['security_score']}/100")
```

### API Usage
```python
# Use analyzers programmatically
from code_analysis_suite.src.code_quality_dashboard import CodeQualityDashboard

dashboard = CodeQualityDashboard()
report = await dashboard.generate_comprehensive_report(
    root_path="my_project/",
    patterns=["**/*.py"],
    include_trends=True
)
```

## 🛠️ Extending the Suite

### Adding New Analyzers
1. Create analyzer class inheriting from base patterns
2. Implement analysis methods with Redis caching
3. Add to dashboard integration
4. Create analysis script
5. Update documentation

### Custom Fix Templates
```python
# Add to AutomatedFixGenerator
custom_template = FixTemplate(
    pattern=r'my_pattern',
    replacement=r'my_fix',
    fix_type='my_fix_type',
    description='Custom fix description',
    confidence=0.8,
    risk_level='low'
)
```

## 📚 Documentation

- `docs/ARCHITECTURE.md` - System architecture details
- `docs/API.md` - API reference documentation  
- `docs/EXTENDING.md` - Guide for adding new analyzers
- `docs/TROUBLESHOOTING.md` - Common issues and solutions
- `examples/` - Usage examples and integration patterns

## 🧪 Testing

```bash
# Run analyzer tests
python -m pytest code-analysis-suite/tests/

# Test individual analyzers
python -m pytest code-analysis-suite/tests/test_security_analyzer.py

# Integration tests
python -m pytest code-analysis-suite/tests/test_integration.py
```

## 📊 Performance

- **Redis Caching**: 10x faster repeated analysis
- **Parallel Processing**: All analyzers run concurrently
- **NPU Acceleration**: Optional hardware acceleration for ML operations
- **Memory Efficient**: Streaming analysis for large codebases

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-analyzer`)
3. Add tests for new functionality
4. Run quality checks: `python scripts/analyze_code_quality.py`
5. Submit pull request

## 📜 License

MIT License - see LICENSE file for details

## 🆘 Support

- **Issues**: Report bugs and request features via GitHub issues
- **Documentation**: Check `docs/` directory for detailed guides
- **Examples**: See `examples/` for integration patterns

---

*AutoBot Code Analysis Suite - Making code quality measurable and actionable* 🚀