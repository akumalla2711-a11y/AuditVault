# =============================================================================
# Get-NetworkInfo.ps1
# Gathers network adapter details and their IPv4 addresses.
# Combines Win32_NetworkAdapter (for MAC / connection status) with
# Get-NetIPAddress (for IP addresses). Returns array of PSCustomObjects.
# =============================================================================

function Get-NetworkInfo {
    [CmdletBinding()]
    param()

    # -------------------------------------------------------------------------
    # Helper: Translate numeric NetConnectionStatus codes to readable text
    # Reference: https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-networkadapter
    # -------------------------------------------------------------------------
    function ConvertTo-ConnectionStatus {
        param([int]$Code)

        switch ($Code) {
            0  { "Disconnected" }
            1  { "Connecting" }
            2  { "Connected" }
            3  { "Disconnecting" }
            4  { "Hardware Not Present" }
            5  { "Hardware Disabled" }
            6  { "Hardware Malfunction" }
            7  { "Media Disconnected" }
            8  { "Authenticating" }
            9  { "Authentication Succeeded" }
            10 { "Authentication Failed" }
            11 { "Invalid Address" }
            12 { "Credentials Required" }
            default { "Unknown ($Code)" }
        }
    }

    try {
        # Get all physical/virtual adapters that have a NetConnectionID (filters out internal-only adapters)
        $adapters = Get-CimInstance -ClassName Win32_NetworkAdapter -ErrorAction SilentlyContinue |
            Where-Object { $null -ne $_.NetConnectionID }

        # Pre-fetch all IPv4 addresses (exclude loopback 127.x.x.x) and index by InterfaceIndex
        $ipAddresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -ne "127.0.0.1" }

        # Build a lookup hashtable: InterfaceIndex -> IP address string
        $ipLookup = @{}
        foreach ($ip in $ipAddresses) {
            $ipLookup[$ip.InterfaceIndex] = $ip.IPAddress
        }

        foreach ($adapter in $adapters) {
            [PSCustomObject]@{
                Name           = $adapter.Name
                Status         = ConvertTo-ConnectionStatus -Code $adapter.NetConnectionStatus
                IPAddress      = $ipLookup[[int]$adapter.InterfaceIndex]
                MACAddress     = $adapter.MACAddress
                InterfaceAlias = $adapter.NetConnectionID
            }
        }
    }
    catch {
        @([PSCustomObject]@{
            Error   = $true
            Message = $_.Exception.Message
        })
    }
}

# Execute and output
Get-NetworkInfo
