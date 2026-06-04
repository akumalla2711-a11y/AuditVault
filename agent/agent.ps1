# =============================================================================
# agent.ps1 — AuditVault V2 Remote Audit Agent
# Handles Registration, Telemetry Collection, and Server Communication.
# =============================================================================

Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ConfigPath = Join-Path $ScriptDir "config.json"
$ModulesDir = Join-Path $ScriptDir "modules"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AuditVault V2 Agent" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

if (-not (Test-Path $ConfigPath)) {
    Write-Host "[ERROR] Configuration file not found: $ConfigPath" -ForegroundColor Red
    exit 1
}

$Config = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json

$ServerUrl       = $Config.server_url
$EnrollmentKey   = $Config.enrollment_key
$EndpointId      = $Config.endpoint_id
$ApiKey          = $Config.api_key
$IntervalSeconds = $Config.interval_seconds
$RunMode         = $Config.run_mode

# =============================================================================
# Registration Flow
# =============================================================================
function Register-Agent {
    Write-Host "[*] Endpoint not registered. Initiating Enrollment Flow..." -ForegroundColor Yellow
    
    $machineGuid = (Get-CimInstance Win32_ComputerSystemProduct).UUID
    if (-not $machineGuid) { $machineGuid = [guid]::NewGuid().ToString() }
    
    $osInfo = Get-CimInstance Win32_OperatingSystem
    
    $payload = @{
        enrollment_key = $EnrollmentKey
        machine_guid   = $machineGuid
        hostname       = $env:COMPUTERNAME
        os_caption     = $osInfo.Caption
        os_version     = $osInfo.Version
        agent_version  = "2.0"
    } | ConvertTo-Json
    
    $regUrl = $ServerUrl.Replace("/api/audit", "/api/register")
    
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
        $response = Invoke-RestMethod -Uri $regUrl -Method Post -Body $bytes -ContentType "application/json; charset=utf-8" -ErrorAction Stop
        
        Write-Host "[+] Registration successful. Identity assigned." -ForegroundColor Green
        
        # Save to config
        $Config.endpoint_id = $response.endpoint_id
        $Config.api_key = $response.api_key
        $Config | ConvertTo-Json -Depth 5 | Out-File $ConfigPath -Encoding UTF8
        
        $script:EndpointId = $response.endpoint_id
        $script:ApiKey = $response.api_key
        
        if ($response.status -eq "Pending") {
            Write-Host "[!] Endpoint is Pending Approval by an Administrator." -ForegroundColor Magenta
            Write-Host "[!] Please approve this endpoint in the AuditVault Dashboard." -ForegroundColor Magenta
            exit 0
        }
    }
    catch {
        Write-Host "[!] Registration failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

if (-not $ApiKey) {
    Register-Agent
}

# =============================================================================
# Audit Modules Helper
# =============================================================================
function Invoke-AuditModule {
    param([string]$ModuleName)
    $scriptPath = Join-Path $ModulesDir "$ModuleName.ps1"
    if (-not (Test-Path $scriptPath)) { return $null }
    try { return & $scriptPath } catch { return $null }
}

# =============================================================================
# Main Audit Collection
# =============================================================================
function Start-AuditCollection {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    Write-Host "[*] Starting audit collection at $timestamp" -ForegroundColor Cyan

    $payload = [PSCustomObject]@{
        endpoint_id     = $EndpointId
        hostname        = $env:COMPUTERNAME
        timestamp       = $timestamp
        os_details      = Invoke-AuditModule "Get-OSDetails"
        software_list   = @(Invoke-AuditModule "Get-InstalledSoftware")
        network_info    = @(Invoke-AuditModule "Get-NetworkInfo")
        connections     = @(Invoke-AuditModule "Get-ActiveConnections")
        process_list    = @(Invoke-AuditModule "Get-ProcessList")
        login_history   = @(Invoke-AuditModule "Get-LoginHistory")
        usb_history     = @(Invoke-AuditModule "Get-USBHistory")
        defender_status = Invoke-AuditModule "Get-DefenderStatus"
    }

    $jsonPayload = $payload | ConvertTo-Json -Depth 10

    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonPayload)
        $response = Invoke-RestMethod -Uri $ServerUrl -Method Post -Body $bytes -ContentType "application/json; charset=utf-8" -Headers @{ "X-API-Key" = $ApiKey } -ErrorAction Stop
        Write-Host "[+] Audit data submitted successfully." -ForegroundColor Green
    }
    catch {
        $ex = $_.Exception
        if ($ex.Response.StatusCode -eq 403) {
            Write-Host "[!] Server rejected payload (403 Forbidden). Endpoint may be Pending Approval or Blocked." -ForegroundColor Magenta
        } else {
            Write-Host "[!] Audit submission failed: $($ex.Message)" -ForegroundColor Red
        }
    }
}

# =============================================================================
# Run Loop
# =============================================================================
if ($RunMode.ToLower() -eq "loop") {
    Write-Host "[*] Running in LOOP mode ($IntervalSeconds sec)" -ForegroundColor Cyan
    while ($true) {
        Start-AuditCollection
        Start-Sleep -Seconds $IntervalSeconds
    }
} else {
    Start-AuditCollection
}
