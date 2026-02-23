"""
Pivot ITM Trading Dashboard - Flask Server
Serves real-time dashboard with WebSocket updates
"""

import os
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import threading
import time
from shared_state import state

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    """Serve dashboard HTML"""
    return render_template('dashboard.html')

@app.route('/api/state')
def get_state():
    """Return current state as JSON"""
    return jsonify(state.get_state())

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "timestamp": time.time()})

def run_dashboard_server(host='127.0.0.1', port=5000, debug=False):
    """Run Flask server in background thread"""
    app.run(host=host, port=port, debug=debug, use_reloader=False)

def start_dashboard(host='127.0.0.1', port=5000):
    """Start dashboard server in background thread"""
    thread = threading.Thread(
        target=run_dashboard_server,
        args=(host, port, False),
        daemon=True
    )
    thread.start()
    print(f"🌐 Dashboard server started at http://{host}:{port}")
    return thread

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 8000))
#     app.run(host="0.0.0.0", port=port)
    
if __name__ == '__main__':
    # Test mode - run server directly
    print("🚀 Starting Pivot ITM Dashboard Server...")
    print("📊 Dashboard available at: http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)
