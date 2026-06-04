# =============================================================================
# Get-ProcessList.ps1
# Lists the top 100 processes sorted by memory usage (descending).
# Returns an array of PSCustomObjects with Name, PID, CPU time, and MemoryMB.
# =============================================================================

function Get-ProcessList {
    [CmdletBinding()]
    param()

    try {
        Get-Process -ErrorAction SilentlyContinue |
            # Calculate MemoryMB from WorkingSet64, rounded to 2 decimal places
            Select-Object Name, Id, CPU,
                @{ Name = 'MemoryMB'; Expression = { [math]::Round($_.WorkingSet64 / 1MB, 2) } } |
            # Sort heaviest processes first
            Sort-Object -Property MemoryMB -Descending |
            # Limit to top 100
            Select-Object -First 100
    }
    catch {
        @([PSCustomObject]@{
            Error   = $true
            Message = $_.Exception.Message
        })
    }
}

# Execute and output
Get-ProcessList
