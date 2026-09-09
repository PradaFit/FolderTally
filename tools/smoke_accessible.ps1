param([Parameter(Mandatory)][string]$Exe, [string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class FolderTallyWindowTest {
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int w, int h, uint flags);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr hwnd, uint attribute, out Rect rect, int size);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hwnd, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int command);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
    public static bool OwnsForeground(int processId) {
        uint owner; GetWindowThreadProcessId(GetForegroundWindow(), out owner);
        return owner == processId;
    }
    private delegate bool EnumProc(IntPtr hwnd, IntPtr data);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc callback, IntPtr data);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int length);
    public static IntPtr FindMain(int processId, string expected = "FolderTally") {
        IntPtr found = IntPtr.Zero;
        EnumWindows((hwnd, data) => {
            uint owner; GetWindowThreadProcessId(hwnd, out owner);
            if (owner == processId && IsWindowVisible(hwnd)) {
                var title = new StringBuilder(256); GetWindowText(hwnd, title, 256);
                if (title.ToString() == expected) { found = hwnd; return false; }
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
}
'@
$null = [FolderTallyWindowTest]::SetProcessDpiAwarenessContext([IntPtr](-4))
$root = Split-Path -Parent $PSScriptRoot
$sourceExe = (Resolve-Path -LiteralPath $Exe).Path
$output = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else { Join-Path $root ('_Internal\verification\accessible-smoke-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
if (Test-Path -LiteralPath $output) { throw 'Smoke-test output must be a new directory.' }
$sourceFolder = Split-Path -Parent $sourceExe
if (-not (Test-Path -LiteralPath (Join-Path $sourceFolder '_internal\PySide6\Qt6Widgets.dll'))) { throw 'Expected the complete onedir package.' }
$portable = Join-Path $output 'Portable Copy'
$sample = Join-Path $output 'Sample folder'
$reports = Join-Path $output 'Reports'
$settings = Join-Path $output 'AppData'
$null = New-Item -ItemType Directory -Path $portable, $sample, $reports, $settings
$isolatedExe = Join-Path $portable 'FolderTally.exe'
Write-Host "Synthetic smoke-test copy: $sourceFolder -> $portable. Copy the complete onedir package, excluding nothing; reject reparse points and verify every SHA-256 before launch. No existing files are replaced."
$packageFiles = @(Get-ChildItem -LiteralPath $sourceFolder -Recurse -Force)
if (@($packageFiles | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Package contains a reparse point.' }
foreach ($item in @(Get-ChildItem -LiteralPath $sourceFolder -Force)) { Copy-Item -LiteralPath $item.FullName -Destination $portable -Recurse }
foreach ($item in @($packageFiles | Where-Object { -not $_.PSIsContainer })) {
    $relative = [IO.Path]::GetRelativePath($sourceFolder, $item.FullName)
    if ((Get-FileHash -LiteralPath $item.FullName).Hash -ne (Get-FileHash -LiteralPath (Join-Path $portable $relative)).Hash) { throw "Copy mismatch: $relative" }
}
$hash = (Get-FileHash -LiteralPath $sourceExe -Algorithm SHA256).Hash
if ((Get-FileHash -LiteralPath $isolatedExe -Algorithm SHA256).Hash -ne $hash) { throw 'Copied EXE hash mismatch.' }
$null = New-Item -ItemType Directory -Path (Join-Path $sample 'Contracts'), (Join-Path $sample 'Empty')
[IO.File]::WriteAllText((Join-Path $sample 'Notes.txt'), 'FolderTally test')
[IO.File]::WriteAllText((Join-Path $sample 'Contracts\Résumé_漢.json'), '{}')
$expectedBytes = 18
$script:target = $null
$script:window = $null
$script:launch = $null
$results = [Collections.Generic.List[object]]::new()

function Start-TestApp {
    $start = [Diagnostics.ProcessStartInfo]::new($isolatedExe)
    $start.WorkingDirectory = $portable
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    # This is the GUI under test, not a background helper. Match Explorer launch.
    $start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Normal
    $start.Environment['LOCALAPPDATA'] = $settings
    $start.Environment['PATH'] = Join-Path $env:SystemRoot 'System32'
    foreach ($name in 'PYTHONPATH', 'PYTHONHOME', 'TCL_LIBRARY', 'TK_LIBRARY') { $null = $start.Environment.Remove($name) }
    $script:launch = [Diagnostics.Process]::Start($start)
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        foreach ($candidate in @(Get-Process -Name FolderTally -ErrorAction SilentlyContinue)) {
            if ($candidate.Path -ne $isolatedExe) { continue }
            $appHandle = [FolderTallyWindowTest]::FindMain($candidate.Id)
            if ($appHandle -ne [IntPtr]::Zero) {
                $null = [FolderTallyWindowTest]::ShowWindow($appHandle, 5)
                $candidate.Refresh()
                $script:target = if ($candidate.Id -eq $script:launch.Id) { $script:launch } else { $candidate }
                $null = $script:target.Handle  # Retain an exit-code-capable handle before closing.
                $script:window = [System.Windows.Automation.AutomationElement]::FromHandle($appHandle)
                Start-Sleep -Milliseconds 350
                return
            }
        }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Portable EXE did not open a window.'
}

function Find-Control([string]$Id) {
    $nodes = $script:window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($node in $nodes) { if ($node.Current.AutomationId.EndsWith('.' + $Id)) { return $node } }
    throw "Missing accessible control: $Id"
}

function Set-Field([string]$Id, [string]$Value) {
    $control = Find-Control $Id
    $pattern = $control.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $pattern.SetValue($Value)
    if ($pattern.Current.Value -ne $Value) { throw "Value did not update: $Id" }
}

function Invoke-Control([string]$Id) {
    $control = Find-Control $Id
    $control.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

function Select-Choice([string]$Id, [int]$Index, [string]$Expected) {
    $control = Find-Control $Id
    $null = [FolderTallyWindowTest]::SetForegroundWindow([FolderTallyWindowTest]::FindMain($script:target.Id))
    $control.SetFocus()
    Start-Sleep -Milliseconds 100
    $expand = $control.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
    $expand.Expand()
    Start-Sleep -Milliseconds 200
    $nodes = $script:window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $choice = @($nodes | Where-Object { $_.Current.Name -eq $Expected -and $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::ListItem })
    if ($choice.Count -ne 1) { throw "Dropdown option not exposed: $Id / $Expected ($($choice.Count))" }
    # Qt exposes popup selection separately from accepting a combo choice.
    # Exercise its normal keyboard route, only while this test owns focus.
    if (-not [FolderTallyWindowTest]::OwnsForeground($script:target.Id)) { throw 'Test app does not own keyboard focus.' }
    [Windows.Forms.SendKeys]::SendWait('{HOME}' + ('{DOWN}' * $Index) + '{ENTER}')
    Start-Sleep -Milliseconds 200
    $actual = (Find-Control $Id).GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    if ($actual -ne $Expected) { throw "Choice did not update: $Id ($actual, expected $Expected)" }
}

function Wait-Status([string]$Expected) {
    $deadline = [DateTime]::UtcNow.AddSeconds(40)
    do {
        $status = (Find-Control 'scanStatus').Current.Name
        if ($status -eq $Expected) { return }
        if ($status -eq 'Report could not be created') { throw (Find-Control 'scanDetail').Current.Name }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Expected status '$Expected', got '$status'."
}

function Close-TestApp {
    if ($null -ne $script:target -and -not $script:target.HasExited) {
        $handle = [FolderTallyWindowTest]::FindMain($script:target.Id)
        $expectedScreen = [Windows.Forms.Screen]::FromHandle($handle)
        $null = [FolderTallyWindowTest]::PostMessage($handle, 0x10, [IntPtr]::Zero, [IntPtr]::Zero)
        if (-not $script:target.WaitForExit(10000)) { throw 'Application did not close normally.' }
        if ($script:target.ExitCode -ne 0) { throw "Application returned an error exit code: $($script:target.ExitCode)" }
        $results.Add(@{ check = 'Direct clean exit without a modal'; monitor = $expectedScreen.DeviceName; passed = $true })
    }
    if ($null -ne $script:launch -and -not $script:launch.WaitForExit(10000)) { throw 'Portable launcher did not exit.' }
    $script:target = $null
    $script:window = $null
}

try {
    Start-TestApp
    $uia = & (Join-Path $PSScriptRoot 'inspect_uia.ps1') -TargetProcessId $script:target.Id -OutputFile (Join-Path $output 'uia.json')
    foreach ($id in 'sourceFolder', 'reportFolder', 'format_txt', 'format_json', 'format_pdf', 'memoryLimit', 'textSize', 'appearanceTheme', 'createReport', 'cancelScan', 'help', 'about', 'savedReport', 'openReport', 'showFolder') {
        $control = Find-Control $id
        if (-not $control.Current.Name -or -not $control.Current.IsKeyboardFocusable) { throw "Control is not named or focusable: $id" }
    }
    $results.Add(@{ check = 'Windows UI Automation controls'; passed = $true })
    Write-Host 'Accessible controls passed.'
    $allNodes = $script:window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    if (@($allNodes | Where-Object { $_.Current.AutomationId.EndsWith('.authorCredit') }).Count) { throw 'Main header still contains author credit.' }
    $titleBounds = (Find-Control 'brandTitle').Current.BoundingRectangle
    $themeBounds = (Find-Control 'appearanceTheme').Current.BoundingRectangle
    $textBounds = (Find-Control 'textSize').Current.BoundingRectangle
    $introBounds = (Find-Control 'workflowIntro').Current.BoundingRectangle
    if ($themeBounds.Top -le $titleBounds.Bottom -or $introBounds.Top -le $themeBounds.Bottom -or [Math]::Abs($themeBounds.Top - $textBounds.Top) -gt 1) {
        throw 'Appearance controls are not aligned below the title and above the introduction.'
    }
    $results.Add(@{ check = 'Compact appearance row beneath title; no header credit'; passed = $true })
    Select-Choice 'appearanceTheme' 1 'Light'
    Select-Choice 'appearanceTheme' 2 'Dark'
    Select-Choice 'textSize' 1 '125%'
    Close-TestApp
    Start-TestApp
    foreach ($item in @(@('appearanceTheme', 'Dark'), @('textSize', '125%'))) {
        $value = (Find-Control $item[0]).GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
        if ($value -ne $item[1]) { throw "Preference did not persist: $($item[0])" }
    }
    Select-Choice 'textSize' 0 '100%'
    $results.Add(@{ check = 'Accessible theme selection and preference persistence'; passed = $true })
    Invoke-Control 'createReport'
    Wait-Status 'Check your folder selection'
    Set-Field 'sourceFolder' $sample
    Set-Field 'reportFolder' $reports
    foreach ($format in 'txt', 'json', 'pdf') {
        $previous = (Find-Control 'savedReport').GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
        (Find-Control ('format_' + $format)).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Milliseconds 150
        if (-not (Find-Control ('format_' + $format)).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Current.IsSelected) { throw 'Format selection failed.' }
        Invoke-Control 'createReport'
        $deadline = [DateTime]::UtcNow.AddSeconds(40)
        do {
            Start-Sleep -Milliseconds 100
            $report = (Find-Control 'savedReport').GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
            $status = (Find-Control 'scanStatus').Current.Name
            if ($status -eq 'Report could not be created') { throw (Find-Control 'scanDetail').Current.Name }
            if ($report -ne $previous -and $report.EndsWith('.' + $format) -and $status -eq 'Report ready') { break }
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($report -eq $previous -or -not $report.EndsWith('.' + $format) -or $status -ne 'Report ready') { throw "No new $format report was created." }
        if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Saved report missing.' }
        if ((Find-Control 'total_size').Current.Name -ne "Total file size: $expectedBytes B") { throw 'Incorrect inventory total.' }
        $results.Add(@{ check = $format + ' export'; path = $report; passed = $true })
        Write-Host "$format export passed."
    }
    $before = @(Get-ChildItem -LiteralPath $reports).Count
    if ($before -ne 3) { throw 'Expected exactly three reports.' }
    $cancelSource = Join-Path $output 'Cancellation folder'
    $null = New-Item -ItemType Directory -Path $cancelSource
    for ($index = 0; $index -lt 3000; $index++) { [IO.File]::WriteAllText((Join-Path $cancelSource ($index.ToString() + '.txt')), '') }
    Set-Field 'sourceFolder' $cancelSource
    Invoke-Control 'createReport'
    Start-Sleep -Milliseconds 180
    Invoke-Control 'cancelScan'
    Wait-Status 'Scan cancelled'
    if (@(Get-ChildItem -LiteralPath $reports).Count -ne $before) { throw 'Cancellation left an output file.' }
    $results.Add(@{ check = 'Cooperative cancellation'; passed = $true })
    foreach ($item in @(@('help', 'FolderTally help'), @('about', 'About FolderTally'), @('browseSource', 'Choose source folder'), @('browseReports', 'Choose report folder'))) {
        Invoke-Control $item[0]
        Start-Sleep -Milliseconds 400
        $dialogHandle = [FolderTallyWindowTest]::FindMain($script:target.Id, $item[1])
        if ($dialogHandle -eq [IntPtr]::Zero) { throw "Dialog did not open: $($item[1])" }
        $dialog = [System.Windows.Automation.AutomationElement]::FromHandle($dialogHandle)
        if ($item[0] -eq 'about') {
            $dialogNodes = $dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
            $documentNode = @($dialogNodes | Where-Object { $_.Current.AutomationId.EndsWith('.documentText') })
            if ($documentNode.Count -ne 1) { throw 'About text control is missing.' }
            $textPattern = $documentNode[0].GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
            $aboutText = $textPattern.DocumentRange.GetText(300)
            if ($aboutText -notmatch 'Published by PradaFit') { throw 'About is missing publisher attribution.' }
        }
        $dialog.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern).Close()
        Start-Sleep -Milliseconds 200
        $results.Add(@{ check = $item[1]; passed = $true })
    }
    foreach ($screen in [Windows.Forms.Screen]::AllScreens) {
        $work = $screen.WorkingArea
        $null = [FolderTallyWindowTest]::SetWindowPos($script:target.MainWindowHandle, [IntPtr]::Zero, $work.X + 70, $work.Y + 45, 900, 760, 0x0014)
        Start-Sleep -Milliseconds 500
        Close-TestApp
        Start-TestApp
        $rect = [FolderTallyWindowTest+Rect]::new()
        # Exclude invisible Windows resize borders; compare the visible frame.
        $nativeResult = [FolderTallyWindowTest]::DwmGetWindowAttribute($script:target.MainWindowHandle, 9, [ref]$rect, 16)
        if ($nativeResult -ne 0) { throw 'Could not measure the visible DWM frame.' }
        $dx = [Math]::Abs(($rect.Left + $rect.Right) / 2 - ($work.Left + $work.Right) / 2)
        $dy = [Math]::Abs(($rect.Top + $rect.Bottom) / 2 - ($work.Top + $work.Bottom) / 2)
        if ($dx -gt 2 -or $dy -gt 2) { throw "Window was not centered on $($screen.DeviceName): $dx, $dy" }
        $results.Add(@{ check = 'Monitor reopen'; monitor = $screen.DeviceName; delta = @($dx, $dy); passed = $true })
    }
    $preferences = Get-Content -Raw -LiteralPath (Join-Path $settings 'PradaFit\FolderTally\window.json') | ConvertFrom-Json
    if (@($preferences.PSObject.Properties).Count -ne 3 -or -not $preferences.monitor -or $preferences.theme -ne 'dark' -or $preferences.text_size -ne 100) { throw 'Unexpected preference contents.' }
    Close-TestApp
    if ((Get-FileHash -LiteralPath $isolatedExe).Hash -ne $hash -or (Get-FileHash -LiteralPath $sourceExe).Hash -ne $hash) { throw 'EXE changed during verification.' }
    $result = @{ exe = $sourceExe; sha256 = $hash.ToLowerInvariant(); checks = $results.ToArray(); output = $output; exited_cleanly = $true }
    $result | ConvertTo-Json -Depth 6 | Out-File -LiteralPath (Join-Path $output 'results.json') -Encoding utf8
    $result | ConvertTo-Json -Depth 6
} finally {
    if ($null -ne $script:target -and -not $script:target.HasExited) {
        $null = $script:target.CloseMainWindow()
        $null = $script:target.WaitForExit(2000)
    }
}
