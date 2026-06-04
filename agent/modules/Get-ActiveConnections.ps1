# =============================================================================
# Get-ActiveConnections.ps1
# Lists active TCP connections (Established + Listen) using Get-NetTCPConnection.
# Maps each connection's OwningProcess PID to its process name.
# Returns an array of PSCustomObjects.
# =============================================================================

function Get-ActiveConnections {
    [CmdletBinding()]
    param()

    try {
        # Fetch only Established and Listen connections
        $connections = Get-NetTCPConnection -State Established, Listen -ErrorAction SilentlyContinue

        # Build a PID-to-Name lookup table to avoid calling Get-Process per connection
        $processLookup = @{}
        Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
            $processLookup[$_.Id] = $_.ProcessName
        }

        foreach ($conn in $connections) {
            # Resolve process name from PID; fall back to "Unknown" if not found
            $processName = $processLookup[[int]$conn.OwningProcess]
            if (-not $processName) {
                $processName = "PID: $($conn.OwningProcess)"
            }

            [PSCustomObject]@{
                LocalAddress  = $conn.LocalAddress
                LocalPort     = $conn.LocalPort
                RemoteAddress = $conn.RemoteAddress
                RemotePort    = $conn.RemotePort
                State         = $conn.State.ToString()
                OwningProcess = $processName
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
Get-ActiveConnections
