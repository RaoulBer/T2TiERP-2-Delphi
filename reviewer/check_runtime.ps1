$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$paths = @(Get-ChildItem "$root\benchmark\runtime" -Filter '*.ps1') + @(Get-ChildItem $PSScriptRoot -Filter '*.ps1')
foreach ($path in $paths) {
    $tokens = $null
    $errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($path.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) {
        throw ($path.Name + ': ' + ($errors.Message -join ', '))
    }
}
@{ status = 'PASS'; parsed_scripts = $paths.Count; cloud_operations = 0 } | ConvertTo-Json
