$ErrorActionPreference = 'Stop'
$taskName = 'ResearchDailyOnLogon'
$scriptPath = Join-Path $PSScriptRoot 'start-daily.ps1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$privateDir = if ($env:RESEARCH_DAILY_PRIVATE) { [IO.Path]::GetFullPath($env:RESEARCH_DAILY_PRIVATE) } else { Join-Path $projectRoot '.private' }
$configPath = Join-Path $privateDir 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) { throw 'Run automation/setup.mjs and verify a daily report before installing the startup task.' }
$dailyConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if (-not $dailyConfig.enabled -or $dailyConfig.qqAccount -notmatch '^\d+$') { throw 'Verify QQ login first, then run setup.mjs --enable --account YOUR_QQ_ACCOUNT.' }
if ($env:RESEARCH_DAILY_PRIVATE) { throw 'The scheduled task uses the project .private directory. Install it without RESEARCH_DAILY_PRIVATE set.' }
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
# Use the same PowerShell 7 runtime that ran installation and the login test.
# Windows PowerShell 5 can have a different execution policy on the same computer.
$runtimeCandidates = @()
if ($PSEdition -eq 'Core') { $runtimeCandidates += (Join-Path $PSHOME 'pwsh.exe') }
$availableRuntime = Get-Command pwsh.exe -ErrorAction SilentlyContinue
if ($availableRuntime) { $runtimeCandidates += $availableRuntime.Source }
$powerShellExe = $null
$runtimeFailures = @()
foreach ($candidate in ($runtimeCandidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    $probeCommand = '[pscustomobject]@{edition=$PSEdition;major=$PSVersionTable.PSVersion.Major;policy=[string](Get-ExecutionPolicy)} | ConvertTo-Json -Compress'
    try {
        $probeOutput = & $candidate -NoProfile -NonInteractive -Command $probeCommand 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'runtime probe failed' }
        $runtime = $probeOutput | ConvertFrom-Json
        if ($runtime.edition -ne 'Core' -or $runtime.major -lt 7) { throw 'PowerShell 7 or newer is required' }
        if ($runtime.policy -notin @('RemoteSigned', 'Unrestricted', 'Bypass')) { throw ('execution policy is ' + $runtime.policy) }
        $powerShellExe = $candidate
        break
    } catch { $runtimeFailures += ($candidate + ': ' + $_.Exception.Message) }
}
if (-not $powerShellExe) {
    throw ('No usable PowerShell 7 runtime was found. Run installation with the PowerShell 7 runtime used for the successful QQ login test. No execution policy was changed. ' + ($runtimeFailures -join '; '))
}
$action = New-ScheduledTaskAction -Execute $powerShellExe -Argument ('-NoProfile -WindowStyle Hidden -File "{0}"' -f $scriptPath) -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$trigger.Delay = 'PT1M'
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Read yesterday QQ history and publish a research daily after Windows sign-in.' -Force | Out-Null
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
