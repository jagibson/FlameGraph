#!/usr/bin/env python3
"""
Convert Brendan Gregg's folded flamegraph format to Grafana's nested set model.

Usage:
    ./files.pl /path/to/dir | python3 folded_to_grafana.py > output.csv
    # Or for JSON output suitable for Grafana's JSON data source:
    ./files.pl /path/to/dir | python3 folded_to_grafana.py --json > output.json

The output can be loaded into Grafana via:
- CSV data source plugin
- JSON API data source
- Infinity data source (for CSV/JSON files)
- TestData data source (paste the data)
"""

import sys
import json
import argparse
from collections import defaultdict


class TrieNode:
    def __init__(self, name):
        self.name = name
        self.children = {}
        self.self_value = 0
        self.total_value = 0


def build_trie(folded_lines, separator=';'):
    """Build a trie from folded stack format."""
    root = TrieNode("total")
    
    for line in folded_lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Split line into stack and count
        # Format: "stack;trace;here count"
        parts = line.rsplit(' ', 1)
        if len(parts) != 2:
            continue
        
        stack_str, count_str = parts
        try:
            count = int(count_str)
        except ValueError:
            try:
                count = float(count_str)
            except ValueError:
                continue
        
        # Handle both ; and / as separators (files.pl uses /)
        if '/' in stack_str and ';' not in stack_str:
            separator = '/'
        
        stack = [s for s in stack_str.split(separator) if s]  # Filter empty strings
        
        # Navigate/create path in trie
        node = root
        for frame in stack:
            if frame not in node.children:
                node.children[frame] = TrieNode(frame)
            node = node.children[frame]
        
        # Add self value at the leaf
        node.self_value += count
    
    return root


def calculate_totals(node):
    """Calculate total values (self + all children) for each node."""
    total = node.self_value
    for child in node.children.values():
        calculate_totals(child)
        total += child.total_value
    node.total_value = total


def trie_to_nested_set(node, level=0, result=None):
    """Convert trie to Grafana's nested set model via depth-first traversal."""
    if result is None:
        result = []
    
    result.append({
        'level': level,
        'label': node.name,
        'value': node.total_value,
        'self': node.self_value
    })
    
    # Sort children by total value (descending) for consistent output
    sorted_children = sorted(
        node.children.values(),
        key=lambda x: x.total_value,
        reverse=True
    )
    
    for child in sorted_children:
        trie_to_nested_set(child, level + 1, result)
    
    return result


def convert_folded_to_grafana(input_lines, separator=';'):
    """Main conversion function."""
    root = build_trie(input_lines, separator)
    calculate_totals(root)
    return trie_to_nested_set(root)


def output_csv(data):
    """Output as CSV."""
    print("level,value,self,label")
    for row in data:
        # Escape quotes in label
        label = row['label'].replace('"', '""')
        print(f"{row['level']},{row['value']},{row['self']},\"{label}\"")


def output_json(data):
    """Output as JSON suitable for Grafana JSON data source."""
    # Grafana expects data frame format
    output = {
        "results": {
            "A": {
                "frames": [{
                    "schema": {
                        "fields": [
                            {"name": "level", "type": "number"},
                            {"name": "value", "type": "number"},
                            {"name": "self", "type": "number"},
                            {"name": "label", "type": "string"}
                        ]
                    },
                    "data": {
                        "values": [
                            [row['level'] for row in data],
                            [row['value'] for row in data],
                            [row['self'] for row in data],
                            [row['label'] for row in data]
                        ]
                    }
                }]
            }
        }
    }
    print(json.dumps(output, indent=2))


def output_json_simple(data):
    """Output as simple JSON array."""
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description='Convert folded flamegraph format to Grafana nested set model'
    )
    parser.add_argument(
        '--json', action='store_true',
        help='Output as JSON (Grafana data frame format)'
    )
    parser.add_argument(
        '--json-simple', action='store_true',
        help='Output as simple JSON array'
    )
    parser.add_argument(
        '--separator', '-s', default=';',
        help='Stack separator character (default: ";", files.pl uses "/")'
    )
    parser.add_argument(
        'input', nargs='?', type=argparse.FileType('r'), default=sys.stdin,
        help='Input file (default: stdin)'
    )
    
    args = parser.parse_args()
    
    lines = args.input.readlines()
    data = convert_folded_to_grafana(lines, args.separator)
    
    if args.json:
        output_json(data)
    elif args.json_simple:
        output_json_simple(data)
    else:
        output_csv(data)


if __name__ == '__main__':
    main()
