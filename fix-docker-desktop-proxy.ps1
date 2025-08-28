# PowerShell script to fix Docker Desktop proxy settings
# Run this in Windows PowerShell as Administrator

Write-Host "Fixing Docker Desktop proxy settings..." -ForegroundColor Yellow

# Stop Docker Desktop
Write-Host "Stopping Docker Desktop..."
Stop-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

# Clear Docker proxy settings
$dockerConfigPath = "$env:APPDATA\Docker\settings.json"
if (Test-Path $dockerConfigPath) {
    $config = Get-Content $dockerConfigPath | ConvertFrom-Json
    $config.proxyHttpMode = "system"
    $config | ConvertTo-Json -Depth 10 | Set-Content $dockerConfigPath
    Write-Host "Proxy settings cleared in Docker Desktop config" -ForegroundColor Green
}

# Restart Docker Desktop
Write-Host "Starting Docker Desktop..."
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

Write-Host "Done! Docker Desktop should now work without proxy issues." -ForegroundColor Green
Write-Host "Please wait for Docker Desktop to fully start before running AutoBot setup." -ForegroundColor Yellow