# =============================================================================
# Get-LoginHistory.ps1
# Retrieves recent security logon events (successful, failed, explicit creds)
# from the Windows Security event log using Get-WinEvent.
# Requires elevated privileges (Run as Administrator) for Security log access.
# Returns an array of PSCustomObjects.
# =============================================================================

function Get-LoginHistory {
    [CmdletBinding()]
    param()

    try {
        # Use FilterHashtable for efficient server-side filtering
        # Event IDs:
        #   4624 = Successful logon
        #   4625 = Failed logon
        #   4648 = Logon using explicit credentials (e.g. RunAs)
        $events = Get-WinEvent -FilterHashtable @{
            LogName = 'Security'
            Id      = @(4624, 4625, 4648)
        } -MaxEvents 100 -ErrorAction SilentlyContinue

        if (-not $events) {
            # No events found or no permission — return empty array
            return @()
        }

        foreach ($event in $events) {
            # Parse event XML to extract structured fields
            $xml = [xml]$event.ToXml()
            $eventData = $xml.Event.EventData.Data

            # TargetUser: field name depends on Event ID
            #   4624/4625 -> TargetUserName (index 5)
            #   4648      -> TargetUserName (index 5) — the account whose creds were used
            $targetUser  = ($eventData | Where-Object { $_.Name -eq 'TargetUserName' }).'#text'
            $logonType   = ($eventData | Where-Object { $_.Name -eq 'LogonType' }).'#text'
            $ipAddress   = ($eventData | Where-Object { $_.Name -eq 'IpAddress' }).'#text'

            # Truncate the full message to 300 characters to keep payload small
            $messageText = $event.Message
            if ($messageText -and $messageText.Length -gt 300) {
                $messageText = $messageText.Substring(0, 300) + "..."
            }

            [PSCustomObject]@{
                TimeCreated = $event.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                EventId     = $event.Id
                Level       = $event.LevelDisplayName
                TargetUser  = $targetUser
                LogonType   = $logonType
                IpAddress   = $ipAddress
                Message     = $messageText
            }
        }
    }
    catch {
        # Gracefully handle lack of admin rights or missing log
        @([PSCustomObject]@{
            Error   = $true
            Message = "Failed to read Security log: $($_.Exception.Message). Run as Administrator."
        })
    }
}

# Execute and output
Get-LoginHistory
