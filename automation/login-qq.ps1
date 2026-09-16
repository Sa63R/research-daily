param([switch]$Scan, [ValidateRange(30, 900)][int]$TimeoutSeconds = 300)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$privateDir = if ($env:RESEARCH_DAILY_PRIVATE) { [IO.Path]::GetFullPath($env:RESEARCH_DAILY_PRIVATE) } else { Join-Path $projectRoot '.private' }
$configPath = Join-Path $privateDir 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Run node automation/setup.mjs first.' }
$dailyConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if ($Scan) { $dailyConfig.qqAccount = '' }
. (Join-Path $PSScriptRoot 'napcat-process.ps1')
$reader = $null
Push-Location -LiteralPath $projectRoot
try {
    $reader = Start-NapCatReader -Config $dailyConfig -LogDirectory (Join-Path $privateDir 'logs')
    $shellDir = $dailyConfig.napcatShellDir
    if (-not $shellDir) {
        $shellDir = $dailyConfig.napcatDir
        if (-not (Test-Path -LiteralPath (Join-Path $shellDir 'napcat.mjs'))) { $shellDir = Join-Path $shellDir 'napcat' }
    }
    $qrFile = Join-Path $shellDir 'cache\qrcode.png'
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastQrTime = [DateTime]::MinValue
    $endpoint = [Uri]$dailyConfig.websocket
    if ($endpoint.Scheme -notin @('ws', 'wss') -or $endpoint.Host -notin @('127.0.0.1', 'localhost', '::1', '[::1]')) { throw 'History endpoint must be on this computer.' }
    $port = if ($endpoint.Port -gt 0) { $endpoint.Port } elseif ($endpoint.Scheme -eq 'wss') { 443 } else { 80 }
    Write-Host 'Waiting for QQ login. Open the QR image below, scan with mobile QQ, and confirm.'
    $online = $false
    do {
        Update-NapCatOwnedProcesses -Session $reader
        if (Test-NapCatEndpoint -HostName $endpoint.DnsSafeHost -Port $port) { $online = $true; break }
        if (-not (Test-NapCatOwnedProcessAlive -Session $reader)) { throw 'QQ reader exited. See private NapCat logs.' }
        $qr = Get-Item -LiteralPath $qrFile -ErrorAction SilentlyContinue
        if ($qr -and $qr.LastWriteTimeUtc -ge $reader.StartedAt -and $qr.LastWriteTimeUtc -gt $lastQrTime) {
            Write-Host ('QR image: ' + $qr.FullName)
            $lastQrTime = $qr.LastWriteTimeUtc
        }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $online) { throw 'Login timed out. Run this command again when ready.' }
    $loginQuery = @'
import {config,QQReader} from './automation/core.mjs';
const reader=new QQReader(config());
try { await reader.open(); const login=await reader.call('get_login_info'); if(!/^\d+$/.test(String(login.user_id)))throw Error('QQ is not logged in'); console.log(String(login.user_id)); }
finally { reader.close(); }
'@
    $account = & node.exe --input-type=module -e $loginQuery
    if ($LASTEXITCODE -ne 0 -or [string]$account -notmatch '^\d+$') { throw 'Could not verify the signed-in QQ account.' }
    & node.exe (Join-Path $PSScriptRoot 'setup.mjs') --account $account
    if ($LASTEXITCODE -ne 0) { throw 'QQ logged in, but the account setting could not be saved.' }
    Write-Host 'QQ login verified and saved. This reader session will close; daily runs can now use quick login.'
} finally {
    if ($reader) { Stop-NapCatReader -Session $reader }
    Pop-Location
}
