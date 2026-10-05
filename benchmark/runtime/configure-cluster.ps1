param([string]$ManifestPath)
$m=Get-Content $ManifestPath -Raw|ConvertFrom-Json
$bucket=$m.bucket
$phase=$m.phase
$work='C:\benchmark\db'
. 'C:\benchmark\common.ps1'
$r=@{
    status='STARTING'
}
try{
    foreach($a in $m.assets){
        $null=Get-VerifiedAsset $a
    }
    Write-JsonFile $m.cluster_control (Join-Path $work 'cluster-control.json')
    $exe=(Get-ChildItem (Join-Path $work 'shell') -Filter mysqlsh.exe -Recurse|Select-Object -First 1).FullName
    $out=Invoke-ChildProcess $exe ('--js --file "'+(Join-Path $work 'cluster.js')+'"') '' 1800
    $p=Join-Path $work 'cluster-status.txt'
    [IO.File]::WriteAllText($p,$out,[Text.UTF8Encoding]::new($false))
    Publish-EvidenceFile $p ('cluster-'+$m.cluster_control.action+'-status.txt')
    $r.status='CLUSTER_CONFIGURED'
}
catch{
    $r.status='FAILED'
    $r.failure=$_.Exception.Message -replace '[a-f0-9]{48}','REDACTED'
}
finally{
    $p=Join-Path $work 'cluster-receipt.json'
    Write-JsonFile $r $p
    Publish-EvidenceFile $p ('cluster-'+$m.cluster_control.action+'.json')
}
