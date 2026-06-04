"""
AuditVault Agent v3.0 — Python Windows Service
================================================
A lightweight endpoint monitoring agent that runs as a Windows Service.
Collects system telemetry via PowerShell modules and sends it to the
AuditVault server. Features local logging, offline queueing, and full
service lifecycle management.

Usage:
    AuditVaultAgent.exe install
    AuditVaultAgent.exe uninstall
    AuditVaultAgent.exe start
    AuditVaultAgent.exe stop
    AuditVaultAgent.exe status
"""

import os
import sys
import json
import time
import uuid
import socket
import logging
import subprocess
import platform
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Third-party
import requests

# Windows Service support
import win32serviceutil
import win32service
import win32event
import servicemanager


# =============================================================================
# Constants
# =============================================================================
AGENT_VERSION = "3.0.0"

SERVICE_NAME = "AuditVaultAgent"
SERVICE_DISPLAY = "AuditVault Monitoring Agent"
SERVICE_DESCRIPTION = "Collects system telemetry and security data for the AuditVault dashboard."

# Resolve paths relative to the EXE/script location
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_PATH  = BASE_DIR / "config.json"
MODULES_DIR  = BASE_DIR / "modules"
LOG_DIR      = BASE_DIR / "logs"
QUEUE_DIR    = BASE_DIR / "queue"

POWERSHELL_MODULES = [
    "Get-OSDetails",
    "Get-InstalledSoftware",
    "Get-NetworkInfo",
    "Get-ActiveConnections",
    "Get-ProcessList",
    "Get-LoginHistory",
    "Get-USBHistory",
    "Get-DefenderStatus",
]


# =============================================================================
# Logging Setup
# =============================================================================
def setup_logging():
    """Configure rotating file + console logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "agent.log"

    logger = logging.getLogger("AuditVault")
    logger.setLevel(logging.DEBUG)

    # Rotate at 5 MB, keep 3 backups
    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(file_handler)

    # Console handler (useful when running interactively)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "[%(levelname)-7s] %(message)s"
    ))
    logger.addHandler(console_handler)

    return logger


log = setup_logging()


# =============================================================================
# Configuration
# =============================================================================
class Config:
    """Reads and manages the external config.json."""

    def __init__(self):
        self.server_url = ""
        self.enrollment_key = ""
        self.endpoint_id = ""
        self.api_key = ""
        self.interval_seconds = 300
        self.run_mode = "loop"
        self.load()

    def load(self):
        if not CONFIG_PATH.exists():
            log.error("Configuration file not found: %s", CONFIG_PATH)
            raise FileNotFoundError(f"config.json not found at {CONFIG_PATH}")

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.server_url       = data.get("server_url", "")
        self.enrollment_key   = data.get("enrollment_key", "")
        self.endpoint_id      = data.get("endpoint_id", "")
        self.api_key          = data.get("api_key", "")
        self.interval_seconds = data.get("interval_seconds", 300)
        self.run_mode         = data.get("run_mode", "loop")

        log.info("Configuration loaded from %s", CONFIG_PATH)

    def save(self):
        data = {
            "server_url":       self.server_url,
            "enrollment_key":   self.enrollment_key,
            "endpoint_id":      self.endpoint_id,
            "api_key":          self.api_key,
            "interval_seconds": self.interval_seconds,
            "run_mode":         self.run_mode,
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        log.info("Configuration saved to %s", CONFIG_PATH)


# =============================================================================
# Offline Queue
# =============================================================================
class OfflineQueue:
    """
    Persists failed telemetry payloads to disk so they can be retried
    when connectivity is restored. Each payload is stored as a separate
    JSON file in the queue/ directory.
    """

    def __init__(self):
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)

    def enqueue(self, payload: dict):
        """Save a failed payload to the queue."""
        filename = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.json"
        filepath = QUEUE_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        log.info("Payload queued for retry: %s", filename)

    def pending_files(self) -> list:
        """Return a sorted list of queued payload file paths (oldest first)."""
        files = sorted(QUEUE_DIR.glob("evt_*.json"))
        return files

    def dequeue(self, filepath: Path):
        """Remove a successfully sent payload from the queue."""
        try:
            filepath.unlink()
            log.debug("Dequeued: %s", filepath.name)
        except OSError as e:
            log.warning("Failed to delete queue file %s: %s", filepath.name, e)

    @property
    def size(self) -> int:
        return len(list(QUEUE_DIR.glob("evt_*.json")))


# =============================================================================
# PowerShell Module Runner
# =============================================================================
def invoke_ps_module(module_name: str) -> object:
    """
    Execute a PowerShell module script and return its output as parsed JSON.
    Falls back to None on any failure.
    """
    script_path = MODULES_DIR / f"{module_name}.ps1"
    if not script_path.exists():
        log.warning("Module not found: %s", script_path)
        return None

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command",
                f"$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                f"& {{ . '{script_path}' | ConvertTo-Json -Depth 10 -Compress }}"
            ],
            capture_output=True, timeout=30,
            encoding="utf-8", errors="replace"
        )

        if result.returncode != 0 and result.stderr.strip():
            log.warning("Module %s stderr: %s", module_name, result.stderr.strip()[:200])

        output = result.stdout.strip()
        if not output:
            return None

        return json.loads(output)

    except subprocess.TimeoutExpired:
        log.error("Module %s timed out after 30 seconds", module_name)
        return None
    except json.JSONDecodeError as e:
        log.error("Module %s returned invalid JSON: %s", module_name, e)
        return None
    except Exception as e:
        log.error("Module %s execution error: %s", module_name, e)
        return None


# =============================================================================
# Agent Core Logic
# =============================================================================
class AuditAgent:
    """Core agent logic: registration, collection, transmission, queueing."""

    def __init__(self):
        self.config = Config()
        self.queue = OfflineQueue()

    # --- Registration ---
    def register(self):
        """Register this endpoint with the AuditVault server."""
        log.info("Endpoint not registered. Starting enrollment flow...")

        reg_url = self.config.server_url.replace("/api/audit", "/api/register")

        # Gather machine identity
        try:
            machine_guid = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                capture_output=True, text=True, timeout=15, encoding="utf-8"
            ).stdout.strip()
        except Exception:
            machine_guid = str(uuid.uuid4())

        if not machine_guid:
            machine_guid = str(uuid.uuid4())

        os_info = platform.uname()

        payload = {
            "enrollment_key": self.config.enrollment_key,
            "machine_guid":   machine_guid,
            "hostname":       socket.gethostname(),
            "os_caption":     f"{os_info.system} {os_info.release}",
            "os_version":     os_info.version,
            "agent_version":  AGENT_VERSION,
        }

        try:
            resp = requests.post(reg_url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            self.config.endpoint_id = data.get("endpoint_id", "")
            self.config.api_key = data.get("api_key", "")
            self.config.save()

            status = data.get("status", "Unknown")
            log.info("Registration successful. Status: %s", status)

            if status == "Pending":
                log.warning("Endpoint is PENDING admin approval. Telemetry will be rejected until approved.")

        except requests.RequestException as e:
            log.error("Registration failed: %s", e)
            raise

    # --- Collection ---
    def collect_telemetry(self) -> dict:
        """Run all PowerShell modules and assemble a telemetry payload."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log.info("Starting telemetry collection at %s", timestamp)

        payload = {
            "endpoint_id":     self.config.endpoint_id,
            "hostname":        socket.gethostname(),
            "agent_version":   AGENT_VERSION,
            "timestamp":       timestamp,
            "os_details":      invoke_ps_module("Get-OSDetails"),
            "software_list":   invoke_ps_module("Get-InstalledSoftware") or [],
            "network_info":    invoke_ps_module("Get-NetworkInfo") or [],
            "connections":     invoke_ps_module("Get-ActiveConnections") or [],
            "process_list":    invoke_ps_module("Get-ProcessList") or [],
            "login_history":   invoke_ps_module("Get-LoginHistory") or [],
            "usb_history":     invoke_ps_module("Get-USBHistory") or [],
            "defender_status": invoke_ps_module("Get-DefenderStatus"),
        }

        # Ensure list fields are actually lists
        for key in ["software_list", "network_info", "connections", "process_list",
                     "login_history", "usb_history"]:
            if not isinstance(payload[key], list):
                payload[key] = [payload[key]] if payload[key] else []

        module_count = sum(1 for k, v in payload.items()
                          if k not in ("endpoint_id", "hostname", "timestamp") and v)
        log.info("Collection complete. %d modules returned data.", module_count)
        return payload

    # --- Transmission ---
    def send_payload(self, payload: dict) -> bool:
        """POST a telemetry payload to the server. Returns True on success."""
        try:
            resp = requests.post(
                self.config.server_url,
                json=payload,
                headers={"X-API-Key": self.config.api_key},
                timeout=20,
            )

            if resp.status_code == 403:
                log.warning("Server rejected payload (403). Endpoint may be Pending or Blocked.")
                return False

            resp.raise_for_status()
            log.info("Telemetry submitted successfully.")
            return True

        except requests.ConnectionError:
            log.error("Connection failed — server unreachable.")
            return False
        except requests.Timeout:
            log.error("API request timed out.")
            return False
        except requests.RequestException as e:
            log.error("Submission failed: %s", e)
            return False

    # --- Heartbeat ---
    def send_heartbeat(self) -> bool:
        """Send a lightweight heartbeat ping to keep last_seen accurate."""
        heartbeat_url = self.config.server_url.replace("/api/audit", "/api/heartbeat")
        payload = {
            "endpoint_id":   self.config.endpoint_id,
            "hostname":      socket.gethostname(),
            "agent_version": AGENT_VERSION,
            "timestamp":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type":          "heartbeat",
        }
        try:
            resp = requests.post(
                heartbeat_url, json=payload,
                headers={"X-API-Key": self.config.api_key},
                timeout=10,
            )
            if resp.ok:
                log.debug("Heartbeat sent successfully.")
                return True
            else:
                log.warning("Heartbeat rejected (HTTP %d).", resp.status_code)
                return False
        except requests.RequestException as e:
            log.warning("Heartbeat failed: %s", e)
            return False

    # --- Queue Drain ---
    def drain_queue(self):
        """Attempt to resend all queued payloads (oldest first)."""
        pending = self.queue.pending_files()
        if not pending:
            return

        log.info("Draining offline queue: %d pending payloads", len(pending))
        for filepath in pending:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                if self.send_payload(payload):
                    self.queue.dequeue(filepath)
                else:
                    log.warning("Queue drain: still failing to send. Stopping drain.")
                    break  # Server is still down, stop trying
            except Exception as e:
                log.error("Error reading queued file %s: %s", filepath.name, e)

    # --- Single Audit Cycle ---
    def run_cycle(self):
        """One complete audit cycle: heartbeat → drain queue → collect → send/queue."""
        # 0. Send heartbeat first
        self.send_heartbeat()

        # 1. Try to drain any backlog
        self.drain_queue()

        # 2. Collect fresh telemetry
        payload = self.collect_telemetry()

        # 3. Try to send; queue on failure
        if not self.send_payload(payload):
            self.queue.enqueue(payload)
            log.warning("Payload queued for later delivery. Queue size: %d", self.queue.size)


# =============================================================================
# Windows Service
# =============================================================================
class AuditVaultService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY
    _svc_description_ = SERVICE_DESCRIPTION

    @classmethod
    def customInstall(cls, *args):
        """Post-install: configure auto-restart on failure."""
        try:
            # Restart after 30 seconds on all three failure attempts
            subprocess.run(
                ["sc", "failure", SERVICE_NAME,
                 "reset=", "86400",
                 "actions=", "restart/30000/restart/30000/restart/30000"],
                check=True, capture_output=True
            )
            print(f"  [+] Service recovery configured: auto-restart on failure (30s delay)")
        except Exception as e:
            print(f"  [!] Warning: Could not set recovery options: {e}")

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        log.info("Service stop requested.")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        log.info("=" * 50)
        log.info("AuditVault Agent v3.0 — Service Started")
        log.info("=" * 50)

        try:
            agent = AuditAgent()

            # Register if not yet enrolled
            if not agent.config.api_key:
                agent.register()

            # Main service loop
            while self.running:
                try:
                    agent.run_cycle()
                except Exception as e:
                    log.error("Audit cycle error: %s", e)

                # Wait for the configured interval, or until stop is signaled
                result = win32event.WaitForSingleObject(
                    self.stop_event, agent.config.interval_seconds * 1000
                )
                if result == win32event.WAIT_OBJECT_0:
                    break  # Stop signal received

        except Exception as e:
            log.critical("Fatal service error: %s", e)

        log.info("AuditVault Agent — Service Stopped")


# =============================================================================
# CLI: Service Lifecycle Commands
# =============================================================================
def print_banner():
    print()
    print("  ============================================")
    print("  |      AuditVault Agent v3.0               |")
    print("  |      Windows Service Manager             |")
    print("  ============================================")
    print()


def cmd_status():
    """Check the current status of the Windows service."""
    import win32service as ws
    try:
        scm = ws.OpenSCManager(None, None, ws.SC_MANAGER_CONNECT)
        svc = ws.OpenService(scm, SERVICE_NAME, ws.SERVICE_QUERY_STATUS)
        status = ws.QueryServiceStatus(svc)
        ws.CloseServiceHandle(svc)
        ws.CloseServiceHandle(scm)

        state_map = {
            ws.SERVICE_STOPPED:          "STOPPED",
            ws.SERVICE_START_PENDING:    "START_PENDING",
            ws.SERVICE_STOP_PENDING:     "STOP_PENDING",
            ws.SERVICE_RUNNING:          "RUNNING",
            ws.SERVICE_CONTINUE_PENDING: "CONTINUE_PENDING",
            ws.SERVICE_PAUSE_PENDING:    "PAUSE_PENDING",
            ws.SERVICE_PAUSED:           "PAUSED",
        }
        state_str = state_map.get(status[1], f"UNKNOWN ({status[1]})")
        print(f"  Service '{SERVICE_NAME}': {state_str}")

    except Exception as e:
        if "1060" in str(e):
            print(f"  Service '{SERVICE_NAME}' is NOT INSTALLED.")
        else:
            print(f"  Error querying service: {e}")


def main():
    """Entry point: handle CLI commands or delegate to Windows Service framework."""
    if len(sys.argv) == 1:
        # Started by Windows Service Control Manager (SCM) with no arguments
        try:
            import winerror
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(AuditVaultService)
            servicemanager.StartServiceCtrlDispatcher()
        except win32service.error as details:
            if details.winerror == winerror.ERROR_FAILED_SERVICE_CONTROLLER_CONNECT:
                win32serviceutil.usage()
        return

    print_banner()

    command = sys.argv[1].lower()
    if command not in ["install", "uninstall", "start", "stop", "status", "run"]:
        print("  Usage:")
        print("    AuditVaultAgent.exe install    — Install the Windows Service")
        print("    AuditVaultAgent.exe uninstall  — Remove the Windows Service")
        print("    AuditVaultAgent.exe start      — Start the service")
        print("    AuditVaultAgent.exe stop       — Stop the service")
        print("    AuditVaultAgent.exe status     — Check service status")
        print("    AuditVaultAgent.exe run        — Run interactively (debug mode)")
        print()
        return

    if command == "status":
        cmd_status()
    elif command == "run":
        # Interactive mode for testing — runs outside the service framework
        log.info("Running in interactive (debug) mode. Press Ctrl+C to stop.")
        agent = AuditAgent()
        if not agent.config.api_key:
            agent.register()
        try:
            while True:
                agent.run_cycle()
                log.info("Sleeping for %d seconds...", agent.config.interval_seconds)
                time.sleep(agent.config.interval_seconds)
        except KeyboardInterrupt:
            log.info("Interrupted. Exiting.")
    else:
        # Delegate install/uninstall/start/stop to pywin32
        win32serviceutil.HandleCommandLine(AuditVaultService)


if __name__ == "__main__":
    main()
