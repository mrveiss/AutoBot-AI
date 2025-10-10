#!/usr/bin/env python3
"""
Standalone Codebase Analytics Tester
Tests the codebase analysis functionality without Redis dependency
"""

import ast
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

class StandaloneCodebaseAnalyzer:
    """Standalone codebase analyzer that doesn't require Redis"""

    def __init__(self, root_path: str = "/home/kali/Desktop/AutoBot"):
        self.root_path = root_path
        self.analysis_data = {}

    def analyze_python_file(self, file_path: str) -> Dict[str, Any]:
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

            # Check content for hardcoded values using regex
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                # Look for IP addresses
                ip_matches = re.findall(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', line)
                for ip in ip_matches:
                    if ip.startswith('172.16.168.'):
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
                    if port in ['8001', '8080', '6379', '11434', '5173']:
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

    def analyze_javascript_vue_file(self, file_path: str) -> Dict[str, Any]:
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
                    if ip.startswith('172.16.168.'):
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
            return {'functions': [], 'classes': [], 'imports': [], 'hardcodes': [], 'problems': [], 'line_count': 0}

    def scan_codebase(self) -> Dict[str, Any]:
        """Scan the entire codebase"""

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
            root_path_obj = Path(self.root_path)

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
                        file_analysis = self.analyze_python_file(str(file_path))

                    elif extension in JS_EXTENSIONS:
                        analysis_results['stats']['javascript_files'] += 1
                        file_analysis = self.analyze_javascript_vue_file(str(file_path))

                    elif extension in VUE_EXTENSIONS:
                        analysis_results['stats']['vue_files'] += 1
                        file_analysis = self.analyze_javascript_vue_file(str(file_path))

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

            # Store results in memory
            self.analysis_data = analysis_results

            return analysis_results

        except Exception as e:
            print(f"Error scanning codebase: {e}")
            return analysis_results

    def test_functionality(self):
        """Test all aspects of the codebase analysis"""
        print("🚀 Starting Standalone Codebase Analysis Test")
        print("=" * 60)

        start_time = time.time()

        # Test 1: Scan codebase
        print("\n🔍 Testing Codebase Scanning...")
        results = self.scan_codebase()

        stats = results.get('stats', {})
        print(f"✅ Scanned {stats.get('total_files', 0)} files in {time.time() - start_time:.2f} seconds")

        # Test 2: File type detection
        print("\n📁 Testing File Type Detection...")
        print(f"   • Python files: {stats.get('python_files', 0)}")
        print(f"   • JavaScript/TypeScript files: {stats.get('javascript_files', 0)}")
        print(f"   • Vue files: {stats.get('vue_files', 0)}")
        print(f"   • Config files: {stats.get('config_files', 0)}")
        print(f"   • Other files: {stats.get('other_files', 0)}")

        # Test 3: Function and class extraction
        print("\n🔧 Testing Function and Class Extraction...")
        functions = results.get('all_functions', [])
        classes = results.get('all_classes', [])
        print(f"   • Total functions found: {len(functions)}")
        print(f"   • Total classes found: {len(classes)}")

        if functions:
            print(f"   • Sample functions: {[f['name'] for f in functions[:5]]}")
        if classes:
            print(f"   • Sample classes: {[c['name'] for c in classes[:5]]}")

        # Test 4: Hardcode detection
        print("\n🔍 Testing Hardcode Detection...")
        hardcodes = results.get('all_hardcodes', [])
        print(f"   • Total hardcodes found: {len(hardcodes)}")

        hardcode_types = defaultdict(int)
        ip_addresses = set()

        for hardcode in hardcodes:
            hardcode_types[hardcode.get('type', 'unknown')] += 1
            if hardcode.get('type') == 'ip':
                ip_addresses.add(hardcode.get('value'))

        for htype, count in hardcode_types.items():
            print(f"   • {htype}: {count}")

        if ip_addresses:
            print(f"   • Found IP addresses: {sorted(ip_addresses)}")

        # Test 5: Problem detection
        print("\n⚠️  Testing Problem Detection...")
        problems = results.get('all_problems', [])
        print(f"   • Total problems found: {len(problems)}")

        problem_types = defaultdict(int)
        for problem in problems:
            problem_types[problem.get('type', 'unknown')] += 1

        for ptype, count in problem_types.items():
            print(f"   • {ptype}: {count}")

        # Test 6: Specific hardcode validation
        print("\n🎯 Testing Specific Hardcode Detection...")

        expected_ips = ['172.16.168.20', '172.16.168.21', '172.16.168.22', '172.16.168.23', '172.16.168.24', '172.16.168.25']
        expected_ports = ['8001', '8080', '6379', '11434', '5173']

        found_ips = [h['value'] for h in hardcodes if h.get('type') == 'ip']
        found_ports = [h['value'] for h in hardcodes if h.get('type') == 'port']

        for expected_ip in expected_ips:
            if expected_ip in found_ips:
                print(f"   ✅ Found expected IP: {expected_ip}")
            else:
                print(f"   ⚠️  Missing expected IP: {expected_ip}")

        for expected_port in expected_ports:
            if expected_port in found_ports:
                print(f"   ✅ Found expected port: {expected_port}")
            else:
                print(f"   ⚠️  Missing expected port: {expected_port}")

        # Test 7: Expected functions
        print("\n🔧 Testing Expected Function Detection...")

        expected_functions = [
            'scan_codebase', 'analyze_python_file', 'get_redis_connection',
            'index_codebase', 'get_codebase_stats'
        ]

        function_names = [f['name'] for f in functions]

        for expected_func in expected_functions:
            if expected_func in function_names:
                print(f"   ✅ Found expected function: {expected_func}")
            else:
                print(f"   ⚠️  Missing expected function: {expected_func}")

        # Generate summary
        print("\n" + "=" * 60)
        print("📋 ANALYSIS SUMMARY")
        print("=" * 60)

        success_indicators = 0
        total_indicators = 8

        if stats.get('total_files', 0) > 0:
            success_indicators += 1
        if stats.get('python_files', 0) > 0:
            success_indicators += 1
        if len(functions) > 0:
            success_indicators += 1
        if len(classes) > 0:
            success_indicators += 1
        if len(hardcodes) > 0:
            success_indicators += 1
        if any(ip in found_ips for ip in expected_ips):
            success_indicators += 1
        if any(port in found_ports for port in expected_ports):
            success_indicators += 1
        if any(func in function_names for func in expected_functions):
            success_indicators += 1

        success_rate = (success_indicators / total_indicators) * 100

        print(f"📊 Files analyzed: {stats.get('total_files', 0)}")
        print(f"📊 Total lines of code: {stats.get('total_lines', 0)}")
        print(f"📊 Functions found: {len(functions)}")
        print(f"📊 Classes found: {len(classes)}")
        print(f"📊 Hardcodes detected: {len(hardcodes)}")
        print(f"📊 Problems identified: {len(problems)}")
        print(f"📊 Processing time: {time.time() - start_time:.2f} seconds")
        print(f"🎯 Success rate: {success_rate:.1f}%")

        if success_rate >= 80:
            print("🎉 CODEBASE ANALYSIS SUCCESSFUL - All core functionality working!")
        elif success_rate >= 60:
            print("⚠️  CODEBASE ANALYSIS PARTIAL - Some features working")
        else:
            print("❌ CODEBASE ANALYSIS FAILED - Major issues detected")

        # Save results
        results_file = "/home/kali/Desktop/AutoBot/tests/results/standalone_codebase_analysis.json"
        Path(results_file).parent.mkdir(parents=True, exist_ok=True)

        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n📝 Full results saved to: {results_file}")

        return success_rate >= 80

def main():
    """Main test execution"""
    analyzer = StandaloneCodebaseAnalyzer()
    success = analyzer.test_functionality()
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)