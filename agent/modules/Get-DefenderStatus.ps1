function Get-DefenderStatus {
    try {
        $defender = Get-MpComputerStatus -ErrorAction Stop
        
        # Threat count requires querying Get-MpThreat which can be slow and requires elevation.
        # We will default to 0 for now to keep the payload lightweight.
        
        return [PSCustomObject]@{
            enabled      = if ($defender.AMServiceEnabled) { 1 } else { 0 }
            real_time    = if ($defender.RealTimeProtectionEnabled) { 1 } else { 0 }
            antispyware  = if ($defender.AntispywareEnabled) { 1 } else { 0 }
            sig_age      = if ($defender.AntispywareSignatureAge) { $defender.AntispywareSignatureAge } else { 0 }
            threats      = 0 
        }
    }
    catch {
        # Defender might be uninstalled or disabled via GPO
        return [PSCustomObject]@{
            enabled      = 0
            real_time    = 0
            antispyware  = 0
            sig_age      = 999
            threats      = 0 
        }
    }
}

Get-DefenderStatus
