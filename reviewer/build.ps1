param(
[Parameter(Mandatory=$true)][string]$RsVars,
[string]$OutputDirectory = "$PSScriptRoot\inputs\native"
)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if(-not(Test-Path $RsVars)){
    throw 'A licensed Delphi Windows installation and rsvars.bat are required'
}
New-Item $OutputDirectory -ItemType Directory -Force|Out-Null
$OutputDirectory=(Resolve-Path $OutputDirectory).Path
$workspace=Join-Path $OutputDirectory 'build-source'
New-Item $workspace -ItemType Directory -Force|Out-Null
Copy-Item "$root\benchmark\source\*" $workspace -Recurse -Force
Copy-Item "$root\benchmark\driver-source\*" $workspace -Recurse -Force
# Load the official SDK environment without storing account or activation information.
$vars=& cmd.exe /d /s /c ('""'+$RsVars+'" >nul && set"')
foreach($entry in $vars){
    if($entry -match '^([^=]+)=(.*)$'){
        [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2],'Process')
    }
}
$driver=Join-Path $workspace 'benchmark\mysql-open-driver-probe'
$dcu=Join-Path $OutputDirectory 'driver-dcu'
New-Item $dcu -ItemType Directory -Force|Out-Null
Push-Location "$driver\generated-compat"
try{
    & "$env:BDS\bin\dcc32.exe" '-B' '-NSSystem;System.Win;Winapi;Data;Datasnap' '-ADBXJSON=System.JSON' "-E$OutputDirectory" "-N0$dcu" "-U$env:BDS\lib\win32\release;$driver\generated-compat;$driver\vendor\source\packages;$driver\vendor\source\driver" "-I$driver\vendor\source\driver" 'dbxoodbc.dpr' *> "$OutputDirectory\driver-build.log"
    if($LASTEXITCODE -ne 0){
        throw 'Driver compilation failed; see driver-build.log'
    }
}
finally{
    Pop-Location
}
$projects=@{
    'unified-mysql-performance'='SalePerformance'
    'unified-mysql-synchronized-performance'='SaleSynchronizedPerformance'
    'unified-mysql-inquiry-performance'='SaleInquiryPerformance'
    'unified-mysql-conflict-performance'='SaleConflictPerformance'
    'unified-mysql-shared-contention'='SaleSharedContention'
    'unified-mysql-worker'='SaleQualificationUiCodesV2'
}
$artifacts=@()
foreach($folder in ($projects.Keys|Sort-Object)){
    $name=$projects[$folder]
    $project=Join-Path $workspace ("benchmark\$folder\$name.dproj")
    & msbuild.exe $project '/t:Build' '/p:Config=Debug;Platform=Win32' '/v:minimal' *> "$OutputDirectory\$name-build.log"
    if($LASTEXITCODE -ne 0){
        throw "Compilation failed: $name; see the build log"
    }
    $binary=Get-ChildItem (Split-Path $project) -Filter "$name.exe" -Recurse|Sort-Object LastWriteTime -Descending|Select-Object -First 1
    if(-not $binary){
        throw "Missing compiler output: $name"
    }
    Copy-Item $binary.FullName (Join-Path $OutputDirectory "$name.exe") -Force
    $artifacts+=@{
        name="$name.exe"
        project=$folder
        sha256=(Get-FileHash $binary.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
& msbuild.exe (Join-Path $workspace 'benchmark\unified-mysql-synchronized-performance\SaleInquirySynchronizedPerformance.dproj') '/t:Build' '/p:Config=Debug;Platform=Win32' '/v:minimal' *> "$OutputDirectory\SaleInquirySynchronizedPerformance-build.log"
if($LASTEXITCODE -ne 0){
    throw 'Synchronized inquiry compilation failed'
}
$binary=Get-ChildItem (Join-Path $workspace 'benchmark\unified-mysql-synchronized-performance') -Filter 'SaleInquirySynchronizedPerformance.exe' -Recurse|Sort-Object LastWriteTime -Descending|Select-Object -First 1
if(-not $binary){
    throw 'Missing synchronized inquiry executable'
}
Copy-Item $binary.FullName (Join-Path $OutputDirectory 'SaleInquirySynchronizedPerformance.exe') -Force
$artifacts+=@{
    name='SaleInquirySynchronizedPerformance.exe'
    project='unified-mysql-synchronized-performance'
    sha256=(Get-FileHash $binary.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$adapter=Join-Path $env:BDS 'bin\dbxadapter.dll'
if(-not(Test-Path $adapter)){
    throw 'Official SDK Win32 dbxadapter.dll is required'
}
Copy-Item $adapter (Join-Path $OutputDirectory 'dbxadapter.dll') -Force
foreach($name in @('dbxadapter.dll','dbxoodbc.dll')){
    $artifacts+=@{
        name=$name
        sha256=(Get-FileHash (Join-Path $OutputDirectory $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$receipt=@{
    status='COMPILED_PENDING_RUNTIME_VERIFICATION'
    platform='Win32'
    configuration='Debug'
    compiler=(Get-Item "$env:BDS\bin\dcc32.exe").VersionInfo.FileVersion
    source_manifest_sha256=(Get-FileHash "$root\benchmark\source-manifest.json" -Algorithm SHA256).Hash.ToLowerInvariant()
    artifacts=$artifacts
}
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'build-receipt.json'),($receipt|ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
