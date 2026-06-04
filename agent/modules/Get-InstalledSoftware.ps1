# =============================================================================
# Get-InstalledSoftware.ps1
# Enumerates installed software from the Windows registry (Uninstall keys).
# Avoids Win32_Product which triggers MSI reconfiguration and is extremely slow.
# Returns an array of PSCustomObjects sorted by Name.
# =============================================================================

function Get-InstalledSoftware {
    [CmdletBinding()]
    param()

    try {
        # Define all three registry paths to scan:
        #   1. 64-bit machine-wide installs
        #   2. 32-bit (WoW64) machine-wide installs
        #   3. Current-user installs
        $registryPaths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
        )

        $softwareList = foreach ($path in $registryPaths) {
            # SilentlyContinue handles cases where the path doesn't exist (e.g. no WoW64 on ARM)
            Get-ItemProperty -Path $path -ErrorAction SilentlyContinue |
                Where-Object { $_.DisplayName } |
                ForEach-Object {
                    [PSCustomObject]@{
                        Name        = $_.DisplayName
                        Publisher   = $_.Publisher
                        Version     = $_.DisplayVersion
                        InstallDate = $_.InstallDate
                    }
                }
        }

        # Deduplicate by Name+Version (same app may appear in both 64-bit and WoW64 paths),
        # then sort alphabetically by name
        $softwareList |
            Sort-Object -Property Name, Version -Unique |
            Sort-Object -Property Name
    }
    catch {
        @([PSCustomObject]@{
            Error   = $true
            Message = $_.Exception.Message
        })
    }
}

# Execute and output
Get-InstalledSoftware
