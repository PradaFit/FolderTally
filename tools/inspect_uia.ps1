param([Parameter(Mandatory)][int]$TargetProcessId, [string]$OutputFile)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$targetProcess = Get-Process -Id $TargetProcessId
$targetProcess.Refresh()
if ($targetProcess.MainWindowHandle -eq 0) { throw 'Target has no main window.' }
$element = [System.Windows.Automation.AutomationElement]::FromHandle($targetProcess.MainWindowHandle)
$nodes = $element.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$result = foreach ($node in $nodes) {
    $current = $node.Current
    [pscustomobject]@{
        Name = $current.Name
        Id = $current.AutomationId
        Type = $current.ControlType.ProgrammaticName
        Focusable = $current.IsKeyboardFocusable
        Enabled = $current.IsEnabled
        Patterns = @($node.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
    }
}
$json = ConvertTo-Json -InputObject @($result) -Depth 5
if ($OutputFile) { $json | Out-File -LiteralPath $OutputFile -Encoding utf8 }
$json
