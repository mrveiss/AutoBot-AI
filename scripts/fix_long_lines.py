#!/usr/bin/env python3
"""Fix long lines in Python files."""

import os
import re
from pathlib import Path


def fix_long_lines(filepath, max_length=88):
    """Fix long lines in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        modified = False
        new_lines = []
        
        for i, line in enumerate(lines):
            # Skip lines that are already within limit
            if len(line.rstrip()) <= max_length:
                new_lines.append(line)
                continue
            
            # Handle different types of long lines
            stripped = line.strip()
            
            # Long strings in logger/print statements
            if 'logger.' in line or 'logging.' in line or 'print(' in line:
                # Try to break at commas within function calls
                if '(' in line and ')' in line:
                    indent = len(line) - len(line.lstrip())
                    parts = re.split(r'([\(\)])', line)
                    new_line = ''
                    current_len = 0
                    
                    for part in parts:
                        if current_len + len(part) > max_length and part.strip():
                            new_line += '\n' + ' ' * (indent + 4) + part
                            current_len = indent + 4 + len(part)
                        else:
                            new_line += part
                            current_len += len(part)
                    
                    if new_line != line:
                        new_lines.append(new_line)
                        modified = True
                        continue
            
            # Long dictionaries
            if '{' in line and '}' in line and ':' in line:
                indent = len(line) - len(line.lstrip())
                # Split dictionary items
                dict_match = re.search(r'\{(.+)\}', line)
                if dict_match:
                    dict_content = dict_match.group(1)
                    items = [item.strip() for item in dict_content.split(',')]
                    
                    prefix = line[:dict_match.start()] + '{\n'
                    suffix = '\n' + ' ' * indent + '}'
                    
                    new_content = prefix
                    for item in items:
                        if item:
                            new_content += ' ' * (indent + 4) + item + ',\n'
                    new_content = new_content.rstrip(',\n') + suffix
                    
                    if line.endswith('\n'):
                        new_content += '\n'
                    
                    new_lines.append(new_content)
                    modified = True
                    continue
            
            # Long function calls
            if '(' in line and ')' in line and ',' in line:
                indent = len(line) - len(line.lstrip())
                # Try to break at commas
                func_match = re.match(r'^(\s*\S+)\((.*)\)(.*)$', line)
                if func_match:
                    prefix = func_match.group(1) + '(\n'
                    args = func_match.group(2)
                    suffix = func_match.group(3)
                    
                    arg_list = []
                    current_arg = ''
                    paren_depth = 0
                    
                    for char in args:
                        if char == '(' or char == '[' or char == '{':
                            paren_depth += 1
                        elif char == ')' or char == ']' or char == '}':
                            paren_depth -= 1
                        
                        if char == ',' and paren_depth == 0:
                            arg_list.append(current_arg.strip())
                            current_arg = ''
                        else:
                            current_arg += char
                    
                    if current_arg.strip():
                        arg_list.append(current_arg.strip())
                    
                    new_content = prefix
                    for arg in arg_list:
                        new_content += ' ' * (indent + 4) + arg + ',\n'
                    new_content = new_content.rstrip(',\n') + '\n' + ' ' * indent + ')' + suffix
                    
                    if line.endswith('\n') and not new_content.endswith('\n'):
                        new_content += '\n'
                    
                    new_lines.append(new_content)
                    modified = True
                    continue
            
            # If we couldn't fix it automatically, just add it as is
            new_lines.append(line)
        
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix long lines in specific files with E501 errors."""
    root_dir = Path(__file__).parent.parent
    fixed_count = 0
    
    # Files with E501 errors that need fixing
    files_to_fix = [
        'backend/api/advanced_workflow_orchestrator.py',
        'backend/api/agent_config.py',
        'src/workflow_templates.py',
        'src/voice_processing_system.py',
        'src/system_integration.py',
        'src/task_execution_tracker.py',
        'src/source_attribution.py',
    ]
    
    for filepath in files_to_fix:
        full_path = root_dir / filepath
        if full_path.exists():
            if fix_long_lines(full_path):
                fixed_count += 1
                print(f"Fixed: {filepath}")
        else:
            print(f"File not found: {filepath}")
    
    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()