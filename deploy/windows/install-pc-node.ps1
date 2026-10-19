# Connects this Windows PC to the OpenClaw Gateway in WSL as a node, so commands from the
# Watch can act on Windows (exec host=node runs them in PowerShell here).
#
# Run by deploy/pc-node.sh, which reads a single-use setup code from the Gateway and passes it
# on standard input; it never appears on a command line and is not stored.
#
# Everything is Ceviz's own and kept apart from any OpenClaw you use on Windows yourself:
# OpenClaw $Version (the Gateway's version) in $Prefix and the node's identity in $StateDir. A
# shared state folder is what broke an earlier node on this kind of setup: another OpenClaw
# build migrated it to a schema the node's version could not open.
#
# Exit codes: 0 connected and installed, 3 Node.js missing or too old, 4 another OpenClaw node
# service exists (rerun with -Replace to replace it), 5 OpenClaw download failed, 6 pairing failed,
# 7 replacing a node service registered by an administrator was not approved.
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$DisplayName = 'Ceviz PC',
    [switch]$Replace,
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA 'Ceviz\pc-node'),
    [string]$StateDir = (Join-Path $env:USERPROFILE '.openclaw-ceviz-pc'),
    [string]$Node = '',
    [string]$Npm = '',
    [string]$Winget = 'winget.exe',
    [string]$PowerShell = 'powershell.exe'
)
$ErrorActionPreference = 'Stop'
$TaskName = 'OpenClaw Node'  # fixed by OpenClaw: one node service per Windows user
# Started from WSL the current folder is a \\wsl.localhost path, which npm.cmd cannot use.
Set-Location -LiteralPath $env:USERPROFILE

if ($Version -notmatch '^\d{4}\.\d+\.\d+([-+.][0-9A-Za-z.-]+)?$') { throw "Unexpected OpenClaw version: $Version" }
if ($DisplayName -notmatch '^[\w .()-]{1,40}$') { throw "Unexpected node name: $DisplayName" }
$code = [Console]::In.ReadToEnd().Trim()
if (-not $code) { throw 'No setup code arrived on standard input.' }

function Test-NodeVersion([string]$Have, [string]$Range) {
    # npm-style ranges as OpenClaw writes them: ">=24.16.0 <25 || >=26.1.0".
    $have = [version]($Have.TrimStart('v') -replace '[-+].*$', '')
    foreach ($alternative in ($Range -split '\|\|')) {
        $ok = $true
        foreach ($comparator in ($alternative.Trim() -split '\s+' | Where-Object { $_ })) {
            if ($comparator -notmatch '^(>=|<=|>|<|=)?v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$') { $ok = $false; break }
            $bound = [version]('{0}.{1}.{2}' -f $Matches[2], [int]$Matches[3], [int]$Matches[4])
            switch ($Matches[1]) {
                '>=' { $ok = $ok -and $have -ge $bound }
                '>' { $ok = $ok -and $have -gt $bound }
                '<=' { $ok = $ok -and $have -le $bound }
                '<' { $ok = $ok -and $have -lt $bound }
                default { $ok = $ok -and $have -eq $bound }
            }
        }
        if ($ok) { return $true }
    }
    return $false
}

function Remove-NodeTask {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        return
    } catch {
        # A task registered from an elevated terminal can be removed only by an administrator.
        Write-Output "Eski '$TaskName' gorevi yonetici izniyle kurulmus; Windows bir onay (UAC) isteyecek."
    }
    $remove = "Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
    try {
        $admin = Start-Process $PowerShell -Verb RunAs -WindowStyle Hidden -Wait -PassThru `
            -ArgumentList @('-NoProfile', '-NonInteractive', '-Command', $remove)
    } catch {
        $admin = $null  # the approval was declined
    }
    if (-not $admin -or $admin.ExitCode -ne 0 -or (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
        Write-Output "CEVIZ_PC_NODE_ERROR=Replacing the existing '$TaskName' task needs administrator approval; it was not changed."
        exit 7
    }
}

function Find-Node {
    $found = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $installed = Join-Path $env:ProgramFiles 'nodejs\node.exe'
    if (Test-Path -LiteralPath $installed) { return $installed }
    return ''
}

# 1) An existing node service that Ceviz did not create is replaced only on request.
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    $launcher = @($task.Actions | ForEach-Object { $_.Execute })[0]
    $ours = $launcher -and ([IO.Path]::GetDirectoryName([string]$launcher)).TrimEnd('\') -ieq $StateDir.TrimEnd('\')
    if (-not $ours -and -not $Replace) {
        Write-Output "CEVIZ_PC_NODE_FOREIGN=$launcher"
        exit 4
    }
}

# 2) Node.js for OpenClaw; the LTS release is installed with winget when there is none.
if (-not $Node) { $Node = Find-Node }
if (-not $Node -and (Get-Command $Winget -ErrorAction SilentlyContinue)) {
    Write-Output 'Node.js bulunamadi; winget ile Node.js LTS kuruluyor (Windows onay isteyebilir).'
    & $Winget install --id OpenJS.NodeJS.LTS --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Null
    $Node = Find-Node
}
if (-not $Node) {
    Write-Output 'CEVIZ_PC_NODE_ERROR=Node.js is not installed on Windows (https://nodejs.org, LTS).'
    exit 3
}
if (-not $Npm) { $Npm = Join-Path (Split-Path -Parent $Node) 'npm.cmd' }

# 3) OpenClaw at the Gateway's version, in Ceviz's own folder.
$package = Join-Path $Prefix 'node_modules\openclaw\package.json'
$current = if (Test-Path -LiteralPath $package) { (Get-Content -LiteralPath $package -Raw | ConvertFrom-Json).version } else { '' }
if ($current -ne $Version) {
    Write-Output "OpenClaw $Version Windows'a indiriliyor ($Prefix)"
    New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
    & $Npm install --prefix $Prefix --no-fund --no-audit --omit=dev --loglevel=error "openclaw@$Version" | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $package)) {
        Write-Output "CEVIZ_PC_NODE_ERROR=npm could not install openclaw@$Version."
        exit 5
    }
}
$manifest = Get-Content -LiteralPath $package -Raw | ConvertFrom-Json
$nodeVersion = [string](& $Node --version)
if ($manifest.engines.node -and -not (Test-NodeVersion $nodeVersion $manifest.engines.node)) {
    Write-Output "CEVIZ_PC_NODE_ERROR=OpenClaw $Version needs Node.js $($manifest.engines.node); Windows has $nodeVersion."
    exit 3
}
$bin = if ($manifest.bin -is [string]) { $manifest.bin } else { $manifest.bin.openclaw }
$entry = Join-Path (Split-Path -Parent $package) $bin

# 4) Pair with the single-use code and install the node service under Ceviz's state folder.
if ($task) { Remove-NodeTask }
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$env:OPENCLAW_STATE_DIR = $StateDir
# A private file that `openclaw connect --target-file` reads and removes.
$codeFile = Join-Path $StateDir ('pair-' + [guid]::NewGuid().ToString('N') + '.txt')
Set-Content -LiteralPath $codeFile -Value $code -NoNewline -Encoding ascii
try {
    & $Node $entry connect --target-file $codeFile --service --display-name $DisplayName | Out-Null
    $paired = $LASTEXITCODE -eq 0
} finally {
    Remove-Item -LiteralPath $codeFile -Force -ErrorAction SilentlyContinue
}
if (-not $paired) {
    Write-Output 'CEVIZ_PC_NODE_ERROR=openclaw connect could not pair this PC with the Gateway.'
    exit 6
}
$identity = (& $Node $entry node identity --json) -join "`n" | ConvertFrom-Json
$deviceId = if ($identity.deviceId) { $identity.deviceId } else { $identity.id }
if ([string]$deviceId -notmatch '^[0-9a-f]{64}$') {
    Write-Output 'CEVIZ_PC_NODE_ERROR=The paired node did not report its device id.'
    exit 6
}
Write-Output "CEVIZ_PC_NODE_ID=$deviceId"
exit 0
