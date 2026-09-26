# Windows Hello identity check for the NeoFace dashboard.
#
# Prompts Windows Hello (PIN/biometric) - the same UserConsentVerifier API
# Google Password Manager uses before autofill - and reports the result via
# exit code. The prompt is shown in the interactive user session; this script
# must be started from that session (the dashboard does).
#
# Exit codes:
#   0 = Verified (user approved with PIN/biometric)
#   1 = declined / cancelled / retries exhausted / busy
#   2 = Windows Hello unavailable (not configured / no device / policy)
#   3 = unexpected error (details on stderr)
param(
    [string]$Message = "Verify it's you to change your saved password"
)
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Security.Credentials.UI.UserConsentVerifier,Windows.Security.Credentials.UI,ContentType=WindowsRuntime]
    $null = [Windows.Foundation.IAsyncOperation`1,Windows.Foundation,ContentType=WindowsRuntime]

    $cvType = [Windows.Security.Credentials.UI.UserConsentVerifier]

    function Wait-WinRtOp($method, $invokeArgs) {
        if (-not $method) { throw "WinRT method not found" }
        $op = $method.Invoke($null, $invokeArgs)
        if (-not $op) { throw "WinRT operation returned null" }
        $garg = $method.ReturnType.GetGenericArguments()[0]
        $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and
            $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        })[0]
        $task = $asTask.MakeGenericMethod($garg).Invoke($null, @($op))
        [void]$task.Wait(60000)
        if (-not $task.IsCompleted) { throw "consent prompt timed out" }
        return $task.Result
    }

    $checkM = $cvType.GetMethod('CheckAvailabilityAsync')
    $avail = (Wait-WinRtOp $checkM @()).ToString()
    if ($avail -ne 'Available') {
        # NotConfigured / DeviceNotPresent / DeviceNotSupported / DisabledByPolicy
        exit 2
    }

    $verifyM = $cvType.GetMethod('RequestVerificationAsync')
    if (-not $verifyM) { $verifyM = $cvType.GetMethod('VerifyUserConsentAsync') }
    $result = (Wait-WinRtOp $verifyM @($Message)).ToString()

    switch ($result) {
        'Verified'             { exit 0 }
        'NotConfiguredForUser' { exit 2 }
        'DeviceNotPresent'     { exit 2 }
        'DisabledByPolicy'     { exit 2 }
        default                { exit 1 }   # Canceled, DeviceBusy, RetriesExhausted
    }
} catch {
    [Console]::Error.WriteLine("win_consent: " + $_.Exception.Message)
    exit 3
}
