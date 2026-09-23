# Parse every tracked PowerShell script; exit 1 on any parse error.
# Run from the repo root:  powershell -File tools\check_ps1_syntax.ps1
$files = @(git ls-files "*.ps1")
if ($files.Count -eq 0) {
    Write-Host "no PowerShell files tracked"
    exit 1
}
$bad = 0
foreach ($f in $files) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Get-Location) $f), [ref]$tokens, [ref]$errors)
    if ($errors -and $errors.Count) {
        $bad++
        foreach ($e in $errors) {
            Write-Host "FAIL ${f}:$($e.Extent.StartLineNumber): $($e.Message)"
        }
    }
}
Write-Host "checked $($files.Count) PowerShell files, $bad bad"
if ($bad -gt 0) { exit 1 }
exit 0
