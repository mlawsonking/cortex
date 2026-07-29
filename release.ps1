# release.ps1 - build the Cortex bundle, hash it, gate it, and flip the junction. Pure ASCII (PS5.1 rule).
#
# ORDER MATTERS AND IS THE POINT:
#   build -> hash -> LEAK-GREP the built output -> only then flip /v2 to it.
# A release that fails the leak gate never becomes reachable (guardrail 6). Releases are immutable directories;
# rollback is a junction flip, which is why nothing is ever built in place.
#
# npm caging (guardrail: npm is the new attack surface): `npm ci --ignore-scripts` ONLY - no lifecycle scripts,
# exact versions from the committed lockfile. A missing lockfile is a hard stop, not an excuse to run `npm install`.
#
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File release.ps1 [-SkipInstall] [-Prune]
param(
  [switch]$SkipInstall,
  [switch]$Prune
)
$ErrorActionPreference = 'Stop'
$BRAIN    = "C:\Users\bobdo\wg\brain"
$APP      = Join-Path $BRAIN 'app'
$RELEASES = Join-Path $BRAIN 'releases'
$TMP      = Join-Path $RELEASES '.build-tmp'
$LINK     = "C:\Users\bobdo\wg\dashboard\v2"

function Die($msg) { Write-Host "RELEASE ABORT: $msg"; exit 1 }

if (-not (Test-Path (Join-Path $APP 'package-lock.json'))) {
  Die "no package-lock.json. Bootstrap ONCE with: npm install --ignore-scripts (in $APP), then commit the lockfile."
}

Push-Location $APP
try {
  if (-not $SkipInstall) {
    Write-Host "== npm ci --ignore-scripts =="
    & npm ci --ignore-scripts
    if ($LASTEXITCODE -ne 0) { Die "npm ci failed ($LASTEXITCODE)" }
  }
  Write-Host "== vite build =="
  & npm run build
  if ($LASTEXITCODE -ne 0) { Die "vite build failed ($LASTEXITCODE)" }
} finally {
  Pop-Location
}

if (-not (Test-Path (Join-Path $TMP 'index.html'))) { Die "build produced no index.html at $TMP" }

# ---- content hash over every emitted byte (relative path + sha256, sorted) ----
$files = @(Get-ChildItem -Path $TMP -Recurse -File | Sort-Object FullName)
$lines = @()
$manifest = @{}
foreach ($f in $files) {
  $rel = $f.FullName.Substring($TMP.Length).TrimStart('\')
  $h = (Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower()
  $lines += ("{0}:{1}" -f ($rel -replace '\\', '/'), $h)
  $manifest[($rel -replace '\\', '/')] = $h
}
$joined = ($lines -join "`n")
$sha = [System.BitConverter]::ToString(
  [System.Security.Cryptography.SHA256]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes($joined))
).Replace('-', '').ToLower()
$short = $sha.Substring(0, 12)
$dest = Join-Path $RELEASES $short

if (Test-Path $dest) {
  Write-Host "release $short already exists (identical build) - reusing it"
  Remove-Item $TMP -Recurse -Force
} else {
  Move-Item $TMP $dest
}

# release.json: what P6's verify-brain diffs the served bundle against.
$rel = [ordered]@{
  hash     = $sha
  short    = $short
  built_at = (Get-Date).ToString('o')
  node     = (& node --version)
  npm      = (& npm --version)
  files    = $manifest
}
($rel | ConvertTo-Json -Depth 5) | Set-Content (Join-Path $dest 'release.json') -Encoding ASCII

# ---- LEAK GATE: must pass before this release can become reachable ----
Write-Host "== leak-grep (release dir) =="
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $BRAIN 'leak-grep.ps1') -Path $dest
if ($LASTEXITCODE -ne 0) { Die "leak-grep FAILED on release $short - junction NOT flipped, release not reachable" }

# ---- flip the junction (cmd rmdir/mklink: PS5.1's Remove-Item on a junction can recurse into the TARGET) ----
if (Test-Path $LINK) {
  $item = Get-Item $LINK -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    & cmd /c rmdir "`"$LINK`"" | Out-Null
  } else {
    Die "$LINK exists and is NOT a junction - refusing to touch it"
  }
}
& cmd /c mklink /J "`"$LINK`"" "`"$dest`"" | Out-Null
if ($LASTEXITCODE -ne 0) { Die "mklink failed ($LASTEXITCODE)" }
$short | Set-Content (Join-Path $RELEASES 'ACTIVE.txt') -Encoding ASCII

if ($Prune) {
  $keep = 5
  $old = @(Get-ChildItem $RELEASES -Directory | Where-Object { $_.Name -ne $short } | Sort-Object LastWriteTime -Descending | Select-Object -Skip ($keep - 1))
  foreach ($o in $old) { Write-Host ("pruning old release {0}" -f $o.Name); Remove-Item $o.FullName -Recurse -Force }
}

Write-Host ""
Write-Host ("RELEASE OK  hash={0}  files={1}" -f $short, $files.Count)
Write-Host ("  /v2 -> {0}" -f $dest)
Write-Host ("  rollback: cmd /c rmdir `"{0}`"  &&  cmd /c mklink /J `"{0}`" `"{1}\<previous-hash>`"" -f $LINK, $RELEASES)
exit 0
