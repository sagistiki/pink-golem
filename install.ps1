# ClawdBlock installer for Windows (PowerShell).
#   Right-click → Run with PowerShell, or:  powershell -ExecutionPolicy Bypass -File install.ps1 [--yes]
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "ClawdBlock — checking what your computer has" -ForegroundColor Magenta
$py = $null
foreach ($c in @("py", "python", "python3")) {
  if (Get-Command $c -ErrorAction SilentlyContinue) {
    & $c -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
  }
}
if (-not $py) {
  Write-Host "! Python 3.9+ is needed:  winget install Python.Python.3.12   (or https://www.python.org/downloads/ — tick 'Add to PATH')" -ForegroundColor Yellow
  exit 1
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
  Write-Host "! Java 25 is needed for Minecraft 26.x:  winget install EclipseAdoptium.Temurin.25.JDK" -ForegroundColor Yellow
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "! Node.js 20+ is needed for the AI connection:  winget install OpenJS.NodeJS.LTS" -ForegroundColor Yellow
}
& $py clawdblock.py setup @args
exit $LASTEXITCODE
