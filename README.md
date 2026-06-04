# AuditVault

> Centralized Remote System Audit & Security Dashboard

AuditVault is a web-based remote auditing platform for Windows endpoints. It deploys a lightweight agent (PowerShell or compiled Windows Service) that collects system telemetry — USB device history, network connections, running processes, installed software, login events, and Windows Defender status — and transmits it to a Flask-powered dashboard for centralized monitoring, alerting, and investigation.

---

## Features

### Server & Dashboard
- **Real-Time Dashboard** — Responsive SPA with dark-mode glassmorphism design, built with vanilla HTML/CSS/JS and Chart.js
- **Telemetry Processor** — Delta-tracking engine that detects software installs/removals, USB insertions, Defender state changes, and generates granular timeline events
- **Alert Engine** — Rule-based alert system (failed login brute-force detection, Defender disabled, unknown USB devices) with Open → Acknowledged → Resolved lifecycle
- **Endpoint Investigation** — Per-endpoint drill-down views: software inventory, USB history, event timeline, alert history, Defender status
- **Enrollment System** — Secure agent registration via enrollment keys with admin approval workflow
- **Session + API Auth** — Session-based authentication for the dashboard UI, API key authentication for agent endpoints

### Agent
- **PowerShell Orchestrator** (`agent.ps1`) — Zero-install, runs on any Windows 10/11 machine using native cmdlets and WMI/CIM
- **Python Windows Service** (`agent.py`) — Production-grade service with auto-restart on failure, rotating file logs, and offline payload queueing
- **8 Modular Collectors** — Each audit capability is a standalone PowerShell script in `modules/`, making it easy to extend
- **Offline Queue** — Failed transmissions are persisted to disk and retried automatically on the next cycle
- **Heartbeat System** — Lightweight pings to keep last-seen timestamps accurate between full audit cycles

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Target Windows Machines                                            │
│                                                                     │
│  ┌─────────────┐     ┌──────────────────────────────────────────┐   │
│  │  agent.ps1   │ OR  │  AuditVaultAgent.exe (Windows Service)   │   │
│  └──────┬──────┘     └──────────────┬───────────────────────────┘   │
│         │                           │                               │
│         └─────────┬─────────────────┘                               │
│                   │ PowerShell Modules                              │
│         ┌─────────┴─────────┐                                       │
│         │  modules/         │                                       │
│         │  ├─ Get-OSDetails │                                       │
│         │  ├─ Get-Installed │                                       │
│         │  │  Software      │                                       │
│         │  ├─ Get-Login     │                                       │
│         │  │  History       │                                       │
│         │  ├─ Get-USBHistory│                                       │
│         │  ├─ Get-Defender  │                                       │
│         │  │  Status        │                                       │
│         │  └─ ...           │                                       │
│         └───────────────────┘                                       │
└─────────────────────┬───────────────────────────────────────────────┘
                      │  HTTPS POST (JSON + X-API-Key)
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AuditVault Server                                                  │
│                                                                     │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Flask API │→│ Processor  │→│ Alert    │→│ SQLite Database  │  │
│  │ (app.py)  │  │(processor  │  │ Engine   │  │ (auditvault.db)  │  │
│  │          │  │  .py)      │  │          │  │                  │  │
│  └──────────┘  └────────────┘  └──────────┘  └──────────────────┘  │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────┐                      │
│  │ Dashboard UI (SPA)                       │                      │
│  │ HTML/CSS/JS + Chart.js                   │                      │
│  └──────────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
AuditVault/
├── server/                          # Flask backend + dashboard
│   ├── app.py                       # Main Flask app — routes & API
│   ├── auth.py                      # Session & API key auth decorators
│   ├── config.py                    # App configuration (dev/prod)
│   ├── models.py                    # SQLite schema & initialization
│   ├── processor.py                 # Telemetry ingestion & alert engine
│   ├── requirements.txt             # Python dependencies
│   ├── static/
│   │   ├── css/style.css            # Dashboard theme & glassmorphism styles
│   │   └── js/
│   │       ├── app.js               # SPA logic, routing, API calls
│   │       └── charts.js            # Chart.js dashboard visualizations
│   └── templates/
│       ├── base.html                # Base template
│       ├── login.html               # Login page
│       └── dashboard.html           # Main dashboard SPA
│
├── agent/                           # Endpoint audit agent
│   ├── agent.ps1                    # PowerShell orchestrator (lightweight)
│   ├── agent.py                     # Python Windows Service (production)
│   ├── build_agent.bat              # PyInstaller build script → .exe
│   ├── config.example.json          # Sample config (copy to config.json)
│   ├── requirements.txt             # Agent Python dependencies
│   └── modules/                     # Modular PowerShell collectors
│       ├── Get-OSDetails.ps1
│       ├── Get-InstalledSoftware.ps1
│       ├── Get-NetworkInfo.ps1
│       ├── Get-ActiveConnections.ps1
│       ├── Get-ProcessList.ps1
│       ├── Get-LoginHistory.ps1
│       ├── Get-USBHistory.ps1
│       └── Get-DefenderStatus.ps1
│
├── .gitignore
├── LICENSE
└── README.md
```

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- Windows 10/11 (for the agent)

### 1. Start the Server

```powershell
cd server
pip install -r requirements.txt
python app.py
```

On first run, the SQLite database is automatically created with:
- A default admin account (`admin` / `admin`)
- An enrollment key (printed in the console — save this)

The dashboard will be available at **http://localhost:5000**

### 2. Configure the Agent

```powershell
cd agent
copy config.example.json config.json
```

Edit `config.json` with the enrollment key from the server console:

```json
{
    "server_url": "http://<YOUR_SERVER_IP>:5000/api/audit",
    "enrollment_key": "<PASTE_ENROLLMENT_KEY_FROM_SERVER_CONSOLE>",
    "endpoint_id": "",
    "api_key": "",
    "interval_seconds": 300,
    "run_mode": "once"
}
```

> **Note:** `endpoint_id` and `api_key` are auto-populated after the agent registers with the server. Leave them empty for first-time setup.

### 3. Run the Agent

**Option A — PowerShell (Quick Test)**
```powershell
.\agent.ps1
```

**Option B — Windows Service (Production)**
```powershell
# Build the executable
.\build_agent.bat

# Install & start the service (requires Administrator)
cd dist\AuditVaultAgent
.\AuditVaultAgent.exe install
.\AuditVaultAgent.exe start
.\AuditVaultAgent.exe status
```

### 4. Approve the Endpoint

After the agent registers, log into the dashboard and approve the endpoint to begin receiving telemetry.

---

## Alert Rules

| Alert | Trigger | Severity |
|---|---|---|
| `MULTIPLE_FAILED_LOGINS` | 5+ failed logins for the same user within 5 minutes | Critical |
| `DEFENDER_DISABLED` | Windows Defender or Real-Time Protection turned off | Critical |
| `UNKNOWN_USB` | USB storage device with unknown status detected | Warning |

---

## Configuration

| Setting | File | Description |
|---|---|---|
| Dashboard theme | `server/static/css/style.css` | CSS custom properties for colors, spacing |
| Server mode | `server/config.py` | Development vs Production settings |
| Agent interval | `agent/config.json` | Telemetry collection frequency (seconds) |
| Run mode | `agent/config.json` | `"once"` for single run, `"loop"` for continuous |

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python, Flask, SQLite |
| Frontend | Vanilla HTML/CSS/JS, Chart.js |
| Agent | PowerShell, Python (pywin32) |
| Packaging | PyInstaller |
| Auth | Werkzeug (password hashing), session-based + API key |

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

*Built for advanced remote auditing and endpoint visibility.*
