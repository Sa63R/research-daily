$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'ResearchDailyOnLogon' -ErrorAction SilentlyContinue
if ($task) { $task | Unregister-ScheduledTask -Confirm:$false }
