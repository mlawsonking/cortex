# register-streaming-tasks.ps1 - registers the two producer tasks for the Cortex Streaming Best / Missed Gems pages
# (wg\GAMEPLAN-STREAMING-PAGES-2026-10.md). Pure ASCII (PS5.1 rule). Runs as bobdo, NOT elevated, via the
# Register-ScheduledTask cmdlets (user principal - the cmdlet persists fine for a user task; the SYSTEM-principal
# persistence bug in engineering-minefields does not apply) - never schtasks /tr (quoting minefield).
# Settings mirror the sibling producer tasks (Monthly Wrapped / Taste Velocity): pythonw (no console flash, exit
# code still reaches the task-health watchdog), Interactive logon (Plex token lives in HKCU), 1h limit, IgnoreNew.
#
#   "Streaming Best" - DAILY 07:20. The monthly cadence lives in streaming_best.py's self-gate (Wrapped pattern:
#                      Windows has no clean monthly trigger cmdlet); most days it prints why it skipped and exits 0.
#   "Missed Gems"    - WEEKLY Saturday 06:50.
#
# Idempotent: re-running replaces both tasks (-Force).
$ErrorActionPreference = 'Stop'
$PYW  = 'C:\Users\bobdo\AppData\Local\Programs\Python\Python310\pythonw.exe'
$PROD = 'C:\Users\bobdo\wg\brain\producers'

$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -StartWhenAvailable `
  -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId 'bobdo' -LogonType Interactive -RunLevel Limited

$defs = @(
  @{ Name = 'Streaming Best'; Script = 'streaming_best.py';
     Trigger = (New-ScheduledTaskTrigger -Daily -At '07:20');
     Desc = 'Cortex page 1 producer (streaming-best contract). Daily trigger, monthly self-gate inside the script. claude -p subscription only.' },
  @{ Name = 'Missed Gems'; Script = 'missed_gems.py';
     Trigger = (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At '06:50');
     Desc = 'Cortex page 2 producer (missed-gems contract). Weekly, deterministic, no model call.' }
)

foreach ($d in $defs) {
  $action = New-ScheduledTaskAction -Execute $PYW -Argument ('"' + (Join-Path $PROD $d.Script) + '"') -WorkingDirectory $PROD
  Register-ScheduledTask -TaskName $d.Name -Action $action -Trigger $d.Trigger -Settings $settings `
    -Principal $principal -Description $d.Desc -Force | Out-Null
  $chk = Get-ScheduledTask -TaskName $d.Name -ErrorAction Stop
  $info = Get-ScheduledTaskInfo -TaskName $d.Name
  Write-Host ("registered: {0} | state {1} | next run {2} | {3} {4}" -f $d.Name, $chk.State, $info.NextRunTime,
    $chk.Actions[0].Execute, $chk.Actions[0].Arguments)
}
