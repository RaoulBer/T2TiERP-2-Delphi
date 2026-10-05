$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
function Get-FileSha256($p){
    (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-AccessToken{
    (Invoke-RestMethod -Headers @{
        'Metadata-Flavor'='Google'
    } -Uri 'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token').access_token
}
function Get-VerifiedAsset($a){
    $p=Join-Path $work $a.name
    if((Test-Path -LiteralPath $p) -and (Get-FileSha256 $p) -ceq $a.sha256){
        return $p
    }
    if($a.download_uri){
        if($a.download_uri -notmatch '^https://cdn\.mysql\.com/Downloads/(MySQL-8\.4/mysql-8\.4\.11-winx64|MySQL-Shell/mysql-shell-8\.4\.10-windows-x86-64bit|MySQL-Router/mysql-router-8\.4\.10-winx64|Connector-ODBC/8\.0/mysql-connector-odbc-noinstall-8\.0\.46-win32)\.zip$'){
            throw 'OFFICIAL_DOWNLOAD_URI'
        }
        Invoke-WebRequest -UseBasicParsing -Uri $a.download_uri -OutFile $p -TimeoutSec 600
    }
    else{
        Invoke-WebRequest -UseBasicParsing -Headers @{
            Authorization=('Bearer '+(Get-AccessToken))
        } -Uri ('https://storage.googleapis.com/'+$bucket+'/'+$a.object) -OutFile $p -TimeoutSec 120
    }
    if((Get-FileSha256 $p) -cne $a.sha256){
        throw 'ASSET_HASH'
    }
    return $p
}
function Publish-EvidenceFile($p,$name){
    $uri='https://storage.googleapis.com/upload/storage/v1/b/'+$bucket+'/o?uploadType=media&ifGenerationMatch=0&name='+[uri]::EscapeDataString('results/'+$phase+'/benchmark/'+$name)
    Invoke-RestMethod -Method Post -Headers @{
        Authorization=('Bearer '+(Get-AccessToken))
    } -Uri $uri -ContentType application/octet-stream -InFile $p -TimeoutSec 120|Out-Null
}
function Write-JsonFile($o,$p){
    [IO.File]::WriteAllText($p,($o|ConvertTo-Json -Depth 30),[Text.UTF8Encoding]::new($false))
}
function Invoke-ChildProcess($exe,$commandArguments,$inputText='',$timeout=180){
    $si=[Diagnostics.ProcessStartInfo]::new()
    $si.FileName=$exe
    $si.Arguments=$commandArguments
    $si.UseShellExecute=$false
    $si.CreateNoWindow=$true
    $si.RedirectStandardOutput=$true
    $si.RedirectStandardError=$true
    $si.RedirectStandardInput=$true
    $si.StandardOutputEncoding=[Text.Encoding]::UTF8
    $si.StandardErrorEncoding=[Text.Encoding]::UTF8
    $p=[Diagnostics.Process]::new()
    $p.StartInfo=$si
    $null=$p.Start()
    $out=$p.StandardOutput.ReadToEndAsync()
    $err=$p.StandardError.ReadToEndAsync()
    try{
        if($inputText){
            $w=$p.StandardInput.WriteAsync($inputText)
            if(-not $w.Wait($timeout*1000)){
                throw 'INPUT_TIMEOUT'
            }
        }
        $p.StandardInput.Close()
        if(-not $p.WaitForExit($timeout*1000)){
            throw 'PROCESS_TIMEOUT'
        }
        $stdout=$out.Result
        $stderr=$err.Result
        $script:lastChildError=$stderr
        if($p.ExitCode -ne 0){
            $code=[regex]::Match($stderr,'ERROR\s+\d+').Value
            throw ('CHILD_EXIT_'+$p.ExitCode+'_'+$code)
        }
        return $stdout
    }
    catch{
        if($p.HasExited){
            $script:lastChildError=$err.Result
        }
        throw
    }
    finally{
        if(-not $p.HasExited){
            $p.Kill()
            $p.WaitForExit()
        }
        $p.Dispose()
    }
}
function Invoke-MySqlQuery($sql,$options){
    Invoke-ChildProcess $mysql ('--defaults-extra-file="'+$options+'" --batch --raw --skip-column-names --default-character-set=utf8mb4') $sql 180
}
function Write-MySqlOptions($user,$pw,$hostName,$database,$p){
    [IO.File]::WriteAllText($p,"[client]`nuser=$user`npassword=$pw`nhost=$hostName`nport=3306`nprotocol=TCP`nconnect-timeout=5`ndatabase=$database`n",[Text.UTF8Encoding]::new($false))
    return $p
}
function Initialize-ResourceCounters{
    $script:cts=@{
    }
    foreach($c in @(@('cpu','Processor','% Processor Time','_Total'),@('available_mb','Memory','Available MBytes',''),@('disk_read_bytes_sec','PhysicalDisk','Disk Read Bytes/sec','_Total'),@('disk_write_bytes_sec','PhysicalDisk','Disk Write Bytes/sec','_Total'),@('disk_queue','PhysicalDisk','Current Disk Queue Length','_Total'),@('disk_read_latency_seconds','PhysicalDisk','Avg. Disk sec/Read','_Total'),@('disk_write_latency_seconds','PhysicalDisk','Avg. Disk sec/Write','_Total'))){
        try{
            $v=[Diagnostics.PerformanceCounter]::new($c[1],$c[2],$c[3])
            $null=$v.NextValue()
            $script:cts[$c[0]]=$v
        }
        catch{
        }
    }
    $script:nets=@{
    }
    try{
        foreach($n in ([Diagnostics.PerformanceCounterCategory]::new('Network Interface')).GetInstanceNames()){
            $v=[Diagnostics.PerformanceCounter]::new('Network Interface','Bytes Total/sec',$n)
            $null=$v.NextValue()
            $script:nets[$n]=$v
        }
    }
    catch{
    }
}
function Get-ResourceSample{
    $o=[ordered]@{
        utc=[datetime]::UtcNow.ToString('o')
        qpc=[Diagnostics.Stopwatch]::GetTimestamp()
        qpc_frequency=[Diagnostics.Stopwatch]::Frequency
    }
    foreach($k in $script:cts.Keys){
        try{
            $o[$k]=$script:cts[$k].NextValue()
        }
        catch{
            $o[$k]=$null
        }
    }
    $o.network_bytes_sec=@{
    }
    foreach($k in $script:nets.Keys){
        try{
            $o.network_bytes_sec[$k]=$script:nets[$k].NextValue()
        }
        catch{
            $o.network_bytes_sec[$k]=$null
        }
    }
    $o.processes=@(Get-Process -Name SalePerformance,SaleSynchronizedPerformance,SaleInquirySynchronizedPerformance,CustomerPerformance,mysqld,mysqlrouter -ErrorAction SilentlyContinue|ForEach-Object{
        @{
            pid=$_.Id
            creation_utc=$_.StartTime.ToUniversalTime().ToString('o')
            cpu_seconds=$_.TotalProcessorTime.TotalSeconds
            working_set=$_.WorkingSet64
            private_bytes=$_.PrivateMemorySize64
            threads=$_.Threads.Count
            handles=$_.HandleCount
        }
    })
    return $o
}
function Invoke-MySqlFile($inputPath,$options,$outputPath,$timeout){
    $si=[Diagnostics.ProcessStartInfo]::new()
    $si.FileName=$mysql
    $si.Arguments=('--defaults-extra-file="'+$options+'" --batch --raw --quick --skip-column-names --default-character-set=utf8mb4')
    $si.UseShellExecute=$false
    $si.CreateNoWindow=$true
    $si.RedirectStandardInput=$true
    $si.RedirectStandardOutput=$true
    $si.RedirectStandardError=$true
    $p=[Diagnostics.Process]::new()
    $p.StartInfo=$si
    $inputFile=[IO.File]::OpenRead($inputPath)
    $outputFile=[IO.File]::Create($outputPath)
    $clock=[Diagnostics.Stopwatch]::StartNew()
    try{
        $null=$p.Start()
        $err=$p.StandardError.ReadToEndAsync()
        $out=$p.StandardOutput.BaseStream.CopyToAsync($outputFile)
        $write=$inputFile.CopyToAsync($p.StandardInput.BaseStream)
        if(-not $write.Wait($timeout*1000)){
            throw 'SQL_INPUT_TIMEOUT'
        }
        $p.StandardInput.Close()
        $remaining=[math]::Max(1,$timeout*1000-$clock.ElapsedMilliseconds)
        if(-not $p.WaitForExit([int]$remaining)){
            throw 'SQL_PROCESS_TIMEOUT'
        }
        if(-not $out.Wait([int][math]::Max(1,$timeout*1000-$clock.ElapsedMilliseconds))){
            throw 'SQL_OUTPUT_TIMEOUT'
        }
        $script:lastChildError=$err.Result
        if($p.ExitCode -ne 0){
            throw ('SQL_CHILD_EXIT_'+$p.ExitCode)
        }
    }
    finally{
        if($p.Id -and -not $p.HasExited){
            $p.Kill()
            $p.WaitForExit()
        }
        $inputFile.Dispose()
        $outputFile.Dispose()
        $p.Dispose()
    }
}
