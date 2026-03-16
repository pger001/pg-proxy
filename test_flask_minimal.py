#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal Flask test"""

from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/test', methods=['GET'])
def test():
    return jsonify({'status': 'ok', 'message': 'Flask is working'})

if __name__ == '__main__':
    print("Starting Flask test server...")
    app.run(debug=False, host='127.0.0.1', port=5001, use_reloader=False)
