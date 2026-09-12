"""Real PowerShell subprocess tests; WSL, tasks and firewall calls are substituted."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(POWERSHELL, "Windows PowerShell subprocess proof")
class WindowsLifecycleTests(unittest.TestCase):
    def run_powershell(self, source):
        # Load native utility exports before substituting sibling commands such
        # as Start-Sleep; the substitutes must not interfere with autoload.
        source = "Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop\n" + source
        encoded = base64.b64encode(source.encode("utf-16le")).decode("ascii")
        result = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                                capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [line[len("CEVIZ_TEST_RESULT="):] for line in result.stdout.splitlines()
                   if line.startswith("CEVIZ_TEST_RESULT=")]
        self.assertEqual(len(records), 1, result.stdout + result.stderr)
        return json.loads(records[0])

    def test_all_windows_scripts_parse_on_windows_powershell(self):
        source = r'''
$errors = @()
Get-ChildItem -LiteralPath DIRECTORY -Filter '*.ps1' | ForEach-Object {
    $tokens=$null; $problems=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$problems)
    $errors += @($problems | ForEach-Object Message)
}
'CEVIZ_TEST_RESULT=' + (@{ errors=@($errors) } | ConvertTo-Json -Compress)
'''.replace("DIRECTORY", literal(ROOT / "deploy/windows"))
        self.assertEqual(self.run_powershell(source)["errors"], [])

    def test_relay_requires_explicit_unambiguous_distro_before_any_host_action(self):
        for distro in (None, "", " ", " Fixture Distro", "Fixture Distro "):
            with self.subTest(distro=distro):
                source = r'''
$ErrorActionPreference='Stop'
$global:events=[System.Collections.Generic.List[string]]::new()
function global:wsl.exe { $global:events.Add('implicit-wsl-selection'); 'First Distro' }
function global:Start-Process { $global:events.Add('process-launch'); throw 'Live process launch denied' }
function global:Get-NetRoute { $global:events.Add('network-query'); throw 'Live network query denied' }
function global:Get-ScheduledTask { $global:events.Add('task-query'); throw 'Live task query denied' }
function global:New-Item { throw 'Live file mutation denied' }
$failed=$false; $messages=@()
try { $messages=@(& SCRIPT ARGUMENTS) } catch { $failed=$true }
'CEVIZ_TEST_RESULT=' + (@{failed=$failed;events=@($global:events);messages=@($messages)} | ConvertTo-Json -Compress)
'''.replace("SCRIPT", literal(ROOT / "deploy/windows/install-relay.ps1")).replace(
                    "ARGUMENTS", "" if distro is None else "-Distro " + literal(distro))
                result = self.run_powershell(source)
                self.assertTrue(result["failed"], result)
                self.assertEqual(result["events"], [], "Missing/ambiguous distro must not select or touch a host")
                self.assertEqual(result["messages"], [])

    def registration_fixture(self, directory, mode="success", existing=False):
        source = r'''
$ErrorActionPreference='Stop'
$env:LOCALAPPDATA=DIRECTORY
$global:mode=MODE
$global:calls=[System.Collections.Generic.List[string]]::new()
$global:registered=$null; $global:existing=$null; $global:exports=0
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function global:wsl.exe {
    if (($args -join ' ') -cne '--list --quiet') { throw 'Non-passive WSL command denied' }
    $global:calls.Add('wsl-list'); $global:LASTEXITCODE=0
    if ($global:mode -eq 'unknown-distro') { 'Other Distro' }
    elseif ($global:mode -eq 'list-failure') { $global:LASTEXITCODE=1 }
    else { 'Fixture Distro' }
}
function global:Start-Process { throw 'Live process launch denied' }
function global:Stop-Process { throw 'Live process stop denied' }
function global:Get-NetRoute { throw 'Network dependency denied' }
function global:New-NetFirewallRule { throw 'Firewall mutation denied' }
function global:Copy-Item {
    throw 'Lifetime action must not depend on a copied PowerShell wrapper'
}
function global:Get-ScheduledTask {
    param($TaskPath,$TaskName)
    if ($TaskPath -cne '\' -or ($TaskName -and $TaskName -cne 'Ceviz WSL Lifetime')) { throw 'Wrong task query' }
    if ($global:registered) { $global:registered }
    elseif ($global:existing) { $global:existing }
    elseif ($TaskName) { throw 'fixture-task-not-found' }
}
function global:Export-ScheduledTask {
    param($TaskName,$TaskPath)
    $global:exports++; $global:calls.Add('backup-read')
    if ($global:mode -eq 'drift' -and $global:exports -gt 1) { '<Task>changed</Task>' } else { '<Task>previous</Task>' }
}
function global:New-ScheduledTaskAction { param($Execute,$Argument) [pscustomobject]@{Execute=$Execute;Arguments=$Argument} }
function global:New-ScheduledTaskTrigger {
    param([switch]$AtLogOn,$User,[switch]$Once,$At,$RepetitionInterval)
    if ($AtLogOn) { [pscustomobject]@{UserId=$User} }
    elseif ($Once -and $RepetitionInterval.TotalMinutes -eq 1) {
        [pscustomobject]@{Repetition=[pscustomobject]@{Interval='PT1M';Duration=$null}}
    } else { throw 'Wrong lifetime trigger' }
}
function global:New-ScheduledTaskPrincipal {
    param($UserId,$LogonType,$RunLevel)
    if ($LogonType -ne 'Interactive' -or $RunLevel -ne 'Limited') { throw 'Wrong privilege boundary' }
    [pscustomobject]@{UserId=$UserId;LogonType=$LogonType;RunLevel=$RunLevel}
}
function global:New-ScheduledTaskSettingsSet {
    param($ExecutionTimeLimit,$MultipleInstances,[switch]$StartWhenAvailable,[switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries)
    if ($ExecutionTimeLimit -ne [TimeSpan]::Zero -or $MultipleInstances -ne 'IgnoreNew' -or
        -not $StartWhenAvailable -or -not $AllowStartIfOnBatteries -or -not $DontStopIfGoingOnBatteries) { throw 'Wrong lifetime settings' }
    [pscustomobject]@{ExecutionTimeLimit='PT0S';MultipleInstances=2;Enabled=$true;RunOnlyIfNetworkAvailable=$false;RunOnlyIfIdle=$false}
}
function global:Register-ScheduledTask {
    param($TaskName,$TaskPath,$Action,$Trigger,$Principal,$Settings,$Description,[switch]$Force)
    if ($TaskName -ne 'Ceviz WSL Lifetime' -or $TaskPath -ne '\' -or
        [bool]$Force -ne [bool]$global:existing -or
        $Action.Execute -ne (Join-Path $env:SystemRoot 'System32\wsl.exe') -or
        $Action.Arguments -cne '--distribution "Fixture Distro" --exec /bin/sleep infinity') { throw 'Wrong registration owner or foreground process' }
    $global:calls.Add('register')
    if ($global:mode -eq 'registration-failure') { throw 'fixture-registration-failure' }
    $global:registered=[pscustomobject]@{Actions=@($Action);Triggers=@($Trigger);Principal=$Principal;Settings=$Settings;State='Ready'}
    if ($global:mode -eq 'readback-failure') { $global:registered.Settings.RunOnlyIfNetworkAvailable=$true }
    if ($global:mode -eq 'named-principal') {
        $global:registered.Principal.UserId=[Security.Principal.WindowsIdentity]::GetCurrent().Name
        $global:registered.Triggers[0].UserId=$global:registered.Principal.UserId
    }
}
function global:Start-ScheduledTask {
    param($TaskName,$TaskPath)
    if ($TaskName -ne 'Ceviz WSL Lifetime' -or $TaskPath -ne '\') { throw 'Wrong task start' }
    $global:calls.Add('start-task')
    if ($global:mode -eq 'start-failure') { throw 'fixture-start-failure' }
    if ($global:mode -ne 'not-running') { $global:registered.State='Running' }
}
function global:Start-Sleep {}
EXISTING
$failed=$false; $messages=@(); $failure=''
try { $messages=@(& SCRIPT -Distro 'Fixture Distro') }
catch { $failed=$true; $failure=$_.Exception.Message }
'CEVIZ_TEST_RESULT=' + (@{failed=$failed;failure=$failure;calls=@($global:calls);messages=@($messages)} | ConvertTo-Json -Compress)
'''
        existing_source = r'''
$oldArguments='--distribution "Fixture Distro" --exec /bin/sleep infinity'
$global:existing=[pscustomobject]@{
    TaskName='Ceviz WSL Lifetime'
    Description='Ceviz WSL lifetime; independent of LAN, Tailscale and firewall'
    Principal=[pscustomobject]@{UserId=$sid}
    Actions=@([pscustomobject]@{Execute=(Join-Path $env:SystemRoot 'System32\wsl.exe');Arguments=$oldArguments})
    State='Ready';Settings=[pscustomobject]@{Enabled=$true}
}
if ($global:mode -eq 'different-owner') { $global:existing.Principal.UserId='S-1-0-0' }
if ($global:mode -eq 'different-distro') { $global:existing.Actions[0].Arguments=$oldArguments.Replace('Fixture Distro','Other Distro') }
if ($global:mode -eq 'running') { $global:existing.State='Running' }
if ($global:mode -eq 'disabled') { $global:existing.Settings.Enabled=$false }
if ($global:mode -eq 'different-executable') { $global:existing.Actions[0].Execute='powershell.exe' }
''' if existing else ""
        return (source.replace("DIRECTORY", literal(directory)).replace("MODE", literal(mode))
                .replace("EXISTING", existing_source).replace("SCRIPT", literal(ROOT / "deploy/windows/install-wsl-lifetime.ps1")))

    def test_task_install_is_network_independent_and_readback_verified(self):
        with tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
            root = Path(temporary)
            result = self.run_powershell(self.registration_fixture(root))
            self.assertFalse(result["failed"], result)
            self.assertEqual(result["calls"], ["wsl-list", "register", "start-task"])
            self.assertTrue(result["messages"][0].startswith("CEVIZ_WSL_LIFETIME=running"))
            self.assertFalse((root / "Ceviz").exists(), "The direct task action needs no runtime files")

    def test_task_failures_do_not_report_installed_success(self):
        for mode in ("unknown-distro", "list-failure", "registration-failure", "readback-failure", "start-failure", "not-running"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                result = self.run_powershell(self.registration_fixture(Path(temporary), mode))
                self.assertTrue(result["failed"], result)
                self.assertEqual(result["messages"], [])
                if mode in ("unknown-distro", "list-failure", "registration-failure", "readback-failure"):
                    self.assertNotIn("start-task", result["calls"])
                if mode in ("unknown-distro", "list-failure"):
                    self.assertNotIn("register", result["calls"])

    def test_unknown_or_maintenance_task_is_not_overwritten(self):
        for mode in ("different-owner", "different-distro", "running", "disabled", "different-executable"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                root = Path(temporary)
                result = self.run_powershell(self.registration_fixture(root, mode, existing=True))
                self.assertTrue(result["failed"], result)
                self.assertEqual(result["calls"], ["wsl-list"])
                self.assertFalse((root / "Ceviz").exists())

    def test_account_name_readback_resolves_to_the_same_windows_sid(self):
        with tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
            result = self.run_powershell(self.registration_fixture(Path(temporary), "named-principal"))
            self.assertFalse(result["failed"], result)
            self.assertEqual(result["calls"], ["wsl-list", "register", "start-task"])

    def test_invalid_distro_rejected_before_any_wsl_or_task_call(self):
        for distro in ('Fixture" Distro', 'Fixture\\Distro', 'Fixture\nDistro'):
            with self.subTest(distro=distro), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                source = self.registration_fixture(Path(temporary)).replace("-Distro 'Fixture Distro')", "-Distro " + literal(distro) + ")")
                result = self.run_powershell(source)
                self.assertTrue(result["failed"], result)
                self.assertEqual(result["calls"], [])

    def test_same_task_upgrade_backs_up_definition_without_copying_runtime(self):
        with tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
            root = Path(temporary)
            result = self.run_powershell(self.registration_fixture(root, existing=True))
            self.assertFalse(result["failed"], result)
            self.assertEqual(result["calls"], ["wsl-list", "backup-read", "backup-read", "register", "start-task"])
            self.assertEqual(list((root / "Ceviz/wsl-lifetime").glob("*.ps1")), [])
            backups = list((root / "Ceviz/wsl-lifetime").glob("task-backup-*.xml"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "<Task>previous</Task>")

    def test_task_drift_after_backup_stops_before_registration(self):
        with tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
            result = self.run_powershell(self.registration_fixture(Path(temporary), "drift", existing=True))
            self.assertTrue(result["failed"], result)
            self.assertEqual(result["calls"], ["wsl-list", "backup-read", "backup-read"])

    def test_lan_loss_does_not_own_or_kill_wsl_lifetime(self):
        # IPv6 loopback is a real isolated listener, not an operator LAN binding.
        # Route loss occurs after the first successful listen, matching the old
        # relay's finally path without invoking WSL or touching the firewall.
        source = r'''
$ErrorActionPreference = 'Stop'
$global:events = [System.Collections.Generic.List[string]]::new()
$global:routes = 0
function global:Start-Process {
    $global:events.Add('keeper-start')
    $process = [pscustomobject]@{ HasExited = $false; Id = 987654 }
    $process | Add-Member ScriptMethod Dispose { $global:events.Add('keeper-dispose') }
    $process
}
function global:Stop-Process { $global:events.Add('keeper-stop') }
function global:wsl.exe { $global:events.Add('wsl-command') }
function global:Get-NetRoute {
    $global:routes++
    if ($global:routes -gt 1) { throw 'fixture-network-lost' }
    [pscustomobject]@{ InterfaceIndex = 777; RouteMetric = 1 }
}
function global:Get-NetIPAddress { [pscustomobject]@{ IPAddress = '::1' } }
function global:Get-NetFirewallRule {}
function global:Remove-NetFirewallRule {}
function global:New-NetFirewallRule {}
$caught = $false
$failure = ''
try { & SCRIPT -Distro 'Fixture Distro' -ListenPort 0 }
catch { $failure = $_.Exception.Message; $caught = $failure -eq 'fixture-network-lost' }
'CEVIZ_TEST_RESULT=' + (@{ caught = $caught; failure = $failure; events = @($global:events) } | ConvertTo-Json -Compress)
'''.replace("SCRIPT", literal(ROOT / "deploy/windows/ceviz-backend-relay.ps1"))
        result = self.run_powershell(source)
        self.assertTrue(result["caught"], result)
        self.assertEqual(result["events"], [], "LAN relay must not own, kill or restart the independent WSL lifetime")


if __name__ == "__main__":
    unittest.main(verbosity=2)
