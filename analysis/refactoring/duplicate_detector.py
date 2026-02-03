#!/usr/bin/env python3
"""
Manual Duplicate Code Detection Script
Identifies duplicate patterns in AutoBot codebase for refactoring
"""

import os
import re
import ast
import hashlib
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List


class DuplicateDetector:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.exclude_dirs = {
            'node_modules', '.git', '__pycache__', '.pytest_cache',
            'venv', 'env', 'dist', 'build', 'temp', 'logs'
        }
        self.exclude_files = {
            '__pycache__', '.pyc', '.pyo', '.git', '.log'
        }

        # Storage for different types of duplicates
        self.function_duplicates = defaultdict(list)
        self.class_duplicates = defaultdict(list)
        self.import_patterns = defaultdict(list)
        self.config_patterns = defaultdict(list)
        self.api_patterns = defaultdict(list)
        self.string_patterns = defaultdict(list)

    def should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded from analysis"""
        # Exclude specific directories
        if any(exclude_dir in path.parts for exclude_dir in self.exclude_dirs):
            return True

        # Exclude non-code files
        if path.suffix not in {'.py', '.js', '.vue', '.ts', '.jsx', '.tsx'}:
            return True

        return False

    def get_code_files(self) -> List[Path]:
        """Get all code files for analysis"""
        files = []
        for file_path in self.root_path.rglob('*'):
            if file_path.is_file() and not self.should_exclude(file_path):
                files.append(file_path)
        return files

    def normalize_code(self, code: str) -> str:
        """Normalize code for comparison - remove whitespace, comments"""
        # Remove comments
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Remove extra whitespace
        code = re.sub(r'\s+', ' ', code)
        code = code.strip()

        return code

    def extract_functions(self, content: str, file_path: Path) -> List[Dict]:
        """Extract function definitions from Python files"""
        functions = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Get function source
                    lines = content.split('\n')
                    start_line = node.lineno - 1
                    end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 10

                    func_source = '\n'.join(lines[start_line:end_line])
                    normalized = self.normalize_code(func_source)

                    if len(normalized) > 50:  # Only check substantial functions
                        functions.append({
                            'name': node.name,
                            'source': func_source,
                            'normalized': normalized,
                            'file': str(file_path),
                            'line': node.lineno,
                            'hash': hashlib.md5(normalized.encode()).hexdigest()
                        })
        except SyntaxError:
            pass  # Skip files with syntax errors

        return functions

    def extract_classes(self, content: str, file_path: Path) -> List[Dict]:
        """Extract class definitions from Python files"""
        classes = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Get class source
                    lines = content.split('\n')
                    start_line = node.lineno - 1
                    end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 20

                    class_source = '\n'.join(lines[start_line:end_line])
                    normalized = self.normalize_code(class_source)

                    if len(normalized) > 100:  # Only check substantial classes
                        classes.append({
                            'name': node.name,
                            'source': class_source,
                            'normalized': normalized,
                            'file': str(file_path),
                            'line': node.lineno,
                            'hash': hashlib.md5(normalized.encode()).hexdigest()
                        })
        except SyntaxError:
            pass  # Skip files with syntax errors

        return classes

    def extract_import_patterns(self, content: str, file_path: Path) -> List[str]:
        """Extract import statements for pattern analysis"""
        imports = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith(('import ', 'from ')):
                normalized = self.normalize_code(line)
                imports.append(normalized)
        return imports

    def extract_api_patterns(self, content: str, file_path: Path) -> List[Dict]:
        """Extract API route patterns and decorators"""
        patterns = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line = line.strip()

            # Flask/FastAPI route patterns
            if any(pattern in line for pattern in ['@app.route', '@router.', '@api.', 'app.get', 'app.post']):
                # Get surrounding context
                start = max(0, i-2)
                end = min(len(lines), i+5)
                context = '\n'.join(lines[start:end])
                normalized = self.normalize_code(context)

                patterns.append({
                    'pattern': line,
                    'context': context,
                    'normalized': normalized,
                    'file': str(file_path),
                    'line': i+1,
                    'hash': hashlib.md5(normalized.encode()).hexdigest()
                })

        return patterns

    def extract_config_patterns(self, content: str, file_path: Path) -> List[Dict]:
        """Extract configuration and initialization patterns"""
        patterns = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Configuration patterns
            if any(pattern in line_stripped for pattern in [
                'redis.Redis(', 'Redis(', 'redis_client =', 'RedisClient(',
                'FastAPI(', 'Flask(', 'app = ', 'client = ',
                'config =', 'Config(', 'settings =', 'REDIS_HOST',
                'BACKEND_URL', 'API_URL', 'DATABASE_URL'
            ]):
                # Get multi-line context for configuration blocks
                start = max(0, i-3)
                end = min(len(lines), i+8)
                context = '\n'.join(lines[start:end])
                normalized = self.normalize_code(context)

                if len(normalized) > 30:
                    patterns.append({
                        'pattern': line_stripped,
                        'context': context,
                        'normalized': normalized,
                        'file': str(file_path),
                        'line': i+1,
                        'hash': hashlib.md5(normalized.encode()).hexdigest()
                    })

        return patterns

    def find_string_patterns(self, content: str, file_path: Path) -> List[Dict]:
        """Find repeated string literals and hardcoded values"""
        patterns = []

        # Find URLs, IPs, connection strings
        url_pattern = r'https?://[^\s"\']+'
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        redis_pattern = r'redis://[^\s"\']+'

        for pattern_type, regex in [
            ('url', url_pattern),
            ('ip', ip_pattern),
            ('redis_url', redis_pattern)
        ]:
            matches = re.finditer(regex, content)
            for match in matches:
                value = match.group()
                line_num = content[:match.start()].count('\n') + 1

                patterns.append({
                    'type': pattern_type,
                    'value': value,
                    'file': str(file_path),
                    'line': line_num,
                    'hash': hashlib.md5(value.encode()).hexdigest()
                })

        return patterns

    def analyze_file(self, file_path: Path):
        """Analyze a single file for duplicate patterns"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Extract different types of patterns
            if file_path.suffix == '.py':
                functions = self.extract_functions(content, file_path)
                classes = self.extract_classes(content, file_path)

                for func in functions:
                    self.function_duplicates[func['hash']].append(func)

                for cls in classes:
                    self.class_duplicates[cls['hash']].append(cls)

                imports = self.extract_import_patterns(content, file_path)
                for imp in imports:
                    self.import_patterns[imp].append(str(file_path))

            # Extract patterns from all file types
            api_patterns = self.extract_api_patterns(content, file_path)
            for pattern in api_patterns:
                self.api_patterns[pattern['hash']].append(pattern)

            config_patterns = self.extract_config_patterns(content, file_path)
            for pattern in config_patterns:
                self.config_patterns[pattern['hash']].append(pattern)

            string_patterns = self.find_string_patterns(content, file_path)
            for pattern in string_patterns:
                self.string_patterns[pattern['hash']].append(pattern)

        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")

    def run_analysis(self) -> Dict:
        """Run complete duplicate analysis"""
        print(f"🔍 Analyzing codebase at: {self.root_path}")

        files = self.get_code_files()
        print(f"📁 Found {len(files)} code files to analyze")

        for i, file_path in enumerate(files):
            if i % 50 == 0:
                print(f"   Processed {i}/{len(files)} files...")
            self.analyze_file(file_path)

        # Find duplicates (patterns that appear 2+ times)
        results = {
            'total_files': len(files),
            'duplicate_functions': [],
            'duplicate_classes': [],
            'duplicate_imports': [],
            'duplicate_api_patterns': [],
            'duplicate_config_patterns': [],
            'duplicate_strings': [],
            'summary': {}
        }

        # Function duplicates
        for hash_key, functions in self.function_duplicates.items():
            if len(functions) >= 2:
                results['duplicate_functions'].append({
                    'count': len(functions),
                    'functions': functions,
                    'sample_code': functions[0]['source'][:200]
                })

        # Class duplicates
        for hash_key, classes in self.class_duplicates.items():
            if len(classes) >= 2:
                results['duplicate_classes'].append({
                    'count': len(classes),
                    'classes': classes,
                    'sample_code': classes[0]['source'][:200]
                })

        # Import duplicates
        for import_stmt, files in self.import_patterns.items():
            if len(files) >= 5:  # Only report imports used in 5+ files
                results['duplicate_imports'].append({
                    'count': len(files),
                    'import': import_stmt,
                    'files': files
                })

        # API pattern duplicates
        for hash_key, patterns in self.api_patterns.items():
            if len(patterns) >= 2:
                results['duplicate_api_patterns'].append({
                    'count': len(patterns),
                    'patterns': patterns,
                    'sample_code': patterns[0]['context'][:200]
                })

        # Config pattern duplicates
        for hash_key, patterns in self.config_patterns.items():
            if len(patterns) >= 3:  # Config patterns need 3+ occurrences
                results['duplicate_config_patterns'].append({
                    'count': len(patterns),
                    'patterns': patterns,
                    'sample_code': patterns[0]['context'][:200]
                })

        # String pattern duplicates
        string_counts = Counter()
        for hash_key, patterns in self.string_patterns.items():
            if len(patterns) >= 3:
                value = patterns[0]['value']
                string_counts[value] = len(patterns)
                results['duplicate_strings'].append({
                    'count': len(patterns),
                    'value': value,
                    'type': patterns[0]['type'],
                    'occurrences': patterns
                })

        # Summary
        results['summary'] = {
            'total_duplicate_functions': len(results['duplicate_functions']),
            'total_duplicate_classes': len(results['duplicate_classes']),
            'total_duplicate_imports': len(results['duplicate_imports']),
            'total_duplicate_api_patterns': len(results['duplicate_api_patterns']),
            'total_duplicate_config_patterns': len(results['duplicate_config_patterns']),
            'total_duplicate_strings': len(results['duplicate_strings']),
            'total_patterns': (
                len(results['duplicate_functions']) +
                len(results['duplicate_classes']) +
                len(results['duplicate_imports']) +
                len(results['duplicate_api_patterns']) +
                len(results['duplicate_config_patterns']) +
                len(results['duplicate_strings'])
            )
        }

        return results


def main():
    detector = DuplicateDetector('/home/kali/Desktop/AutoBot')
    results = detector.run_analysis()

    print("\n" + "="*60)
    print("🎯 DUPLICATE CODE ANALYSIS RESULTS")
    print("="*60)

    summary = results['summary']
    print("📊 SUMMARY:")
    print(f"   Total duplicate patterns found: {summary['total_patterns']}")
    print(f"   - Duplicate functions: {summary['total_duplicate_functions']}")
    print(f"   - Duplicate classes: {summary['total_duplicate_classes']}")
    print(f"   - Duplicate imports: {summary['total_duplicate_imports']}")
    print(f"   - Duplicate API patterns: {summary['total_duplicate_api_patterns']}")
    print(f"   - Duplicate config patterns: {summary['total_duplicate_config_patterns']}")
    print(f"   - Duplicate strings: {summary['total_duplicate_strings']}")

    # Show top duplicates
    print("\n🔄 TOP FUNCTION DUPLICATES:")
    for dup in sorted(results['duplicate_functions'], key=lambda x: x['count'], reverse=True)[:5]:
        print(f"   {dup['count']} occurrences: {dup['functions'][0]['name']}")
        for func in dup['functions']:
            print(f"     - {func['file']}:{func['line']}")

    print("\n🔄 TOP CONFIGURATION DUPLICATES:")
    for dup in sorted(results['duplicate_config_patterns'], key=lambda x: x['count'], reverse=True)[:5]:
        print(f"   {dup['count']} occurrences: {dup['patterns'][0]['pattern'][:50]}...")
        for pattern in dup['patterns']:
            print(f"     - {pattern['file']}:{pattern['line']}")

    print("\n🔄 TOP STRING DUPLICATES:")
    for dup in sorted(results['duplicate_strings'], key=lambda x: x['count'], reverse=True)[:5]:
        print(f"   {dup['count']} occurrences: {dup['value']}")
        for occ in dup['occurrences'][:3]:  # Show first 3
            print(f"     - {occ['file']}:{occ['line']}")

    # Save detailed results
    import json
    output_file = '/home/kali/Desktop/AutoBot/analysis/refactoring/duplicate_analysis_results.json'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n💾 Detailed results saved to: {output_file}")

    return results


if __name__ == "__main__":
    main()
