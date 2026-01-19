#!/usr/bin/env python3
"""Fix critical flake8 errors (F811, F841)."""

import ast
import os
from pathlib import Path


class UnusedVariableFixer(ast.NodeTransformer):
    """Fix unused variable assignments by prefixing with underscore."""
    
    def __init__(self):
        self.unused_vars = set()
        self.used_vars = set()
        self.current_scope = []
        
    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            # Variable assignment
            if self.current_scope:
                self.current_scope[-1].add(node.id)
        elif isinstance(node.ctx, ast.Load):
            # Variable usage
            self.used_vars.add(node.id)
        return node
    
    def visit_FunctionDef(self, node):
        # Enter new scope
        self.current_scope.append(set())
        self.generic_visit(node)
        # Check for unused vars in this scope
        scope_vars = self.current_scope.pop()
        for var in scope_vars:
            if var not in self.used_vars and not var.startswith('_'):
                self.unused_vars.add(var)
        return node


def fix_file(filepath):
    """Fix critical issues in a single file."""
    try:
        filepath_str = str(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        modified = False
        lines = content.splitlines(keepends=True)
        
        # Fix specific known issues
        if filepath_str.endswith('backend/api/advanced_workflow_orchestrator.py'):
            # Fix F811: redefinition of 'asyncio'
            for i, line in enumerate(lines):
                if line.strip() == 'import asyncio' and i > 100:  # Skip first import
                    lines[i] = '# ' + line  # Comment out duplicate import
                    modified = True
                    print(f"Fixed F811 in {filepath}: commented duplicate asyncio import")
        
        # Fix F841: unused variables in specific files
        if filepath_str.endswith('backend/api/advanced_workflow_orchestrator.py'):
            for i, line in enumerate(lines):
                if 'workflow = self.active_workflows.get(workflow_id)' in line:
                    # Check if 'workflow' is used in next few lines
                    used = False
                    for j in range(i+1, min(i+10, len(lines))):
                        if 'workflow' in lines[j]:
                            used = True
                            break
                    if not used:
                        lines[i] = line.replace('workflow =', '_ =')
                        modified = True
                        print(f"Fixed F841 in {filepath}: renamed unused 'workflow' to '_'")
                
                if 'complexity_mapping = {' in line:
                    # This variable is defined but not used
                    lines[i] = line.replace('complexity_mapping =', '_ =')
                    modified = True
                    print(f"Fixed F841 in {filepath}: renamed unused 'complexity_mapping' to '_'")
        
        if filepath_str.endswith('src/takeover_manager.py'):
            for i, line in enumerate(lines):
                if 'request = {"user": user' in line:
                    lines[i] = line.replace('request =', '_ =')
                    modified = True
                    print(f"Fixed F841 in {filepath}: renamed unused 'request' to '_'")
        
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return True
        return False
        
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix critical flake8 errors."""
    root_dir = Path(__file__).parent.parent
    fixed_count = 0
    
    files_to_fix = [
        'backend/api/advanced_workflow_orchestrator.py',
        'src/takeover_manager.py',
    ]
    
    for filepath in files_to_fix:
        full_path = root_dir / filepath
        if full_path.exists():
            if fix_file(full_path):
                fixed_count += 1
        else:
            print(f"File not found: {filepath}")
    
    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()