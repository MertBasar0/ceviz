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
        for distro in (None, "", " ", " FixtureDistro", "FixtureDistro "):
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

    def registration_fixture(self, directory, mode="success", existing=False, non_interactive=False):
        source = r'''
$ErrorActionPreference='Stop'
$env:LOCALAPPDATA=DIRECTORY
$global:mode=MODE
$global:expectedLogon=EXPECTED_LOGON
$global:calls=[System.Collections.Generic.List[string]]::new()
$global:registered=$null; $global:existing=$null; $global:exports=0
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function global:wsl.exe {
    if (($args -join ' ') -cne '--list --quiet') { throw 'Non-passive WSL command denied' }
    $global:calls.Add('wsl-list'); $global:LASTEXITCODE=0
    if ($global:mode -eq 'unknown-distro') { 'OtherDistro' }
    elseif ($global:mode -eq 'list-failure') { $global:LASTEXITCODE=1 }
    else { 'FixtureDistro' }
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
    if ($LogonType -ne $global:expectedLogon -or $RunLevel -ne 'Limited') { throw 'Wrong privilege boundary' }
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
        $Action.Arguments -cne '--distribution FixtureDistro --exec /bin/sleep infinity') { throw 'Wrong registration owner or foreground process' }
    $global:calls.Add('register')
    if ($global:mode -eq 'registration-failure') { throw 'fixture-registration-failure' }
    $global:registered=[pscustomobject]@{Actions=@($Action);Triggers=@($Trigger);Principal=$Principal;Settings=$Settings;State='Ready'}
    if ($global:mode -eq 'readback-failure') { $global:registered.Settings.RunOnlyIfNetworkAvailable=$true }
    if ($global:mode -in @('readback-logon','readback-runlevel')) {
        $global:registered.Principal=[pscustomobject]@{UserId=$Principal.UserId;LogonType=$Principal.LogonType;RunLevel=$Principal.RunLevel}
        if ($global:mode -eq 'readback-logon') {
            $global:registered.Principal.LogonType=if ($global:expectedLogon -eq 'S4U') {'Interactive'} else {'S4U'}
        } else { $global:registered.Principal.RunLevel='Highest' }
    }
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
try { $messages=@(& SCRIPT -Distro 'FixtureDistro' EXTRA_ARGUMENT) }
catch { $failed=$true; $failure=$_.Exception.Message }
'CEVIZ_TEST_RESULT=' + (@{failed=$failed;failure=$failure;calls=@($global:calls);messages=@($messages)} | ConvertTo-Json -Compress)
'''
        existing_source = r'''
$oldArguments='--distribution FixtureDistro --exec /bin/sleep infinity'
$global:existing=[pscustomobject]@{
    TaskName='Ceviz WSL Lifetime'
    Description='Ceviz WSL lifetime; independent of LAN, Tailscale and firewall'
    Principal=[pscustomobject]@{UserId=$sid;LogonType=$global:expectedLogon;RunLevel='Limited'}
    Actions=@([pscustomobject]@{Execute=(Join-Path $env:SystemRoot 'System32\wsl.exe');Arguments=$oldArguments})
    State='Ready';Settings=[pscustomobject]@{Enabled=$true}
}
if ($global:mode -eq 'different-owner') { $global:existing.Principal.UserId='S-1-0-0' }
if ($global:mode -eq 'different-logon') { $global:existing.Principal.LogonType=if ($global:expectedLogon -eq 'S4U') {'Interactive'} else {'S4U'} }
if ($global:mode -eq 'different-runlevel') { $global:existing.Principal.RunLevel='Highest' }
if ($global:mode -eq 'different-distro') { $global:existing.Actions[0].Arguments=$oldArguments.Replace('FixtureDistro','OtherDistro') }
if ($global:mode -eq 'quoted-distro') { $global:existing.Actions[0].Arguments='--distribution "FixtureDistro" --exec /bin/sleep infinity' }
if ($global:mode -eq 'running') { $global:existing.State='Running' }
if ($global:mode -eq 'disabled') { $global:existing.Settings.Enabled=$false }
if ($global:mode -eq 'different-executable') { $global:existing.Actions[0].Execute='powershell.exe' }
''' if existing else ""
        return (source.replace("DIRECTORY", literal(directory)).replace("MODE", literal(mode))
                .replace("EXPECTED_LOGON", literal("S4U" if non_interactive else "Interactive"))
                .replace(" EXTRA_ARGUMENT", " -NonInteractive" if non_interactive else "")
                .replace("EXISTING", existing_source).replace("SCRIPT", literal(ROOT / "deploy/windows/install-wsl-lifetime.ps1")))

    def test_noninteractive_lifetime_is_explicit_limited_and_never_falls_back(self):
        for mode in ("success", "named-principal", "registration-failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                result = self.run_powershell(self.registration_fixture(Path(temporary), mode, non_interactive=True))
                self.assertEqual(result["failed"], mode == "registration-failure", result)
                self.assertEqual(result["calls"].count("register"), 1, result)
                self.assertEqual(result["calls"], ["wsl-list", "register"] if result["failed"]
                                 else ["wsl-list", "register", "start-task"])
                if result["failed"]:
                    self.assertEqual(result["messages"], [])

    def test_existing_lifetime_principal_mode_cannot_change_implicitly(self):
        for non_interactive in (False, True):
            for mode in ("different-logon", "different-runlevel"):
                with self.subTest(non_interactive=non_interactive, mode=mode), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                    root = Path(temporary)
                    result = self.run_powershell(self.registration_fixture(root, mode, existing=True,
                                                                          non_interactive=non_interactive))
                    self.assertTrue(result["failed"], result)
                    self.assertNotIn("register", result["calls"])
                    self.assertFalse((root / "Ceviz").exists(), "Principal changes must stop before backup/mutation")

    def test_task_install_is_network_independent_and_readback_verified(self):
        with tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
            root = Path(temporary)
            result = self.run_powershell(self.registration_fixture(root))
            self.assertFalse(result["failed"], result)
            self.assertEqual(result["calls"], ["wsl-list", "register", "start-task"])
            self.assertTrue(result["messages"][0].startswith("CEVIZ_WSL_LIFETIME=running"))
            self.assertFalse((root / "Ceviz").exists(), "The direct task action needs no runtime files")

    def test_task_failures_do_not_report_installed_success(self):
        for non_interactive in (False, True):
            for mode in ("unknown-distro", "list-failure", "registration-failure", "readback-failure",
                         "readback-logon", "readback-runlevel", "start-failure", "not-running"):
                with self.subTest(non_interactive=non_interactive, mode=mode), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                    result = self.run_powershell(self.registration_fixture(Path(temporary), mode,
                                                                          non_interactive=non_interactive))
                    self.assertTrue(result["failed"], result)
                    self.assertEqual(result["messages"], [])
                    if mode not in ("start-failure", "not-running"):
                        self.assertNotIn("start-task", result["calls"])
                    if mode in ("unknown-distro", "list-failure"):
                        self.assertNotIn("register", result["calls"])

    def test_unknown_or_maintenance_task_is_not_overwritten(self):
        for mode in ("different-owner", "different-distro", "quoted-distro", "running", "disabled", "different-executable"):
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
        for distro in ('Fixture"Distro', 'Fixture\\Distro', 'Fixture\nDistro',
                       'Fixture Distro', 'Fixture\tDistro', 'Fixture\u00a0Distro'):
            with self.subTest(distro=distro), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                source = self.registration_fixture(Path(temporary)).replace("-Distro 'FixtureDistro')", "-Distro " + literal(distro) + ")")
                result = self.run_powershell(source)
                self.assertTrue(result["failed"], result)
                self.assertEqual(result["calls"], [])

    def test_same_task_upgrade_backs_up_definition_without_copying_runtime(self):
        for non_interactive in (False, True):
            with self.subTest(non_interactive=non_interactive), tempfile.TemporaryDirectory(prefix="ceviz-lifetime-test-") as temporary:
                root = Path(temporary)
                result = self.run_powershell(self.registration_fixture(root, existing=True,
                                                                      non_interactive=non_interactive))
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
try { & SCRIPT -Distro 'FixtureDistro' -ListenPort 0 }
catch { $failure = $_.Exception.Message; $caught = $failure -eq 'fixture-network-lost' }
'CEVIZ_TEST_RESULT=' + (@{ caught = $caught; failure = $failure; events = @($global:events) } | ConvertTo-Json -Compress)
'''.replace("SCRIPT", literal(ROOT / "deploy/windows/ceviz-backend-relay.ps1"))
        result = self.run_powershell(source)
        self.assertTrue(result["caught"], result)
        self.assertEqual(result["events"], [], "LAN relay must not own, kill or restart the independent WSL lifetime")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell subprocess proof")
class PCNodeInstallerTests(unittest.TestCase):
    """install-pc-node.ps1 with substituted task, npm and node calls; nothing is installed."""

    DEVICE = "d" * 64

    def run_installer(self, directory, arguments="", task=None, node_version="v24.19.0", engines=">=24.16.0 <25 || >=26.1.0",
                      protected=False, decline=False):
        source = r'''
$ErrorActionPreference='Stop'
$global:calls=[System.Collections.Generic.List[string]]::new()
$global:removed=$false
function global:Get-ScheduledTask { if (__TASK__ -and -not $global:removed) { [pscustomobject]@{ Actions = @([pscustomobject]@{ Execute = __TASK__ }) } } }
function global:Stop-ScheduledTask { $global:calls.Add('stop-task') }
function global:Unregister-ScheduledTask {
    if (__PROTECTED__) { $global:calls.Add('unregister-denied'); throw 'Access is denied.' }
    $global:calls.Add('unregister-task'); $global:removed=$true
}
function global:Start-Process {
    param($FilePath, $Verb, $WindowStyle, [switch]$Wait, [switch]$PassThru, $ArgumentList)
    $global:calls.Add("elevated $FilePath $Verb " + ($ArgumentList -join ' '))
    if (__DECLINE__) { throw 'The operation was canceled by the user.' }
    $global:removed=$true
    [pscustomobject]@{ ExitCode = 0 }
}
function global:fake-winget { $global:calls.Add('winget') }
function global:fake-npm {
    $global:calls.Add('npm ' + ($args -join ' '))
    $prefix = $args[[array]::IndexOf($args, '--prefix') + 1]
    $package = Join-Path $prefix 'node_modules\openclaw'
    New-Item -ItemType Directory -Force -Path $package | Out-Null
    @{ version = '2026.9.1'; bin = @{ openclaw = 'openclaw.mjs' }; engines = @{ node = __ENGINES__ } } | ConvertTo-Json | Set-Content (Join-Path $package 'package.json')
    $global:LASTEXITCODE = 0
}
function global:fake-node {
    if ($args[0] -eq '--version') { return __NODE_VERSION__ }
    if ($args[1] -eq 'connect') {
        $file = $args[3]
        $global:calls.Add('connect state=' + $env:OPENCLAW_STATE_DIR + ' code=' + (Get-Content -Raw $file) + ' ' + ($args[4..7] -join ' '))
        $global:LASTEXITCODE = 0; return
    }
    if ($args[1] -eq 'node' -and $args[2] -eq 'identity') { '{"deviceId":"__DEVICE__","publicKey":"x"}'; $global:LASTEXITCODE = 0; return }
    throw ('unexpected node call: ' + ($args -join ' '))
}
$output = @(& __SCRIPT__ -Version '2026.9.1' -Prefix __PREFIX__ -StateDir __STATE__ -Node fake-node -Npm fake-npm -Winget fake-winget __ARGUMENTS__)
$code = $LASTEXITCODE
'CEVIZ_TEST_RESULT=' + (@{ code = $code; output = @($output | ForEach-Object { "$_" }); calls = @($global:calls);
    leftovers = @(Get-ChildItem -LiteralPath __STATE__ -Filter 'pair-*' -ErrorAction SilentlyContinue | ForEach-Object Name) } | ConvertTo-Json -Compress)
'''
        for key, value in {"__SCRIPT__": literal(ROOT / "deploy/windows/install-pc-node.ps1"),
                           "__PREFIX__": literal(Path(directory) / "prefix"), "__STATE__": literal(Path(directory) / "state"),
                           "__TASK__": "$null" if task is None else literal(task), "__ENGINES__": literal(engines),
                           "__NODE_VERSION__": literal(node_version), "__DEVICE__": self.DEVICE, "__ARGUMENTS__": arguments,
                           "__PROTECTED__": "$true" if protected else "$false",
                           "__DECLINE__": "$true" if decline else "$false"}.items():
            source = source.replace(key, value)
        source = "Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop\n" + source
        encoded = base64.b64encode(source.encode("utf-16le")).decode("ascii")
        result = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-EncodedCommand", encoded], capture_output=True, text=True, timeout=30,
                                input="SINGLE-USE-CODE",  # the setup code arrives on standard input only
                                creationflags=subprocess.CREATE_NO_WINDOW)
        records = [line[len("CEVIZ_TEST_RESULT="):] for line in result.stdout.splitlines()
                   if line.startswith("CEVIZ_TEST_RESULT=")]
        self.assertEqual(len(records), 1, result.stdout + result.stderr)
        return json.loads(records[0])

    def test_a_node_service_ceviz_did_not_create_is_left_alone_without_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(directory, task=r"C:\Users\me\.openclaw\node.vbs")
        self.assertEqual(result["code"], 4)
        self.assertIn(r"CEVIZ_PC_NODE_FOREIGN=C:\Users\me\.openclaw\node.vbs", result["output"])
        self.assertEqual(result["calls"], [], "Nothing is downloaded, stopped or paired")

    def test_pairs_from_a_private_file_with_its_own_openclaw_copy_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(directory, "-Replace", task=r"C:\Users\me\.openclaw\node.vbs")
            state = str(Path(directory) / "state")
            prefix = str(Path(directory) / "prefix")
        self.assertEqual(result["code"], 0, result)
        self.assertEqual(result["output"][-1], "CEVIZ_PC_NODE_ID=" + self.DEVICE)
        self.assertEqual(result["calls"][0], f"npm install --prefix {prefix} --no-fund --no-audit --omit=dev "
                                             "--loglevel=error openclaw@2026.9.1")
        self.assertEqual(result["calls"][1:3], ["stop-task", "unregister-task"])
        self.assertEqual(result["calls"][3], f"connect state={state} code=SINGLE-USE-CODE --service --display-name Ceviz PC")
        self.assertEqual(result["leftovers"], [], "The setup code file is removed")

    def test_a_node_task_registered_by_an_administrator_is_replaced_only_with_approval(self):
        foreign = r"C:\Users\me\.openclaw\node.vbs"
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(directory, "-Replace", task=foreign, protected=True)
        self.assertEqual(result["code"], 0, result)
        self.assertEqual(result["calls"][1:4], [
            "stop-task", "unregister-denied",
            "elevated powershell.exe RunAs -NoProfile -NonInteractive -Command "
            "Unregister-ScheduledTask -TaskName 'OpenClaw Node' -Confirm:$false"])
        self.assertTrue(result["calls"][4].startswith("connect "), result)
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(directory, "-Replace", task=foreign, protected=True, decline=True)
        self.assertEqual(result["code"], 7)
        self.assertTrue(any("needs administrator approval" in line for line in result["output"]), result)
        self.assertFalse(any(call.startswith("connect") for call in result["calls"]))

    def test_a_node_too_old_for_this_openclaw_is_reported_before_pairing(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer(directory, node_version="v22.12.0")
        self.assertEqual(result["code"], 3)
        self.assertTrue(any("needs Node.js >=24.16.0" in line for line in result["output"]), result)
        self.assertFalse(any(call.startswith("connect") for call in result["calls"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
