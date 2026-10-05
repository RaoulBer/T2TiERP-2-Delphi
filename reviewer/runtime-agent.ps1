$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$meta=@{
    'Metadata-Flavor'='Google'
}
$bucket=Invoke-RestMethod -Headers $meta -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/study-bucket'
$role=Invoke-RestMethod -Headers $meta -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/study-role'
$base='C:\benchmark'
$active=@{
}
$seen=Join-Path $base 'completed-jobs.txt'
while($true){
    try{
        $token=(Invoke-RestMethod -Headers $meta -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token').access_token
        $auth=@{
            Authorization=('Bearer '+$token)
        }
        $job=Invoke-RestMethod -Headers $auth -Uri ('https://storage.googleapis.com/'+$bucket+'/jobs/'+$role+'/latest.json') -TimeoutSec 10
        $done=if(Test-Path $seen){
            @(Get-Content $seen)
        }
        else{
            @()
        }
        if($job.id -notmatch '^[a-f0-9]{32}$'){
            throw 'JOB_ID'
        }
        if($job.id -notin $done -and -not $active.ContainsKey($job.id)){
            if([datetime]::UtcNow -ge [datetime]::Parse($job.deadline_utc)){
                throw 'JOB_EXPIRED'
            }
            $dir=Join-Path $base $job.work_directory
            New-Item $dir -ItemType Directory -Force|Out-Null
            foreach($asset in $job.files){
                if($asset.name -notmatch '^[A-Za-z0-9_.-]+$' -or $asset.sha256 -notmatch '^[a-f0-9]{64}$'){
                    throw 'ASSET_NAME'
                }
                $path=Join-Path $dir $asset.name
                Invoke-WebRequest -UseBasicParsing -Headers $auth -Uri ('https://storage.googleapis.com/'+$bucket+'/'+$asset.object) -OutFile $path -TimeoutSec 600
                if((Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $asset.sha256){
                    throw 'ASSET_HASH'
                }
                if($asset.name -eq 'common.ps1'){
                    Copy-Item $path (Join-Path $base 'common.ps1') -Force
                }
            }
            if($job.script -notmatch '^[A-Za-z0-9_.-]+\.ps1$' -or $job.script -notin @($job.files.name)){
                throw 'SCRIPT_NOT_BOUND'
            }
            $script=Join-Path $dir $job.script
            $manifest=Join-Path $dir 'manifest.json'
            [IO.File]::WriteAllText($manifest,($job.manifest|ConvertTo-Json -Depth 40),[Text.UTF8Encoding]::new($false))
            $p=Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$script+'" -ManifestPath "'+$manifest+'"') -PassThru -RedirectStandardOutput (Join-Path $dir ($job.id+'.stdout')) -RedirectStandardError (Join-Path $dir ($job.id+'.stderr'))
            $active[$job.id]=$p
            # Once launched, a transport restart must not relaunch the same transaction job.
            Add-Content $seen $job.id
        }
    }
    catch{
        [IO.File]::WriteAllText((Join-Path $base 'transport-error.txt'),($_.Exception.Message -replace '[a-f0-9]{48}','REDACTED'))
    }
    foreach($id in @($active.Keys)){
        if($active[$id].HasExited){
            $active.Remove($id)
        }
    }
    Start-Sleep -Seconds 2
}
