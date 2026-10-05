$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$base = 'C:\benchmark'
New-Item $base -ItemType Directory -Force | Out-Null
$meta = @{
    'Metadata-Flavor' = 'Google'
}
$bucket = Invoke-RestMethod -Headers $meta -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/study-bucket'
$role = Invoke-RestMethod -Headers $meta -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/study-role'
# A persistent SYSTEM task keeps transport independent of an RDP session.
$agentPath = Join-Path $base 'agent.ps1'
$scriptText = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${agent_script}'))
[IO.File]::WriteAllText($agentPath,$scriptText,[Text.UTF8Encoding]::new($false))
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "'+$agentPath+'"')
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([timespan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'SalesStudyTransport' -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'SalesStudyTransport'
