#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test complete dashboard loading"""

import requests

# Test 1: Check if dashboard page loads
print("Test 1: Loading dashboard page...")
try:
    response = requests.get('http://localhost:5000/', timeout=5)
    if response.status_code == 200:
        print(f"✓ Dashboard page loaded (Status: {response.status_code})")
        # Check if script tag with API calls is present
        if 'loadAllData()' in response.text:
            print("✓ JavaScript loadAllData function found")
        else:
            print("✗ JavaScript loadAllData function NOT found")
        
        if 'Chart.js' in response.text:
            print("✓ Chart.js included")
        else:
            print("✗ Chart.js NOT found")
            
        if 'axios' in response.text or 'Axios' in response.text:
            print("✓ Axios included")
        else:
            print("✗ Axios NOT found")
    else:
        print(f"✗ Failed to load dashboard (Status: {response.status_code})")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Check if all API endpoints work
print("\nTest 2: Testing API endpoints...")
endpoints = ['/summary', '/tenant-ranking', '/slow-queries', '/high-traffic-queries', '/timeline', '/cache-stats']

for endpoint in endpoints:
    try:
        response = requests.get(f'http://localhost:5000/api{endpoint}', timeout=5)
        if response.status_code == 200:
            data = response.json()
            count = len(data) if isinstance(data, list) else 1
            print(f"✓ GET /api{endpoint}: {response.status_code} (records: {count})")
        else:
            print(f"✗ GET /api{endpoint}: {response.status_code}")
    except Exception as e:
        print(f"✗ GET /api{endpoint}: {e}")

print("\nAll tests complete. Try accessing http://localhost:5000/ in your browser and check the console for any errors.")
