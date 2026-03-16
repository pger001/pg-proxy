#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose and restart Flask service"""

import subprocess
import time
import os
import signal

def check_port(port):
    """Check if port is in use"""
    try:
        result = subprocess.run(
            f'netstat -ano | Select-String "{port}"',
            shell=True,
            check=False,
            capture_output=True,
            text=True
        )
        return len(result.stdout.strip()) > 0
    except:
        return False

def kill_flask():
    """Kill any Flask processes"""
    try:
        subprocess.run('taskkill /IM python.exe /F', shell=True)
        print("Killed Python processes")
        time.sleep(1)
    except:
        pass

def start_flask():
    """Start Flask service"""
    print("\nStarting Flask service...")
    subprocess.Popen(['python', 'web_dashboard.py'])
    time.sleep(3)
    print("Flask should be starting...")

# Main
print("Step 1: Checking port 5000...")
if check_port(5000):
    print("- Port 5000 is in use. Killing service...")
    kill_flask()
else:
    print("- Port 5000 is free")

print("\nStep 2: Starting Flask service...")
start_flask()

print("\nStep 3: Testing API...")
time.sleep(2)
try:
    import requests
    response = requests.get('http://localhost:5000/api/summary', timeout=3)
    print(f"- API Response: {response.status_code}")
    if response.status_code == 200:
        print("- SUCCESS! API is working")
    else:
        print(f"- ERROR: Status {response.status_code}")
except Exception as e:
    print(f"- ERROR: {e}")

print("\nDone! Try accessing http://localhost:5000/ in your browser")
