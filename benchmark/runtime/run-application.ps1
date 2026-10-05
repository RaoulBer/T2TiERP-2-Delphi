param([string]$ManifestPath)
$m=Get-Content $ManifestPath -Raw|ConvertFrom-Json
$bucket=$m.bucket
$phase=$m.phase
$work='C:\benchmark\app'
$null=New-Item $work -ItemType Directory -Force
. 'C:\benchmark\common.ps1'
$receipt=[ordered]@{
    role=$m.role
    status='STARTING'
    start_utc=[datetime]::UtcNow.ToString('o')
    instance_id=(Invoke-RestMethod -Headers @{
        'Metadata-Flavor'='Google'
    } -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/id')
    cells=@()
}
$driverName=''
$dsnName=''
$workers=@()
$sampler=$null
$router=$null
try{
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object{
        $_.CommandLine -match 'C:\\benchmark\\sampler\.ps1'
    }|ForEach-Object{
        Invoke-CimMethod -InputObject $_ -MethodName Terminate|Out-Null
    }
    foreach($a in $m.assets){
        $p=Get-VerifiedAsset $a
        if($a.name -in @('vc_redist.x86.exe','vc_redist.x64.exe')){
            if((Get-AuthenticodeSignature $p).Status -ne 'Valid'){
                throw 'VC_SIGNATURE'
            }
            $null=Invoke-ChildProcess $p '/install /quiet /norestart' '' 180
        }
    }
    Copy-Item (Join-Path $work 'sampler.ps1') 'C:\benchmark\sampler.ps1' -Force
    $binaryRoot='C:\build-inputs\benchmark-app'
    $null=New-Item $binaryRoot -ItemType Directory -Force
    Copy-Item (Join-Path $work $m.worker_executable),(Join-Path $work 'dbxoodbc.dll'),(Join-Path $work 'dbxadapter.dll') -Destination $binaryRoot -Force
    $creds=Get-Content (Join-Path $work 'credentials.json') -Raw|ConvertFrom-Json
    $readyFile=Join-Path $work 'db-ready.json'
    $ready=$null
    for($i=0;$i -lt 14400;$i++){
        if([datetime]::UtcNow.AddSeconds(610) -ge [datetime]::Parse($m.stop_utc)){
            throw 'READY_DEADLINE'
        }
        try{
            Invoke-WebRequest -UseBasicParsing -Headers @{
                Authorization=('Bearer '+(Get-AccessToken))
            } -Uri ('https://storage.googleapis.com/'+$bucket+'/results/'+$phase+('/benchmark/'+$m.database_role+'-ready.json')) -OutFile $readyFile -TimeoutSec 5
            $ready=Get-Content $readyFile -Raw|ConvertFrom-Json
            if($ready.status -eq 'READY'){
                break
            }
        }
        catch{
        }
        Start-Sleep -Seconds 1
    }
    if(-not $ready -or $ready.status -ne 'READY'){
        throw 'DB_NOT_READY'
    }
    if([string]$ready.instance_id -ne [string]$m.database_instance_id){
        throw 'DB_INSTANCE_BINDING'
    }
    if(-not (Test-Path (Join-Path $work 'odbc\mysql-connector-odbc-noinstall-8.0.46-win32\bin\myodbc-installer.exe'))){
        Expand-Archive (Join-Path $work 'odbc.zip') (Join-Path $work 'odbc') -Force
    }
    $odbc=Join-Path $work 'odbc\mysql-connector-odbc-noinstall-8.0.46-win32'
    $installer=Join-Path $odbc 'bin\myodbc-installer.exe'
    $unicode=Join-Path $odbc 'lib\myodbc8w.dll'
    $setup=Join-Path $odbc 'lib\myodbc8S.dll'
    $driverName='T2TiBenchmark_'+$m.run_id.Substring(0,16)
    $null=Invoke-ChildProcess $installer ('-d -a -n "'+$driverName+'" -t "DRIVER='+$unicode+';SETUP='+$setup+'"') '' 30
    $dsnName='CQ_'+$m.run_id.Substring(0,28)
    Add-OdbcDsn -Name $dsnName -DriverName $driverName -DsnType System -Platform '32-bit' -SetPropertyValue @(('Server='+$m.database_ip),('Port='+$(if($m.route_kind -eq 'direct'){
        3306
    }
    else{
        6447
    })),'Database=t2ti_bench','SSLMode=PREFERRED')
    if($m.route_kind -ne 'direct'){
        if(-not(Test-Path (Join-Path $work 'router'))){
            Expand-Archive (Join-Path $work 'router.zip') (Join-Path $work 'router') -Force
        }
        $routerExe=(Get-ChildItem (Join-Path $work 'router') -Filter mysqlrouter.exe -Recurse|Select-Object -First 1).FullName
    }
    $env:T2TI_MYSQL_USER='bench'
    $env:T2TI_MYSQL_PASSWORD=$creds.app_password
    $env:T2TI_MYSQL_DSN=$dsnName
    $env:T2TI_MYSQL_DATABASE='t2ti_bench'
    $env:T2TI_MYSQL_ISOLATED='YES'
    $env:T2TI_MYSQL_FUNCTIONAL='YES'
    $env:T2TI_OPEN_DBX_SHA256=Get-FileSha256 (Join-Path $work 'dbxoodbc.dll')
    if(Test-Path 'C:\benchmark\app-metrics.ndjson'){
        Move-Item 'C:\benchmark\app-metrics.ndjson' 'C:\benchmark\app-previous-metrics.ndjson' -Force
    }
    $sampler=Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File C:\benchmark\sampler.ps1' -PassThru -RedirectStandardOutput (Join-Path $work 'sampler.stdout') -RedirectStandardError (Join-Path $work 'sampler.stderr')
    foreach($cell in $m.cells){
        if($m.route_kind -ne 'direct'){
            if($router -and -not $router.HasExited){
                $router.Kill()
                $router.WaitForExit()
            }
            $targets=if($m.route_kind -eq 'read'){
                @($m.read_target_ips|Select-Object -First ([int]$cell.read_targets))
            }
            else{
                @($m.write_target_ips|Select-Object -First ([int]$cell.write_targets))
            }
            $offset=[int]$m.app_index % $targets.Count
            $dest=@()
            for($ri=0;$ri -lt $targets.Count;$ri++){
                $dest+=($targets[($ri+$offset)%$targets.Count]+':3306')
            }
            $rc=Join-Path $work ($cell.run_id+'-router.conf')
            $config="[DEFAULT]`nlogging_folder=$($work.Replace('\','/'))`nruntime_folder=$($work.Replace('\','/'))`n[logger]`nlevel=INFO`n[routing:t2ti_explicit_write]`nbind_address=127.0.0.1`nbind_port=6447`ndestinations=$($dest -join ',')`nrouting_strategy=round-robin`nprotocol=classic`nconnect_timeout=30`nclient_connect_timeout=120`n"
            [IO.File]::WriteAllText($rc,$config,[Text.UTF8Encoding]::new($false))
            $router=Start-Process $routerExe -ArgumentList ('-c "'+$rc+'"') -PassThru -RedirectStandardOutput (Join-Path $work ($cell.run_id+'-router.stdout')) -RedirectStandardError (Join-Path $work ($cell.run_id+'-router.stderr'))
            Start-Sleep -Seconds 2
            if($router.HasExited){
                throw 'ROUTER_START_FAILED'
            }
            Publish-EvidenceFile $rc ($cell.run_id+'-'+$m.role+'-router.conf')
        }
        if([datetime]::UtcNow.AddSeconds(610) -ge [datetime]::Parse($m.stop_utc)){
            break
        }
        if($m.synchronized){
            $hostReady=[ordered]@{
                status='HOST_READY'
                run_id=$cell.run_id
                role=$m.role
                instance_id=$receipt.instance_id
                worker_offset=$m.worker_offset
                workers=$cell.workers
                utc=[datetime]::UtcNow.ToString('o')
            }
            $readyPath=Join-Path $work ($cell.run_id+'-'+$m.role+'-ready.json')
            Write-JsonFile $hostReady $readyPath
            Publish-EvidenceFile $readyPath (Split-Path $readyPath -Leaf)
            $barrier=$null
            while([datetime]::UtcNow.AddSeconds(610) -lt [datetime]::Parse($m.stop_utc)){
                try{
                    $barrier=Invoke-RestMethod -Headers @{
                        Authorization=('Bearer '+(Get-AccessToken))
                    } -Uri ('https://storage.googleapis.com/'+$bucket+'/results/'+$phase+'/benchmark/'+$cell.run_id+'-start.json') -TimeoutSec 5
                    if($barrier.run_id -eq $cell.run_id -and $barrier.status -eq 'START'){
                        break
                    }
                }
                catch{
                }
                Start-Sleep -Seconds 1
            }
            if(-not $barrier){
                throw 'BARRIER_NOT_ARMED'
            }
            $start=[datetime]::Parse($barrier.start_utc)
            if([datetime]::UtcNow -gt $start.AddSeconds(3)){
                throw 'BARRIER_MISSED'
            }
            while([datetime]::UtcNow -lt $start){
                Start-Sleep -Milliseconds 50
            }
        }
        $cellId=$cell.run_id
        $cfg=@{
            run_id=$cellId
            worker_id=0
            instance_id=[string]$receipt.instance_id
            source_manifest_sha256=$m.source_manifest_sha256
            exe_sha256=(Get-FileSha256 (Join-Path $work $m.worker_executable))
            database='t2ti_bench'
            sale_contract_sha256='2775e3fbcefcb324d4c529c625bb04d44da2434bf4ed7e5988676157c12847e3'
            functional_receipt_path=(Join-Path $work 'parent-qualification-receipt.json')
            functional_receipt_sha256=(Get-FileSha256 (Join-Path $work 'parent-qualification-receipt.json'))
            deadline_utc=$m.stop_utc
            operation=$cell.operation
            maximum_attempts=100000
            baseline_header_max_id=$ready.baselines.header
            baseline_detail_max_id=$ready.baselines.detail
            baseline_commission_max_id=$ready.baselines.commission
            customer_id=1
            seller_id=1
            invoice_type_id=1
            payment_terms_id=1
            transporter_id=1
            product_ids=@(1,1,1,1,1)
        }
        $exeName=$m.worker_executable
        if($m.shared_pool_size){
            $cfg.shared_pool_size=[int]$m.shared_pool_size
        }
        $measurementPath=Join-Path $work ($cellId+'-measurement-start.json')
        $cfg.measurement_barrier_path=$measurementPath
        $measurementArmed=$false
        $measurementReadyUploaded=$false
        $workers=@()
        $record=[ordered]@{
            role=$m.role
            worker_offset=$m.worker_offset
            instance_id=$receipt.instance_id
            run_id=$cellId
            operation=$cell.operation
            worker_count=$cell.workers
            start_utc=[datetime]::UtcNow.ToString('o')
            workers=@()
        }
        for($i=0;$i -lt $cell.workers;$i++){
            $workerId=$m.worker_offset+$i
            $cfg.worker_id=$workerId
            $cfg.measurement_barrier_path=$measurementPath+'-'+$workerId
            if($m.customer_id){
                $cfg.customer_id=$m.customer_id
            }
            $config=Join-Path $work ($cellId+'-'+$workerId+'.json')
            Write-JsonFile $cfg $config
            $output=Join-Path $work ($cellId+'-'+$workerId+'.ndjson')
            $errorFile=Join-Path $work ($cellId+'-'+$workerId+'.stderr')
            $command='""'+(Join-Path $binaryRoot $exeName)+'" '+$cellId+' "'+$config+'" 1>"'+$output+'" 2>"'+$errorFile+'""'
            $p=Start-Process ($env:SystemRoot+'\System32\cmd.exe') -ArgumentList ('/d /s /c '+$command) -NoNewWindow -PassThru
            $null=$p.Handle
            if($m.launch_stagger_ms){
                Start-Sleep -Milliseconds ([int]$m.launch_stagger_ms)
            }
            $workers+=@{
                p=$p
                output=$output
                stderr=$errorFile
                pid=$p.Id
                creation_utc=$p.StartTime.ToUniversalTime().ToString('o')
            }
        }
        $watch=[Diagnostics.Stopwatch]::StartNew()
        while(@($workers|Where-Object{
            -not $_.p.HasExited
        }).Count -gt 0){
            if($watch.Elapsed.TotalSeconds -gt 600){
                throw 'WORKER_TIMEOUT'
            }
            if($m.fail_fast -and @($workers|Where-Object{
                $_.p.HasExited -and $_.p.ExitCode -ne 0
            }).Count -gt 0){
                throw 'NATIVE_WORKER_FAILED_DURING_CELL'
            }
            if($m.synchronized -and -not $measurementArmed){
                if(@($workers|Where-Object{
                    $_.p.HasExited
                }).Count -gt 0){
                    throw 'STARTUP_WORKER_FAILED_BEFORE_MEASUREMENT'
                }
                $allReady=$true
                for($k=0;$k -lt $cell.workers;$k++){
                    $readyPath=$measurementPath+'-'+($m.worker_offset+$k)+'.'+($m.worker_offset+$k)+'.ready.json'
                    try{
                        $nativeReady=Get-Content $readyPath -Raw|ConvertFrom-Json
                        if($nativeReady.status -ne 'WARMUP_COMPLETE' -or $nativeReady.run_id -ne $cellId -or [string]$nativeReady.instance_id -ne [string]$receipt.instance_id){
                            $allReady=$false
                        }
                    }
                    catch{
                        $allReady=$false
                    }
                }
                if($allReady){
                    if($m.synchronized){
                        if(-not $measurementReadyUploaded){
                            $mr=@{
                                status='HOST_READY'
                                run_id=$cellId
                                role=$m.role
                                instance_id=$receipt.instance_id
                                worker_offset=$m.worker_offset
                                workers=$cell.workers
                                utc=[datetime]::UtcNow.ToString('o')
                            }
                            $mrFile=Join-Path $work ($cellId+'-'+$m.role+'-measurement-ready.json')
                            Write-JsonFile $mr $mrFile
                            Publish-EvidenceFile $mrFile (Split-Path $mrFile -Leaf)
                            $measurementReadyUploaded=$true
                        }
                        $next=$null
                        try{
                            $next=Invoke-RestMethod -Headers @{
                                Authorization=('Bearer '+(Get-AccessToken))
                            } -Uri ('https://storage.googleapis.com/'+$bucket+'/results/'+$phase+'/benchmark/'+$cellId+'-measurement-start.json') -TimeoutSec 3
                        }
                        catch{
                        }
                    }
                    else{
                        $next=@{
                            status='START'
                            run_id=$cellId
                            start_utc=[datetime]::UtcNow.AddSeconds(10).ToString('o')
                        }
                    }
                    if($next){
                        if($next.status -ne 'START' -or $next.run_id -ne $cellId){
                            throw 'MEASUREMENT_BARRIER_BINDING'
                        }
                        for($bi=0;$bi -lt $cell.workers;$bi++){
                            $bp=$measurementPath+'-'+($m.worker_offset+$bi)
                            Write-JsonFile $next ($bp+'.tmp')
                            [IO.File]::Move(($bp+'.tmp'),$bp)
                        }
                        $measurementArmed=$true
                    }
                }
            }
            Start-Sleep -Milliseconds 200
        }
        foreach($w in $workers){
            $w.p.Refresh()
            $first=Get-Content $w.output -TotalCount 1|ConvertFrom-Json
            $record.workers+=@{
                pid=$first.identity.pid
                native_creation_utc=$first.identity.creation_utc
                supervisor_pid=$w.pid
                creation_utc=$w.creation_utc
                exit_code=$w.p.ExitCode
                output_sha256=(Get-FileSha256 $w.output)
                stderr_bytes=(Get-Item $w.stderr).Length
            }
            Publish-EvidenceFile $w.output (Split-Path $w.output -Leaf)
            $w.exported=$true
            if((Get-Item $w.stderr).Length -gt 0){
                $record.status='WORKER_STDERR_PRESENT'
            }
        }
        $record.finish_utc=[datetime]::UtcNow.ToString('o')
        $receipt.cells+=@($record)
        Write-JsonFile $record (Join-Path $work ($cellId+'-'+$m.role+'-receipt.json'))
        Publish-EvidenceFile (Join-Path $work ($cellId+'-'+$m.role+'-receipt.json')) ($cellId+'-'+$m.role+'-receipt.json')
        if(@($record.workers|Where-Object{
            $_.exit_code -ne 0
        }).Count -gt 0){
            throw 'NATIVE_WORKER_FAILED'
        }
    }
    $receipt.status='FINISHED'
}
catch{
    $receipt.status='FAILED'
    $receipt.failure=$_.Exception.Message -replace '[a-f0-9]{48}','REDACTED'
}
finally{
    if($receipt.status -ne 'FINISHED'){
        Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($m.worker_executable)) -ErrorAction SilentlyContinue|Stop-Process -Force
    }
    foreach($w in $workers){
        if(-not $w.p.HasExited){
            $w.p.Kill()
            $w.p.WaitForExit()
        }
        if(-not $w.exported -and (Test-Path $w.output)){
            try{
                Publish-EvidenceFile $w.output (Split-Path $w.output -Leaf)
            }
            catch{
                $receipt.partial_export_failure='UPLOAD_FAILED'
            }
        }
    }
    if($router -and -not $router.HasExited){
        $router.Kill()
        $router.WaitForExit()
    }
    if($sampler -and -not $sampler.HasExited){
        $sampler.Kill()
        $sampler.WaitForExit()
    }
    if($dsnName){
        Remove-OdbcDsn -Name $dsnName -DsnType System -Platform '32-bit' -ErrorAction SilentlyContinue
    }
    if($driverName){
        try{
            $null=Invoke-ChildProcess $installer ('-d -r -n "'+$driverName+'"') '' 30
        }
        catch{
        }
    }
    $env:T2TI_MYSQL_PASSWORD=$null
    Remove-Item (Join-Path $work 'credentials.json') -Force -ErrorAction SilentlyContinue
    $receipt.finished_utc=[datetime]::UtcNow.ToString('o')
    Write-JsonFile $receipt (Join-Path $work 'final.json')
    Publish-EvidenceFile (Join-Path $work 'final.json') ($m.role+'-final.json')
    if(Test-Path 'C:\benchmark\app-metrics.ndjson'){
        Publish-EvidenceFile 'C:\benchmark\app-metrics.ndjson' ($m.role+'-metrics.ndjson')
    }
}
