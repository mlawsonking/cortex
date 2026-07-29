# leak-grep.ps1 - the secret-leak gate for the Cortex brain app (same pattern as the config time machine).
# Harvests every real secret VALUE on this box, then greps a target tree for those values. Exact-value hits are a
# HARD FAIL (exit 1); high-signal generic patterns are WARNINGS (exit 0) so a hex-looking bundle hash cannot cry
# wolf. Run before ANY release goes live, and from verify-brain.ps1 on a schedule (P6).
#
# PS5.1 rules observed: pure ASCII source, no inline-if inside strings, ${var} in interpolation, no wildcards fed
# to cmdlets from harvested data. Empty/short harvested values are DISCARDED - a zero-length needle matches every
# file (the "x".Contains('') class of bug) and would produce a fake catastrophe.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File leak-grep.ps1 [-Path <dir>] [-Quiet]
param(
  [string]$Path = "C:\Users\bobdo\wg\brain",
  [switch]$Quiet
)
$ErrorActionPreference = 'Continue'
$WG = "C:\Users\bobdo\wg"
$MIN = 8          # never search for anything shorter than this
$fail = 0
$warn = 0

function Add-Secret {
  param([hashtable]$Bag, [string]$Label, [string]$Value)
  if ($null -eq $Value) { return }
  $v = $Value.Trim()
  if ($v.Length -lt $MIN) { return }
  if (-not $Bag.ContainsKey($v)) { $Bag[$v] = $Label }
}

$secrets = @{}

# 1. wg\*.key, *.pass, *.url, act/cmd secrets, ntfy topic
$files = @()
$files += Get-ChildItem -Path $WG -Filter *.key -File -ErrorAction SilentlyContinue
$files += Get-ChildItem -Path $WG -Filter *.pass -File -ErrorAction SilentlyContinue
$files += Get-ChildItem -Path $WG -Filter *.url -File -ErrorAction SilentlyContinue
$files += Get-ChildItem -Path $WG -Filter act-secret.txt -File -ErrorAction SilentlyContinue
$files += Get-ChildItem -Path (Join-Path $WG 'audit') -Filter cmd-secret.txt -File -ErrorAction SilentlyContinue
$files += Get-ChildItem -Path (Join-Path $WG 'audit') -Filter ntfy-topic.txt -File -ErrorAction SilentlyContinue
foreach ($f in $files) {
  try { Add-Secret $secrets $f.Name ((Get-Content $f.FullName -Raw -ErrorAction Stop)) } catch {}
}

# 2. Plex token (registry, never on disk in plaintext)
try {
  $pt = (Get-ItemProperty 'HKCU:\Software\Plex, Inc.\Plex Media Server' -Name PlexOnlineToken -ErrorAction Stop).PlexOnlineToken
  Add-Secret $secrets 'PlexOnlineToken' $pt
} catch {}

# 3. Trakt OAuth (PlexTraktSync)
try {
  $ptj = Join-Path $env:LOCALAPPDATA 'PlexTraktSync\PlexTraktSync\.pytrakt.json'
  if (Test-Path $ptj) {
    $j = Get-Content $ptj -Raw | ConvertFrom-Json
    Add-Secret $secrets 'trakt CLIENT_ID' $j.CLIENT_ID
    Add-Secret $secrets 'trakt CLIENT_SECRET' $j.CLIENT_SECRET
    Add-Secret $secrets 'trakt OAUTH_TOKEN' $j.OAUTH_TOKEN
    Add-Secret $secrets 'trakt REFRESH_TOKEN' $j.OAUTH_REFRESH
  }
} catch {}

# 4. qBit WebUI password (already covered by *.pass, kept explicit for clarity)
try { Add-Secret $secrets 'qbit-webui.pass' ((Get-Content (Join-Path $WG 'qbit-webui.pass') -Raw -ErrorAction Stop)) } catch {}

if (-not $Quiet) { Write-Host ("harvested {0} distinct secret values" -f $secrets.Count) }
if ($secrets.Count -eq 0) {
  Write-Host "LEAK-GREP ABORT: harvested zero secrets - the gate cannot honestly pass. Check the harvest paths."
  exit 1
}

# Generic high-signal patterns: warnings only.
$patterns = @(
  @{ n = 'discord webhook URL'; re = 'https://discord(app)?\.com/api/webhooks/' },
  @{ n = 'plex token in a URL'; re = 'X-Plex-Token=[A-Za-z0-9_\-]{8,}' },
  @{ n = 'bearer token';        re = 'Bearer\s+[A-Za-z0-9\._\-]{20,}' },
  @{ n = 'ntfy topic URL';      re = 'ntfy\.sh/[A-Za-z0-9\-]{10,}' }
)

$skipExt = @('.png', '.jpg', '.jpeg', '.ico', '.gif', '.woff', '.woff2', '.ttf', '.db', '.zip', '.pyc', '.map')
$targets = @(Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\(node_modules|\.git)\\' -and
                 $skipExt -notcontains $_.Extension.ToLower() -and
                 $_.Length -lt 8MB })

if (-not $Quiet) { Write-Host ("scanning {0} files under {1}" -f $targets.Count, $Path) }

foreach ($t in $targets) {
  $text = $null
  try { $text = Get-Content $t.FullName -Raw -ErrorAction Stop } catch { continue }
  if ([string]::IsNullOrEmpty($text)) { continue }
  foreach ($k in $secrets.Keys) {
    if ($text.Contains($k)) {
      $lbl = $secrets[$k]
      Write-Host ("LEAK: {0} contains the value of {1}" -f $t.FullName, $lbl)
      $fail++
    }
  }
  foreach ($p in $patterns) {
    if ($text -match $p.re) {
      Write-Host ("WARN: {0} matches pattern '{1}'" -f $t.FullName, $p.n)
      $warn++
    }
  }
}

if ($fail -gt 0) {
  Write-Host ("LEAK-GREP FAIL: {0} exact secret hit(s), {1} warning(s). Do NOT release." -f $fail, $warn)
  exit 1
}
Write-Host ("LEAK-GREP PASS: 0 exact secret hits, {0} warning(s), {1} files scanned, {2} secrets checked." -f $warn, $targets.Count, $secrets.Count)
exit 0
