# AutoBot Optimization Deployment Guide

## 🚀 Overview

This guide covers the deployment of the enhanced AutoBot system with four major optimization components:

1. **Redis Caching Layer** - Intelligent query caching with LRU eviction
2. **Hybrid Search** - Semantic + keyword matching for improved relevance  
3. **Real-time Monitoring** - Comprehensive system metrics and alerting
4. **Model Optimization** - Intelligent LLM model selection and performance tracking

## 📋 Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 20.04+ recommended) or WSL2
- **Memory**: 16GB+ RAM (32GB recommended for optimal performance)
- **Storage**: 100GB+ free space
- **Network**: Stable internet connection for model downloads

### Software Dependencies
- Python 3.9+
- Redis 7.0+
- Docker & Docker Compose
- Ollama with desired LLM models
- Node.js 18+ (for frontend)

### Hardware Recommendations
- **CPU**: Intel Core i7/i9 or AMD Ryzen 7/9 (16+ cores recommended)
- **GPU**: NVIDIA RTX 3070+ with 8GB+ VRAM (optional but recommended)
- **NPU**: Intel Ultra series for AI acceleration (if available)

## 🔧 Pre-Deployment Checklist

### 1. Verify Base System
```bash
# Check AutoBot base system
bash run_autobot.sh --dev --no-build

# Verify services
curl http://localhost:8001/api/health
curl http://localhost:5173  # Frontend
```

### 2. Verify Dependencies
```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Check Redis
redis-cli ping

# Check Python packages
pip list | grep -E "(aiohttp|psutil|redis)"
```

### 3. Configuration Validation
```bash
# Validate configuration
python scripts/validate-env-files.py

# Test configuration loading
python -c "from src.config_helper import cfg; print('Config loaded:', cfg.get('redis.host'))"
```

## 📦 Deployment Steps

### Phase 1: Configuration Setup

#### 1.1 Update Configuration Files
The optimizations use the centralized configuration in `config/complete.yaml`. Key sections:

```yaml
# Knowledge Base Cache Configuration
knowledge_base:
  cache:
    enabled: true
    ttl: 300
    max_size: 1000
    prefix: "kb_cache:"

# Hybrid Search Configuration  
search:
  hybrid:
    enabled: true
    semantic_weight: 0.7
    keyword_weight: 0.3
    min_keyword_score: 0.1

# Monitoring Configuration
monitoring:
  metrics:
    collection_interval: 5
    retention_hours: 24
    buffer_size: 1000

# LLM Optimization Configuration
llm:
  optimization:
    performance_threshold: 0.8
    auto_selection: true
    cache_ttl: 3600
```

#### 1.2 Redis Database Configuration
Ensure Redis databases are properly configured:

```bash
# Check database configuration
cat config/redis-databases.yaml
```

Expected databases:
- DB 0: Main application data
- DB 1: Knowledge base metadata  
- DB 2: Cache data
- DB 4: System metrics
- DB 5: LLM optimization data

### Phase 2: Service Deployment

#### 2.1 Stop Existing Services
```bash
# Stop current AutoBot instance
docker compose down

# Clear any cached data (optional)
docker system prune -f
```

#### 2.2 Deploy with Optimizations
```bash
# Deploy with optimizations enabled
bash run_autobot.sh --dev --build

# Wait for services to start (2-3 minutes)
sleep 180

# Verify all services
bash scripts/utilities/check-time-sync.sh
```

#### 2.3 Initialize Optimization Systems
```bash
# Run initialization tests
python test_knowledge_cache.py
python test_hybrid_search.py  
python test_monitoring_system.py
python test_model_optimization.py
```

### Phase 3: Integration Verification

#### 3.1 Run Integrated Tests
```bash
# Comprehensive integration test
python test_integrated_optimizations.py
```

Expected output:
- ✅ Knowledge Base Integration: PASSED
- ✅ Model Optimization Integration: PASSED  
- ✅ Monitoring System Integration: PASSED
- ✅ API Integration: PASSED
- ✅ Performance Benchmarks: PASSED

#### 3.2 API Endpoint Verification
Test key endpoints:

```bash
# Knowledge base with caching
curl -X POST http://localhost:8001/api/knowledge_base/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "top_k": 5}'

# Hybrid search
curl -X POST http://localhost:8001/api/knowledge_base/search/hybrid \
  -H "Content-Type: application/json" \
  -d '{"query": "Python programming", "top_k": 5}'

# Model optimization
curl -X POST http://localhost:8001/api/llm_optimization/models/select \
  -H "Content-Type: application/json" \
  -d '{"query": "Write a web scraper", "task_type": "code"}'

# System monitoring
curl http://localhost:8001/api/monitoring/dashboard/overview
```

### Phase 4: Performance Tuning

#### 4.1 Cache Optimization
Monitor and adjust cache settings:

```bash
# Check cache performance
curl http://localhost:8001/api/knowledge_base/cache/stats

# Clear cache if needed
curl -X POST http://localhost:8001/api/knowledge_base/cache/clear
```

#### 4.2 Model Optimization Tuning
```bash
# Check available models
curl http://localhost:8001/api/llm_optimization/models/available

# Get optimization suggestions  
curl http://localhost:8001/api/llm_optimization/optimization/suggestions
```

#### 4.3 Monitoring Setup
```bash
# Start metrics collection
curl -X POST http://localhost:8001/api/monitoring/metrics/collection/start

# Check collection status
curl http://localhost:8001/api/monitoring/metrics/collection/status
```

## 📊 Performance Monitoring

### Key Metrics to Monitor

#### 1. Cache Performance
- **Hit Rate**: Target >70%
- **Response Time**: <100ms for cached queries
- **Memory Usage**: Monitor cache size growth

```bash
# Monitor cache stats
watch -n 5 "curl -s http://localhost:8001/api/knowledge_base/cache/stats | jq '.cache_utilization'"
```

#### 2. Search Performance  
- **Hybrid vs Semantic**: Compare result quality
- **Response Times**: Target <2s for complex queries
- **Result Relevance**: Monitor user feedback

#### 3. Model Optimization
- **Selection Accuracy**: Monitor task-model matching
- **Performance Tracking**: Response times by model
- **Resource Utilization**: CPU/Memory usage per model

#### 4. System Health
- **Overall Health Score**: Target >80%
- **Service Availability**: All services online
- **Resource Usage**: CPU <80%, Memory <90%

### Alerting Setup

Configure alerts for:
- Cache hit rate below 50%
- Search response time >5s  
- Model selection failures
- System health score <60%
- High resource utilization

## 🔍 Troubleshooting

### Common Issues

#### 1. Cache Not Working
**Symptoms**: No performance improvement, cache stats show 0 entries
**Solutions**:
```bash
# Check Redis connection
redis-cli -h 172.16.168.23 ping

# Verify cache configuration
python -c "from src.config_helper import cfg; print(cfg.get('knowledge_base.cache.enabled'))"

# Clear and restart cache
curl -X POST http://localhost:8001/api/knowledge_base/cache/clear
```

#### 2. Hybrid Search Errors
**Symptoms**: Fallback to semantic-only search
**Solutions**:
```bash
# Check hybrid search config
curl http://localhost:8001/api/knowledge_base/search/config

# Test hybrid search directly
python -c "
from src.utils.hybrid_search import get_hybrid_search_engine
from src.knowledge_base import KnowledgeBase
import asyncio
async def test():
    kb = KnowledgeBase()
    await kb.ainit()
    engine = get_hybrid_search_engine(kb)
    results = await engine.search('test query', 5)
    print(f'Results: {len(results)}')
asyncio.run(test())
"
```

#### 3. Model Optimization Issues
**Symptoms**: Always selects same model, no performance tracking
**Solutions**:
```bash
# Refresh model list
curl http://localhost:8001/api/llm_optimization/models/available

# Check Ollama connection
curl http://localhost:11434/api/tags

# Reset model performance data
redis-cli -h 172.16.168.23 -n 5 FLUSHDB
```

#### 4. Monitoring Not Collecting
**Symptoms**: No recent metrics, empty dashboard
**Solutions**:
```bash
# Start collection manually
curl -X POST http://localhost:8001/api/monitoring/metrics/collection/start

# Check collector status
python -c "
from src.utils.system_metrics import get_metrics_collector
import asyncio
async def test():
    collector = get_metrics_collector()
    metrics = await collector.collect_all_metrics()
    print(f'Collected: {len(metrics)} metrics')
asyncio.run(test())
"
```

### Performance Issues

#### 1. Slow Cache Performance
- Check Redis memory usage: `redis-cli info memory`
- Reduce cache TTL or max size
- Consider Redis clustering for large datasets

#### 2. Poor Hybrid Search Results
- Adjust semantic/keyword weights in config
- Add domain-specific stop words  
- Tune keyword scoring parameters

#### 3. Suboptimal Model Selection
- Add more performance samples for models
- Adjust complexity classification rules
- Monitor resource constraints

## 🔧 Maintenance

### Daily Maintenance
```bash
# Check system health
curl http://localhost:8001/api/monitoring/dashboard/overview

# Monitor cache performance
curl http://localhost:8001/api/knowledge_base/cache/stats

# Review optimization suggestions
curl http://localhost:8001/api/llm_optimization/optimization/suggestions
```

### Weekly Maintenance  
```bash
# Clear old cache entries
curl -X POST http://localhost:8001/api/knowledge_base/cache/clear

# Review model performance
curl http://localhost:8001/api/llm_optimization/models/comparison

# Check system alerts
curl http://localhost:8001/api/monitoring/alerts/check
```

### Monthly Maintenance
```bash
# Full system optimization review
python test_integrated_optimizations.py

# Update model classifications if needed
# Review and adjust configuration parameters
# Performance baseline comparison
```

## 📈 Scaling Considerations

### Horizontal Scaling
- **Cache**: Redis clustering for distributed caching
- **Search**: Multiple knowledge base instances
- **Models**: Load balancing across multiple Ollama instances
- **Monitoring**: Separate metrics collection per service

### Vertical Scaling
- **Memory**: Increase for larger caches and model contexts
- **CPU**: More cores for parallel processing  
- **Storage**: SSD for faster cache and metrics storage
- **GPU**: Multiple GPUs for concurrent model serving

### Performance Optimization
- **Cache Warming**: Pre-populate frequently accessed queries
- **Model Preloading**: Keep hot models in memory
- **Connection Pooling**: Optimize database connections
- **Async Processing**: Maximize concurrent operations

## 🚀 Production Deployment

### Final Checklist
- [ ] All integration tests pass
- [ ] Performance benchmarks meet targets
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery procedures tested
- [ ] Documentation updated
- [ ] Team training completed

### Go-Live Steps
1. **Final System Validation**: Run complete test suite
2. **Performance Baseline**: Establish baseline metrics
3. **Gradual Traffic Increase**: Monitor during ramp-up
4. **24-Hour Monitoring**: Watch for issues first day
5. **Optimization Review**: Fine-tune based on real usage

### Success Criteria
- **Availability**: >99.5% uptime
- **Performance**: <2s average response time
- **Cache Efficiency**: >70% hit rate
- **Model Selection**: >85% appropriate matches
- **User Satisfaction**: Improved response quality

---

## 📞 Support

For issues with the optimization deployment:

1. **Check logs**: `docker compose logs -f backend`
2. **Run diagnostics**: `python test_integrated_optimizations.py`
3. **Review configuration**: Verify `config/complete.yaml` settings
4. **Performance analysis**: Use monitoring dashboard insights

**Remember**: The optimization systems are designed to fail gracefully - if any component has issues, the system will fall back to standard operation while logging the problems for resolution.

---

🎉 **Congratulations!** You now have a fully optimized AutoBot system with intelligent caching, enhanced search capabilities, comprehensive monitoring, and smart model selection!