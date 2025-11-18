#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Microservice Architecture Evaluator for AutoBot
Analyzes the current monolithic structure and provides recommendations for microservice decomposition
"""

import ast
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class MicroserviceArchitectureEvaluator:
    """Evaluates current monolithic architecture for microservice decomposition opportunities"""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path(__file__).parent.parent
        self.reports_dir = self.project_root / "reports" / "architecture"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        self.analysis_results = {
            "timestamp": datetime.now().isoformat(),
            "project_structure": {},
            "dependency_analysis": {},
            "service_boundaries": {},
            "migration_strategy": {},
            "recommendations": []
        }

    def analyze_project_structure(self) -> Dict[str, Any]:
        """Analyze the current project structure and components"""
        logger.info("🏗️  Analyzing project structure...")
        
        structure = {
            "directories": {},
            "key_components": {},
            "file_statistics": {},
            "architecture_patterns": {}
        }
        
        # Analyze directory structure (focus on key directories)
        key_directories = [
            "src/", "backend/", "autobot-vue/", 
            "scripts/", "config/"
        ]
        
        for directory in key_directories:
            dir_path = self.project_root / directory
            if dir_path.exists():
                structure["directories"][directory] = self._analyze_directory(dir_path)
        
        # Identify key components
        structure["key_components"] = self._identify_key_components()
        
        # File statistics
        structure["file_statistics"] = self._get_file_statistics()
        
        # Architecture patterns
        structure["architecture_patterns"] = self._identify_architecture_patterns()
        
        logger.info(f"📊 Analyzed {len(structure['directories'])} directories")
        logger.info(f"🔍 Identified {len(structure['key_components'])} key components")
        
        return structure

    def _analyze_directory(self, directory: Path) -> Dict[str, Any]:
        """Analyze a specific directory for microservice potential"""
        info = {
            "file_count": 0,
            "python_files": 0,
            "javascript_files": 0,
            "config_files": 0,
            "total_loc": 0,
            "subdirectories": [],
            "main_files": []
        }
        
        for item in directory.rglob("*"):
            if item.is_file():
                info["file_count"] += 1
                suffix = item.suffix.lower()
                
                if suffix == ".py":
                    info["python_files"] += 1
                    info["total_loc"] += self._count_lines_of_code(item)
                    if item.name in ["main.py", "app.py", "__init__.py", "router.py"]:
                        info["main_files"].append(str(item.relative_to(self.project_root)))
                
                elif suffix in [".js", ".ts", ".vue"]:
                    info["javascript_files"] += 1
                    info["total_loc"] += self._count_lines_of_code(item)
                
                elif suffix in [".json", ".yaml", ".yml", ".toml", ".ini"]:
                    info["config_files"] += 1
            
            elif item.is_dir() and item != directory:
                info["subdirectories"].append(item.name)
        
        return info

    def _count_lines_of_code(self, file_path: Path) -> int:
        """Count non-empty, non-comment lines of code"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            loc = 0
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and not stripped.startswith('//'):
                    loc += 1
            
            return loc
        except Exception:
            return 0

    def _identify_key_components(self) -> Dict[str, Any]:
        """Identify key architectural components that could be microservices"""
        components = {
            "api_endpoints": self._analyze_api_endpoints(),
            "data_models": self._analyze_data_models(),
            "agents": self._analyze_agents(),
            "utilities": self._analyze_utilities(),
            "services": self._analyze_services()
        }
        
        return components

    def _analyze_api_endpoints(self) -> Dict[str, Any]:
        """Analyze API endpoints for service boundaries"""
        endpoints = {
            "routers": [],
            "endpoint_groups": {},
            "total_endpoints": 0
        }
        
        # Analyze backend API files
        backend_api_dir = self.project_root / "backend" / "api"
        if backend_api_dir.exists():
            for api_file in backend_api_dir.glob("*.py"):
                if api_file.name == "__init__.py":
                    continue
                
                router_info = {
                    "file": str(api_file.relative_to(self.project_root)),
                    "name": api_file.stem,
                    "endpoints": [],
                    "dependencies": []
                }
                
                # Parse the file for endpoint definitions
                try:
                    with open(api_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Find FastAPI route decorators
                    route_pattern = r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']'
                    routes = re.findall(route_pattern, content)
                    
                    for method, path in routes:
                        router_info["endpoints"].append({
                            "method": method.upper(),
                            "path": path
                        })
                    
                    # Find imports to understand dependencies
                    import_pattern = r'from\s+([^\\s]+)\s+import|import\s+([^\\s]+)'
                    imports = re.findall(import_pattern, content)
                    
                    for imp1, imp2 in imports:
                        dep = imp1 or imp2
                        if dep and not dep.startswith(('fastapi', 'pydantic', 'typing')):
                            router_info["dependencies"].append(dep)
                    
                    endpoints["routers"].append(router_info)
                    endpoints["total_endpoints"] += len(router_info["endpoints"])
                    
                    # Group endpoints by domain
                    domain = api_file.stem
                    endpoints["endpoint_groups"][domain] = router_info["endpoints"]
                
                except Exception as e:
                    logger.warning(f"Could not analyze API file {api_file}: {e}")
        
        return endpoints

    def _analyze_data_models(self) -> Dict[str, Any]:
        """Analyze data models and database interactions"""
        models = {
            "database_files": [],
            "model_classes": [],
            "database_types": set()
        }
        
        # Look for database-related files
        for py_file in self.project_root.rglob("*.py"):
            if any(keyword in py_file.name.lower() for keyword in 
                   ["model", "db", "database", "schema", "table"]):
                
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Check for database frameworks
                    if any(framework in content for framework in 
                           ["sqlite3", "SQLAlchemy", "peewee", "asyncpg", "aiomysql"]):
                        
                        model_info = {
                            "file": str(py_file.relative_to(self.project_root)),
                            "classes": [],
                            "database_type": None
                        }
                        
                        # Identify database type
                        if "sqlite3" in content or ".db" in content or ".sqlite" in content:
                            model_info["database_type"] = "SQLite"
                            models["database_types"].add("SQLite")
                        elif "postgres" in content or "asyncpg" in content:
                            model_info["database_type"] = "PostgreSQL"
                            models["database_types"].add("PostgreSQL")
                        elif "mysql" in content or "aiomysql" in content:
                            model_info["database_type"] = "MySQL"  
                            models["database_types"].add("MySQL")
                        elif "redis" in content.lower():
                            model_info["database_type"] = "Redis"
                            models["database_types"].add("Redis")
                        
                        # Find class definitions
                        tree = ast.parse(content)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                model_info["classes"].append(node.name)
                        
                        models["database_files"].append(model_info)
                        models["model_classes"].extend(model_info["classes"])
                
                except Exception as e:
                    logger.debug(f"Could not analyze model file {py_file}: {e}")
        
        return models

    def _analyze_agents(self) -> Dict[str, Any]:
        """Analyze AI agents for potential service boundaries"""
        agents = {
            "agent_files": [],
            "agent_types": {},
            "total_agents": 0
        }
        
        agents_dir = self.project_root / "src" / "agents"
        if agents_dir.exists():
            for agent_file in agents_dir.glob("*.py"):
                if agent_file.name == "__init__.py":
                    continue
                
                try:
                    with open(agent_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    agent_info = {
                        "file": str(agent_file.relative_to(self.project_root)),
                        "name": agent_file.stem,
                        "classes": [],
                        "functions": [],
                        "dependencies": [],
                        "agent_type": "unknown"
                    }
                    
                    # Parse AST to find classes and functions
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            agent_info["classes"].append(node.name)
                            # Determine agent type based on name
                            name_lower = node.name.lower()
                            if any(keyword in name_lower for keyword in ["research", "web", "search"]):
                                agent_info["agent_type"] = "research"
                            elif any(keyword in name_lower for keyword in ["chat", "conversation", "dialogue"]):
                                agent_info["agent_type"] = "chat"
                            elif any(keyword in name_lower for keyword in ["knowledge", "kb", "memory"]):
                                agent_info["agent_type"] = "knowledge"
                            elif any(keyword in name_lower for keyword in ["terminal", "command", "shell"]):
                                agent_info["agent_type"] = "execution"
                            elif any(keyword in name_lower for keyword in ["file", "project", "code"]):
                                agent_info["agent_type"] = "file_management"
                        
                        elif isinstance(node, ast.FunctionDef):
                            if not node.name.startswith('_'):  # Skip private functions
                                agent_info["functions"].append(node.name)
                    
                    # Find imports
                    import_pattern = r'from\s+([^\\s]+)\s+import|import\s+([^\\s]+)'
                    imports = re.findall(import_pattern, content)
                    for imp1, imp2 in imports:
                        dep = imp1 or imp2
                        if dep and dep.startswith(('src.', 'backend.')):
                            agent_info["dependencies"].append(dep)
                    
                    agents["agent_files"].append(agent_info)
                    agents["total_agents"] += len(agent_info["classes"])
                    
                    # Group by agent type
                    agent_type = agent_info["agent_type"]
                    if agent_type not in agents["agent_types"]:
                        agents["agent_types"][agent_type] = []
                    agents["agent_types"][agent_type].append(agent_info["name"])
                
                except Exception as e:
                    logger.warning(f"Could not analyze agent file {agent_file}: {e}")
        
        return agents

    def _analyze_utilities(self) -> Dict[str, Any]:
        """Analyze utility modules for shared services potential"""
        utilities = {
            "util_files": [],
            "shared_utilities": [],
            "utility_types": {}
        }
        
        utils_dirs = [
            self.project_root / "src" / "utils",
            self.project_root / "backend" / "utils",
            self.project_root / "scripts"
        ]
        
        for utils_dir in utils_dirs:
            if not utils_dir.exists():
                continue
                
            for util_file in utils_dir.glob("*.py"):
                if util_file.name == "__init__.py":
                    continue
                
                try:
                    with open(util_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    util_info = {
                        "file": str(util_file.relative_to(self.project_root)),
                        "name": util_file.stem,
                        "functions": [],
                        "classes": [],
                        "utility_type": self._categorize_utility(util_file.stem, content)
                    }
                    
                    # Parse functions and classes
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if not node.name.startswith('_'):
                                util_info["functions"].append(node.name)
                        elif isinstance(node, ast.ClassDef):
                            util_info["classes"].append(node.name)
                    
                    utilities["util_files"].append(util_info)
                    
                    # Categorize utilities
                    util_type = util_info["utility_type"]
                    if util_type not in utilities["utility_types"]:
                        utilities["utility_types"][util_type] = []
                    utilities["utility_types"][util_type].append(util_info["name"])
                    
                    # Mark as shared if used across multiple modules
                    if len(util_info["functions"]) > 3 or len(util_info["classes"]) > 1:
                        utilities["shared_utilities"].append(util_info["name"])
                
                except Exception as e:
                    logger.debug(f"Could not analyze utility file {util_file}: {e}")
        
        return utilities

    def _categorize_utility(self, filename: str, content: str) -> str:
        """Categorize utility based on filename and content"""
        filename_lower = filename.lower()
        content_lower = content.lower()
        
        if any(keyword in filename_lower for keyword in ["config", "settings"]):
            return "configuration"
        elif any(keyword in filename_lower for keyword in ["db", "database", "sql"]):
            return "database"
        elif any(keyword in filename_lower for keyword in ["http", "client", "request", "api"]):
            return "http_client"
        elif any(keyword in filename_lower for keyword in ["cache", "redis"]):
            return "caching"
        elif any(keyword in filename_lower for keyword in ["log", "logging"]):
            return "logging"
        elif any(keyword in filename_lower for keyword in ["memory", "optimization"]):
            return "performance"
        elif any(keyword in filename_lower for keyword in ["terminal", "websocket"]):
            return "communication"
        elif any(keyword in filename_lower for keyword in ["file", "io"]):
            return "file_operations"
        elif any(keyword in content_lower for keyword in ["encrypt", "security", "auth"]):
            return "security"
        else:
            return "general"

    def _analyze_services(self) -> Dict[str, Any]:
        """Analyze existing service-like modules"""
        services = {
            "service_files": [],
            "service_types": {},
            "total_services": 0
        }
        
        # Look for service directories and files
        service_patterns = ["service", "manager", "handler", "processor", "worker"]
        
        for pattern in service_patterns:
            # Search in main directories
            for py_file in self.project_root.rglob(f"*{pattern}*.py"):
                if py_file.name == "__init__.py":
                    continue
                
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    service_info = {
                        "file": str(py_file.relative_to(self.project_root)),
                        "name": py_file.stem,
                        "classes": [],
                        "functions": [],
                        "service_type": pattern
                    }
                    
                    # Parse classes and functions
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            service_info["classes"].append(node.name)
                        elif isinstance(node, ast.FunctionDef):
                            if not node.name.startswith('_'):
                                service_info["functions"].append(node.name)
                    
                    services["service_files"].append(service_info)
                    services["total_services"] += 1
                    
                    # Group by service type
                    if pattern not in services["service_types"]:
                        services["service_types"][pattern] = []
                    services["service_types"][pattern].append(service_info["name"])
                
                except Exception as e:
                    logger.debug(f"Could not analyze service file {py_file}: {e}")
        
        return services

    def _get_file_statistics(self) -> Dict[str, Any]:
        """Get overall file statistics"""
        stats = {
            "total_files": 0,
            "python_files": 0,
            "javascript_files": 0,
            "config_files": 0,
            "total_loc": 0,
            "largest_files": []
        }
        
        files_info = []
        
        for file_path in self.project_root.rglob("*"):
            if file_path.is_file():
                stats["total_files"] += 1
                size = file_path.stat().st_size
                suffix = file_path.suffix.lower()
                
                loc = self._count_lines_of_code(file_path)
                stats["total_loc"] += loc
                
                if suffix == ".py":
                    stats["python_files"] += 1
                elif suffix in [".js", ".ts", ".vue"]:
                    stats["javascript_files"] += 1
                elif suffix in [".json", ".yaml", ".yml", ".toml", ".ini"]:
                    stats["config_files"] += 1
                
                if loc > 100:  # Files with significant code
                    files_info.append({
                        "file": str(file_path.relative_to(self.project_root)),
                        "loc": loc,
                        "size_kb": round(size / 1024, 2)
                    })
        
        # Sort by LOC and get top 10
        files_info.sort(key=lambda x: x["loc"], reverse=True)
        stats["largest_files"] = files_info[:10]
        
        return stats

    def _identify_architecture_patterns(self) -> Dict[str, Any]:
        """Identify current architecture patterns"""
        patterns = {
            "mvc_pattern": False,
            "layered_architecture": False,
            "microservice_readiness": 0,  # Score 0-10
            "api_gateway_present": False,
            "event_driven_components": [],
            "shared_dependencies": [],
            "tight_coupling_areas": []
        }
        
        # Check for MVC pattern
        has_models = (self.project_root / "src" / "models").exists() or any(
            "model" in str(p) for p in self.project_root.rglob("*.py")
        )
        has_views = (self.project_root / "frontend").exists() or (self.project_root / "autobot-vue").exists()
        has_controllers = (self.project_root / "backend" / "api").exists()
        
        patterns["mvc_pattern"] = has_models and has_views and has_controllers
        
        # Check for layered architecture
        has_data_layer = bool(self.analysis_results.get("project_structure", {}).get("key_components", {}).get("data_models", {}).get("database_files", []))
        has_business_layer = (self.project_root / "src").exists()
        has_presentation_layer = has_views
        
        patterns["layered_architecture"] = has_data_layer and has_business_layer and has_presentation_layer
        
        # Calculate microservice readiness score
        readiness_score = 0
        
        # +2 if API is well-organized
        api_endpoints = self.analysis_results.get("project_structure", {}).get("key_components", {}).get("api_endpoints", {})
        if len(api_endpoints.get("endpoint_groups", {})) >= 3:
            readiness_score += 2
        
        # +2 if agents are well-separated
        agents = self.analysis_results.get("project_structure", {}).get("key_components", {}).get("agents", {})
        if len(agents.get("agent_types", {})) >= 3:
            readiness_score += 2
        
        # +2 if database access is abstracted
        if has_data_layer:
            readiness_score += 2
        
        # +2 if utilities are well-organized
        utilities = self.analysis_results.get("project_structure", {}).get("key_components", {}).get("utilities", {})
        if len(utilities.get("utility_types", {})) >= 4:
            readiness_score += 2
        
        # +1 if configuration is centralized
        if (self.project_root / "src" / "config.py").exists():
            readiness_score += 1
        
        # +1 if Docker is already used
        if (self.project_root / "docker").exists():
            readiness_score += 1
        
        patterns["microservice_readiness"] = readiness_score
        
        # Check for API gateway
        patterns["api_gateway_present"] = (self.project_root / "backend" / "app_factory.py").exists()
        
        return patterns

    def analyze_dependencies(self) -> Dict[str, Any]:
        """Analyze dependencies between components"""
        logger.info("🔗 Analyzing component dependencies...")
        
        dependencies = {
            "import_graph": {},
            "coupling_analysis": {},
            "shared_modules": [],
            "circular_dependencies": []
        }
        
        # Build import graph
        import_graph = defaultdict(set)
        
        for py_file in self.project_root.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Find local imports (src.* and backend.*)
                import_pattern = r'from\s+(src\.[^\\s]+|backend\.[^\\s]+)\s+import|import\s+(src\.[^\\s]+|backend\.[^\\s]+)'
                imports = re.findall(import_pattern, content)
                
                file_module = str(py_file.relative_to(self.project_root)).replace('/', '.').replace('.py', '')
                
                for imp1, imp2 in imports:
                    imported_module = (imp1 or imp2).split('.')[0:3]  # Take first 3 parts
                    imported_module = '.'.join(imported_module)
                    import_graph[file_module].add(imported_module)
                    
            except Exception as e:
                logger.debug(f"Could not analyze imports in {py_file}: {e}")
        
        dependencies["import_graph"] = {k: list(v) for k, v in import_graph.items()}
        
        # Analyze coupling
        dependencies["coupling_analysis"] = self._analyze_coupling(import_graph)
        
        # Find shared modules (imported by many others)
        import_counts = defaultdict(int)
        for module, imports in import_graph.items():
            for imported in imports:
                import_counts[imported] += 1
        
        dependencies["shared_modules"] = [
            {"module": module, "import_count": count}
            for module, count in sorted(import_counts.items(), key=lambda x: x[1], reverse=True)
            if count >= 3
        ][:10]
        
        # Detect potential circular dependencies (simplified)
        dependencies["circular_dependencies"] = self._detect_circular_dependencies(import_graph)
        
        logger.info(f"📊 Analyzed {len(import_graph)} modules")
        logger.info(f"🔄 Found {len(dependencies['circular_dependencies'])} potential circular dependencies")
        
        return dependencies

    def _analyze_coupling(self, import_graph: Dict[str, Set[str]]) -> Dict[str, Any]:
        """Analyze coupling between different components"""
        coupling = {
            "high_coupling_modules": [],
            "coupling_by_domain": {},
            "fan_out": {},  # How many modules each module imports
            "fan_in": {}    # How many modules import each module
        }
        
        # Calculate fan-out
        for module, imports in import_graph.items():
            coupling["fan_out"][module] = len(imports)
        
        # Calculate fan-in
        fan_in_count = defaultdict(int)
        for module, imports in import_graph.items():
            for imported in imports:
                fan_in_count[imported] += 1
        
        coupling["fan_in"] = dict(fan_in_count)
        
        # Identify high coupling modules (high fan-out or fan-in)
        high_coupling_threshold = 5
        
        for module in import_graph.keys():
            fan_out = coupling["fan_out"].get(module, 0)
            fan_in = coupling["fan_in"].get(module, 0)
            
            if fan_out >= high_coupling_threshold or fan_in >= high_coupling_threshold:
                coupling["high_coupling_modules"].append({
                    "module": module,
                    "fan_out": fan_out,
                    "fan_in": fan_in,
                    "coupling_score": fan_out + fan_in
                })
        
        # Sort by coupling score
        coupling["high_coupling_modules"].sort(key=lambda x: x["coupling_score"], reverse=True)
        
        return coupling

    def _detect_circular_dependencies(self, import_graph: Dict[str, Set[str]]) -> List[List[str]]:
        """Detect circular dependencies using DFS"""
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(module, path):
            visited.add(module)
            rec_stack.add(module)
            current_path = path + [module]
            
            for imported in import_graph.get(module, []):
                if imported not in visited:
                    dfs(imported, current_path)
                elif imported in rec_stack:
                    # Found a cycle
                    cycle_start = current_path.index(imported)
                    cycle = current_path[cycle_start:] + [imported]
                    if cycle not in cycles and len(cycle) > 2:
                        cycles.append(cycle)
            
            rec_stack.remove(module)
        
        for module in import_graph:
            if module not in visited:
                dfs(module, [])
        
        return cycles[:5]  # Return top 5 circular dependencies

    def identify_service_boundaries(self) -> Dict[str, Any]:
        """Identify potential microservice boundaries"""
        logger.info("🎯 Identifying potential service boundaries...")
        
        boundaries = {
            "proposed_services": [],
            "shared_services": [],
            "data_services": [],
            "boundary_rationale": {}
        }
        
        # Analyze API endpoints for service boundaries
        api_endpoints = self.analysis_results["project_structure"]["key_components"]["api_endpoints"]
        for domain, endpoints in api_endpoints.get("endpoint_groups", {}).items():
            if len(endpoints) >= 3:  # Domains with sufficient endpoints
                service = {
                    "name": f"{domain.title()}Service",
                    "type": "api_service",
                    "endpoints": endpoints,
                    "estimated_complexity": len(endpoints),
                    "responsibilities": self._infer_responsibilities(domain, endpoints)
                }
                boundaries["proposed_services"].append(service)
        
        # Analyze agents for service boundaries  
        agents = self.analysis_results["project_structure"]["key_components"]["agents"]
        for agent_type, agent_names in agents.get("agent_types", {}).items():
            if len(agent_names) >= 2:  # Agent types with multiple agents
                service = {
                    "name": f"{agent_type.title()}AgentService",
                    "type": "agent_service", 
                    "agents": agent_names,
                    "estimated_complexity": len(agent_names) * 2,
                    "responsibilities": self._infer_agent_responsibilities(agent_type)
                }
                boundaries["proposed_services"].append(service)
        
        # Identify shared services
        utilities = self.analysis_results["project_structure"]["key_components"]["utilities"]
        for util_type, util_names in utilities.get("utility_types", {}).items():
            if util_type in ["caching", "database", "http_client", "configuration", "logging"]:
                service = {
                    "name": f"{util_type.title()}Service",
                    "type": "shared_service",
                    "utilities": util_names,
                    "estimated_complexity": 3,
                    "responsibilities": [f"Provide {util_type} functionality across all services"]
                }
                boundaries["shared_services"].append(service)
        
        # Identify data services
        models = self.analysis_results["project_structure"]["key_components"]["data_models"]
        for db_type in models.get("database_types", []):
            service = {
                "name": f"{db_type}DataService",
                "type": "data_service",
                "database_type": db_type,
                "estimated_complexity": 4,
                "responsibilities": [f"Manage {db_type} data operations", "Data validation", "Query optimization"]
            }
            boundaries["data_services"].append(service)
        
        # Generate rationale for boundaries
        for service in boundaries["proposed_services"] + boundaries["shared_services"] + boundaries["data_services"]:
            boundaries["boundary_rationale"][service["name"]] = self._generate_boundary_rationale(service)
        
        logger.info(f"🎯 Identified {len(boundaries['proposed_services'])} proposed services")
        logger.info(f"🔧 Identified {len(boundaries['shared_services'])} shared services")
        logger.info(f"💾 Identified {len(boundaries['data_services'])} data services")
        
        return boundaries

    def _infer_responsibilities(self, domain: str, endpoints: List[Dict]) -> List[str]:
        """Infer service responsibilities from domain and endpoints"""
        responsibilities = [f"Handle all {domain}-related operations"]
        
        methods = set(endpoint["method"] for endpoint in endpoints)
        if "GET" in methods:
            responsibilities.append(f"Retrieve {domain} data")
        if "POST" in methods:
            responsibilities.append(f"Create new {domain} entries")
        if "PUT" in methods or "PATCH" in methods:
            responsibilities.append(f"Update {domain} data")
        if "DELETE" in methods:
            responsibilities.append(f"Delete {domain} entries")
        
        return responsibilities

    def _infer_agent_responsibilities(self, agent_type: str) -> List[str]:
        """Infer responsibilities for agent services"""
        responsibility_map = {
            "research": [
                "Perform web research operations",
                "Aggregate and analyze research data",
                "Cache research results",
                "Manage research sessions"
            ],
            "chat": [
                "Handle conversation management",
                "Maintain chat history",
                "Process user inputs",
                "Generate responses"
            ],
            "knowledge": [
                "Manage knowledge base operations",
                "Index and search knowledge",
                "Update knowledge entries",
                "Provide knowledge retrieval"
            ],
            "execution": [
                "Execute system commands",
                "Manage terminal sessions",
                "Handle code execution",
                "Monitor execution status"
            ],
            "file_management": [
                "Perform file operations",
                "Manage project structure",
                "Handle file uploads/downloads",
                "Track file changes"
            ]
        }
        
        return responsibility_map.get(agent_type, [f"Handle {agent_type} operations"])

    def _generate_boundary_rationale(self, service: Dict[str, Any]) -> str:
        """Generate rationale for service boundary decision"""
        service_type = service["type"]
        name = service["name"]
        
        if service_type == "api_service":
            return f"{name} should be a separate service because it handles a distinct domain with {service['estimated_complexity']} endpoints, allowing for independent scaling and development."
        
        elif service_type == "agent_service":
            return f"{name} should be a separate service because AI agents require specialized resources, can benefit from independent scaling, and have distinct computational requirements."
        
        elif service_type == "shared_service":
            return f"{name} should be a shared service because it provides common functionality needed across multiple services, reducing duplication and ensuring consistency."
        
        elif service_type == "data_service":
            return f"{name} should be a separate service to provide data abstraction, handle database-specific optimizations, and allow for independent data management."
        
        else:
            return f"{name} represents a logical boundary for separation based on functionality and responsibilities."

    def create_migration_strategy(self) -> Dict[str, Any]:
        """Create a microservice migration strategy"""
        logger.info("🗺️  Creating microservice migration strategy...")
        
        strategy = {
            "migration_phases": [],
            "dependency_order": [],
            "risk_assessment": {},
            "implementation_plan": {},
            "rollback_strategy": {}
        }
        
        # Phase 1: Shared Services (Foundation)
        shared_services = self.analysis_results["service_boundaries"]["shared_services"]
        if shared_services:
            phase1 = {
                "phase": 1,
                "name": "Foundation Services",
                "services": [s["name"] for s in shared_services],
                "rationale": "Extract shared utilities first to provide foundation for other services",
                "estimated_duration_weeks": 4,
                "complexity": "Medium",
                "risks": ["Service discovery setup", "Configuration management"]
            }
            strategy["migration_phases"].append(phase1)
        
        # Phase 2: Data Services
        data_services = self.analysis_results["service_boundaries"]["data_services"]
        if data_services:
            phase2 = {
                "phase": 2,
                "name": "Data Services",
                "services": [s["name"] for s in data_services],
                "rationale": "Establish data layer services to provide consistent data access",
                "estimated_duration_weeks": 6,
                "complexity": "High",
                "risks": ["Data consistency", "Transaction management", "Performance impact"]
            }
            strategy["migration_phases"].append(phase2)
        
        # Phase 3: Agent Services (Compute-Heavy)
        agent_services = [s for s in self.analysis_results["service_boundaries"]["proposed_services"] if s["type"] == "agent_service"]
        if agent_services:
            phase3 = {
                "phase": 3,
                "name": "Agent Services",
                "services": [s["name"] for s in agent_services],
                "rationale": "Extract AI agents for independent scaling and resource management",
                "estimated_duration_weeks": 8,
                "complexity": "High",
                "risks": ["AI model distribution", "GPU resource management", "Session management"]
            }
            strategy["migration_phases"].append(phase3)
        
        # Phase 4: API Services
        api_services = [s for s in self.analysis_results["service_boundaries"]["proposed_services"] if s["type"] == "api_service"]
        if api_services:
            phase4 = {
                "phase": 4,
                "name": "API Services",
                "services": [s["name"] for s in api_services],
                "rationale": "Extract domain-specific API services last, after dependencies are established",
                "estimated_duration_weeks": 10,
                "complexity": "Medium",
                "risks": ["API gateway configuration", "Load balancing", "Authentication propagation"]
            }
            strategy["migration_phases"].append(phase4)
        
        # Create dependency order
        strategy["dependency_order"] = self._create_dependency_order(strategy["migration_phases"])
        
        # Risk assessment
        strategy["risk_assessment"] = self._assess_migration_risks()
        
        # Implementation plan
        strategy["implementation_plan"] = self._create_implementation_plan()
        
        # Rollback strategy
        strategy["rollback_strategy"] = self._create_rollback_strategy()
        
        logger.info(f"📋 Created {len(strategy['migration_phases'])}-phase migration strategy")
        
        return strategy

    def _create_dependency_order(self, phases: List[Dict]) -> List[str]:
        """Create dependency-based service extraction order"""
        order = []
        for phase in sorted(phases, key=lambda x: x["phase"]):
            order.extend(phase["services"])
        return order

    def _assess_migration_risks(self) -> Dict[str, Any]:
        """Assess risks of microservice migration"""
        return {
            "high_risks": [
                "Distributed system complexity",
                "Data consistency across services",
                "Network latency and failure handling",
                "Service discovery and configuration management"
            ],
            "medium_risks": [
                "Increased deployment complexity",
                "Monitoring and debugging challenges",
                "Team coordination overhead",
                "Initial performance degradation"
            ],
            "mitigation_strategies": [
                "Implement comprehensive monitoring and logging",
                "Use circuit breakers and retry mechanisms",
                "Establish clear service contracts and APIs",
                "Implement gradual rollout with feature flags",
                "Maintain backward compatibility during transition"
            ]
        }

    def _create_implementation_plan(self) -> Dict[str, Any]:
        """Create detailed implementation plan"""
        return {
            "prerequisites": [
                "Set up container orchestration (Docker/Kubernetes)",
                "Implement service discovery (Consul/Eureka)",
                "Establish API gateway (Kong/Ambassador)",
                "Set up centralized logging and monitoring",
                "Implement distributed tracing",
                "Create CI/CD pipelines for microservices"
            ],
            "tools_and_technologies": {
                "containerization": "Docker + Docker Compose",
                "orchestration": "Kubernetes or Docker Swarm",
                "service_discovery": "Consul or Eureka",
                "api_gateway": "Kong or Traefik",
                "monitoring": "Prometheus + Grafana",
                "logging": "ELK Stack (Elasticsearch + Logstash + Kibana)",
                "tracing": "Jaeger or Zipkin",
                "message_queue": "Redis Pub/Sub or RabbitMQ"
            },
            "development_practices": [
                "Domain-driven design for service boundaries",
                "API-first development approach",
                "Database per service pattern",
                "Event-driven architecture for loose coupling",
                "Circuit breaker pattern for resilience"
            ]
        }

    def _create_rollback_strategy(self) -> Dict[str, Any]:
        """Create rollback strategy for migration"""
        return {
            "rollback_triggers": [
                "Performance degradation > 50%",
                "Error rate increase > 10%",
                "Unresolvable data consistency issues",
                "Critical functionality failures"
            ],
            "rollback_procedures": [
                "Revert traffic routing to monolithic application",
                "Restore database connections to original configuration",
                "Disable new service endpoints",
                "Restart monolithic application with previous configuration"
            ],
            "data_recovery": [
                "Maintain data synchronization during migration",
                "Regular backup checkpoints",
                "Transaction log replay capability",
                "Data validation and consistency checks"
            ],
            "testing_strategy": [
                "Comprehensive integration testing",
                "Load testing with realistic traffic patterns",
                "Chaos engineering to test failure scenarios",
                "Gradual traffic shifting (blue-green deployment)"
            ]
        }

    def generate_recommendations(self) -> List[str]:
        """Generate comprehensive recommendations"""
        recommendations = []
        
        # Analyze current state
        structure = self.analysis_results["project_structure"]
        boundaries = self.analysis_results["service_boundaries"]
        
        # Current architecture analysis
        file_stats = structure["file_statistics"]
        total_services = len(boundaries["proposed_services"]) + len(boundaries["shared_services"]) + len(boundaries["data_services"])
        
        # Recommendations based on analysis
        if file_stats["total_loc"] > 50000:
            recommendations.append(f"🔴 HIGH PRIORITY: Large codebase ({file_stats['total_loc']:,} LOC) - microservices migration recommended")
        
        if total_services >= 6:
            recommendations.append(f"✅ GOOD CANDIDATE: Identified {total_services} potential services - suitable for microservices")
        elif total_services >= 3:
            recommendations.append(f"🟡 MODERATE: Identified {total_services} potential services - consider selective extraction")
        else:
            recommendations.append("🔴 WARNING: Few clear service boundaries identified - reconsider microservices approach")
        
        # Architecture readiness
        readiness = structure["architecture_patterns"]["microservice_readiness"]
        if readiness >= 7:
            recommendations.append(f"✅ HIGH READINESS: Microservice readiness score {readiness}/10 - well-prepared for migration")
        elif readiness >= 4:
            recommendations.append(f"🟡 MEDIUM READINESS: Score {readiness}/10 - some preparation needed")
        else:
            recommendations.append(f"🔴 LOW READINESS: Score {readiness}/10 - significant preparation required")
        
        # Dependency analysis
        dependencies = self.analysis_results["dependency_analysis"]
        high_coupling_count = len(dependencies["coupling_analysis"]["high_coupling_modules"])
        
        if high_coupling_count > 5:
            recommendations.append(f"⚠️  HIGH COUPLING: {high_coupling_count} highly coupled modules - refactor before migration")
        
        circular_deps = len(dependencies["circular_dependencies"])
        if circular_deps > 0:
            recommendations.append(f"🔄 CIRCULAR DEPENDENCIES: {circular_deps} detected - must resolve before migration")
        
        # Specific recommendations
        recommendations.extend([
            "📋 PHASE 1: Start with shared services (caching, configuration, logging)",
            "💾 PHASE 2: Extract data services for database abstraction",
            "🤖 PHASE 3: Isolate AI agents for independent scaling",
            "🌐 PHASE 4: Split API endpoints by business domain",
            "🔧 INFRASTRUCTURE: Implement Docker + Kubernetes + API Gateway",
            "📊 MONITORING: Set up distributed tracing and centralized logging",
            "🧪 TESTING: Establish comprehensive integration testing strategy"
        ])
        
        return recommendations

    def save_analysis_report(self):
        """Save comprehensive analysis report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON report
        json_report_path = self.reports_dir / f"microservice_analysis_{timestamp}.json"
        with open(json_report_path, 'w') as f:
            json.dump(self.analysis_results, f, indent=2)
        
        # Save markdown summary
        md_report_path = self.reports_dir / f"microservice_evaluation_summary_{timestamp}.md"
        with open(md_report_path, 'w') as f:
            f.write(self._generate_markdown_report())
        
        logger.info(f"📄 Microservice analysis reports saved:")
        logger.info(f"  JSON: {json_report_path}")
        logger.info(f"  Markdown: {md_report_path}")
        
        return {"json": json_report_path, "markdown": md_report_path}

    def _generate_markdown_report(self) -> str:
        """Generate comprehensive markdown analysis report"""
        structure = self.analysis_results["project_structure"]
        dependencies = self.analysis_results["dependency_analysis"]
        boundaries = self.analysis_results["service_boundaries"]
        migration = self.analysis_results["migration_strategy"]
        recommendations = self.analysis_results["recommendations"]
        
        report = f"""# 🏗️ AutoBot Microservice Architecture Evaluation

**Analysis Date:** {self.analysis_results["timestamp"]}

## 📊 Executive Summary

This analysis evaluates the AutoBot codebase for microservice architecture migration potential. The system shows {"strong" if structure["architecture_patterns"]["microservice_readiness"] >= 7 else "moderate" if structure["architecture_patterns"]["microservice_readiness"] >= 4 else "limited"} readiness for microservice decomposition.

### Key Findings
- **Total Lines of Code:** {structure["file_statistics"]["total_loc"]:,}
- **Microservice Readiness Score:** {structure["architecture_patterns"]["microservice_readiness"]}/10
- **Identified Services:** {len(boundaries["proposed_services"]) + len(boundaries["shared_services"]) + len(boundaries["data_services"])}
- **Migration Phases:** {len(migration["migration_phases"])}

## 🏢 Current Architecture Analysis

### Project Structure
- **Total Files:** {structure["file_statistics"]["total_files"]:,}
- **Python Files:** {structure["file_statistics"]["python_files"]:,}
- **JavaScript/TypeScript Files:** {structure["file_statistics"]["javascript_files"]:,}
- **Configuration Files:** {structure["file_statistics"]["config_files"]:,}

### Architecture Patterns
- **MVC Pattern:** {"✅ Present" if structure["architecture_patterns"]["mvc_pattern"] else "❌ Not Present"}
- **Layered Architecture:** {"✅ Present" if structure["architecture_patterns"]["layered_architecture"] else "❌ Not Present"}
- **API Gateway:** {"✅ Present" if structure["architecture_patterns"]["api_gateway_present"] else "❌ Not Present"}

### Component Analysis

#### API Endpoints
"""
        
        api_endpoints = structure["key_components"]["api_endpoints"]
        report += f"- **Total Endpoints:** {api_endpoints['total_endpoints']}\n"
        report += f"- **Router Files:** {len(api_endpoints['routers'])}\n"
        
        for router in api_endpoints["routers"][:5]:  # Top 5 routers
            report += f"  - `{router['name']}`: {len(router['endpoints'])} endpoints\n"
        
        agents = structure["key_components"]["agents"]
        report += f"""
#### AI Agents
- **Total Agents:** {agents['total_agents']}
- **Agent Types:** {len(agents['agent_types'])}

"""
        for agent_type, agent_names in agents["agent_types"].items():
            report += f"- **{agent_type.title()}:** {', '.join(agent_names)}\n"
        
        models = structure["key_components"]["data_models"]
        report += f"""
#### Data Models
- **Database Files:** {len(models['database_files'])}
- **Database Types:** {', '.join(models['database_types']) if models['database_types'] else 'None'}
- **Model Classes:** {len(models['model_classes'])}

"""
        
        utilities = structure["key_components"]["utilities"]
        report += f"""#### Utilities
- **Utility Files:** {len(utilities['util_files'])}
- **Shared Utilities:** {len(utilities['shared_utilities'])}
- **Utility Types:** {', '.join(utilities['utility_types'].keys())}

## 🔗 Dependency Analysis

### Coupling Analysis
"""
        
        coupling = dependencies["coupling_analysis"]
        report += f"- **High Coupling Modules:** {len(coupling['high_coupling_modules'])}\n\n"
        
        for module in coupling["high_coupling_modules"][:5]:  # Top 5 highly coupled
            report += f"- `{module['module']}`: Fan-out({module['fan_out']}) + Fan-in({module['fan_in']}) = {module['coupling_score']}\n"
        
        report += f"""
### Shared Dependencies
"""
        for shared in dependencies["shared_modules"][:5]:  # Top 5 shared modules
            report += f"- `{shared['module']}`: Used by {shared['import_count']} modules\n"
        
        if dependencies["circular_dependencies"]:
            report += f"""
### ⚠️ Circular Dependencies
"""
            for cycle in dependencies["circular_dependencies"]:
                report += f"- {' → '.join(cycle)}\n"
        
        report += """
## 🎯 Proposed Service Boundaries

### Core Services
"""
        
        for service in boundaries["proposed_services"]:
            report += f"""
#### {service['name']}
- **Type:** {service['type'].replace('_', ' ').title()}
- **Complexity:** {service['estimated_complexity']}/10
- **Responsibilities:**
"""
            for resp in service["responsibilities"]:
                report += f"  - {resp}\n"
            
            report += f"- **Rationale:** {boundaries['boundary_rationale'][service['name']]}\n"
        
        if boundaries["shared_services"]:
            report += """
### Shared Services
"""
            for service in boundaries["shared_services"]:
                report += f"""
#### {service['name']}
- **Utilities:** {', '.join(service.get('utilities', []))}
- **Purpose:** Provide common {service['name'].replace('Service', '').lower()} functionality
"""
        
        if boundaries["data_services"]:
            report += """
### Data Services
"""
            for service in boundaries["data_services"]:
                report += f"""
#### {service['name']}
- **Database Type:** {service['database_type']}
- **Purpose:** Manage {service['database_type']} operations
"""
        
        report += """
## 🗺️ Migration Strategy
"""
        
        for phase in migration["migration_phases"]:
            report += f"""
### Phase {phase['phase']}: {phase['name']}
- **Duration:** {phase['estimated_duration_weeks']} weeks
- **Complexity:** {phase['complexity']}
- **Services:** {', '.join(phase['services'])}
- **Rationale:** {phase['rationale']}
- **Risks:** {', '.join(phase['risks'])}
"""
        
        report += f"""
## 🛠️ Implementation Requirements

### Prerequisites
"""
        for prereq in migration["implementation_plan"]["prerequisites"]:
            report += f"- {prereq}\n"
        
        report += f"""
### Technology Stack
"""
        for tech, tool in migration["implementation_plan"]["tools_and_technologies"].items():
            report += f"- **{tech.replace('_', ' ').title()}:** {tool}\n"
        
        report += """
## ⚠️ Risk Assessment

### High Risks
"""
        for risk in migration["risk_assessment"]["high_risks"]:
            report += f"- {risk}\n"
        
        report += """
### Mitigation Strategies
"""
        for strategy in migration["risk_assessment"]["mitigation_strategies"]:
            report += f"- {strategy}\n"
        
        report += """
## 📋 Recommendations

"""
        for i, rec in enumerate(recommendations, 1):
            report += f"{i}. {rec}\n"
        
        report += f"""
## 🎯 Next Steps

### Immediate Actions (1-2 weeks)
1. Set up Docker containerization for existing application
2. Implement comprehensive monitoring and logging
3. Create API documentation and service contracts

### Short Term (1-3 months)  
1. Begin Phase 1 migration (shared services)
2. Set up service discovery and API gateway
3. Implement distributed tracing

### Long Term (3-12 months)
1. Complete all migration phases
2. Optimize service performance and scaling
3. Establish microservice governance and best practices

---
**Generated by AutoBot Microservice Architecture Evaluator**
"""
        
        return report

    def run_full_evaluation(self):
        """Run complete microservice architecture evaluation"""
        logger.info("🚀 Starting comprehensive microservice architecture evaluation...")
        
        try:
            # Step 1: Analyze project structure
            self.analysis_results["project_structure"] = self.analyze_project_structure()
            
            # Step 2: Analyze dependencies
            self.analysis_results["dependency_analysis"] = self.analyze_dependencies()
            
            # Step 3: Identify service boundaries
            self.analysis_results["service_boundaries"] = self.identify_service_boundaries()
            
            # Step 4: Create migration strategy
            self.analysis_results["migration_strategy"] = self.create_migration_strategy()
            
            # Step 5: Generate recommendations
            self.analysis_results["recommendations"] = self.generate_recommendations()
            
            # Step 6: Save reports
            report_files = self.save_analysis_report()
            
            # Print summary
            self._print_evaluation_summary()
            
            return self.analysis_results
            
        except Exception as e:
            logger.error(f"Microservice evaluation failed: {e}")
            raise

    def _print_evaluation_summary(self):
        """Print evaluation summary to console"""
        structure = self.analysis_results["project_structure"]
        boundaries = self.analysis_results["service_boundaries"]
        migration = self.analysis_results["migration_strategy"]
        
        logger.info("\n" + "=" * 70)
        logger.info("🏗️ MICROSERVICE ARCHITECTURE EVALUATION SUMMARY")
        logger.info("=" * 70)
        
        logger.info(f"📊 CODEBASE ANALYSIS:")
        logger.info(f"  • Total Lines of Code: {structure['file_statistics']['total_loc']:,}")
        logger.info(f"  • Python Files: {structure['file_statistics']['python_files']:,}")
        logger.info(f"  • API Endpoints: {structure['key_components']['api_endpoints']['total_endpoints']}")
        logger.info(f"  • AI Agents: {structure['key_components']['agents']['total_agents']}")
        
        logger.info(f"\n🎯 SERVICE BOUNDARIES:")
        logger.info(f"  • Proposed Services: {len(boundaries['proposed_services'])}")
        logger.info(f"  • Shared Services: {len(boundaries['shared_services'])}")
        logger.info(f"  • Data Services: {len(boundaries['data_services'])}")
        
        logger.info(f"\n📋 MIGRATION STRATEGY:")
        logger.info(f"  • Migration Phases: {len(migration['migration_phases'])}")
        logger.info(f"  • Estimated Duration: {sum(phase['estimated_duration_weeks'] for phase in migration['migration_phases'])} weeks")
        
        logger.info(f"\n⚡ READINESS ASSESSMENT:")
        readiness = structure["architecture_patterns"]["microservice_readiness"]
        logger.info(f"  • Microservice Readiness: {readiness}/10")
        
        if readiness >= 7:
            logger.info("  ✅ HIGH READINESS - Excellent candidate for microservices")
        elif readiness >= 4:
            logger.info("  🟡 MEDIUM READINESS - Good candidate with some preparation needed")
        else:
            logger.info("  🔴 LOW READINESS - Significant refactoring required before migration")
        
        logger.info("=" * 70)


def main():
    """Main entry point"""
    try:
        evaluator = MicroserviceArchitectureEvaluator()
        results = evaluator.run_full_evaluation()
        
        # Return success
        return 0
        
    except Exception as e:
        logger.error(f"Microservice evaluation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())