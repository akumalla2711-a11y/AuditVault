"""
AuditVault — Authentication Helpers
Session-based auth for dashboard, API key auth for agents.
"""
from functools import wraps
from flask import session, redirect, url_for, request, jsonify


def login_required(f):
    """Decorator: redirects to login page if no active session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def api_key_required(f):
    """Decorator: validates X-API-Key header against the endpoints table."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import get_db
        from flask import current_app

        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'status': 'error', 'message': 'Missing X-API-Key header'}), 401

        db = get_db(current_app.config['DATABASE'])
        endpoint = db.execute(
            "SELECT id, endpoint_id, approval_state FROM endpoints WHERE api_key = ?", (api_key,)
        ).fetchone()
        db.close()

        if not endpoint:
            return jsonify({'status': 'error', 'message': 'Invalid API key'}), 403
            
        if endpoint['approval_state'] != 'Approved':
            return jsonify({'status': 'error', 'message': 'Endpoint is Pending Approval or Blocked'}), 403

        # Attach endpoint_id to request so the route can use it
        request.endpoint_db_id = endpoint['id']
        request.endpoint_uuid = endpoint['endpoint_id']

        return f(*args, **kwargs)
    return decorated_function
