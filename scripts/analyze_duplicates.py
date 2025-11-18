#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase Duplicate Detection Script

Analyzes the AutoBot codebase to detect:
1. Duplicate function declarations
2. Duplicate class declarations  
3. Similar code patterns
4. Potential refactoring opportunities

Uses the same patterns as the Codebase Analytics System.
"""

import os
import re
import json
from collections import defaultdict, Counter
from pathlib import Path


class DuplicateDetector:
    def __init__(self, root_path):
        self.root_path = Path(root_path)
        self.supported_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx'}
        
        # Regex patterns for different languages
        self.patterns = {
            "python_functions": [
                r"def\s+(\w+)\s*\(",
                r"async\s+def\s+(\w+)\s*\(",
            ],
            "python_classes": [
                r"class\s+(\w+)(?:\s*\([^)]*\))?\s*:",
            ],
            "js_functions": [
                r"function\s+(\w+)\s*\(",
                r"const\s+(\w+)\s*=\s*\(",
                r"(\w+)\s*=\s*async\s*\(",
                r"async\s+function\s+(\w+)\s*\(",
            ],
            "js_classes": [
                r"class\s+(\w+)",
            ],
        }
        
    def get_code_files(self):
        """Get all code files in the project"""
        files = []
        for root, dirs, filenames in os.walk(self.root_path):
            # Skip common ignore directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                'node_modules', '__pycache__', '.git', 'dist', 'build', 'target', 'venv'
            }]
            
            for filename in filenames:
                if any(filename.endswith(ext) for ext in self.supported_extensions):
                    files.append(Path(root) / filename)
        return files
    
    def extract_declarations(self, file_path):
        """Extract function and class declarations from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return []
            
        declarations = []
        language = 'python' if file_path.suffix == '.py' else 'js'
        
        # Select appropriate patterns
        pattern_groups = []
        if language == 'python':
            pattern_groups = ['python_functions', 'python_classes']
        else:
            pattern_groups = ['js_functions', 'js_classes']
        
        lines = content.split('\n')
        for pattern_group in pattern_groups:
            for pattern in self.patterns[pattern_group]:
                for i, line in enumerate(lines):
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        name = match.group(1) if match.groups() else match.group(0)
                        if name and len(name) > 1:
                            declarations.append({
                                'name': name,
                                'type': pattern_group.split('_')[-1][:-1],  # function/class
                                'file': str(file_path.relative_to(self.root_path)),
                                'line': i + 1,
                                'definition': line.strip(),
                                'language': language
                            })
        
        return declarations
    
    def analyze_duplicates(self):
        """Analyze codebase for duplicate declarations"""
        print("🔍 Analyzing AutoBot codebase for duplicates...")
        
        files = self.get_code_files()
        print(f"📁 Found {len(files)} code files to analyze")
        
        all_declarations = []
        declaration_names = defaultdict(list)
        
        # Extract declarations from all files
        for file_path in files:
            declarations = self.extract_declarations(file_path)
            all_declarations.extend(declarations)
            
            for decl in declarations:
                declaration_names[decl['name']].append(decl)
        
        # Find duplicates
        duplicates = {name: decls for name, decls in declaration_names.items() if len(decls) > 1}
        
        return {
            'total_declarations': len(all_declarations),
            'unique_names': len(declaration_names),
            'duplicate_names': len(duplicates),
            'duplicates': duplicates,
            'all_declarations': all_declarations
        }
    
    def generate_report(self, analysis):
        """Generate a comprehensive duplicate detection report"""
        print("\n" + "="*80)
        print("📊 AUTOBOT DUPLICATE DECLARATION ANALYSIS REPORT")
        print("="*80)
        
        print(f"\n📈 SUMMARY STATISTICS:")
        print(f"  • Total Declarations Found: {analysis['total_declarations']}")
        print(f"  • Unique Declaration Names: {analysis['unique_names']}")
        print(f"  • Duplicate Declaration Names: {analysis['duplicate_names']}")
        print(f"  • Duplication Rate: {(analysis['duplicate_names']/analysis['unique_names']*100):.1f}%")
        
        # Top duplicate declarations
        print(f"\n🔥 TOP DUPLICATE DECLARATIONS:")
        duplicates_by_count = sorted(
            analysis['duplicates'].items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        )
        
        for i, (name, decls) in enumerate(duplicates_by_count[:10]):
            print(f"\n{i+1:2d}. '{name}' - {len(decls)} occurrences")
            
            # Group by type and language
            by_type = defaultdict(list)
            for decl in decls:
                by_type[f"{decl['language']}_{decl['type']}"].append(decl)
            
            for type_lang, items in by_type.items():
                print(f"    📁 {type_lang}: {len(items)} files")
                for item in items[:3]:  # Show first 3
                    print(f"      • {item['file']}:{item['line']}")
                if len(items) > 3:
                    print(f"      • ... and {len(items)-3} more")
        
        # Potential refactoring opportunities
        print(f"\n🛠️  REFACTORING OPPORTUNITIES:")
        
        high_priority = [(name, decls) for name, decls in duplicates_by_count if len(decls) >= 5]
        medium_priority = [(name, decls) for name, decls in duplicates_by_count if 3 <= len(decls) < 5]
        
        print(f"\n🔴 HIGH PRIORITY (5+ duplicates): {len(high_priority)} items")
        for name, decls in high_priority[:5]:
            python_count = len([d for d in decls if d['language'] == 'python'])
            js_count = len([d for d in decls if d['language'] == 'js'])
            print(f"  • '{name}': {len(decls)} total (Python: {python_count}, JS: {js_count})")
        
        print(f"\n🟡 MEDIUM PRIORITY (3-4 duplicates): {len(medium_priority)} items")
        for name, decls in medium_priority[:5]:
            types = Counter(d['type'] for d in decls)
            type_summary = ', '.join(f"{t}:{c}" for t, c in types.items())
            print(f"  • '{name}': {len(decls)} total ({type_summary})")
        
        # Language breakdown
        print(f"\n🌐 LANGUAGE BREAKDOWN:")
        lang_stats = defaultdict(int)
        type_stats = defaultdict(int)
        
        for decl in analysis['all_declarations']:
            lang_stats[decl['language']] += 1
            type_stats[decl['type']] += 1
        
        for lang, count in lang_stats.items():
            print(f"  • {lang.upper()}: {count} declarations")
        
        print(f"\n📊 TYPE BREAKDOWN:")
        for type_name, count in type_stats.items():
            print(f"  • {type_name.upper()}S: {count} declarations")
        
        # Specific recommendations
        print(f"\n💡 SPECIFIC RECOMMENDATIONS:")
        
        if high_priority:
            print(f"  🔥 CRITICAL: Review '{high_priority[0][0]}' - {len(high_priority[0][1])} duplicates")
            print(f"     Consider creating a base class or utility function")
        
        common_names = [name for name, decls in duplicates_by_count[:20] 
                       if any(word in name.lower() for word in ['init', 'setup', 'config', 'handler', 'process'])]
        if common_names:
            print(f"  🔧 PATTERN: Common initialization patterns found:")
            for name in common_names[:3]:
                print(f"     • '{name}' - Consider standardization")
        
        test_duplicates = [name for name, decls in duplicates_by_count 
                          if 'test' in name.lower() and len(decls) > 2]
        if test_duplicates:
            print(f"  🧪 TESTING: {len(test_duplicates)} test function patterns could be unified")
        
        return analysis

def main():
    """Main execution function"""
    root_path = "/home/kali/Desktop/AutoBot"
    
    if not os.path.exists(root_path):
        print(f"❌ Error: AutoBot directory not found at {root_path}")
        return
    
    detector = DuplicateDetector(root_path)
    analysis = detector.analyze_duplicates()
    detector.generate_report(analysis)
    
    # Save detailed results
    output_file = "/home/kali/Desktop/AutoBot/reports/duplicate_analysis_results.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Prepare serializable data
    serializable_analysis = {
        'total_declarations': analysis['total_declarations'],
        'unique_names': analysis['unique_names'], 
        'duplicate_names': analysis['duplicate_names'],
        'duplicates': {name: decls for name, decls in analysis['duplicates'].items()},
        'summary_stats': {
            'duplication_rate': analysis['duplicate_names']/analysis['unique_names']*100,
            'top_duplicates': sorted(analysis['duplicates'].items(), key=lambda x: len(x[1]), reverse=True)[:20]
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(serializable_analysis, f, indent=2)
    
    print(f"\n💾 Detailed analysis saved to: {output_file}")
    print(f"\n✅ Duplicate detection analysis complete!")

if __name__ == "__main__":
    main()