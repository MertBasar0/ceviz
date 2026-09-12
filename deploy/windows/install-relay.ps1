param([ValidateRange(1,65535)][int]$Port=8080,[Parameter(Mandatory=$true)][string]$Distro, [switch]$Elevated, [string]$ResultPath='')
$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Distro) -or $Distro -cne $Distro.Trim() -or $Distro -match '["\\\x00-\x1f]') { throw "Invalid WSL distribution name" }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $result = Join-Path $env:TEMP ("ceviz-relay-" + [guid]::NewGuid().ToString('N') + '.txt')
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',("`"$PSCommandPath`""),'-Port',"$Port",'-Distro',("`"$Distro`""),'-Elevated','-ResultPath',("`"$result`""))
    $admin = Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($admin.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $result)) { throw "Relay administrator approval failed" }
    Get-Content -LiteralPath $result
    Remove-Item -LiteralPath $result -Force
    exit 0
}
$lan = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | ForEach-Object {
    Get-NetIPAddress -InterfaceIndex $_.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
} | Where-Object { $_.IPAddress -notmatch '^(127|169\.254|172\.(1[6-9]|2[0-9]|3[01])|100\.)\.' } | Select-Object -First 1
if (-not $lan) { throw "No LAN IPv4 address found" }
$dir = Join-Path $env:LOCALAPPDATA 'Ceviz'
if (Test-Path -LiteralPath $dir) {
    $item = Get-Item -LiteralPath $dir -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Relay directory requires manual inspection' }
}
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$relay = Join-Path $dir 'ceviz-backend-relay.ps1'
$source = Join-Path $PSScriptRoot 'ceviz-backend-relay.ps1'
$taskName = 'Ceviz Backend Relay'
$principalId = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$taskArguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$relay`" -ListenAddress auto -ListenPort $Port -BackendPort $Port -Distro `"$Distro`""
$existing = @(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop | Where-Object TaskName -eq $taskName)
$previous = $null
if ($existing.Count) {
    if ($existing.Count -ne 1 -or @($existing[0].Actions).Count -ne 1 -or
        $existing[0].Actions[0].Execute -ne 'powershell.exe' -or $existing[0].Actions[0].Arguments -cne $taskArguments -or
        $existing[0].Description -ne 'Watch Ceviz WSL2 LAN relay') { throw 'Existing relay task identity changed; no overwrite' }
    $owner = $existing[0].Principal.UserId
    if (-not $owner.StartsWith('S-1-', [StringComparison]::Ordinal)) { $owner = [Security.Principal.NTAccount]::new($owner).Translate([Security.Principal.SecurityIdentifier]).Value }
    if ($owner -ne $principalId -or $existing[0].State -eq 'Running' -or -not $existing[0].Settings.Enabled) {
        throw 'Relay owner or maintenance state requires explicit review; no overwrite or stop'
    }
    if (-not (Test-Path -LiteralPath $relay -PathType Leaf) -or
        ((Get-Item -LiteralPath $relay -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Existing relay source requires manual inspection' }
    $previous = Export-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop
    $backup = Join-Path $dir ('relay-task-backup-' + [guid]::NewGuid().ToString('N') + '.xml')
    [IO.File]::WriteAllText($backup, $previous)
} elseif (Test-Path -LiteralPath $relay) { throw 'Unowned relay source exists; no overwrite' }
# Stage and verify on the same volume, then replace atomically with a retained
# old-source backup. A partial copy must never corrupt the live task action.
$temporary = Join-Path $dir ('relay-copy-' + [guid]::NewGuid().ToString('N') + '.tmp')
try {
    Copy-Item -LiteralPath $source -Destination $temporary -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash) { throw 'Relay source copy did not verify' }
    if ($previous) {
        if ((Export-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop) -cne $previous) { throw 'Relay task changed during preparation; no overwrite' }
        $codeBackup = Join-Path $dir ('relay-source-backup-' + [guid]::NewGuid().ToString('N') + '.ps1')
        [IO.File]::Replace($temporary, $relay, $codeBackup)
    } else { [IO.File]::Move($temporary, $relay) }
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
}
$ruleName = 'Watch Ceviz Backend Relay'
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $lan.IPAddress -LocalPort $Port -Profile Private | Out-Null
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $principalId
$principal = New-ScheduledTaskPrincipal -UserId $principalId -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$registration = @{ TaskName=$taskName; TaskPath='\'; Action=$action; Trigger=$trigger; Principal=$principal
    Settings=$settings; Description='Watch Ceviz WSL2 LAN relay'; ErrorAction='Stop' }
if ($previous) { $registration.Force=$true }
Register-ScheduledTask @registration | Out-Null
$registered = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop
if (@($registered.Actions).Count -ne 1 -or $registered.Actions[0].Execute -ne 'powershell.exe' -or
    $registered.Actions[0].Arguments -cne $taskArguments) { throw 'Registered LAN relay action did not verify' }
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
if ((Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop).State -ne 'Running') { throw 'LAN relay task did not start' }
$message = "CEVIZ_RELAY_URL=http://$($lan.IPAddress):$Port"
if ($ResultPath) { Set-Content -LiteralPath $ResultPath -Value $message -Encoding ascii } else { Write-Output $message }
