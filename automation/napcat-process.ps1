# Dot-source these helpers. Loading this file does not launch or stop a process.
function Test-NapCatEndpoint {
    param([string]$HostName = '127.0.0.1', [int]$Port = 3001)
    $probe = New-Object Net.Sockets.TcpClient
    try { $pending = $probe.ConnectAsync($HostName, $Port); return ($pending.Wait(750) -and $probe.Connected) }
    catch { return $false }
    finally { $probe.Dispose() }
}

function Get-NapCatProcessSnapshot {
    $snapshot = @{}
    foreach ($entry in (Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if (-not $entry.CreationDate) { continue }
        $snapshot[[int]$entry.ProcessId] = [pscustomobject]@{
            Id = [int]$entry.ProcessId; ParentId = [int]$entry.ParentProcessId
            Created = $entry.CreationDate.ToUniversalTime(); Path = [string]$entry.ExecutablePath
        }
    }
    return $snapshot
}

function Test-NapCatCreationTime {
    param([DateTime]$First, [DateTime]$Second)
    # CIM truncates the sub-microsecond precision exposed by Process.StartTime.
    return ([Math]::Abs(($First - $Second).TotalMilliseconds) -lt 1)
}

function Update-NapCatOwnedProcesses {
    param([Parameter(Mandatory)]$Session)
    $snapshot = Get-NapCatProcessSnapshot
    $observedAt = [DateTime]::UtcNow
    do {
        $added = $false
        foreach ($entry in $snapshot.Values) {
            if ($Session.Owned.ContainsKey($entry.Id) -or -not $Session.Owned.ContainsKey($entry.ParentId)) { continue }
            $parent = $Session.Owned[$entry.ParentId]
            if ($entry.Created -lt $parent.Created -or $entry.Created -lt $Session.StartedAt) { continue }
            # A recycled parent PID must never cause a user's process to become ours.
            if ($snapshot.ContainsKey($parent.Id)) {
                if (-not (Test-NapCatCreationTime $snapshot[$parent.Id].Created $parent.Created)) { continue }
            } elseif ($entry.Created -gt $parent.LastObservedAt) { continue }
            $Session.Owned[$entry.Id] = [pscustomobject]@{
                Id = $entry.Id; Created = $entry.Created; Path = $entry.Path
                Depth = $parent.Depth + 1; LastObservedAt = $observedAt
            }
            $added = $true
        }
    } while ($added)
    foreach ($owned in $Session.Owned.Values) {
        if ($snapshot.ContainsKey($owned.Id) -and (Test-NapCatCreationTime $snapshot[$owned.Id].Created $owned.Created)) { $owned.LastObservedAt = $observedAt }
    }
}

function Test-NapCatOwnedProcessAlive {
    param([Parameter(Mandatory)]$Session)
    foreach ($owned in $Session.Owned.Values) {
        $current = Get-Process -Id $owned.Id -ErrorAction SilentlyContinue
        if ($current -and (Test-NapCatCreationTime $current.StartTime.ToUniversalTime() $owned.Created)) { return $true }
    }
    return $false
}

function Start-NapCatReader {
    param([Parameter(Mandatory)]$Config, [Parameter(Mandatory)][string]$LogDirectory)
    $shellDir = $Config.napcatShellDir
    if (-not $shellDir) {
        $shellDir = $Config.napcatDir
        if (-not (Test-Path -LiteralPath (Join-Path $shellDir 'napcat.mjs'))) { $shellDir = Join-Path $shellDir 'napcat' }
    }
    $shellDir = [IO.Path]::GetFullPath($shellDir)
    $qqExecutable = $Config.qqExecutable
    if (-not $qqExecutable) {
        $qqExecutable = Join-Path $env:ProgramFiles 'Tencent\QQNT\QQ.exe'
        if (-not (Test-Path -LiteralPath $qqExecutable)) {
            $uninstall = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ' -ErrorAction SilentlyContinue
            if ($uninstall -and $uninstall.UninstallString) {
                $uninstallerPath = $uninstall.UninstallString.Trim('"')
                $qqExecutable = Join-Path (Split-Path -Parent $uninstallerPath) 'QQ.exe'
            }
        }
    }
    $bootExe = Join-Path $shellDir 'NapCatWinBootMain.exe'
    $hookDll = Join-Path $shellDir 'NapCatWinBootHook.dll'
    $loadFile = Join-Path $shellDir 'loadNapCat.js'
    $mainFile = Join-Path $shellDir 'napcat.mjs'
    $packageFile = Join-Path $shellDir 'qqnt.json'
    foreach ($required in @($qqExecutable, $bootExe, $hookDll, $mainFile, $packageFile)) {
        if (-not $required -or -not (Test-Path -LiteralPath $required -PathType Leaf)) { throw ('Required QQ/NapCat file is missing: ' + $required) }
    }
    if (Get-Process -Name QQ -ErrorAction SilentlyContinue) { throw 'Desktop QQ is running; leave it untouched and try after a normal exit.' }
    if ($Config.qqAccount -and $Config.qqAccount -notmatch '^\d+$') { throw 'Configured QQ account is invalid.' }
    New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    $mainUri = (New-Object Uri($mainFile)).AbsoluteUri
    $loader = '(async () => {await import(' + (ConvertTo-Json -InputObject $mainUri -Compress) + ')})()'
    [IO.File]::WriteAllText($loadFile, $loader, (New-Object Text.UTF8Encoding($false)))
    $variables = @{ NAPCAT_PATCH_PACKAGE = $packageFile; NAPCAT_LOAD_PATH = $loadFile; NAPCAT_INJECT_PATH = $hookDll }
    $savedEnvironment = @{}
    $session = $null
    try {
        foreach ($name in $variables.Keys) {
            $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, $variables[$name], 'Process')
        }
        $bootArguments = @(('"{0}"' -f $qqExecutable), ('"{0}"' -f $hookDll))
        # WinBootMain takes the account as its third argument and adds -q itself.
        # Passing '-q account' here makes the loader forward an invalid '-q -q'.
        if ($Config.qqAccount) { $bootArguments += $Config.qqAccount }
        $startedAt = [DateTime]::UtcNow
        $boot = Start-Process -FilePath $bootExe -ArgumentList $bootArguments -WorkingDirectory $shellDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogDirectory 'napcat.stdout.log') -RedirectStandardError (Join-Path $LogDirectory 'napcat.stderr.log')
        $created = $boot.StartTime.ToUniversalTime()
        $session = [pscustomobject]@{ StartedAt = $startedAt; Owned = @{} }
        $session.Owned[$boot.Id] = [pscustomobject]@{ Id = $boot.Id; Created = $created; Path = $bootExe; Depth = 0; LastObservedAt = [DateTime]::UtcNow }
        Update-NapCatOwnedProcesses -Session $session
        return $session
    } catch {
        if ($session) { Stop-NapCatReader -Session $session }
        throw
    } finally {
        foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
    }
}

function Stop-NapCatReader {
    param([Parameter(Mandatory)]$Session)
    try { Update-NapCatOwnedProcesses -Session $Session } catch { Write-Warning 'Could not refresh the reader process tree; checking only previously recorded processes.' }
    foreach ($owned in ($Session.Owned.Values | Sort-Object Depth -Descending)) {
        $current = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $owned.Id) -ErrorAction SilentlyContinue
        if (-not $current -or -not (Test-NapCatCreationTime $current.CreationDate.ToUniversalTime() $owned.Created)) { continue }
        if ($owned.Path -and $current.ExecutablePath -and $current.ExecutablePath -ne $owned.Path) { continue }
        # Creation time is verified again on the live handle immediately before stopping it.
        $process = Get-Process -Id $owned.Id -ErrorAction SilentlyContinue
        if ($process -and (Test-NapCatCreationTime $process.StartTime.ToUniversalTime() $owned.Created)) { $process | Stop-Process -ErrorAction SilentlyContinue }
    }
}
