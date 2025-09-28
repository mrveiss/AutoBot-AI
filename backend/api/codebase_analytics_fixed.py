"""
Real Codebase Analytics API for AutoBot (With Redis Fallback)
Provides comprehensive code analysis with both Redis and in-memory storage
"""

import ast
import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import redis
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/codebase", tags=["codebase-analytics"])

# In-memory storage fallback when Redis is unavailable
_in_memory_storage = {}

class CodebaseStats(BaseModel):
    total_files: int
    total_lines: int
    python_files: int
    javascript_files: int
    vue_files: int
    other_files: int
    total_functions: int
    total_classes: int
    average_file_size: float
    last_indexed: str

class ProblemItem(BaseModel):
    type: str
    severity: str
    file_path: str
    line_number: Optional[int]
    description: str
    suggestion: str

class HardcodeItem(BaseModel):
    file_path: str
    line_number: int
    type: str  # 'url', 'path', 'ip', 'port', 'api_key', 'string'
    value: str
    context: str

class DeclarationItem(BaseModel):
    name: str
    type: str  # 'function', 'class', 'variable'
    file_path: str
    line_number: int
    usage_count: int
    is_exported: bool
    parameters: Optional[List[str]]

async def get_redis_connection():
    """Get Redis connection with multiple host fallbacks"""
    redis_hosts = [
        ("127.0.0.1", 6379),  # Local Redis
        ("localhost", 6379),  # Local Redis alternative
        ("172.16.168.23", 6379),  # VM Redis
    ]

    for host, port in redis_hosts:
        try:
            redis_client = redis.Redis(
                host=host,
                port=port,
                db=11,  # Dedicated DB for codebase analytics
                decode_responses=True,
                socket_timeout=3,
                socket_connect_timeout=3
            )
            # Test connection
            redis_client.ping()
            logger.info(f"Connected to Redis at {host}:{port}")
            return redis_client
        except Exception as e:
            logger.debug(f"Failed to connect to Redis at {host}:{port}: {e}")
            continue

    logger.warning("No Redis connection available, using in-memory storage")
    return None

class InMemoryStorage:
    """In-memory storage fallback when Redis is unavailable"""

    def __init__(self):
        self.data = {}

    def set(self, key: str, value: str):
        self.data[key] = value

    def get(self, key: str):
        return self.data.get(key)

    def hset(self, key: str, mapping: dict):
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)

    def hgetall(self, key: str):
        return self.data.get(key, {})

    def sadd(self, key: str, value: str):
        if key not in self.data:
            self.data[key] = set()
        self.data[key].add(value)

    def smembers(self, key: str):
        return self.data.get(key, set())

    def scan_iter(self, match: str):
        import fnmatch
        pattern = match.replace('*', '.*')
        for key in self.data.keys():
            if re.match(pattern, key):
                yield key

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
        return len(keys)

    def exists(self, key: str):
        return key in self.data

def analyze_python_file(file_path: str) -> Dict[str, Any]:
    """Analyze a Python file for functions, classes, and potential issues"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)

        functions = []
        classes = []
        imports = []
        hardcodes = []
        problems = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append({
                    'name': node.name,
                    'line': node.lineno,
                    'args': [arg.arg for arg in node.args.args],
                    'docstring': ast.get_docstring(node),
                    'is_async': isinstance(node, ast.AsyncFunctionDef)
                })

                # Check for long functions
                if hasattr(node, 'end_lineno') and node.end_lineno:
                    func_length = node.end_lineno - node.lineno
                    if func_length > 50:
                        problems.append({
                            'type': 'long_function',
                            'severity': 'medium',
                            'line': node.lineno,
                            'description': f"Function '{node.name}' is {func_length} lines long",
                            'suggestion': 'Consider breaking into smaller functions'
                        })

            elif isinstance(node, ast.ClassDef):
                classes.append({
                    'name': node.name,
                    'line': node.lineno,
                    'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)],
                    'docstring': ast.get_docstring(node)
                })

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                else:
                    imports.append(node.module or '')

        # Check content for hardcoded values using regex (more reliable than AST for this)
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Look for IP addresses
            ip_matches = re.findall(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', line)
            for ip in ip_matches:
                if ip.startswith('172.16.168.') or ip.startswith('127.0.0.') or ip.startswith('192.168.'):
                    hardcodes.append({
                        'type': 'ip',
                        'value': ip,
                        'line': i,
                        'context': line.strip()
                    })

            # Look for URLs
            url_matches = re.findall(r'[\'"`](https?://[^\'"` ]+)[\'"`]', line)
            for url in url_matches:
                hardcodes.append({
                    'type': 'url',
                    'value': url,
                    'line': i,
                    'context': line.strip()
                })

            # Look for port numbers
            port_matches = re.findall(r'\b(80[0-9][0-9]|[1-9][0-9]{3,4})\b', line)
            for port in port_matches:
                if port in ['8001', '8080', '6379', '11434', '5173', '3000']:
                    hardcodes.append({
                        'type': 'port',
                        'value': port,
                        'line': i,
                        'context': line.strip()
                    })

        return {
            'functions': functions,
            'classes': classes,
            'imports': imports,
            'hardcodes': hardcodes,
            'problems': problems,
            'line_count': len(content.splitlines())
        }

    except Exception as e:
        logger.error(f"Error analyzing Python file {file_path}: {e}")
        return {
            'functions': [],
            'classes': [],
            'imports': [],
            'hardcodes': [],
            'problems': [{'type': 'parse_error', 'severity': 'high', 'line': 1,
                         'description': f"Failed to parse file: {str(e)}",
                         'suggestion': 'Check syntax errors'}],
            'line_count': 0
        }

def analyze_javascript_vue_file(file_path: str) -> Dict[str, Any]:
    """Analyze JavaScript/Vue file for functions and hardcodes"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.splitlines()
        functions = []
        hardcodes = []
        problems = []

        # Simple regex-based analysis for JS/Vue
        function_pattern = re.compile(r'(?:function\s+(\w+)|(\w+)\s*[:=]\s*(?:async\s+)?function|\b(\w+)\s*\(.*?\)\s*\{|const\s+(\w+)\s*=\s*\(.*?\)\s*=>)')
        url_pattern = re.compile(r'[\'"`](https?://[^\'"` ]+)[\'"`]')
        api_pattern = re.compile(r'[\'"`](/api/[^\'"` ]+)[\'"`]')
        ip_pattern = re.compile(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')

        for i, line in enumerate(lines, 1):
            # Find functions
            func_matches = function_pattern.findall(line)
            for match in func_matches:
                func_name = next(name for name in match if name)
                if func_name and not func_name.startswith('_'):
                    functions.append({
                        'name': func_name,
                        'line': i,
                        'type': 'function'
                    })

            # Find URLs
            url_matches = url_pattern.findall(line)
            for url in url_matches:
                hardcodes.append({
                    'type': 'url',
                    'value': url,
                    'line': i,
                    'context': line.strip()
                })

            # Find API paths
            api_matches = api_pattern.findall(line)
            for api_path in api_matches:
                hardcodes.append({
                    'type': 'api_path',
                    'value': api_path,
                    'line': i,
                    'context': line.strip()
                })

            # Find IP addresses
            ip_matches = ip_pattern.findall(line)
            for ip in ip_matches:
                if ip.startswith('172.16.168.') or ip.startswith('127.0.0.') or ip.startswith('192.168.'):
                    hardcodes.append({
                        'type': 'ip',
                        'value': ip,
                        'line': i,
                        'context': line.strip()
                    })

            # Check for console.log (potential debugging leftover)
            if 'console.log' in line and not line.strip().startswith('//'):
                problems.append({
                    'type': 'debug_code',
                    'severity': 'low',
                    'line': i,
                    'description': 'console.log statement found',
                    'suggestion': 'Remove debug statements before production'
                })

        return {
            'functions': functions,
            'classes': [],
            'imports': [],
            'hardcodes': hardcodes,
            'problems': problems,
            'line_count': len(lines)
        }

    except Exception as e:
        logger.error(f"Error analyzing JS/Vue file {file_path}: {e}")
        return {'functions': [], 'classes': [], 'imports': [], 'hardcodes': [], 'problems': [], 'line_count': 0}

async def scan_codebase(root_path: str = "/home/kali/Desktop/AutoBot") -> Dict[str, Any]:
    """Scan the entire codebase using MCP-like file operations"""

    # File extensions to analyze
    PYTHON_EXTENSIONS = {'.py'}
    JS_EXTENSIONS = {'.js', '.ts'}
    VUE_EXTENSIONS = {'.vue'}
    CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.ini', '.conf'}

    analysis_results = {
        'files': {},
        'stats': {
            'total_files': 0,
            'python_files': 0,
            'javascript_files': 0,
            'vue_files': 0,
            'config_files': 0,
            'other_files': 0,
            'total_lines': 0,
            'total_functions': 0,
            'total_classes': 0
        },
        'all_functions': [],
        'all_classes': [],
        'all_hardcodes': [],
        'all_problems': []
    }

    # Directories to skip
    SKIP_DIRS = {
        'node_modules', '.git', '__pycache__', '.pytest_cache',
        'dist', 'build', '.venv', 'venv', '.DS_Store', 'logs', 'temp'
    }

    try:
        root_path_obj = Path(root_path)

        # Walk through all files
        for file_path in root_path_obj.rglob('*'):
            if file_path.is_file():
                # Skip if in excluded directory
                if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
                    continue

                extension = file_path.suffix.lower()
                relative_path = str(file_path.relative_to(root_path_obj))

                analysis_results['stats']['total_files'] += 1

                file_analysis = None

                if extension in PYTHON_EXTENSIONS:
                    analysis_results['stats']['python_files'] += 1
                    file_analysis = analyze_python_file(str(file_path))

                elif extension in JS_EXTENSIONS:
                    analysis_results['stats']['javascript_files'] += 1
                    file_analysis = analyze_javascript_vue_file(str(file_path))

                elif extension in VUE_EXTENSIONS:
                    analysis_results['stats']['vue_files'] += 1
                    file_analysis = analyze_javascript_vue_file(str(file_path))

                elif extension in CONFIG_EXTENSIONS:
                    analysis_results['stats']['config_files'] += 1

                else:
                    analysis_results['stats']['other_files'] += 1

                if file_analysis:
                    analysis_results['files'][relative_path] = file_analysis
                    analysis_results['stats']['total_lines'] += file_analysis.get('line_count', 0)
                    analysis_results['stats']['total_functions'] += len(file_analysis.get('functions', []))
                    analysis_results['stats']['total_classes'] += len(file_analysis.get('classes', []))

                    # Aggregate data
                    for func in file_analysis.get('functions', []):
                        func['file_path'] = relative_path
                        analysis_results['all_functions'].append(func)

                    for cls in file_analysis.get('classes', []):
                        cls['file_path'] = relative_path
                        analysis_results['all_classes'].append(cls)

                    for hardcode in file_analysis.get('hardcodes', []):
                        hardcode['file_path'] = relative_path
                        analysis_results['all_hardcodes'].append(hardcode)

                    for problem in file_analysis.get('problems', []):
                        problem['file_path'] = relative_path
                        analysis_results['all_problems'].append(problem)

        # Calculate average file size
        if analysis_results['stats']['total_files'] > 0:
            analysis_results['stats']['average_file_size'] = analysis_results['stats']['total_lines'] / analysis_results['stats']['total_files']
        else:
            analysis_results['stats']['average_file_size'] = 0

        analysis_results['stats']['last_indexed'] = datetime.now().isoformat()

        return analysis_results

    except Exception as e:
        logger.error(f"Error scanning codebase: {e}")
        raise HTTPException(status_code=500, detail=f"Codebase scan failed: {str(e)}")

@router.post("/index")
async def index_codebase(root_path: str = "/home/kali/Desktop/AutoBot"):
    """Index the AutoBot codebase and store results (Redis or in-memory)"""
    try:
        logger.info(f"Starting codebase indexing for: {root_path}")

        # Scan the codebase
        analysis_results = await scan_codebase(root_path)

        # Try to get Redis connection
        redis_client = await get_redis_connection()

        if redis_client:
            storage_type = "redis"
            # Store in Redis DB 11
            redis_client.set("codebase:analysis:full", json.dumps(analysis_results))
            redis_client.set("codebase:analysis:timestamp", datetime.now().isoformat())

            # Store aggregated stats
            redis_client.hset("codebase:stats", mapping=analysis_results['stats'])

            # Store function index
            for func in analysis_results['all_functions']:
                func_key = f"codebase:functions:{func['name']}"
                redis_client.sadd(func_key, json.dumps(func))

            # Store class index
            for cls in analysis_results['all_classes']:
                cls_key = f"codebase:classes:{cls['name']}"
                redis_client.sadd(cls_key, json.dumps(cls))

            # Store problems by type
            problems_by_type = defaultdict(list)
            for problem in analysis_results['all_problems']:
                problems_by_type[problem['type']].append(problem)

            for problem_type, problems in problems_by_type.items():
                redis_client.set(f"codebase:problems:{problem_type}", json.dumps(problems))

            # Store hardcodes by type
            hardcodes_by_type = defaultdict(list)
            for hardcode in analysis_results['all_hardcodes']:
                hardcodes_by_type[hardcode['type']].append(hardcode)

            for hardcode_type, hardcodes in hardcodes_by_type.items():
                redis_client.set(f"codebase:hardcodes:{hardcode_type}", json.dumps(hardcodes))

            # Set expiration for cached data (24 hours)
            for key in redis_client.scan_iter(match="codebase:*"):
                redis_client.expire(key, 86400)
        else:
            # Use in-memory storage
            storage_type = "memory"
            global _in_memory_storage
            storage = InMemoryStorage()
            _in_memory_storage = storage

            # Store main analysis data
            storage.set("codebase:analysis:full", json.dumps(analysis_results))
            storage.set("codebase:analysis:timestamp", datetime.now().isoformat())

            # Store aggregated stats
            storage.hset("codebase:stats", analysis_results['stats'])

            # Store function index
            for func in analysis_results['all_functions']:
                func_key = f"codebase:functions:{func['name']}"
                storage.sadd(func_key, json.dumps(func))

            # Store class index
            for cls in analysis_results['all_classes']:
                cls_key = f"codebase:classes:{cls['name']}"
                storage.sadd(cls_key, json.dumps(cls))

            # Store problems and hardcodes
            problems_by_type = defaultdict(list)
            for problem in analysis_results['all_problems']:
                problems_by_type[problem['type']].append(problem)

            for problem_type, problems in problems_by_type.items():
                storage.set(f"codebase:problems:{problem_type}", json.dumps(problems))

            hardcodes_by_type = defaultdict(list)
            for hardcode in analysis_results['all_hardcodes']:
                hardcodes_by_type[hardcode['type']].append(hardcode)

            for hardcode_type, hardcodes in hardcodes_by_type.items():
                storage.set(f"codebase:hardcodes:{hardcode_type}", json.dumps(hardcodes))

        logger.info(f"Codebase indexing completed using {storage_type}. Analyzed {analysis_results['stats']['total_files']} files")

        return JSONResponse({
            "status": "success",
            "message": f"Indexed {analysis_results['stats']['total_files']} files using {storage_type} storage",
            "stats": analysis_results['stats'],
            "storage_type": storage_type,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Codebase indexing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")

@router.get("/stats")
async def get_codebase_stats():
    """Get real codebase statistics from storage"""
    try:
        redis_client = await get_redis_connection()

        if redis_client:
            # Get stats from Redis
            stats = redis_client.hgetall("codebase:stats")
            timestamp = redis_client.get("codebase:analysis:timestamp") or "Never"
            storage_type = "redis"
        else:
            # Get stats from in-memory storage
            global _in_memory_storage
            if not _in_memory_storage:
                return JSONResponse({
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "stats": None
                })

            storage = _in_memory_storage
            stats = storage.hgetall("codebase:stats")
            timestamp = storage.get("codebase:analysis:timestamp") or "Never"
            storage_type = "memory"

        if not stats:
            return JSONResponse({
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "stats": None
            })

        # Convert string values back to appropriate types
        numeric_fields = ['total_files', 'python_files', 'javascript_files', 'vue_files', 'config_files', 'other_files', 'total_lines', 'total_functions', 'total_classes']
        for field in numeric_fields:
            if field in stats:
                stats[field] = int(stats[field])

        if 'average_file_size' in stats:
            stats['average_file_size'] = float(stats['average_file_size'])

        return JSONResponse({
            "status": "success",
            "stats": stats,
            "last_indexed": timestamp,
            "storage_type": storage_type
        })

    except Exception as e:
        logger.error(f"Failed to get codebase stats: {e}")
        raise HTTPException(status_code=500, detail=f"Stats retrieval failed: {str(e)}")

@router.get("/hardcodes")
async def get_hardcoded_values(hardcode_type: Optional[str] = None):
    """Get real hardcoded values found in the codebase"""
    try:
        redis_client = await get_redis_connection()

        all_hardcodes = []

        if redis_client:
            if hardcode_type:
                hardcodes_data = redis_client.get(f"codebase:hardcodes:{hardcode_type}")
                if hardcodes_data:
                    all_hardcodes = json.loads(hardcodes_data)
            else:
                for key in redis_client.scan_iter(match="codebase:hardcodes:*"):
                    hardcodes_data = redis_client.get(key)
                    if hardcodes_data:
                        all_hardcodes.extend(json.loads(hardcodes_data))
            storage_type = "redis"
        else:
            global _in_memory_storage
            if not _in_memory_storage:
                return JSONResponse({
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "hardcodes": []
                })

            storage = _in_memory_storage
            if hardcode_type:
                hardcodes_data = storage.get(f"codebase:hardcodes:{hardcode_type}")
                if hardcodes_data:
                    all_hardcodes = json.loads(hardcodes_data)
            else:
                for key in storage.scan_iter("codebase:hardcodes:*"):
                    hardcodes_data = storage.get(key)
                    if hardcodes_data:
                        all_hardcodes.extend(json.loads(hardcodes_data))
            storage_type = "memory"

        # Sort by file and line number
        all_hardcodes.sort(key=lambda x: (x.get('file_path', ''), x.get('line', 0)))

        return JSONResponse({
            "status": "success",
            "hardcodes": all_hardcodes,
            "total_count": len(all_hardcodes),
            "hardcode_types": list(set(h.get('type', 'unknown') for h in all_hardcodes)),
            "storage_type": storage_type
        })

    except Exception as e:
        logger.error(f"Failed to get hardcoded values: {e}")
        raise HTTPException(status_code=500, detail=f"Hardcodes retrieval failed: {str(e)}")

@router.get("/problems")
async def get_codebase_problems(problem_type: Optional[str] = None):
    """Get real code problems detected during analysis"""
    try:
        redis_client = await get_redis_connection()

        all_problems = []

        if redis_client:
            if problem_type:
                problems_data = redis_client.get(f"codebase:problems:{problem_type}")
                if problems_data:
                    all_problems = json.loads(problems_data)
            else:
                for key in redis_client.scan_iter(match="codebase:problems:*"):
                    problems_data = redis_client.get(key)
                    if problems_data:
                        all_problems.extend(json.loads(problems_data))
            storage_type = "redis"
        else:
            global _in_memory_storage
            if not _in_memory_storage:
                return JSONResponse({
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "problems": []
                })

            storage = _in_memory_storage
            if problem_type:
                problems_data = storage.get(f"codebase:problems:{problem_type}")
                if problems_data:
                    all_problems = json.loads(problems_data)
            else:
                for key in storage.scan_iter("codebase:problems:*"):
                    problems_data = storage.get(key)
                    if problems_data:
                        all_problems.extend(json.loads(problems_data))
            storage_type = "memory"

        # Sort by severity (high, medium, low)
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        all_problems.sort(key=lambda x: (severity_order.get(x.get('severity', 'low'), 3), x.get('file_path', '')))

        return JSONResponse({
            "status": "success",
            "problems": all_problems,
            "total_count": len(all_problems),
            "problem_types": list(set(p.get('type', 'unknown') for p in all_problems)),
            "storage_type": storage_type
        })

    except Exception as e:
        logger.error(f"Failed to get codebase problems: {e}")
        raise HTTPException(status_code=500, detail=f"Problems retrieval failed: {str(e)}")

@router.delete("/cache")
async def clear_codebase_cache():
    """Clear codebase analysis cache from storage"""
    try:
        redis_client = await get_redis_connection()

        if redis_client:
            # Get all codebase keys
            keys_to_delete = []
            for key in redis_client.scan_iter(match="codebase:*"):
                keys_to_delete.append(key)

            if keys_to_delete:
                redis_client.delete(*keys_to_delete)

            storage_type = "redis"
        else:
            # Clear in-memory storage
            global _in_memory_storage
            if _in_memory_storage:
                keys_to_delete = []
                for key in _in_memory_storage.scan_iter("codebase:*"):
                    keys_to_delete.append(key)

                _in_memory_storage.delete(*keys_to_delete)
                deleted_count = len(keys_to_delete)
            else:
                deleted_count = 0

            storage_type = "memory"

        return JSONResponse({
            "status": "success",
            "message": f"Cleared {len(keys_to_delete) if redis_client else deleted_count} cache entries from {storage_type}",
            "deleted_keys": len(keys_to_delete) if redis_client else deleted_count,
            "storage_type": storage_type
        })

    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")