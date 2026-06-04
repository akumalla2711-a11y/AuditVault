"""
AuditVault V2 — Database Models & Schema
Handles SQLite schema, initialization, and queries.
"""
import sqlite3
import secrets
from datetime import datetime
from werkzeug.security import generate_password_hash

def get_db(database_path):
    """Get a database connection with Row factory for dict-like access."""
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(database_path):
    """Initialize V2 database tables."""
    conn = get_db(database_path)
    c = conn.cursor()

    # --- Authentication & Enrollment ---
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS enrollment_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    # --- Endpoints ---
    c.execute('''CREATE TABLE IF NOT EXISTS endpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id TEXT UNIQUE NOT NULL,
        api_key TEXT UNIQUE NOT NULL,
        machine_guid TEXT,
        hostname TEXT,
        ip_address TEXT,
        os_caption TEXT,
        os_version TEXT,
        agent_version TEXT,
        tags TEXT DEFAULT '[]',
        approval_state TEXT DEFAULT 'Pending',
        status TEXT DEFAULT 'Healthy',
        first_seen TEXT,
        last_seen TEXT
    )''')

    # --- Universal Events Table ---
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        source TEXT,
        description TEXT
    )''')
    
    # Indexes for Timeline Explorer performance
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_endpoint_id ON events (endpoint_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_severity ON events (severity)')

    # --- Alerts ---
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
        related_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
        timestamp TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'Open',
        severity TEXT NOT NULL
    )''')

    # --- Current State Tracking ---
    c.execute('''CREATE TABLE IF NOT EXISTS software_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
        name TEXT,
        publisher TEXT,
        version TEXT,
        install_date TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS network_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
        local_address TEXT,
        local_port INTEGER,
        remote_address TEXT,
        remote_port INTEGER,
        state TEXT,
        owning_process TEXT,
        snapshot_time TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS usb_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint_id INTEGER NOT NULL REFERENCES endpoints(id) ON DELETE CASCADE,
        serial_number TEXT,
        device_name TEXT,
        first_seen TEXT,
        last_seen TEXT,
        connection_count INTEGER DEFAULT 1,
        status TEXT DEFAULT 'Unknown'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS defender_status (
        endpoint_id INTEGER PRIMARY KEY REFERENCES endpoints(id) ON DELETE CASCADE,
        enabled INTEGER,
        real_time_protection INTEGER,
        antispyware_enabled INTEGER,
        signature_age_days INTEGER,
        threat_count INTEGER,
        last_updated TEXT
    )''')

    # --- Defaults ---
    existing_user = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing_user:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                  ('admin', generate_password_hash('admin')))
        print("  [+] Default admin account created (admin / admin)")

    existing_key = c.execute("SELECT id FROM enrollment_keys").fetchone()
    if not existing_key:
        default_key = secrets.token_hex(16)
        c.execute("INSERT INTO enrollment_keys (key, description) VALUES (?, ?)", 
                  (default_key, 'Default Enrollment Key'))
        print(f"\n  {'=' * 52}\n  |  ENROLLMENT KEY: {default_key}  |\n  {'=' * 52}")
        print("  Paste this into your agent's config.json to register endpoints\n")

    conn.commit()
    conn.close()

# Note: The complex business logic for ingesting telemetry, calculating software deltas, 
# generating events, and decoupling alert engines is handled by a processor/service layer in app.py.
