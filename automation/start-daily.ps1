param(
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$Date,
    [switch]$Force,
    [switch]$NoPublish,
    [ValidateRange(15, 600)][int]$LoginTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$privateDir = if ($env:RESEARCH_DAILY_PRIVATE) { [IO.Path]::GetFullPath($env:RESEARCH_DAILY_PRIVATE) } else { Join-Path $projectRoot '.private' }
$configPath = Join-Path $privateDir 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) { exit 2 }
$dailyConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if (-not $dailyConfig.enabled) { exit 0 }
if (-not $Date) { $Date = [DateTime]::UtcNow.AddHours(8).Date.AddDays(-1).ToString('yyyy-MM-dd') }
$targetDay = [DateTime]::ParseExact($Date, 'yyyy-MM-dd', [Globalization.CultureInfo]::InvariantCulture)
if ($targetDay -ge [DateTime]::UtcNow.AddHours(8).Date) { throw 'Only completed dates can be collected.' }

# One mutex spans collection and summarization; the Node lock alone covers only each stage.
$hasher = [Security.Cryptography.SHA256]::Create()
try { $identity = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($privateDir.ToLowerInvariant()))).Replace('-', '').Substring(0, 24) }
finally { $hasher.Dispose() }
$mutex = New-Object Threading.Mutex($false, ('Local\ResearchDaily_' + $identity))
$ownsMutex = $false
$napSession = $null
$exitCode = 0
try {
    try { $ownsMutex = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { exit 0 }
    if (-not $Force -and (Test-Path -LiteralPath (Join-Path $privateDir ('published\' + $Date + '.json')))) { exit 0 }

    $logDir = Join-Path $privateDir 'logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    . (Join-Path $PSScriptRoot 'napcat-process.ps1')
    $nodeTool = Get-Command node.exe -ErrorAction SilentlyContinue
    $nodeCommand = if ($nodeTool) { $nodeTool.Source } else { Join-Path $env:ProgramFiles 'nodejs\node.exe' }
    if (-not (Test-Path -LiteralPath $nodeCommand)) { throw 'Node.js is not installed.' }

    # Keep the saved Codex binary while it exists; recover after an app update removes it.
    if (-not $dailyConfig.codexExecutable -or -not (Test-Path -LiteralPath $dailyConfig.codexExecutable)) {
        $codexTool = Get-Command codex.exe -ErrorAction SilentlyContinue
        $codexPath = if ($codexTool) { $codexTool.Source } else {
            $codexBinRoot = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin'
            (Get-ChildItem -LiteralPath $codexBinRoot -Filter codex.exe -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
        }
        if (-not $codexPath) { throw 'Codex CLI is unavailable. Open Codex and sign in first.' }
        $dailyConfig | Add-Member -NotePropertyName codexExecutable -NotePropertyValue $codexPath -Force
        $temporaryConfig = $configPath + '.startup.tmp'
        [IO.File]::WriteAllText($temporaryConfig, ($dailyConfig | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $temporaryConfig -Destination $configPath -Force
    }

    $endpoint = [Uri]$dailyConfig.websocket
    if ($endpoint.Scheme -notin @('ws', 'wss') -or $endpoint.Host -notin @('127.0.0.1', 'localhost', '::1', '[::1]')) { throw 'History endpoint must be on this computer.' }
    $endpointPort = if ($endpoint.Port -gt 0) { $endpoint.Port } elseif ($endpoint.Scheme -eq 'wss') { 443 } else { 80 }
    if (-not (Test-NapCatEndpoint -HostName $endpoint.DnsSafeHost -Port $endpointPort)) {
        if (Get-Process -Name QQ -ErrorAction SilentlyContinue) { throw 'Desktop QQ is running. The reader did not replace or close that session.' }
        $napSession = Start-NapCatReader -Config $dailyConfig -LogDirectory $logDir
        $deadline = [DateTime]::UtcNow.AddSeconds($LoginTimeoutSeconds)
        $historyOnline = $false
        do {
            Update-NapCatOwnedProcesses -Session $napSession
            if (Test-NapCatEndpoint -HostName $endpoint.DnsSafeHost -Port $endpointPort) { $historyOnline = $true; break }
            if (-not (Test-NapCatOwnedProcessAlive -Session $napSession)) { throw 'QQ history reader exited before login. See the private NapCat logs.' }
            Start-Sleep -Seconds 2
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not $historyOnline) { throw 'QQ login expired or is not ready. A fresh scan is needed.' }
    }

    $runner = Join-Path $PSScriptRoot 'run.mjs'
    $runArguments = @($runner, '--date', $Date)
    if ($Force) { $runArguments += '--force' }
    & $nodeCommand @runArguments --collect-only 1>> (Join-Path $logDir 'daily.log') 2>> (Join-Path $logDir 'daily.error.log')
    if ($LASTEXITCODE -ne 0) { throw ('History collection did not finish (exit ' + $LASTEXITCODE + '). See status.json and private logs.') }

    # Release only the session launched above before the longer model/publishing stage.
    if ($napSession) { Stop-NapCatReader -Session $napSession; $napSession = $null }
    $inputPath = Join-Path $privateDir ('inputs\' + $Date + '.json')
    if (-not (Test-Path -LiteralPath $inputPath)) { throw 'No collected history packet was produced.' }
    $runArguments += @('--from-file', $inputPath)
    if ($NoPublish) { $runArguments += '--no-publish' }
    & $nodeCommand @runArguments 1>> (Join-Path $logDir 'daily.log') 2>> (Join-Path $logDir 'daily.error.log')
    $exitCode = $LASTEXITCODE
} catch {
    $exitCode = 1
    $failure = @{ date = $Date; stage = 'Daily update did not finish'; error = $_.Exception.Message; updatedAt = [DateTime]::UtcNow.ToString('o') }
    [IO.File]::WriteAllText((Join-Path $privateDir 'status.json'), ($failure | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
} finally {
    if ($napSession) { Stop-NapCatReader -Session $napSession }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
exit $exitCode
