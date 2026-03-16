#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web Dashboard - Flask REST API with improved error handling
"""

import sys
import os

# Startup checks
print("="*60)
print("Starting Flask Dashboard...")
print("="*60)

# Check dependencies
print("\n[1/5] Checking dependencies...")
try:
    from flask import Flask, jsonify
    from flask_cors import CORS
    print("  ✓ Flask and Flask-CORS")
except ImportError as e:
    print(f"  ✗ Flask error: {e}")
    print("  Install: pip install flask flask-cors")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("  ✓ psycopg2")
except ImportError:
    print("  ✗ psycopg2 not found")
    print("  Install: pip install psycopg2-binary")
    sys.exit(1)

try:
    import yaml
    print("  ✓ PyYAML")
except ImportError:
    print("  ✗ PyYAML not found")
    print("  Install: pip install pyyaml")
    sys.exit(1)

# Check config file
print("\n[2/5] Checking configuration...")
if not os.path.exists('config.yaml'):
    print("  ✗ config.yaml not found")
    sys.exit(1)

try:
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    db_config = config['backend']
    print(f"  ✓ Config loaded: {db_config['database']}@{db_config['host']}")
except Exception as e:
    print(f"  ✗ Config error: {e}")
    sys.exit(1)

# Test database connection
print("\n[3/5] Testing database connection...")
try:
    test_conn = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    cursor = test_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM public.tenant_stats")
    count = cursor.fetchone()[0]
    print(f"  ✓ Database connected: {count} records")
    cursor.close()
    test_conn.close()
except Exception as e:
    print(f"  ✗ Database error: {e}")
    sys.exit(1)

# Check port availability
print("\n[4/5] Checking port 5000...")
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('127.0.0.1', 5000))
sock.close()
if result == 0:
    print("  ⚠️  Port 5000 is in use")
    print("  Stop the service: taskkill /IM python.exe /F")
    sys.exit(1)
else:
    print("  ✓ Port 5000 available")

# Initialize Flask
print("\n[5/5] Initializing Flask app...")
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password'],
        cursor_factory=RealDictCursor
    )

@app.route('/api/summary', methods=['GET'])
def get_summary():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_queries,
                SUM(estimated_traffic_bytes) as total_traffic_bytes,
                SUM(execution_time_ms) as total_execution_time,
                AVG(execution_time_ms) as avg_execution_time,
                SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_hits,
                COUNT(*) - SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_misses
            FROM public.tenant_stats
        """)
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({
            'total_queries': int(result['total_queries'] or 0),
            'total_traffic_mb': float((result['total_traffic_bytes'] or 0) / 1024 / 1024),
            'total_execution_time_ms': float(result['total_execution_time'] or 0),
            'avg_execution_time_ms': float(result['avg_execution_time'] or 0),
            'avg_time_ms': float(result['avg_execution_time'] or 0),
            'cache_hits': int(result['cache_hits'] or 0),
            'cache_misses': int(result['cache_misses'] or 0),
            'cache_hit_rate': float((result['cache_hits'] or 0) / (result['total_queries'] or 1) * 100)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tenant-ranking', methods=['GET'])
def get_tenant_ranking():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tenant_code, COUNT(*) as query_count,
                   SUM(estimated_traffic_bytes) as traffic_bytes,
                   AVG(execution_time_ms) as avg_time,
                   SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_hits,
                   SUM(rows_returned) as total_rows
            FROM public.tenant_stats
            GROUP BY tenant_code ORDER BY traffic_bytes DESC LIMIT 20
        """)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        data = []
        for idx, r in enumerate(results, 1):
            data.append({
                'rank': idx, 'tenant_code': r['tenant_code'],
                'query_count': int(r['query_count']),
                'total_traffic_bytes': int(r['traffic_bytes'] or 0),
                'total_traffic_mb': float((r['traffic_bytes'] or 0) / 1024 / 1024),
                'traffic_mb': float((r['traffic_bytes'] or 0) / 1024 / 1024),
                'avg_time_ms': float(r['avg_time'] or 0),
                'cache_hits': int(r['cache_hits'] or 0),
                'cache_rate': float((r['cache_hits'] or 0) / (r['query_count'] or 1) * 100),
                'total_rows': int(r['total_rows'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/slow-queries', methods=['GET'])
def get_slow_queries():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, tenant_code, sql_preview, execution_time_ms,
                   rows_returned, estimated_traffic_mb
            FROM public.tenant_stats
            ORDER BY execution_time_ms DESC LIMIT 10
        """)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        data = []
        for idx, r in enumerate(results, 1):
            data.append({
                'rank': idx,
                'timestamp': r['timestamp'].isoformat() if r['timestamp'] else None,
                'tenant_code': r['tenant_code'],
                'sql_preview': str(r['sql_preview'])[:80] if r['sql_preview'] else '',
                'execution_time_ms': float(r['execution_time_ms'] or 0),
                'rows_returned': int(r['rows_returned'] or 0),
                'traffic_mb': float(r['estimated_traffic_mb'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/high-traffic-queries', methods=['GET'])
def get_high_traffic_queries():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, tenant_code, sql_preview, execution_time_ms,
                   rows_returned, estimated_traffic_mb, total_cost, estimated_rows
            FROM public.tenant_stats
            ORDER BY estimated_traffic_bytes DESC LIMIT 10
        """)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        data = []
        for idx, r in enumerate(results, 1):
            data.append({
                'rank': idx,
                'timestamp': r['timestamp'].isoformat() if r['timestamp'] else None,
                'tenant_code': r['tenant_code'],
                'sql_preview': str(r['sql_preview'])[:80] if r['sql_preview'] else '',
                'execution_time_ms': float(r['execution_time_ms'] or 0),
                'rows_returned': int(r['rows_returned'] or 0),
                'traffic_mb': float(r['estimated_traffic_mb'] or 0),
                'query_cost': float(r['total_cost'] or 0),
                'estimated_rows': int(r['estimated_rows'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/timeline', methods=['GET'])
def get_timeline():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DATE_TRUNC('hour', timestamp) as time_bucket,
                   COUNT(*) as query_count,
                   SUM(estimated_traffic_bytes) as traffic_bytes,
                   AVG(execution_time_ms) as avg_time,
                   SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as cache_hits
            FROM public.tenant_stats
            WHERE timestamp IS NOT NULL
            GROUP BY DATE_TRUNC('hour', timestamp)
            ORDER BY time_bucket DESC LIMIT 168
        """)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        data = []
        for r in sorted(results, key=lambda x: x['time_bucket'] or '', reverse=False):
            data.append({
                'timestamp': r['time_bucket'].isoformat() if r['time_bucket'] else None,
                'query_count': int(r['query_count']),
                'traffic_mb': float((r['traffic_bytes'] or 0) / 1024 / 1024),
                'avg_time_ms': float(r['avg_time'] or 0),
                'cache_hits': int(r['cache_hits'] or 0)
            })
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache-stats', methods=['GET'])
def get_cache_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(CASE WHEN from_cache THEN execution_time_ms ELSE 0 END) as cache_time_saved,
                   SUM(CASE WHEN from_cache THEN 1 ELSE 0 END) as total_cache_hits,
                   COUNT(*) as total_queries
            FROM public.tenant_stats
        """)
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({
            'cache_hits': int(result['total_cache_hits'] or 0),
            'total_cache_hits': int(result['total_cache_hits'] or 0),
            'total_queries': int(result['total_queries'] or 0),
            'cache_hit_rate': float((result['total_cache_hits'] or 0) / (result['total_queries'] or 1) * 100),
            'saved_time_ms': float(result['cache_time_saved'] or 0),
            'time_saved_ms': float(result['cache_time_saved'] or 0)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dashboard.html')
@app.route('/')
def serve_dashboard():
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
    except Exception as e:
        return f"<p>Error loading dashboard: {e}</p>", 500

if __name__ == '__main__':
    print("  ✓ Flask app initialized")
    print("\n" + "="*60)
    print("🚀 Dashboard Ready!")
    print("="*60)
    print("\n📊 Access: http://localhost:5000/")
    print("\n🔌 API Endpoints:")
    print("   - GET /api/summary")
    print("   - GET /api/tenant-ranking")
    print("   - GET /api/slow-queries")
    print("   - GET /api/high-traffic-queries")
    print("   - GET /api/timeline")
    print("   - GET /api/cache-stats")
    print("\n" + "="*60)
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")
    
    try:
        app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        sys.exit(1)
