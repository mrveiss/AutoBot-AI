# 📊 Codebase Analytics System

> **Revolutionary Redis-based code analysis with NPU acceleration**
> 
> Analyze declaration usage, detect duplicates, and discover refactoring opportunities across your entire codebase using AI-powered semantic search.

## 🌟 Overview

The AutoBot Codebase Analytics System is a comprehensive code analysis platform that provides deep insights into your codebase structure, usage patterns, and refactoring opportunities. Built on Redis for high-performance indexing and featuring NPU acceleration for semantic search, it offers unprecedented visibility into code health and reusability.

## 🚀 Key Features

### **📈 Declaration Usage Analysis**
- **Function Analysis**: Track usage patterns of all functions across your codebase
- **Class Analysis**: Monitor class inheritance and instantiation patterns  
- **Variable Analysis**: Identify variable usage and scope patterns
- **Import Analysis**: Analyze dependency patterns and unused imports
- **Reusability Scoring**: AI-powered scoring of code reusability potential

### **🔍 Duplicate Detection**
- **Semantic Search**: Find similar code blocks using NPU-accelerated AI
- **Pattern Recognition**: Identify common patterns that could be refactored
- **Refactoring Opportunities**: Prioritized suggestions for code consolidation
- **Code Similarity**: Advanced similarity detection beyond exact matches

### **🧠 Intelligent Suggestions**
- **Extract Utility Functions**: Identify functions with high reuse potential
- **Create Base Classes**: Suggest inheritance opportunities  
- **Standardize Error Handling**: Find inconsistent error patterns
- **Configuration Centralization**: Identify scattered configuration code

### **⚡ Performance & Scale**
- **NPU Acceleration**: Intel OpenVINO optimization for large codebases
- **Redis Caching**: High-performance indexing for instant results
- **Multi-Language Support**: Python, JavaScript, TypeScript, Java, C++, and 15+ more
- **Incremental Analysis**: Smart caching for updated code analysis

## 🛠️ API Endpoints

### **Index Management**
```http
POST /api/code_search/index
```
Index a codebase for analysis with Redis-based caching.

**Request Body:**
```json
{
  "root_path": "/path/to/your/project",
  "force_reindex": false,
  "include_patterns": ["*.py", "*.js", "*.ts"],
  "exclude_patterns": ["*.pyc", "*.git*", "*__pycache__*"]
}
```

### **Declaration Analysis**
```http
POST /api/code_search/analytics/declarations
```
Analyze function, class, variable, and import usage across the codebase.

**Response Structure:**
```json
{
  "summary": {
    "total_declarations": 1847,
    "most_reused_declaration": "authenticate",
    "max_usage_count": 156,
    "analysis_root": "/path/to/project"
  },
  "declarations_by_type": {
    "functions": [...],
    "classes": [...],
    "variables": [...],
    "imports": [...]
  },
  "reusability_insights": {
    "highly_reusable": [...],
    "underutilized": [...],
    "potential_duplicates": [...]
  }
}
```

### **Duplicate Detection**
```http
POST /api/code_search/analytics/duplicates
```
Find potential code duplicates using semantic search.

**Response Structure:**
```json
{
  "summary": {
    "patterns_analyzed": 10,
    "duplicate_candidates_found": 5,
    "total_similar_blocks": 23,
    "highest_priority_pattern": "error handling"
  },
  "duplicate_candidates": [
    {
      "pattern": "error handling",
      "similar_blocks": [...],
      "potential_savings": "Could refactor 8 similar blocks",
      "refactor_priority": 7.2
    }
  ],
  "recommendations": [...]
}
```

### **Codebase Statistics**
```http
GET /api/code_search/analytics/stats
```
Get comprehensive codebase statistics from Redis index.

### **Refactoring Suggestions**
```http
POST /api/code_search/analytics/refactor-suggestions
```
Generate intelligent refactoring suggestions based on analysis.

## 🖥️ Frontend Interface

### **Access the Analytics Dashboard**
1. Navigate to **Tools → Codebase Analytics** in the AutoBot web interface
2. Enter your project root path (auto-detects `/home/kali/Desktop/AutoBot`)
3. Click **Index Codebase** to build the analysis cache
4. Click **Analyze All** to run comprehensive analysis

### **Analytics Dashboard Features**

#### **📊 Index Status Card**
- Files indexed count
- NPU acceleration availability
- Redis cache efficiency
- Language distribution

#### **🌐 Language Distribution Chart**
- Visual breakdown by programming language
- Interactive bar charts with file counts
- Support for 20+ programming languages

#### **📋 Analysis Results Tabs**

**1. Declarations Tab**
- Declaration usage statistics by type (functions, classes, variables, imports)
- Reusability scoring with color-coded indicators
- Usage count vs definition count analysis
- Top reusable components identification

**2. Duplicates Tab**  
- Similar code block detection
- Refactoring priority scoring
- File location and confidence matching
- Potential savings estimation

**3. Suggestions Tab**
- Intelligent refactoring recommendations
- Priority-based suggestions (High/Medium/Low)
- Impact and effort estimations
- Next steps guidance

## 💡 Usage Examples

### **Analyze a Python Project**
```bash
curl -X POST "http://localhost:8001/api/code_search/index" \
  -H "Content-Type: application/json" \
  -d '{
    "root_path": "/path/to/python/project",
    "include_patterns": ["*.py"],
    "exclude_patterns": ["*.pyc", "*__pycache__*", "*.git*"]
  }'

curl -X POST "http://localhost:8001/api/code_search/analytics/declarations" \
  -H "Content-Type: application/json" \
  -d '{"root_path": "/path/to/python/project"}'
```

### **Analyze a JavaScript Project**
```bash
curl -X POST "http://localhost:8001/api/code_search/index" \
  -H "Content-Type: application/json" \
  -d '{
    "root_path": "/path/to/js/project",
    "include_patterns": ["*.js", "*.ts", "*.jsx", "*.tsx"],
    "exclude_patterns": ["node_modules/*", "*.min.js", "dist/*"]
  }'
```

## 🔧 Configuration

### **NPU Acceleration Setup**
NPU acceleration is automatically detected when Intel OpenVINO is available:

```python
# Check NPU availability
capabilities = worker_node.detect_capabilities()
npu_available = capabilities.get("openvino_npu_available", False)
```

### **Redis Configuration**
Analytics uses the main Redis instance with dedicated prefixes:

```python
# Cache configuration
index_prefix = "autobot:code:index:"
search_cache_prefix = "autobot:search:cache:"
cache_ttl = 3600  # 1 hour cache
```

### **Language Support**
Currently supported languages and file extensions:

- **Python**: `.py`
- **JavaScript/TypeScript**: `.js`, `.ts`, `.jsx`, `.tsx`
- **Java**: `.java`
- **C/C++**: `.c`, `.cpp`, `.h`
- **C#**: `.cs`
- **Ruby**: `.rb`
- **Go**: `.go`
- **Rust**: `.rs`
- **PHP**: `.php`
- **Swift**: `.swift`
- **Kotlin**: `.kt`
- **Scala**: `.scala`
- **Shell**: `.sh`, `.bash`, `.zsh`
- **Configuration**: `.yaml`, `.yml`, `.json`, `.xml`
- **Web**: `.html`, `.css`, `.scss`
- **Database**: `.sql`
- **Documentation**: `.md`

## 📈 Performance Optimization

### **Caching Strategy**
- **Redis Indexing**: Persistent code element caching
- **Search Results**: 1-hour TTL for repeated queries
- **Incremental Updates**: Smart re-indexing of changed files
- **Memory Management**: Automatic cache cleanup and size limits

### **NPU Acceleration**
- **Semantic Search**: Hardware-accelerated similarity detection
- **Large Codebases**: Recommended for projects >1000 files
- **Fallback Mode**: CPU-based processing when NPU unavailable

### **Recommendations**
- **Large Codebases (>1000 files)**: Enable NPU acceleration
- **Very Large Codebases (>5000 files)**: Consider incremental indexing
- **Multi-Language Projects**: Use language filters for targeted analysis

## 🧪 Testing

### **Basic Functionality Test**
```bash
# Test the AutoBot project itself
cd /home/kali/Desktop/AutoBot
curl -X POST "http://localhost:8001/api/code_search/index" \
  -H "Content-Type: application/json" \
  -d '{"root_path": "/home/kali/Desktop/AutoBot"}'

# Analyze declarations
curl -X POST "http://localhost:8001/api/code_search/analytics/declarations" \
  -H "Content-Type: application/json" \
  -d '{"root_path": "/home/kali/Desktop/AutoBot"}'
```

### **Performance Benchmarks**
- **Small Project (<100 files)**: ~5 seconds indexing, <1 second analysis
- **Medium Project (100-1000 files)**: ~30 seconds indexing, ~5 seconds analysis  
- **Large Project (1000+ files)**: ~2 minutes indexing, ~15 seconds analysis (with NPU)

## 🔧 Troubleshooting

### **Common Issues**

**1. Index Not Found Error**
```bash
# Solution: Index the codebase first
curl -X POST "http://localhost:8001/api/code_search/index" \
  -H "Content-Type: application/json" \
  -d '{"root_path": "/your/project/path"}'
```

**2. NPU Not Available**
- Check Intel OpenVINO installation
- Verify hardware NPU support
- System falls back to CPU automatically

**3. Redis Connection Issues**
- Verify Redis Stack is running: `docker ps | grep autobot-redis`
- Check Redis connectivity: `redis-cli ping`

**4. Large File Processing**
- Increase timeout limits for very large codebases
- Use incremental indexing for >10,000 files
- Consider excluding build/dist directories

### **Debug Mode**
Enable detailed logging in the codebase analytics:

```bash
# Check logs
docker logs autobot-backend | grep "code_search"
docker logs autobot-redis | grep "index"
```

## 🚀 Future Enhancements

### **Planned Features**
- **Code Quality Metrics**: Cyclomatic complexity analysis
- **Dependency Graphs**: Visual dependency mapping
- **Security Analysis**: Vulnerability pattern detection
- **Performance Hotspots**: Computational complexity analysis
- **Architecture Insights**: Microservice boundary recommendations
- **Technical Debt Scoring**: Automated technical debt assessment

### **Integration Roadmap**
- **IDE Plugins**: VS Code/IntelliJ integration
- **CI/CD Integration**: Automated analysis in build pipelines
- **Git Hooks**: Pre-commit analysis and suggestions
- **Slack/Teams**: Automated reports and notifications

## 📚 Related Documentation

- **[NPU Code Search Agent](../agents/development/npu_code_search_agent.md)** - Technical implementation details
- **[API Documentation](../api/comprehensive_api_documentation.md)** - Complete API reference
- **[Redis Configuration](../configuration/)** - Redis setup and optimization
- **[Performance Optimization](../features/SYSTEM_OPTIMIZATION_REPORT.md)** - System performance tuning

## 💬 Support

For technical support or feature requests related to codebase analytics:

1. **GitHub Issues**: Report bugs or request features
2. **Documentation**: Check troubleshooting guides
3. **Logs**: Provide relevant log output from backend/Redis
4. **Configuration**: Share your project structure and file counts

---

**🎯 Pro Tip**: Start with a small project to familiarize yourself with the analytics interface, then scale up to larger codebases. The system is designed to handle everything from small scripts to enterprise applications with millions of lines of code.