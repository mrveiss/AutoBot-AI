#!/usr/bin/env python3
"""
Quick Microservice Analysis for AutoBot
Provides a rapid assessment of microservice decomposition potential
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def quick_microservice_analysis():
    """Run quick microservice architecture analysis"""
    project_root = Path(__file__).parent.parent
    
    logger.info("🚀 Starting quick microservice analysis...")
    
    analysis = {
        "timestamp": datetime.now().isoformat(),
        "codebase_metrics": {},
        "api_analysis": {},
        "agent_analysis": {},
        "service_recommendations": [],
        "migration_assessment": {}
    }
    
    # 1. Quick codebase metrics
    logger.info("📊 Analyzing codebase metrics...")
    
    python_files = list(project_root.rglob("*.py"))
    python_files = [f for f in python_files if not any(exclude in str(f) for exclude in ['__pycache__', '.pyc', 'node_modules', '.git'])]
    
    total_loc = 0
    for py_file in python_files[:200]:  # Limit to first 200 files for speed
        try:
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [line.strip() for line in f.readlines()]
                total_loc += len([line for line in lines if line and not line.startswith('#')])
        except Exception:
            continue
    
    analysis["codebase_metrics"] = {
        "python_files_analyzed": min(200, len(python_files)),
        "total_python_files": len(python_files),
        "estimated_total_loc": int(total_loc * (len(python_files) / min(200, len(python_files)))),
        "microservice_readiness_score": 0
    }
    
    # 2. API Analysis
    logger.info("🌐 Analyzing API structure...")
    
    api_dir = project_root / "backend" / "api"
    api_files = []
    total_endpoints = 0
    
    if api_dir.exists():
        for api_file in api_dir.glob("*.py"):
            if api_file.name == "__init__.py":
                continue
                
            try:
                with open(api_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Count route decorators
                route_pattern = r'@router\.(get|post|put|delete|patch)'
                routes = re.findall(route_pattern, content, re.IGNORECASE)
                endpoint_count = len(routes)
                total_endpoints += endpoint_count
                
                if endpoint_count > 0:
                    api_files.append({
                        "name": api_file.stem,
                        "endpoints": endpoint_count
                    })
            except Exception:
                continue
    
    analysis["api_analysis"] = {
        "api_modules": len(api_files),
        "total_endpoints": total_endpoints,
        "modules": api_files
    }
    
    # 3. Agent Analysis
    logger.info("🤖 Analyzing AI agents...")
    
    agents_dir = project_root / "src" / "agents"
    agent_files = []
    
    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.py"):
            if agent_file.name == "__init__.py":
                continue
                
            try:
                with open(agent_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Count classes
                class_pattern = r'class\s+(\w+)'
                classes = re.findall(class_pattern, content)
                
                # Determine agent type
                name_lower = agent_file.stem.lower()
                agent_type = "general"
                if any(keyword in name_lower for keyword in ["research", "web", "search"]):
                    agent_type = "research"
                elif any(keyword in name_lower for keyword in ["chat", "conversation"]):
                    agent_type = "chat"
                elif any(keyword in name_lower for keyword in ["knowledge", "kb", "memory"]):
                    agent_type = "knowledge"
                elif any(keyword in name_lower for keyword in ["terminal", "command"]):
                    agent_type = "execution"
                elif any(keyword in name_lower for keyword in ["file", "project"]):
                    agent_type = "file_management"
                
                agent_files.append({
                    "name": agent_file.stem,
                    "classes": len(classes),
                    "type": agent_type
                })
            except Exception:
                continue
    
    analysis["agent_analysis"] = {
        "agent_modules": len(agent_files),
        "agents": agent_files
    }
    
    # 4. Service Recommendations
    logger.info("🎯 Generating service recommendations...")
    
    recommendations = []
    
    # API-based services
    for api_module in api_files:
        if api_module["endpoints"] >= 3:
            recommendations.append({
                "name": f"{api_module['name'].title()}Service",
                "type": "api_service",
                "rationale": f"Has {api_module['endpoints']} endpoints - sufficient for independent service",
                "complexity": "medium",
                "priority": "high" if api_module["endpoints"] >= 5 else "medium"
            })
    
    # Agent-based services
    agent_types = {}
    for agent in agent_files:
        agent_type = agent["type"]
        if agent_type not in agent_types:
            agent_types[agent_type] = []
        agent_types[agent_type].append(agent["name"])
    
    for agent_type, agents in agent_types.items():
        if len(agents) >= 2 or agent_type in ["research", "chat", "knowledge"]:
            recommendations.append({
                "name": f"{agent_type.title()}AgentService",
                "type": "agent_service",
                "rationale": f"Contains {len(agents)} {agent_type} agents - specialized compute requirements",
                "complexity": "high",
                "priority": "medium"
            })
    
    # Shared services
    shared_services = [
        {"name": "ConfigurationService", "rationale": "Centralized configuration management"},
        {"name": "CachingService", "rationale": "Redis-based caching for all services"},
        {"name": "DatabaseService", "rationale": "SQLite/data access abstraction"},
        {"name": "LoggingService", "rationale": "Centralized logging and monitoring"}
    ]
    
    for service in shared_services:
        recommendations.append({
            "name": service["name"],
            "type": "shared_service", 
            "rationale": service["rationale"],
            "complexity": "low",
            "priority": "high"
        })
    
    analysis["service_recommendations"] = recommendations
    
    # 5. Migration Assessment
    logger.info("🗺️ Assessing migration feasibility...")
    
    # Calculate readiness score
    readiness_score = 0
    
    # +2 for sufficient API endpoints
    if total_endpoints >= 10:
        readiness_score += 2
    elif total_endpoints >= 5:
        readiness_score += 1
    
    # +2 for multiple agents
    if len(agent_files) >= 5:
        readiness_score += 2
    elif len(agent_files) >= 3:
        readiness_score += 1
    
    # +2 for large codebase
    estimated_loc = analysis["codebase_metrics"]["estimated_total_loc"]
    if estimated_loc >= 50000:
        readiness_score += 2
    elif estimated_loc >= 20000:
        readiness_score += 1
    
    # +2 for organized structure
    if len(api_files) >= 5 and len(agent_files) >= 3:
        readiness_score += 2
    
    # +2 for existing containerization
    if (project_root / "docker").exists():
        readiness_score += 2
    
    analysis["codebase_metrics"]["microservice_readiness_score"] = min(10, readiness_score)
    
    # Migration phases
    phases = []
    
    # Phase 1: Shared Services (4-6 weeks)
    shared_recs = [r for r in recommendations if r["type"] == "shared_service"]
    if shared_recs:
        phases.append({
            "phase": 1,
            "name": "Foundation Services",
            "services": [r["name"] for r in shared_recs],
            "duration_weeks": 5,
            "rationale": "Establish shared infrastructure first"
        })
    
    # Phase 2: Agent Services (6-10 weeks)
    agent_recs = [r for r in recommendations if r["type"] == "agent_service"]
    if agent_recs:
        phases.append({
            "phase": 2,
            "name": "AI Agent Services",
            "services": [r["name"] for r in agent_recs],
            "duration_weeks": 8,
            "rationale": "Extract compute-heavy AI services"
        })
    
    # Phase 3: API Services (8-12 weeks)
    api_recs = [r for r in recommendations if r["type"] == "api_service"]
    if api_recs:
        phases.append({
            "phase": 3,
            "name": "Business Logic Services",
            "services": [r["name"] for r in api_recs],
            "duration_weeks": 10,
            "rationale": "Split business logic by domain"
        })
    
    analysis["migration_assessment"] = {
        "readiness_score": readiness_score,
        "readiness_level": "high" if readiness_score >= 7 else "medium" if readiness_score >= 4 else "low",
        "total_services": len(recommendations),
        "migration_phases": phases,
        "estimated_total_duration_weeks": sum(phase["duration_weeks"] for phase in phases),
        "recommendation": _get_migration_recommendation(readiness_score, len(recommendations))
    }
    
    # Save report
    reports_dir = project_root / "reports" / "architecture"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save JSON
    json_file = reports_dir / f"quick_microservice_analysis_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    # Save Markdown
    md_file = reports_dir / f"microservice_analysis_summary_{timestamp}.md"
    with open(md_file, 'w') as f:
        f.write(_generate_markdown_report(analysis))
    
    # Print summary
    _print_summary(analysis)
    
    logger.info(f"📄 Reports saved:")
    logger.info(f"  JSON: {json_file}")
    logger.info(f"  Markdown: {md_file}")
    
    return analysis


def _get_migration_recommendation(score, service_count):
    """Get migration recommendation based on analysis"""
    if score >= 7 and service_count >= 8:
        return "RECOMMENDED: Strong candidate for microservice architecture"
    elif score >= 4 and service_count >= 5:
        return "CONSIDER: Good potential with some preparation needed"
    elif score >= 2:
        return "EVALUATE: Limited benefits, consider modular monolith first"
    else:
        return "NOT RECOMMENDED: Stick with current monolithic architecture"


def _print_summary(analysis):
    """Print analysis summary"""
    metrics = analysis["codebase_metrics"]
    api = analysis["api_analysis"]
    agents = analysis["agent_analysis"]
    migration = analysis["migration_assessment"]
    
    print("\n" + "=" * 70)
    print("🏗️ QUICK MICROSERVICE ANALYSIS SUMMARY")
    print("=" * 70)
    
    print(f"📊 CODEBASE METRICS:")
    print(f"  • Estimated Total LOC: {metrics['estimated_total_loc']:,}")
    print(f"  • Python Files: {metrics['total_python_files']:,}")
    print(f"  • Readiness Score: {metrics['microservice_readiness_score']}/10")
    
    print(f"\n🌐 API STRUCTURE:")
    print(f"  • API Modules: {api['api_modules']}")
    print(f"  • Total Endpoints: {api['total_endpoints']}")
    if api['modules']:
        for module in api['modules'][:3]:
            print(f"    - {module['name']}: {module['endpoints']} endpoints")
    
    print(f"\n🤖 AI AGENTS:")
    print(f"  • Agent Modules: {agents['agent_modules']}")
    agent_types = {}
    for agent in agents['agents']:
        agent_type = agent['type']
        agent_types[agent_type] = agent_types.get(agent_type, 0) + 1
    
    for agent_type, count in agent_types.items():
        print(f"    - {agent_type.title()}: {count} agents")
    
    print(f"\n🎯 SERVICE RECOMMENDATIONS:")
    print(f"  • Total Recommended Services: {migration['total_services']}")
    print(f"  • Migration Phases: {len(migration['migration_phases'])}")
    print(f"  • Estimated Duration: {migration['estimated_total_duration_weeks']} weeks")
    
    print(f"\n⚡ ASSESSMENT:")
    print(f"  • Readiness Level: {migration['readiness_level'].upper()}")
    print(f"  • Recommendation: {migration['recommendation']}")
    
    print("=" * 70)


def _generate_markdown_report(analysis):
    """Generate markdown report"""
    metrics = analysis["codebase_metrics"]
    api = analysis["api_analysis"]
    agents = analysis["agent_analysis"]
    recommendations = analysis["service_recommendations"]
    migration = analysis["migration_assessment"]
    
    report = f"""# 🏗️ AutoBot Microservice Architecture Analysis

**Analysis Date:** {analysis["timestamp"]}

## 📊 Executive Summary

AutoBot shows **{migration["readiness_level"].upper()}** readiness for microservice architecture migration.

- **Readiness Score:** {metrics["microservice_readiness_score"]}/10
- **Recommended Services:** {migration["total_services"]}
- **Migration Duration:** {migration["estimated_total_duration_weeks"]} weeks
- **Recommendation:** {migration["recommendation"]}

## 🔍 Codebase Analysis

### Metrics
- **Estimated Total Lines of Code:** {metrics["estimated_total_loc"]:,}
- **Python Files:** {metrics["total_python_files"]:,}
- **Files Analyzed:** {metrics["python_files_analyzed"]}

### Architecture Assessment
- **Microservice Readiness:** {metrics["microservice_readiness_score"]}/10
- **Overall Size:** {"Large" if metrics["estimated_total_loc"] >= 50000 else "Medium" if metrics["estimated_total_loc"] >= 20000 else "Small"}

## 🌐 API Structure Analysis

- **API Modules:** {api["api_modules"]}
- **Total Endpoints:** {api["total_endpoints"]}

### API Modules by Size
"""
    
    for module in sorted(api["modules"], key=lambda x: x["endpoints"], reverse=True):
        report += f"- **{module['name']}:** {module['endpoints']} endpoints\n"
    
    report += f"""
## 🤖 AI Agent Analysis

- **Agent Modules:** {agents["agent_modules"]}

### Agents by Type
"""
    
    agent_types = {}
    for agent in agents["agents"]:
        agent_type = agent["type"]
        if agent_type not in agent_types:
            agent_types[agent_type] = []
        agent_types[agent_type].append(agent["name"])
    
    for agent_type, agent_names in agent_types.items():
        report += f"- **{agent_type.title()} ({len(agent_names)}):** {', '.join(agent_names)}\n"
    
    report += """
## 🎯 Recommended Service Architecture

### Proposed Services
"""
    
    service_types = {"api_service": [], "agent_service": [], "shared_service": []}
    for rec in recommendations:
        service_types[rec["type"]].append(rec)
    
    for service_type, services in service_types.items():
        if services:
            type_name = service_type.replace("_", " ").title()
            report += f"\n#### {type_name}s\n"
            for service in services:
                report += f"- **{service['name']}**\n"
                report += f"  - *Priority:* {service['priority'].title()}\n"
                report += f"  - *Complexity:* {service['complexity'].title()}\n"
                report += f"  - *Rationale:* {service['rationale']}\n\n"
    
    report += """
## 🗺️ Migration Strategy

### Recommended Phases
"""
    
    for phase in migration["migration_phases"]:
        report += f"""
#### Phase {phase["phase"]}: {phase["name"]}
- **Duration:** {phase["duration_weeks"]} weeks
- **Services:** {len(phase["services"])}
  - {', '.join(phase["services"])}
- **Rationale:** {phase["rationale"]}
"""
    
    report += f"""
### Migration Timeline
- **Total Duration:** {migration["estimated_total_duration_weeks"]} weeks (~{migration["estimated_total_duration_weeks"]//4} months)
- **Parallel Development:** Possible for some phases
- **Rollback Strategy:** Maintain monolith during transition

## 📋 Key Recommendations

### Immediate Actions (Next 2-4 weeks)
1. **Containerize Current Application** - Set up Docker containers
2. **Implement API Documentation** - Document all endpoints
3. **Set Up Monitoring** - Add comprehensive logging and metrics
4. **Create Service Boundaries** - Define clear interfaces

### Short-term Goals (1-3 months)
1. **Extract Shared Services** - Start with configuration, caching, logging
2. **Set Up Service Discovery** - Implement service registry
3. **Implement API Gateway** - Central routing and authentication
4. **Database Abstraction** - Create data access layer

### Long-term Goals (3-12 months)
1. **Migrate AI Agents** - Extract compute-intensive services
2. **Split API Services** - Decompose by business domain
3. **Optimize Performance** - Fine-tune service interactions
4. **Implement Advanced Patterns** - Circuit breakers, saga patterns

## ⚠️ Risks and Considerations

### Technical Risks
- **Distributed System Complexity** - Network failures, latency
- **Data Consistency** - Managing transactions across services
- **Service Discovery** - Dynamic service registration and discovery
- **Monitoring Complexity** - Distributed tracing and debugging

### Organizational Risks
- **Team Coordination** - Multiple service ownership
- **Deployment Complexity** - CI/CD for multiple services
- **Knowledge Distribution** - Understanding system architecture

### Mitigation Strategies
- Start with shared services to build expertise
- Implement comprehensive monitoring from day one
- Maintain monolith as fallback during migration
- Gradual migration with feature flags

## 🎯 Next Steps

Based on the **{migration["readiness_level"].upper()}** readiness assessment:

"""
    
    if migration["readiness_level"] == "high":
        report += """✅ **PROCEED WITH MIGRATION**
1. Begin Phase 1 (Foundation Services) immediately
2. Set up microservice infrastructure
3. Start team training on distributed systems
"""
    elif migration["readiness_level"] == "medium":
        report += """🟡 **PREPARE THEN MIGRATE**
1. Improve code organization and documentation
2. Set up monitoring and containerization
3. Create clear service boundaries
4. Begin with pilot service extraction
"""
    else:
        report += """🔴 **IMPROVE BEFORE MIGRATING**
1. Focus on modular monolith architecture
2. Improve code organization and separation of concerns
3. Implement better testing and monitoring
4. Revisit microservices in 6-12 months
"""
    
    report += """
---
**Generated by AutoBot Quick Microservice Analyzer**
"""
    
    return report


if __name__ == "__main__":
    quick_microservice_analysis()