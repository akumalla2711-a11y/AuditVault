# =============================================================================
# Get-USBHistory.ps1
# Reads USB storage device history from the USBSTOR registry key.
# Uses inline C# (P/Invoke into advapi32.dll) to read registry key timestamps
# that are not exposed by PowerShell's Get-Item / Get-ItemProperty cmdlets.
# Returns an array of PSCustomObjects.
# =============================================================================

function Get-USBHistory {
    [CmdletBinding()]
    param()

    # =========================================================================
    # Step 1: Define the C# interop type for reading registry key timestamps
    # Only add the type once per session to avoid "type already exists" errors
    # =========================================================================
    if (-not ([System.Management.Automation.PSTypeName]'Win32.Advapi32').Type) {
        try {
            Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace Win32
{
    public class Advapi32
    {
        [DllImport("advapi32.dll", EntryPoint = "RegQueryInfoKeyW", SetLastError = true)]
        public static extern int RegQueryInfoKey(
            IntPtr hKey,
            IntPtr lpClass,
            IntPtr lpcchClass,
            IntPtr lpReserved,
            IntPtr lpcSubKeys,
            IntPtr lpcbMaxSubKeyLen,
            IntPtr lpcbMaxClassLen,
            IntPtr lpcValues,
            IntPtr lpcbMaxValueNameLen,
            IntPtr lpcbMaxValueLen,
            IntPtr lpcbSecurityDescriptor,
            out long lpftLastWriteTime
        );

        /// <summary>
        /// Opens a registry key handle via .NET RegistryKey and reads its LastWriteTime.
        /// Returns DateTime.MinValue on failure.
        /// </summary>
        public static DateTime GetRegistryKeyTimestamp(RegistryKey key)
        {
            long timestamp;
            int result = RegQueryInfoKey(
                key.Handle.DangerousGetHandle(),
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero,
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero,
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero,
                IntPtr.Zero, out timestamp
            );

            if (result == 0) // ERROR_SUCCESS
                return DateTime.FromFileTimeUtc(timestamp);

            return DateTime.MinValue;
        }
    }
}
"@ -ErrorAction Stop
        }
        catch {
            # If compilation fails (e.g. constrained language mode), proceed without timestamps
        }
    }

    # =========================================================================
    # Helper: Read a device property timestamp from the GUID-based properties key
    # GUID {83da6326-97a6-4088-9453-a1923f573b29}:
    #   0064 = Date installed
    #   0066 = Date of first connection
    #   0067 = Date of last connection
    # =========================================================================
    function Get-DevicePropertyDate {
        param(
            [string]$DeviceKeyPath,
            [string]$PropertyId   # e.g. "0064", "0066", "0067"
        )

        $guid = "{83da6326-97a6-4088-9453-a1923f573b29}"
        $propPath = Join-Path $DeviceKeyPath "Properties\$guid\$PropertyId"

        try {
            if (Test-Path -Path "Registry::$propPath" -ErrorAction SilentlyContinue) {
                $propKey = Get-ItemProperty -Path "Registry::$propPath" -ErrorAction SilentlyContinue
                # The timestamp is stored as a binary REG_BINARY (FILETIME) in the default value or (Data)
                $data = $propKey.'(default)'
                if ($null -eq $data) {
                    $data = $propKey.Data
                }
                if ($data -is [byte[]] -and $data.Length -ge 8) {
                    $fileTime = [BitConverter]::ToInt64($data, 0)
                    if ($fileTime -gt 0) {
                        return [DateTime]::FromFileTimeUtc($fileTime).ToString("yyyy-MM-dd HH:mm:ss")
                    }
                }
            }
        }
        catch {
            # Silently ignore — property may not exist for this device
        }
        return $null
    }

    # =========================================================================
    # Step 2: Enumerate USBSTOR devices from the registry
    # =========================================================================
    try {
        $usbStorPath = "HKLM:\SYSTEM\CurrentControlSet\Enum\USBSTOR"

        if (-not (Test-Path $usbStorPath)) {
            return @()
        }

        $results = @()

        # Each subkey under USBSTOR represents a device class (e.g. "Disk&Ven_Kingston&Prod_DataTraveler...")
        $deviceClasses = Get-ChildItem -Path $usbStorPath -ErrorAction SilentlyContinue

        foreach ($deviceClass in $deviceClasses) {
            # Each subkey under the device class is a specific device instance (serial number)
            $deviceInstances = Get-ChildItem -Path $deviceClass.PSPath -ErrorAction SilentlyContinue

            foreach ($instance in $deviceInstances) {
                $props = Get-ItemProperty -Path $instance.PSPath -ErrorAction SilentlyContinue

                # Extract the serial number from the registry key name (last path segment)
                $serialNumber = $instance.PSChildName
                # Some serial numbers have a trailing "&0" or "&1" — strip it for cleanliness
                $cleanSerial = $serialNumber -replace '&\d+$', ''

                # Friendly name of the device
                $friendlyName = $props.FriendlyName
                if (-not $friendlyName) {
                    $friendlyName = $props.DeviceDesc
                    # DeviceDesc often has a prefix like "@disk.inf,%disk_devdesc%;"; extract readable part
                    if ($friendlyName -match ';(.+)$') {
                        $friendlyName = $Matches[1]
                    }
                }

                # Read property timestamps via the GUID-based properties subkeys
                $hklmPath = $instance.Name  # Full registry path (HKEY_LOCAL_MACHINE\...)
                $installed      = Get-DevicePropertyDate -DeviceKeyPath $hklmPath -PropertyId "0064"
                $firstConnected = Get-DevicePropertyDate -DeviceKeyPath $hklmPath -PropertyId "0066"
                $lastConnected  = Get-DevicePropertyDate -DeviceKeyPath $hklmPath -PropertyId "0067"

                # Determine connection status:
                # If the device has a "Service" value and its status shows as started,
                # it may be currently connected. A rough heuristic: if last-connected
                # equals first-connected or timestamps are very close, device may still be plugged in.
                $status = "Disconnected"
                if ($lastConnected -and $firstConnected -and ($lastConnected -eq $firstConnected)) {
                    $status = "Currently Connected"
                }
                # Also check if the device is currently present via PnP
                try {
                    $pnpDevice = Get-PnpDevice -InstanceId "$($deviceClass.PSChildName)\$serialNumber" -ErrorAction SilentlyContinue
                    if ($pnpDevice -and $pnpDevice.Status -eq 'OK') {
                        $status = "Currently Connected"
                    }
                }
                catch {
                    # Get-PnpDevice may not be available on all systems
                }

                $results += [PSCustomObject]@{
                    DeviceName     = $friendlyName
                    SerialNumber   = $cleanSerial
                    Status         = $status
                    Installed      = $installed
                    FirstConnected = $firstConnected
                    LastConnected  = $lastConnected
                }
            }
        }

        $results
    }
    catch {
        @([PSCustomObject]@{
            Error   = $true
            Message = $_.Exception.Message
        })
    }
}

# Execute and output
Get-USBHistory
