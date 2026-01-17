#!/usr/bin/env python3
"""Script to rename all route references in the codebase."""

import os
import re
from pathlib import Path

# Replacement mappings
replacements = [
    (r'genie_route', 'genie_route'),
    (r'table_route', 'table_route'),
    (r'table_route', 'table_route'),
    (r'genie route', 'genie route'),
    (r'table route', 'table route'),
    (r'table route', 'table route'),
    (r'Slow [Rr]oute', 'Genie Route'),
    (r'Fast [Rr]oute', 'Table Route'),
    (r'Quick [Rr]oute', 'Table Route'),
]

def update_file(filepath):
    """Update a single file with route name changes."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    """Main function to update all relevant files."""
    root = Path('/Users/yang.yang/CursorProjects/KUMC_POC_hlsfieldtemp')
    
    # File patterns to update
    patterns = ['**/*.md', '**/*.py', '**/*.puml', '**/*.csv', '**/*.mmd']
    
    updated_files = []
    for pattern in patterns:
        for filepath in root.glob(pattern):
            # Skip hidden directories and files
            if any(part.startswith('.') for part in filepath.parts):
                continue
            
            if filepath.is_file():
                if update_file(filepath):
                    updated_files.append(str(filepath.relative_to(root)))
    
    print(f"Updated {len(updated_files)} files:")
    for f in updated_files:
        print(f"  - {f}")

if __name__ == '__main__':
    main()
