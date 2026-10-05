param([string]$ManifestPath)
$m=Get-Content $ManifestPath -Raw|ConvertFrom-Json
$bucket=$m.bucket
$phase=$m.phase
$work='C:\benchmark\db'
. 'C:\benchmark\common.ps1'
$r=[ordered]@{
    status='STARTING'
    role=$m.role
    instance_id=(Invoke-RestMethod -Headers @{
        'Metadata-Flavor'='Google'
    } -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/id')
    baselines=$m.baselines
}
try{
    foreach($a in $m.assets){
        $null=Get-VerifiedAsset $a
    }
    $cred=Get-Content (Join-Path $work 'credentials.json') -Raw|ConvertFrom-Json
    $mysql=Join-Path $work 'mysql\mysql-8.4.11-winx64\bin\mysql.exe'
    $admin=Write-MySqlOptions 'root' $cred.root_password '127.0.0.1' 't2ti_bench' (Join-Path $work 'observer.cnf')
    $p=Join-Path $work ($phase+'-before.tsv')
    Invoke-MySqlFile (Join-Path $work 'verification.sql') $admin $p 1800
    Publish-EvidenceFile $p ($m.role+'-before.tsv')
    $r.first_binlog=(Invoke-MySqlQuery 'SHOW BINARY LOG STATUS;' $admin).Split("`t")[0].Trim()
    $r.status='READY'
    $p=Join-Path $work ($phase+'-ready.json')
    Write-JsonFile $r $p
    Publish-EvidenceFile $p ($m.role+'-ready.json')
    Initialize-ResourceCounters
    $p=Join-Path $work ($phase+'-metrics.ndjson')
    $writer=[IO.StreamWriter]::new($p,$false,[Text.UTF8Encoding]::new($false))
    try{
        while([datetime]::UtcNow -lt [datetime]::Parse($m.stop_utc)){
            $o=Get-ResourceSample
            $o.instance_id=$r.instance_id
            $o.role=$m.role
            try{
                $o.mysql=Invoke-MySqlQuery "SELECT VARIABLE_NAME,VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME IN ('Threads_connected','Threads_running','Questions','Com_commit','Com_rollback','Innodb_buffer_pool_reads','Innodb_buffer_pool_read_requests','Innodb_row_lock_waits','Innodb_row_lock_time');SELECT 'GROUP_MEMBER',MEMBER_HOST,MEMBER_STATE,MEMBER_ROLE FROM performance_schema.replication_group_members;SELECT 'GROUP_STATS',MEMBER_ID,COUNT_TRANSACTIONS_IN_QUEUE,COUNT_TRANSACTIONS_CHECKED,COUNT_CONFLICTS_DETECTED,COUNT_TRANSACTIONS_ROWS_VALIDATING,COUNT_TRANSACTIONS_REMOTE_IN_APPLIER_QUEUE,COUNT_TRANSACTIONS_REMOTE_APPLIED,COUNT_TRANSACTIONS_LOCAL_PROPOSED,COUNT_TRANSACTIONS_LOCAL_ROLLBACK FROM performance_schema.replication_group_member_stats;SELECT 'BENCH_CONNECTION',HOST,COUNT(*) FROM information_schema.PROCESSLIST WHERE USER='bench' GROUP BY HOST;SELECT 'GTID',@@global.gtid_executed;SELECT 'HOST_CACHE',IP,COALESCE(HOST,'') FROM performance_schema.host_cache;" $admin
            }
            catch{
                $o.mysql_error='QUERY_FAILED'
            }
            $writer.WriteLine(($o|ConvertTo-Json -Depth 20 -Compress))
            $writer.Flush()
            $done=0
            foreach($role in $m.application_roles){
                try{
                    $v=Invoke-RestMethod -Headers @{
                        Authorization=('Bearer '+(Get-AccessToken))
                    } -Uri ('https://storage.googleapis.com/'+$bucket+'/results/'+$phase+'/benchmark/'+$role+'-final.json') -TimeoutSec 3
                    if($v.status -eq 'FAILED'){
                        throw 'APPLICATION_FAILED'
                    }
                    if($v.status -eq 'FINISHED'){
                        $done++
                    }
                }
                catch{
                    if($_.Exception.Message -eq 'APPLICATION_FAILED'){
                        throw
                    }
                }
            }
            if($done -eq @($m.application_roles).Count){
                break
            }
            Start-Sleep -Seconds 1
        }
        if($done -ne @($m.application_roles).Count){
            throw 'APPLICATION_DEADLINE'
        }
    }
    finally{
        $writer.Dispose()
        Publish-EvidenceFile $p ($m.role+'-metrics.ndjson')
    }
    $p=Join-Path $work ($phase+'-after.tsv')
    Invoke-MySqlFile (Join-Path $work 'verification.sql') $admin $p 1800
    Publish-EvidenceFile $p ($m.role+'-after.tsv')
    $null=Invoke-MySqlQuery 'FLUSH BINARY LOGS;' $admin
    $last=(Invoke-MySqlQuery 'SHOW BINARY LOG STATUS;' $admin).Split("`t")[0].Trim()
    $logs=@((Invoke-MySqlQuery 'SHOW BINARY LOGS;' $admin).Split("`n")|ForEach-Object{
        ($_ -split "`t")[0].Trim()
    }|Where-Object{
        $_ -ge $r.first_binlog -and $_ -lt $last
    })
    $binlog=Join-Path $work 'mysql\mysql-8.4.11-winx64\bin\mysqlbinlog.exe'
    $decoded=Join-Path $work ($phase+'-sale-row-events.txt')
    $writer=[IO.StreamWriter]::new($decoded,$false,[Text.UTF8Encoding]::new($false))
    try{
        foreach($log in $logs){
            # Read the decoder incrementally; retain every complete transaction boundary and sales row.
            $si=[Diagnostics.ProcessStartInfo]::new()
            $si.FileName=$binlog
            $si.Arguments=('--base64-output=DECODE-ROWS --verbose --verbose "'+(Join-Path (Join-Path $work 'data') $log)+'"')
            $si.UseShellExecute=$false
            $si.RedirectStandardOutput=$true
            $si.RedirectStandardError=$true
            $si.StandardOutputEncoding=[Text.Encoding]::UTF8
            $proc=[Diagnostics.Process]::new()
            $proc.StartInfo=$si
            $null=$proc.Start()
            $err=$proc.StandardError.ReadToEndAsync()
            $sale=$false
            while(-not $proc.StandardOutput.EndOfStream){
                $line=$proc.StandardOutput.ReadLine()
                if($line -match '^### (INSERT INTO|UPDATE|DELETE FROM) '){
                    $sale=$line -match '`t2ti_bench`\.`venda_(cabecalho|detalhe|comissao)`'
                }
                if(($sale -and $line.StartsWith('###')) -or $line -match 'Xid =|^COMMIT'){
                    $writer.WriteLine($line)
                }
            }
            $proc.WaitForExit()
            if($proc.ExitCode -ne 0){
                throw 'BINLOG_DECODE_FAILED'
            }
            $proc.Dispose()
        }
    }
    finally{
        $writer.Dispose()
    }
    Publish-EvidenceFile $decoded ($m.role+'-sale-row-events.txt')
    $r.status='OBSERVATION_COMPLETE'
    $r.binlogs=$logs
    $r.decoder_sha256=Get-FileSha256 $binlog
}
catch{
    $r.status='FAILED'
    $r.failure=$_.Exception.Message -replace '[a-f0-9]{48}','REDACTED'
}
finally{
    $p=Join-Path $work ($phase+'-observer.json')
    Write-JsonFile $r $p
    Publish-EvidenceFile $p ($m.role+'-observer.json')
}
