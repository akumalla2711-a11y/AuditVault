# =============================================================================
# Get-OSDetails.ps1
# Collects operating system information using CIM (WMI v2) instances.
# Returns a single PSCustomObject with OS metadata and memory stats.
# =============================================================================

function Get-OSDetails {
    [CmdletBinding()]
    param()

    try {
        # Query Win32_OperatingSystem via CIM (preferred over deprecated Get-WmiObject)
        $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop

        # Build and return a clean PSCustomObject
        [PSCustomObject]@{
            Caption        = $os.Caption
            CSName         = $os.CSName
            Version        = $os.Version
            BuildNumber    = $os.BuildNumber
            OSArchitecture = $os.OSArchitecture
            RegisteredUser = $os.RegisteredUser
            LastBootUpTime = $os.LastBootUpTime.ToString("yyyy-MM-dd HH:mm:ss")
            InstallDate    = $os.InstallDate.ToString("yyyy-MM-dd HH:mm:ss")
            # Memory values are reported in KB by WMI; convert to MB
            TotalMemoryMB  = [math]::Round($os.TotalVisibleMemorySize / 1024, 2)
            FreeMemoryMB   = [math]::Round($os.FreePhysicalMemory / 1024, 2)
        }
    }
    catch {
        # Return a minimal error object so the agent can still build its payload
        [PSCustomObject]@{
            Error   = $true
            Message = $_.Exception.Message
        }
    }
}

# Execute and output
Get-OSDetails
