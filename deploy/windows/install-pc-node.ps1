# Connects this Windows PC to the OpenClaw Gateway in WSL as a node, so commands from the
# Watch can act on Windows (exec host=node runs them in PowerShell here).
#
# Run by deploy/pc-node.sh, which reads a single-use setup code from the Gateway and passes it
# on standard input; it never appears on a command line and is not stored.
#
# Everything is Ceviz's own and kept apart from any OpenClaw you use on Windows yourself:
# OpenClaw $Version (the Gateway's version) in $Prefix, the node's identity in the OpenClaw
# profile $ProfileName (%USERPROFILE%\.openclaw-ceviz-pc), and the scheduled task $TaskName. A
# shared state folder is what broke an earlier node on this kind of setup: another OpenClaw
# build migrated it to a schema the node's version could not open.
#
# OpenClaw only pairs here. Its own node service cannot be used: it is one fixed task per user
# ('OpenClaw Node'), and 2026.9.6 refuses to install it for a named profile (it compares the
# node's task name with the profile's gateway task name).
#
# Exit codes: 0 paired and started, 3 Node.js missing or too old, 5 OpenClaw download failed,
# 6 pairing failed, 8 the scheduled task could not be registered.
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][ValidateRange(1, 65535)][int]$Port,
    [string]$DisplayName = 'Ceviz PC',
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA 'Ceviz\pc-node'),
    [string]$ProfileName = 'ceviz-pc',
    [string]$StateDir = (Join-Path $env:USERPROFILE '.openclaw-ceviz-pc'),  # the profile's folder
    [string]$Node = '',
    [string]$Npm = '',
    [string]$Winget = 'winget.exe',
    [int]$PairSeconds = 60
)
$ErrorActionPreference = 'Stop'
$TaskName = 'Ceviz PC Node'
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

function Find-Node {
    $found = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $installed = Join-Path $env:ProgramFiles 'nodejs\node.exe'
    if (Test-Path -LiteralPath $installed) { return $installed }
    return ''
}

# 1) Node.js for OpenClaw; the LTS release is installed with winget when there is none.
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

# 2) OpenClaw at the Gateway's version, in Ceviz's own folder.
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

# 3) Pair with the single-use code. `openclaw connect` pairs and then runs the node host in the
# foreground; once it reports the Gateway connection it holds its own device token and stops.
foreach ($name in 'OPENCLAW_STATE_DIR', 'OPENCLAW_CONFIG_PATH', 'OPENCLAW_HOME', 'OPENCLAW_PROFILE') {
    Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
}
# A rerun replaces Ceviz's own node host: the task, and the node process it started.
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($entry) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$logs = Join-Path $StateDir 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$codeFile = Join-Path $StateDir ('pair-' + [guid]::NewGuid().ToString('N') + '.txt')  # connect removes it
Set-Content -LiteralPath $codeFile -Value $code -NoNewline -Encoding ascii
$pairLog = Join-Path $logs 'pair.log'
$pairErrors = Join-Path $logs 'pair-errors.log'
$connected = $false
try {
    $pairing = Start-Process -FilePath $Node -NoNewWindow -PassThru -RedirectStandardOutput $pairLog -RedirectStandardError $pairErrors `
        -ArgumentList @("`"$entry`"", '--profile', $ProfileName, 'connect', '--target-file', "`"$codeFile`"", '--display-name', "`"$DisplayName`"")
    $deadline = (Get-Date).AddSeconds($PairSeconds)
    while ((Get-Date) -lt $deadline -and -not $pairing.HasExited) {
        $seen = (Get-Content -LiteralPath $pairLog, $pairErrors -Raw -ErrorAction SilentlyContinue) -join "`n"
        if ($seen -match 'gateway connected') { $connected = $true; break }
        Start-Sleep -Milliseconds 500
    }
} finally {
    if ($pairing -and -not $pairing.HasExited) { Stop-Process -Id $pairing.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $codeFile -Force -ErrorAction SilentlyContinue
}
if (-not $connected) {
    Write-Output "CEVIZ_PC_NODE_ERROR=openclaw connect did not reach the Gateway on port $Port (see $pairLog)."
    exit 6
}

# 4) Ceviz's own task runs the node host at logon, hidden, with the paired identity.
$launcher = Join-Path $StateDir 'ceviz-node.cmd'
$hidden = Join-Path $StateDir 'ceviz-node.vbs'
Set-Content -LiteralPath $launcher -Encoding ascii -Value @(
    '@echo off',
    'rem Ceviz PC node: OpenClaw node host for the Ceviz helper''s Gateway in WSL (deploy/pc-node.sh)',
    ('"{0}" "{1}" --profile {2} node run --host 127.0.0.1 --port {3} --no-tls --display-name "{4}" < NUL > "{5}" 2>&1' -f
        $Node, $entry, $ProfileName, $Port, $DisplayName, (Join-Path $logs 'node.log'))
)
Set-Content -LiteralPath $hidden -Encoding ascii -Value @(
    "' Ceviz PC node, without a console window",
    ('WScript.Quit CreateObject("WScript.Shell").Run("""' + $launcher + '""", 0, True)')  # parentheses: ',' binds before '+'
)
try {
    $action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$hidden`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -Description 'OpenClaw node host for Ceviz (deploy/pc-node.sh)' -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
} catch {
    Write-Output "CEVIZ_PC_NODE_ERROR=The scheduled task '$TaskName' could not be registered: $($_.Exception.Message)"
    exit 8
}

$identity = (& $Node $entry --profile $ProfileName node identity --json) -join "`n" | ConvertFrom-Json
$deviceId = if ($identity.deviceId) { $identity.deviceId } else { $identity.id }
if ([string]$deviceId -notmatch '^[0-9a-f]{64}$') {
    Write-Output 'CEVIZ_PC_NODE_ERROR=The paired node did not report its device id.'
    exit 6
}
Write-Output "CEVIZ_PC_NODE_ID=$deviceId"
exit 0
