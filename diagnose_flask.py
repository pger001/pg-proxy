#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test web_dashboard.py imports and basic functionality"""

import sys
import traceback

print("Step 1: Testing imports...")
try:
    from flask import Flask, jsonify
    print("  ✓ flask")
except Exception as e:
    print(f"  ✗ flask: {e}")
    sys.exit(1)

try:
    from flask_cors import CORS
    print("  ✓ flask_cors")
except Exception as e:
    print(f"  ✗ flask_cors: {e}")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("  ✓ psycopg2")
except Exception as e:
    print(f"  ✗ psycopg2: {e}")
    sys.exit(1)

try:
    import yaml
    print("  ✓ yaml")
except Exception as e:
    print(f"  ✗ yaml: {e}")
    sys.exit(1)

print("\nStep 2: Testing config file...")
try:
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print("  ✓ config.yaml loaded")
    print(f"  Database: {config['backend']['database']}")
except Exception as e:
    print(f"  ✗ config.yaml: {e}")
    sys.exit(1)

print("\nStep 3: Testing database connection...")
try:
    conn = psycopg2.connect(
        host=config['backend']['host'],
        port=config['backend']['port'],
        database=config['backend']['database'],
        user=config['backend']['user'],
        password=config['backend']['password']
    )
    print("  ✓ Database connection successful")
    conn.close()
except Exception as e:
    print(f"  ✗ Database connection failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\nStep 4: Attempting to import web_dashboard...")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("web_dashboard", "web_dashboard.py")
    module = importlib.util.module_from_spec(spec)
    print("  ✓ Module spec created")
    spec.loader.exec_module(module)
    print("  ✓ web_dashboard.py loaded successfully")
except Exception as e:
    print(f"  ✗ Failed to load web_dashboard.py: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All checks passed! Flask should be able to start.")
print("\nTry running: python web_dashboard.py")
