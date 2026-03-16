#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test API endpoints"""

import requests
import json
import time

# Give server time to start if needed
time.sleep(1)

base_url = "http://localhost:5000/api"

endpoints = [
    '/summary',
    '/tenant-ranking',
    '/slow-queries',
    '/high-traffic-queries',
    '/timeline',
    '/cache-stats'
]

print("Testing API Endpoints:")
print("=" * 60)

for endpoint in endpoints:
    try:
        response = requests.get(f"{base_url}{endpoint}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                print(f"✓ GET {endpoint}")
                print(f"  Status: {response.status_code}")
                print(f"  Records: {len(data)}")
                if isinstance(data, list) and len(data) > 0:
                    print(f"  First record keys: {list(data[0].keys())}")
            else:
                print(f"✓ GET {endpoint}")
                print(f"  Status: {response.status_code}")
                print(f"  Response: {json.dumps(data, default=str, indent=2)[:200]}")
        else:
            print(f"✗ GET {endpoint}")
            print(f"  Status: {response.status_code}")
            print(f"  Error: {response.text[:200]}")
    except Exception as e:
        print(f"✗ GET {endpoint}")
        print(f"  Error: {e}")
    print()

print("=" * 60)
print("API testing complete!")
