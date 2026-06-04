# AuditVault
> Centralized Remote System Audit & Security Dashboard

AuditVault is a premium, web-based remote audit tool for Windows systems. It uses a lightweight PowerShell agent to extract critical security and system data (USB history, network connections, process states, installed software, and login events) and securely transmits it to a modern, glassmorphism-styled Flask dashboard for centralized monitoring.

## Features
- **Lightweight PowerShell Agent**: No installation required on the client side. Runs cleanly on Windows 10/11 using native PowerShell cmdlets and WMI/CIM.
- **Deep System Insight**: Captures OS details, installed software (including WOW6432Node), active network connections, process resource usage, and network adapter details.
- **Security Auditing**: Pulls login events from the Windows Security event log (Success, Failed, Explicit Creds) and reads the registry to extract a historical timeline of all connected USB storage devices.
- **Premium Dashboard**: A beautifully designed, responsive Single Page Application (SPA) dashboard built with vanilla HTML/CSS/JS and Chart.js, featuring a dark mode aesthetic with glassmorphism effects.
- **Secure Architecture**: Session-based authentication for the dashboard and API Key authentication for the agent endpoints.

## Architecture
The application is split into two independent components:
1. **Server (`server/`)**: A Flask application with an SQLite database that provides REST API endpoints for agents and serves the dashboard UI to administrators.
2. **Agent (`agent/`)**: A modular PowerShell payload that executes on target machines and POSTs JSON data back to the server.

## Installation & Setup

### 1. Start the Server
Requires Python 3.8+

```powershell
cd server
pip install -r requirements.txt
python app.py
```
*On first run, the SQLite database is automatically created along with a default admin account and an agent API key.*

- **Dashboard URL**: `http://localhost:5000`
- **Default Login**: `admin` / `admin` (Change this in production)

### 2. Configure the Agent
Open `agent/config.json` and configure it to point to your server:

```json
{
    "server_url": "http://<YOUR_SERVER_IP>:5000/api/audit",
    "api_key": "PASTE_THE_API_KEY_PRINTED_IN_THE_SERVER_CONSOLE",
    "client_id": "CLIENT_001",
    "interval_seconds": 300,
    "run_mode": "once"
}
```

### 3. Run the Agent
Execute the orchestrator script on the target Windows machine:

```powershell
cd agent
.\agent.ps1
```

*(Note: Ensure PowerShell execution policies allow script execution, or run it via a bypass wrapper).*

## Customization
- **CSS Theme**: Modify colors and sizing using CSS custom properties in `server/static/css/style.css`.
- **Database**: The SQLite database is created at `server/auditvault.db`.
- **Agent Modules**: You can add new auditing capabilities by placing additional scripts in `agent/modules/` and updating the payload assembly in `agent.ps1`.

---
*Built for advanced remote auditing and endpoint visibility.*
