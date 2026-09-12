param([Parameter(Mandatory=$true)][ValidatePattern('^[^"\\\x00-\x1f]+$')][string]$Distro)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Distro) -or $Distro -ne $Distro.Trim()) { throw 'Invalid WSL distribution name' }
# Listing is passive: do not enter a stopped distro merely to inspect it.
$distros = @(& wsl.exe --list --quiet) | ForEach-Object { $_.Replace([string][char]0, '').Trim() }
if ($LASTEXITCODE -ne 0 -or $Distro -cnotin $distros) { throw 'Selected WSL distribution is not registered' }

$taskName = 'Ceviz WSL Lifetime'
$description = 'Ceviz WSL lifetime; independent of LAN, Tailscale and firewall'
$principalId = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function Get-TaskPrincipalSid([string]$Value) {
    if ($Value.StartsWith('S-1-', [StringComparison]::Ordinal)) { return [Security.Principal.SecurityIdentifier]::new($Value).Value }
    [Security.Principal.NTAccount]::new($Value).Translate([Security.Principal.SecurityIdentifier]).Value
}
$wsl = Join-Path $env:SystemRoot 'System32\wsl.exe'
$directory = Join-Path $env:LOCALAPPDATA 'Ceviz'
$versions = Join-Path $directory 'wsl-lifetime'
foreach ($path in @($directory, $versions)) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Ceviz lifetime directory requires manual inspection'
        }
    }
}
# The scheduler owns the foreground WSL client directly, not a wrapper which
# could be killed while leaving its child untracked. No custom runtime is copied.
$arguments = '--distribution "' + $Distro + '" --exec /bin/sleep infinity'
$tasks = @(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop | Where-Object TaskName -eq $taskName)
if ($tasks.Count -gt 1) { throw 'Ambiguous Ceviz lifetime task identity' }
$existing = if ($tasks.Count) { $tasks[0] } else { $null }
$previous = $null
if ($existing) {
    $actions = @($existing.Actions)
    if ($existing.Description -ne $description -or (Get-TaskPrincipalSid $existing.Principal.UserId) -ne $principalId -or
        $actions.Count -ne 1 -or $actions[0].Execute -ne $wsl -or $actions[0].Arguments -cne $arguments) {
        throw 'Existing task is not the same Ceviz lifetime component and distro; no overwrite'
    }
    if ($existing.State -eq 'Running' -or -not $existing.Settings.Enabled) {
        throw 'Existing lifetime task is running or disabled for maintenance; inspect it before an explicit upgrade'
    }
    $previous = Export-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop
}

# Preserve an exact owned task definition before replacement. No app-state or
# deployment source files are rewritten by this installer.
if ($previous) {
    New-Item -ItemType Directory -Path $versions -Force | Out-Null
    $backup = Join-Path $versions ('task-backup-' + [guid]::NewGuid().ToString('N') + '.xml')
    [IO.File]::WriteAllText($backup, $previous)
    if ((Export-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop) -cne $previous) {
        throw 'Lifetime task changed during preparation; no overwrite'
    }
}
$action = New-ScheduledTaskAction -Execute $wsl -Argument $arguments
$logon = New-ScheduledTaskTrigger -AtLogOn -User $principalId
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $principalId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$registration = @{ TaskName = $taskName; TaskPath = '\'; Action = $action; Trigger = @($logon, $repeat)
    Principal = $principal; Settings = $settings; Description = $description; ErrorAction = 'Stop' }
if ($previous) { $registration.Force = $true }
Register-ScheduledTask @registration | Out-Null
$registered = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop
if (@($registered.Actions).Count -ne 1 -or $registered.Actions[0].Execute -ne $wsl -or
    $registered.Actions[0].Arguments -cne $arguments -or (Get-TaskPrincipalSid $registered.Principal.UserId) -ne $principalId -or
    $registered.Principal.RunLevel -ne $principal.RunLevel -or $registered.Principal.LogonType -ne $principal.LogonType -or
    -not $registered.Settings.Enabled -or $registered.Settings.RunOnlyIfNetworkAvailable -or
    $registered.Settings.RunOnlyIfIdle -or
    $registered.Settings.ExecutionTimeLimit -ne $settings.ExecutionTimeLimit -or
    $registered.Settings.MultipleInstances -ne $settings.MultipleInstances -or
    @($registered.Triggers).Count -ne 2 -or
    @($registered.Triggers | Where-Object { $_.UserId -and (Get-TaskPrincipalSid $_.UserId) -eq $principalId }).Count -ne 1 -or
    @($registered.Triggers | Where-Object { $_.Repetition.Interval -eq $repeat.Repetition.Interval -and
        [string]::IsNullOrEmpty($_.Repetition.Duration) }).Count -ne 1) {
    throw 'Registered lifetime task did not verify; inspect Task Scheduler before continuing'
}
Start-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop
Start-Sleep -Seconds 2
if ((Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction Stop).State -ne 'Running') {
    throw 'Lifetime task is not running; inspect its LastTaskResult (backend readiness is not established)'
}
Write-Output 'CEVIZ_WSL_LIFETIME=running (network and backend settings unchanged)'
