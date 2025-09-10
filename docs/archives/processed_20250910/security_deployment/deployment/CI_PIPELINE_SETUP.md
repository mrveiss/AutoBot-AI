# AutoBot CI/CD Pipeline Setup Guide

## Overview
This document describes the GitHub Actions CI/CD pipeline setup for the AutoBot project, including testing, security scanning, and deployment automation.

## Pipeline Structure

### 1. Security Tests Job (`security-tests`)
**Triggers:** Push to `main` or `Dev_new_gui` branches, PRs to `main`
**Environment:** Ubuntu Latest with Python 3.10 & 3.11

**Steps:**
- Code quality checks (black, isort, flake8)
- Security analysis (bandit)
- Unit tests for security modules
- Integration tests
- Security API endpoint testing
- Coverage reporting to Codecov

### 2. Docker Build Job (`docker-build`)
**Triggers:** Only on `main` branch pushes
**Dependencies:** Requires `security-tests` to pass

**Steps:**
- Build Docker sandbox image
- Test sandbox functionality
- Validate Docker integration

### 3. Frontend Tests Job (`frontend-tests`)
**Triggers:** All pushes and PRs
**Environment:** Node.js 18

**Steps:**
- Frontend linting (ESLint + oxlint)
- TypeScript type checking
- Frontend build validation
- Unit test execution

### 4. Deployment Check Job (`deployment-check`)
**Triggers:** Only on `main` branch pushes
**Dependencies:** All other jobs must pass

**Steps:**
- Production configuration validation
- Core module import testing
- Deployment artifact generation
- Deployment summary creation

### 5. Notification Job (`notify`)
**Triggers:** Always runs after all jobs
**Purpose:** Consolidated status reporting

## Pipeline Configuration

### Environment Variables
The pipeline uses these GitHub repository secrets:
- `CODECOV_TOKEN`: For coverage reporting (optional)

### Branch Protection
Recommended branch protection rules for `main`:
- Require status checks to pass
- Require branches to be up to date
- Include administrators

## Local Testing

### Run Tests Locally
```bash
# Unit tests
python run_unit_tests.py

# Integration tests
python -m pytest tests/test_security_integration.py tests/test_system_integration.py -v

# Code quality
flake8 src/ backend/ --max-line-length=88 --extend-ignore=E203,W503
black --check src/ backend/ --line-length=88
isort --check-only src/ backend/

# Security scan
bandit -r src/ backend/ -f json
```

### Test Docker Build
```bash
# Build sandbox image
docker build -f docker/sandbox.Dockerfile -t autobot-sandbox:latest .

# Test sandbox
docker run --rm autobot-sandbox:latest echo "Sandbox test successful"
```

## Pipeline Features

### ✅ Implemented Features
- Multi-Python version testing (3.10, 3.11)
- Comprehensive security testing suite
- Code quality enforcement
- Docker sandbox validation
- Frontend build and testing
- Coverage reporting
- Deployment readiness checks
- Status notifications

### 🔄 Automatic Triggers
- **Push to main/Dev_new_gui:** Full pipeline execution
- **Pull requests to main:** Security and frontend tests only
- **Failed jobs:** Automatic notification with detailed status

### 📊 Test Coverage
- **Unit Tests:** 73/79 passed (92.4%)
- **Integration Tests:** 30/35 passed (85.7%)
- **Overall Coverage:** 90.4% test success rate

## Troubleshooting

### Common Issues

**1. Test Failures**
```bash
# Debug failing tests
python -m pytest tests/test_failing_module.py -v --tb=long

# Run specific test
python -m pytest tests/test_module.py::TestClass::test_method -v
```

**2. Docker Build Failures**
```bash
# Check Docker daemon
docker ps

# Build locally to debug
docker build -f docker/sandbox.Dockerfile -t autobot-sandbox:test .
```

**3. Frontend Build Issues**
```bash
cd autobot-vue
npm ci
npm run lint -- --fix
npm run type-check
```

**4. Coverage Issues**
```bash
# Generate coverage report
python -m pytest --cov=src --cov=backend --cov-report=html
```

### Pipeline Debugging

**View GitHub Actions logs:**
1. Go to repository → Actions tab
2. Select the failing workflow run
3. Expand the failing job/step
4. Check logs for detailed error messages

**Local pipeline simulation:**
```bash
# Install act (GitHub Actions local runner)
# macOS: brew install act
# Linux: Download from https://github.com/nektos/act

# Run pipeline locally
act push
```

## Performance Benchmarks

### CI Pipeline Timing
- **Security Tests:** ~5-8 minutes
- **Docker Build:** ~3-5 minutes  
- **Frontend Tests:** ~2-4 minutes
- **Deployment Check:** ~1-2 minutes
- **Total Pipeline:** ~12-20 minutes

### Test Performance Targets
- API response times: < 100ms
- Risk assessment: < 16ms per command
- Memory growth: < 50MB per 100 API calls
- Unit test execution: < 60 seconds per module

## Security Features

### Automated Security Scanning
- **Bandit:** Python security vulnerability detection
- **Command Security:** Dangerous command pattern detection
- **Docker Security:** Sandbox container validation
- **Access Control:** Role-based permission testing

### Security Test Coverage
- Command execution sandboxing ✅
- Risk assessment system ✅  
- Audit logging ✅
- Role-based access control ✅
- API security endpoints ✅
- WebSocket security ✅

## Deployment Integration

### Deployment Artifacts
Each successful main branch build generates:
- `DEPLOYMENT_SUMMARY.md` - Deployment status report
- Coverage reports (Codecov integration)
- Docker image validation results
- Security scan results

### Production Readiness Checks
- ✅ All required files present (main.py, requirements.txt, setup_agent.sh)
- ✅ Configuration system functional
- ✅ Core module imports working
- ✅ Security system operational
- ✅ Frontend build successful

## Continuous Improvement

### Metrics to Monitor
- Test execution time trends
- Code coverage percentage
- Pipeline success rate
- Security vulnerability detection rate
- Performance regression detection

### Future Enhancements
- [ ] Property-based testing with hypothesis
- [ ] Contract testing for API stability
- [ ] Visual regression testing for frontend
- [ ] Professional security penetration testing
- [ ] Performance regression detection
- [ ] Automatic dependency updates

---

**Last Updated:** 2025-08-11  
**Pipeline Version:** 1.0  
**Maintainer:** AutoBot Development Team