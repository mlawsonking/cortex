# register-taste-tasks.ps1 - registers the two taste-loop tasks (wg\GAMEPLAN-TASTE-LOOP-2026-11.md T7). Pure ASCII
# (PS5.1 rule). Same pattern as register-streaming-tasks.ps1: bobdo, NOT elevated, Register-ScheduledTask cmdlets
# (never schtasks /tr), pythonw, Interactive logon (the Plex token lives in HKCU), 1h limit, IgnoreNew.
#
#   "Taste Ledger" - every 2 h from 00:10: ingest Plex ratings made with the remote + compile ratings-effective
#                    (taste_ledger.py). The rate verbs also compile on every click; this catches TV-remote ratings.
#   "Rate Queue"   - DAILY 05:40: taste_daily.py = ledger -> eval -> full rate-queue rescore -> Plex home rows.
#
# Idempotent: re-running replaces both tasks (-Force).
$ErrorActionPreference = 'Stop'
$PYW  = 'C:\Users\bobdo\AppData\Local\Programs\Python\Python310\pythonw.exe'
$PROD = 'C:\Users\bobdo\wg\brain\producers'

$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -StartWhenAvailable `
  -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId 'bobdo' -LogonType Interactive -RunLevel Limited

$every2h = New-ScheduledTaskTrigger -Once -At '00:10' -RepetitionInterval (New-TimeSpan -Hours 2) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

$defs = @(
  @{ Name = 'Taste Ledger'; Script = 'taste_ledger.py'; Trigger = $every2h;
     Desc = 'Taste loop: ingest Plex ratings + compile ratings-effective.json / taste-signals.json / taste-ledger contract. Every 2 h. No network beyond local Plex.' },
  @{ Name = 'Rate Queue'; Script = 'taste_daily.py';
     Trigger = (New-ScheduledTaskTrigger -Daily -At '05:40');
     Desc = 'Taste loop daily chain: ledger -> taste_eval -> rate_queue full rescore -> plex_rows (home-screen collections). Worst step exit code.' }
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
