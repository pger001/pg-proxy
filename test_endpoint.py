#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test Flask API when running"""

import requests
import time
import subprocess
import os
import signal

# Start Flask server in background
print("Starting Flask server...")
proc = subprocess.Popen(['python', 'web_dashboard.py'], 
                       stdout=subprocess.PIPE, 
                       stderr=subprocess.PIPE)

# Wait for server to start
time.sleep(3)

try:
    # Test API endpoint
    url = "http://127.0.0.1:5000/api/summary"
    print(f"\nFetching {url}...")
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response:\n{response.json()}")
except Exception as e:
    print(f"Error: {e}")
finally:
    # Kill the server
    os.kill(proc.pid, signal.SIGTERM)
    proc.wait()
