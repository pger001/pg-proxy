#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check dashboard HTML elements"""

import re

with open('dashboard.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# Extract all element IDs referenced in JavaScript
js_section = re.search(r'<script>(.*?)</script>', html_content, re.DOTALL)
if js_section:
    js_code = js_section.group(1)
    
    # Find all document.getElementById calls
    id_patterns =re.findall(r"document\.getElementById\('([^']+)'\)", js_code)
    
    # Also check for getElementById with double quotes
    id_patterns += re.findall(r"document\.getElementById\(\"([^\"]+)\"\)", js_code)
    
    # Check if each ID exists in HTML
    print("Checking HTML elements referenced in JavaScript:")
    print("=" * 60)
    
    missing = []
    for id_name in sorted(set(id_patterns)):
        if f"id=\"{id_name}\"" in html_content or f"id='{id_name}'" in html_content:
            print(f"✓ id=\"{id_name}\" found")
        else:
            print(f"✗ id=\"{id_name}\" MISSING")
            missing.append(id_name)
    
    if missing:
        print(f"\nWarning: {len(missing)} missing elements:")
        for id_name in missing:
            print(f"  - {id_name}")
    else:
        print("\n✓ All elements found!")

# Check CDN resources
print("\n" + "=" * 60)
print("Checking external CDN resources:")
cdns = re.findall(r'src="([^"]*cdn[^"]*)"', html_content)
for cdn in cdns:
    print(f"  - {cdn}")
