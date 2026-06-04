"""
AuditVault V2 — Telemetry & Alert Processor
Handles the complex logic of parsing incoming agent data, generating delta events,
and evaluating alert conditions independently from the ingestion route.
"""
from datetime import datetime
import json

def process_telemetry(db, endpoint_id, data):
    """Process all incoming telemetry, store snapshots, and generate delta events."""
    timestamp = data.get('timestamp', datetime.now().isoformat())
    
    # 1. Process Software Inventory (Delta tracking)
    process_software(db, endpoint_id, data.get('software_list', []), timestamp)
    
    # 2. Process USB History
    process_usb(db, endpoint_id, data.get('usb_history', []), timestamp)
    
    # 3. Process Login Events
    process_logins(db, endpoint_id, data.get('login_history', []), timestamp)
    
    # 4. Update Network Snapshot (Overwrite current state)
    update_network_snapshot(db, endpoint_id, data.get('connections', []), timestamp)
    
    # 5. Process Defender Status
    process_defender(db, endpoint_id, data.get('defender_status', {}), timestamp)
    
    db.commit()
    
    # 6. Run Alert Engine Rules
    evaluate_alerts(db, endpoint_id, timestamp)


def generate_event(db, endpoint_id, timestamp, event_type, severity, source, description):
    """Insert a universal event."""
    c = db.cursor()
    c.execute('''
        INSERT INTO events (endpoint_id, timestamp, event_type, severity, source, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (endpoint_id, timestamp, event_type, severity, source, description))
    return c.lastrowid


def process_software(db, endpoint_id, incoming_software, timestamp):
    """Compare incoming software to existing DB to find Installs/Removals."""
    c = db.cursor()
    
    # Get existing software
    existing = db.execute(
        "SELECT name, publisher, version FROM software_inventory WHERE endpoint_id = ?",
        (endpoint_id,)
    ).fetchall()
    
    existing_map = {row['name']: row for row in existing}
    incoming_map = {sw.get('Name'): sw for sw in incoming_software if sw.get('Name')}
    
    # Check if this is the absolute first time we are seeing software for this endpoint
    is_initial_ingest = len(existing_map) == 0 and len(incoming_map) > 0
    
    if is_initial_ingest:
        # Just insert everything silently
        for name, sw in incoming_map.items():
            c.execute('''
                INSERT INTO software_inventory (endpoint_id, name, publisher, version, install_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (endpoint_id, name, sw.get('Publisher', ''), sw.get('Version', ''), sw.get('InstallDate', '')))
        
        generate_event(db, endpoint_id, timestamp, 'INITIAL_INVENTORY_CAPTURE', 'Info', 'Software', 
                       f"Captured baseline inventory with {len(incoming_map)} applications.")
        return

    # Check for New or Updated
    for name, sw in incoming_map.items():
        if name not in existing_map:
            # New install
            c.execute('''
                INSERT INTO software_inventory (endpoint_id, name, publisher, version, install_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (endpoint_id, name, sw.get('Publisher', ''), sw.get('Version', ''), sw.get('InstallDate', '')))
            
            generate_event(db, endpoint_id, timestamp, 'SOFTWARE_INSTALLED', 'Info', 'Software', 
                           f"{name} installed (Version {sw.get('Version', '')})")
            
        elif existing_map[name]['version'] != sw.get('Version', ''):
            # Version change
            c.execute("UPDATE software_inventory SET version = ? WHERE endpoint_id = ? AND name = ?",
                      (sw.get('Version', ''), endpoint_id, name))
            
            generate_event(db, endpoint_id, timestamp, 'SOFTWARE_UPDATED', 'Info', 'Software', 
                           f"{name} updated from {existing_map[name]['version']} to {sw.get('Version', '')}")
    
    # Check for Removed
    for name in existing_map:
        if name not in incoming_map:
            c.execute("DELETE FROM software_inventory WHERE endpoint_id = ? AND name = ?", 
                      (endpoint_id, name))
            generate_event(db, endpoint_id, timestamp, 'SOFTWARE_REMOVED', 'Info', 'Software', 
                           f"{name} removed")



def process_usb(db, endpoint_id, usb_history, timestamp):
    """Process USBs. Track connect/disconnect transitions."""
    c = db.cursor()
    existing = db.execute("SELECT device_name, status FROM usb_inventory WHERE endpoint_id = ?", (endpoint_id,)).fetchall()
    existing_map = {row['device_name']: row['status'] for row in existing}
    
    for usb in usb_history:
        name = usb.get('DeviceName', 'Unknown Device')
        serial = usb.get('SerialNumber', 'Unknown')
        current_status = usb.get('Status', 'Unknown')
        
        if name not in existing_map:
            c.execute('''
                INSERT INTO usb_inventory (endpoint_id, serial_number, device_name, first_seen, last_seen, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (endpoint_id, serial, name, timestamp, timestamp, current_status))
            existing_map[name] = current_status
            
            if current_status == 'Currently Connected':
                generate_event(db, endpoint_id, timestamp, 'USB_INSERTED', 'Warning', 'Hardware', 
                               f"New USB Device Connected: {name} (SN: {serial})")
        else:
            old_status = existing_map[name]
            if old_status != current_status:
                if current_status == 'Currently Connected':
                    generate_event(db, endpoint_id, timestamp, 'USB_INSERTED', 'Warning', 'Hardware', 
                                   f"USB Device Connected: {name} (SN: {serial})")
                elif current_status == 'Disconnected' and old_status == 'Currently Connected':
                    generate_event(db, endpoint_id, timestamp, 'USB_REMOVED', 'Info', 'Hardware', 
                                   f"USB Device Removed: {name} (SN: {serial})")
                
                c.execute("UPDATE usb_inventory SET last_seen = ?, status = ? WHERE endpoint_id = ? AND device_name = ?",
                          (timestamp, current_status, endpoint_id, name))
                existing_map[name] = current_status
            else:
                c.execute("UPDATE usb_inventory SET last_seen = ? WHERE endpoint_id = ? AND device_name = ?",
                          (timestamp, endpoint_id, name))


def process_logins(db, endpoint_id, login_history, timestamp):
    """Process login events and generate universal events with deduplication."""
    c = db.cursor()
    for ev in login_history:
        event_id = ev.get('EventId')
        target_user = ev.get('TargetUser', 'Unknown')
        msg = f"User {target_user} {ev.get('Message', '')}"
        ev_timestamp = ev.get('TimeCreated', timestamp)
        
        event_type = 'LOGIN_SUCCESS' if event_id == 4624 else 'LOGIN_FAILED'
        severity = 'Info' if event_type == 'LOGIN_SUCCESS' else 'Warning'
        
        # Deduplicate
        exists = c.execute('''
            SELECT event_id FROM events 
            WHERE endpoint_id = ? AND timestamp = ? AND event_type = ? AND description LIKE ?
        ''', (endpoint_id, ev_timestamp, event_type, f"User {target_user} %")).fetchone()
        
        if not exists:
            generate_event(db, endpoint_id, ev_timestamp, event_type, severity, 'Security', msg)


def update_network_snapshot(db, endpoint_id, connections, timestamp):
    """Wipe old network snapshot and store the current active one."""
    c = db.cursor()
    c.execute("DELETE FROM network_snapshot WHERE endpoint_id = ?", (endpoint_id,))
    
    for cn in connections:
        c.execute('''
            INSERT INTO network_snapshot (endpoint_id, local_address, local_port, remote_address, remote_port, state, owning_process, snapshot_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (endpoint_id, cn.get('LocalAddress', ''), cn.get('LocalPort'), cn.get('RemoteAddress', ''), 
              cn.get('RemotePort'), cn.get('State', ''), cn.get('OwningProcess', ''), timestamp))


def process_defender(db, endpoint_id, defender, timestamp):
    """Check Defender status and generate events on state changes."""
    if not defender:
        return
        
    c = db.cursor()
    prev = c.execute("SELECT enabled, real_time_protection FROM defender_status WHERE endpoint_id = ?", (endpoint_id,)).fetchone()
    
    incoming_enabled = defender.get('enabled', 1)
    incoming_rt = defender.get('real_time', 1)
    
    if prev:
        # Check for state changes
        if prev['enabled'] != incoming_enabled:
            if incoming_enabled == 0:
                generate_event(db, endpoint_id, timestamp, 'DEFENDER_DISABLED', 'Critical', 'Security', "Windows Defender Antivirus has been DISABLED")
            else:
                generate_event(db, endpoint_id, timestamp, 'DEFENDER_ENABLED', 'Info', 'Security', "Windows Defender Antivirus has been ENABLED")
                
        if prev['real_time_protection'] != incoming_rt:
            if incoming_rt == 0:
                generate_event(db, endpoint_id, timestamp, 'REALTIME_PROTECTION_DISABLED', 'Critical', 'Security', "Real-Time Protection has been DISABLED")
            else:
                generate_event(db, endpoint_id, timestamp, 'REALTIME_PROTECTION_ENABLED', 'Info', 'Security', "Real-Time Protection has been ENABLED")
        
        c.execute('''
            UPDATE defender_status 
            SET enabled=?, real_time_protection=?, antispyware_enabled=?, signature_age_days=?, threat_count=?, last_updated=?
            WHERE endpoint_id=?
        ''', (incoming_enabled, incoming_rt, defender.get('antispyware', 1), defender.get('sig_age', 0), defender.get('threats', 0), timestamp, endpoint_id))
    else:
        # First time insert
        c.execute('''
            INSERT INTO defender_status (endpoint_id, enabled, real_time_protection, antispyware_enabled, signature_age_days, threat_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (endpoint_id, incoming_enabled, incoming_rt, defender.get('antispyware', 1), defender.get('sig_age', 0), defender.get('threats', 0), timestamp))
        
        if incoming_enabled == 0 or incoming_rt == 0:
            generate_event(db, endpoint_id, timestamp, 'DEFENDER_DISABLED', 'Critical', 'Security', "Windows Defender is DISABLED on initial check")


def evaluate_alerts(db, endpoint_id, timestamp):
    """Background Alert Engine. Reads DB state and creates Alerts."""
    c = db.cursor()
    
    # 1. Check for Unknown USBs
    unknown_usbs = c.execute("SELECT * FROM usb_inventory WHERE endpoint_id = ? AND status = 'Unknown'", (endpoint_id,)).fetchall()
    for usb in unknown_usbs:
        # Check if alert already exists for this USB
        exists = c.execute("SELECT alert_id FROM alerts WHERE endpoint_id = ? AND alert_type = 'UNKNOWN_USB' AND description LIKE ?", 
                           (endpoint_id, f"%{usb['device_name']}%")).fetchone()
        if not exists:
            c.execute('''
                INSERT INTO alerts (endpoint_id, timestamp, alert_type, description, severity, status)
                VALUES (?, ?, 'UNKNOWN_USB', ?, 'Warning', 'Open')
            ''', (endpoint_id, timestamp, f"Unknown USB Detected: {usb['device_name']}"))
            
    # 2. Check Defender
    defender = c.execute("SELECT * FROM defender_status WHERE endpoint_id = ?", (endpoint_id,)).fetchone()
    if defender and (defender['enabled'] == 0 or defender['real_time_protection'] == 0):
        exists = c.execute("SELECT alert_id FROM alerts WHERE endpoint_id = ? AND alert_type = 'DEFENDER_DISABLED' AND status = 'Open'", 
                           (endpoint_id,)).fetchone()
        if not exists:
            c.execute('''
                INSERT INTO alerts (endpoint_id, timestamp, alert_type, description, severity, status)
                VALUES (?, ?, 'DEFENDER_DISABLED', 'Windows Defender is disabled on this endpoint.', 'Critical', 'Open')
            ''', (endpoint_id, timestamp))
            
    # 3. Check for Multiple Failed Logins (5+ within 5 mins)
    recent_fails = c.execute('''
        SELECT timestamp, description FROM events 
        WHERE endpoint_id = ? 
          AND event_type = 'LOGIN_FAILED' 
          AND timestamp >= datetime(?, '-5 minutes')
    ''', (endpoint_id, timestamp.replace('Z', ''))).fetchall()
    
    if len(recent_fails) >= 5:
        # Group by user (description format: "User {target_user} {msg}")
        user_fails = {}
        for fail in recent_fails:
            desc = fail['description']
            user = desc.split(' ')[1] if desc.startswith("User ") else "Unknown"
            if user not in user_fails:
                user_fails[user] = []
            user_fails[user].append(fail['timestamp'])
            
        for user, timestamps in user_fails.items():
            if len(timestamps) >= 5:
                timestamps.sort()
                try:
                    t1 = datetime.fromisoformat(timestamps[0])
                    t2 = datetime.fromisoformat(timestamps[-1])
                    window_mins = max(1, int((t2 - t1).total_seconds() / 60))
                except:
                    window_mins = 5
                
                alert_desc = f"{len(timestamps)} failed logins\nUser: {user}\nWindow: {window_mins} minute{'s' if window_mins != 1 else ''}"
                
                exists = c.execute('''
                    SELECT alert_id FROM alerts 
                    WHERE endpoint_id = ? AND alert_type = 'MULTIPLE_FAILED_LOGINS' AND status = 'Open' AND description LIKE ?
                ''', (endpoint_id, f"%User: {user}%")).fetchone()
                
                if not exists:
                    c.execute('''
                        INSERT INTO alerts (endpoint_id, timestamp, alert_type, description, severity, status)
                        VALUES (?, ?, 'MULTIPLE_FAILED_LOGINS', ?, 'Critical', 'Open')
                    ''', (endpoint_id, timestamp, alert_desc))
            
    db.commit()
