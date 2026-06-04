"""
AuditVault V2 — Flask Application
Main server: handles agent registration, telemetry ingestion, and UI dashboard.
"""
import secrets
import uuid
from datetime import datetime
from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, g
)
from flask_cors import CORS
from werkzeug.security import check_password_hash

from config import config
from models import get_db, init_db
from auth import login_required, api_key_required
from processor import process_telemetry

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    CORS(app)

    with app.app_context():
        init_db(app.config['DATABASE'])

    # --- UI ROUTES ---

    @app.route('/')
    def index():
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login_page'))

    @app.route('/login', methods=['GET', 'POST'])
    def login_page():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            db = get_db(app.config['DATABASE'])
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            db.close()

            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                return redirect(url_for('dashboard'))
            return render_template('login.html', error='Invalid username or password')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login_page'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        return render_template('dashboard.html', username=session.get('username', 'Admin'))

    # --- AGENT API ROUTES ---

    @app.route('/api/register', methods=['POST'])
    def register_agent():
        """Enrollment flow: Agents submit enrollment key to receive unique API key."""
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

        enrollment_key = data.get('enrollment_key')
        db = get_db(app.config['DATABASE'])
        
        valid_key = db.execute("SELECT id FROM enrollment_keys WHERE key = ?", (enrollment_key,)).fetchone()
        if not valid_key:
            db.close()
            return jsonify({'status': 'error', 'message': 'Invalid Enrollment Key'}), 403

        # Generate unique identity
        endpoint_id = str(uuid.uuid4())
        api_key = secrets.token_hex(24)
        timestamp = datetime.now().isoformat()
        
        # Check if machine_guid already exists to avoid duplicates
        existing = db.execute("SELECT endpoint_id, api_key, approval_state FROM endpoints WHERE machine_guid = ?", 
                              (data.get('machine_guid'),)).fetchone()
                              
        if existing:
            # Re-issue existing keys if re-registering
            db.close()
            return jsonify({
                'endpoint_id': existing['endpoint_id'],
                'api_key': existing['api_key'],
                'status': existing['approval_state']
            })

        db.execute('''
            INSERT INTO endpoints (endpoint_id, api_key, machine_guid, hostname, ip_address, 
                                   os_caption, os_version, agent_version, approval_state, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
        ''', (
            endpoint_id, api_key, data.get('machine_guid'), data.get('hostname'),
            request.remote_addr, data.get('os_caption'), data.get('os_version'),
            data.get('agent_version'), timestamp, timestamp
        ))
        
        db.commit()
        db.close()
        return jsonify({'endpoint_id': endpoint_id, 'api_key': api_key, 'status': 'Pending'})

    @app.route('/api/audit', methods=['POST'])
    @api_key_required
    def receive_audit():
        """Telemetry ingestion route. Fully decoupled from alert engine."""
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

        try:
            db = get_db(app.config['DATABASE'])
            # Update last seen
            db.execute("UPDATE endpoints SET last_seen = ? WHERE id = ?", 
                       (datetime.now().isoformat(), request.endpoint_db_id))
            
            # Send to processor
            process_telemetry(db, request.endpoint_db_id, data)
            db.close()
            
            return jsonify({'status': 'success', 'message': 'Telemetry ingested successfully'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/heartbeat', methods=['POST'])
    @api_key_required
    def receive_heartbeat():
        """Lightweight heartbeat endpoint — updates last_seen and agent_version."""
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

        try:
            db = get_db(app.config['DATABASE'])
            db.execute(
                "UPDATE endpoints SET last_seen = ?, agent_version = ? WHERE id = ?",
                (datetime.now().isoformat(), data.get('agent_version', ''), request.endpoint_db_id)
            )
            db.commit()
            db.close()
            return jsonify({'status': 'success', 'message': 'Heartbeat received'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # --- DASHBOARD API ROUTES (Placeholder for V2 endpoints) ---

    @app.route('/api/endpoints', methods=['GET'])
    @login_required
    def api_get_endpoints():
        db = get_db(app.config['DATABASE'])
        rows = db.execute("SELECT * FROM endpoints ORDER BY last_seen DESC").fetchall()
        db.close()
        
        results = []
        now = datetime.now()
        for r in rows:
            ep = dict(r)
            try:
                last_seen_dt = datetime.fromisoformat(ep['last_seen'])
                ep['is_online'] = (now - last_seen_dt).total_seconds() < 900
            except:
                ep['is_online'] = False
            results.append(ep)
            
        return jsonify(results)

    @app.route('/api/stats', methods=['GET'])
    @login_required
    def api_get_stats():
        db = get_db(app.config['DATABASE'])
        
        # Calculate Online/Offline based on 15 min window
        endpoints = db.execute("SELECT last_seen, approval_state FROM endpoints").fetchall()
        online_count = 0
        active_count = 0
        now = datetime.now()
        
        for ep in endpoints:
            if ep['approval_state'] in ('Active', 'Approved'):
                active_count += 1
                try:
                    if (now - datetime.fromisoformat(ep['last_seen'])).total_seconds() < 900:
                        online_count += 1
                except: pass
                
        stats = {
            'total_endpoints': active_count,
            'online_endpoints': online_count,
            'critical_alerts': db.execute("SELECT COUNT(*) as c FROM alerts WHERE status IN ('Open', 'Acknowledged') AND severity = 'Critical'").fetchone()['c'],
            'warning_alerts': db.execute("SELECT COUNT(*) as c FROM alerts WHERE status IN ('Open', 'Acknowledged') AND severity = 'Warning'").fetchone()['c'],
            'total_events': db.execute("SELECT COUNT(*) as c FROM events").fetchone()['c']
        }
        
        db.close()
        return jsonify(stats)

    @app.route('/api/events', methods=['GET'])
    @login_required
    def api_get_events():
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        offset = (page - 1) * limit
        
        db = get_db(app.config['DATABASE'])
        rows = db.execute('''
            SELECT e.*, end.hostname 
            FROM events e 
            JOIN endpoints end ON e.endpoint_id = end.id 
            ORDER BY e.timestamp DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/alerts', methods=['GET'])
    @login_required
    def api_get_alerts():
        db = get_db(app.config['DATABASE'])
        rows = db.execute('''
            SELECT a.*, end.hostname 
            FROM alerts a 
            JOIN endpoints end ON a.endpoint_id = end.id 
            ORDER BY a.timestamp DESC
        ''').fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/endpoints/<int:endpoint_id>/approve', methods=['POST'])
    @login_required
    def api_approve_endpoint(endpoint_id):
        db = get_db(app.config['DATABASE'])
        db.execute("UPDATE endpoints SET approval_state = 'Approved' WHERE id = ?", (endpoint_id,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
    @login_required
    def api_acknowledge_alert(alert_id):
        db = get_db(app.config['DATABASE'])
        # Only allow Ack if Open
        db.execute("UPDATE alerts SET status = 'Acknowledged' WHERE alert_id = ? AND status = 'Open'", (alert_id,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    @app.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
    @login_required
    def api_resolve_alert(alert_id):
        db = get_db(app.config['DATABASE'])
        db.execute("UPDATE alerts SET status = 'Resolved' WHERE alert_id = ? AND status IN ('Open', 'Acknowledged')", (alert_id,))
        db.commit()
        db.close()
        return jsonify({'status': 'success'})

    # --- ENDPOINT INVESTIGATION ROUTES ---

    @app.route('/api/endpoints/<int:id>', methods=['GET'])
    @login_required
    def api_endpoint_summary(id):
        db = get_db(app.config['DATABASE'])
        ep = db.execute("SELECT * FROM endpoints WHERE id = ?", (id,)).fetchone()
        if not ep: return jsonify({'error': 'Not found'}), 404
        
        ep_dict = dict(ep)
        try:
            ep_dict['is_online'] = (datetime.now() - datetime.fromisoformat(ep_dict['last_seen'])).total_seconds() < 900
        except:
            ep_dict['is_online'] = False
            
        ep_dict['open_alerts'] = db.execute("SELECT COUNT(*) as c FROM alerts WHERE endpoint_id = ? AND status IN ('Open', 'Acknowledged')", (id,)).fetchone()['c']
        ep_dict['total_events'] = db.execute("SELECT COUNT(*) as c FROM events WHERE endpoint_id = ?", (id,)).fetchone()['c']
        db.close()
        return jsonify(ep_dict)

    @app.route('/api/endpoints/<int:id>/software', methods=['GET'])
    @login_required
    def api_endpoint_software(id):
        db = get_db(app.config['DATABASE'])
        rows = db.execute("SELECT * FROM software_inventory WHERE endpoint_id = ?", (id,)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/endpoints/<int:id>/usb', methods=['GET'])
    @login_required
    def api_endpoint_usb(id):
        db = get_db(app.config['DATABASE'])
        rows = db.execute("SELECT * FROM usb_inventory WHERE endpoint_id = ? ORDER BY last_seen DESC", (id,)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/endpoints/<int:id>/timeline', methods=['GET'])
    @login_required
    def api_endpoint_timeline(id):
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        offset = (page - 1) * limit
        
        db = get_db(app.config['DATABASE'])
        rows = db.execute("SELECT * FROM events WHERE endpoint_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (id, limit, offset)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/endpoints/<int:id>/alerts', methods=['GET'])
    @login_required
    def api_endpoint_alerts(id):
        db = get_db(app.config['DATABASE'])
        rows = db.execute("SELECT * FROM alerts WHERE endpoint_id = ? ORDER BY timestamp DESC", (id,)).fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])

    @app.route('/api/endpoints/<int:id>/defender', methods=['GET'])
    @login_required
    def api_endpoint_defender(id):
        db = get_db(app.config['DATABASE'])
        row = db.execute("SELECT * FROM defender_status WHERE endpoint_id = ?", (id,)).fetchone()
        db.close()
        return jsonify(dict(row) if row else {})

    return app

if __name__ == '__main__':
    app = create_app('development')
    print("\n  ========================================")
    print("  |       AuditVault Server v2.0         |")
    print("  ========================================")
    print("  |  Dashboard:  http://localhost:5000   |")
    print("  ========================================\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
