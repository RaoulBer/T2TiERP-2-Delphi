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
}
try{
    if([string]$r.instance_id -ne [string]$m.instance_id){
        throw 'INSTANCE_BINDING'
    }
    foreach($a in $m.assets){
        $p=Get-VerifiedAsset $a
        if($a.name -eq 'vc_redist.x64.exe'){
            if((Get-AuthenticodeSignature $p).Status -ne 'Valid'){
                throw 'VC_SIGNATURE'
            }
            $null=Invoke-ChildProcess $p '/install /quiet /norestart' '' 180
        }
    }
    if(Test-Path (Join-Path $work 'data')){
        throw 'DATA_DIRECTORY_EXISTS_USE_FRESH_TOPOLOGY'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $work 'mysql.zip'),(Join-Path $work 'mysql'))
    if($m.cluster){
        [IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $work 'shell.zip'),(Join-Path $work 'shell'))
    }
    $base=Join-Path $work 'mysql\mysql-8.4.11-winx64'
    $mysql=Join-Path $base 'bin\mysql.exe'
    $mysqld=Join-Path $base 'bin\mysqld.exe'
    $data=Join-Path $work 'data'
    New-Item $data -ItemType Directory|Out-Null
    $cnf=Join-Path $work 'server.cnf'
    $text="[mysqld]`nbasedir=$($base.Replace('\','/'))`ndatadir=$($data.Replace('\','/'))`nbind-address=0.0.0.0`nport=3306`nreport_host=$($m.ip)`nserver_id=$($m.server_id)`nlower_case_table_names=1`nmysqlx=OFF`nperformance_schema=ON`nlog-bin=study-bin`nbinlog_format=ROW`nbinlog_row_image=FULL`nlog_replica_updates=ON`ngtid_mode=ON`nenforce_gtid_consistency=ON`ninnodb_buffer_pool_size=2147483648`nmax_allowed_packet=128M`nsql-mode=STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION,ONLY_FULL_GROUP_BY,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO`n"
    [IO.File]::WriteAllText($cnf,$text,[Text.UTF8Encoding]::new($false))
    $null=Invoke-ChildProcess $mysqld ('--defaults-file="'+$cnf+'" --initialize-insecure') '' 300
    $null=Invoke-ChildProcess $mysqld ('--install T2TiMySQL --defaults-file="'+$cnf+'"') '' 60
    Start-Service T2TiMySQL
    $empty=Write-MySqlOptions 'root' '' '127.0.0.1' 'mysql' (Join-Path $work 'initial.cnf')
    $up=$false
    for($i=0;$i -lt 120;$i++){
        try{
            if((Invoke-MySqlQuery 'SELECT 1;' $empty).Trim() -eq '1'){
                $up=$true
                break
            }
        }
        catch{
        }
        Start-Sleep -Seconds 1
    }
    if(-not $up){
        throw 'MYSQL_START'
    }
    $cred=Get-Content (Join-Path $work 'credentials.json') -Raw|ConvertFrom-Json
    $pw=$cred.root_password
    $ap=$cred.app_password
    if($pw -notmatch '^[a-f0-9]{48}$' -or $ap -notmatch '^[a-f0-9]{48}$'){
        throw 'CREDENTIAL_FORMAT'
    }
    if($m.mysql_host_pattern -notmatch '^\d+\.\d+\.\d+\.%$'){
        throw 'PRIVATE_SUBNET_PATTERN'
    }
    $h=$m.mysql_host_pattern
    $null=Invoke-MySqlQuery "ALTER USER 'root'@'localhost' IDENTIFIED BY '$pw';CREATE USER 'clusteradmin'@'$h' IDENTIFIED BY '$pw';GRANT ALL PRIVILEGES ON *.* TO 'clusteradmin'@'$h' WITH GRANT OPTION;CREATE USER 'bench'@'$h' IDENTIFIED BY '$ap';GRANT SELECT,INSERT,UPDATE,DELETE ON t2ti_bench.* TO 'bench'@'$h';" $empty
    Remove-Item (Join-Path $work 'initial.cnf') -Force
    $admin=Write-MySqlOptions 'root' $pw '127.0.0.1' 'mysql' (Join-Path $work 'admin.cnf')
    if($m.import_fixture){
        $null=Invoke-MySqlQuery 'CREATE DATABASE t2ti_bench CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;' $admin
        $admin=Write-MySqlOptions 'root' $pw '127.0.0.1' 't2ti_bench' (Join-Path $work 'admin.cnf')
        Invoke-MySqlFile (Join-Path $work 'schema.sql') $admin (Join-Path $work 'schema.stdout') 300
        Invoke-MySqlFile (Join-Path $work 'views.sql') $admin (Join-Path $work 'views.stdout') 300
        $inputFile=[IO.File]::OpenRead((Join-Path $work 'dataset.sql.gz'))
        $gzip=[IO.Compression.GzipStream]::new($inputFile,[IO.Compression.CompressionMode]::Decompress)
        $outputFile=[IO.File]::Create((Join-Path $work 'dataset.sql'))
        try{
            $gzip.CopyTo($outputFile)
        }
        finally{
            $outputFile.Dispose()
            $gzip.Dispose()
            $inputFile.Dispose()
        }
        if((Get-FileSha256 (Join-Path $work 'dataset.sql')) -cne $m.dataset_sql_sha256){
            throw 'DATASET_HASH'
        }
        Invoke-MySqlFile (Join-Path $work 'dataset.sql') $admin (Join-Path $work 'dataset.stdout') 1800
        if([int](Invoke-MySqlQuery "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='t2ti_bench' AND table_type='BASE TABLE';" $admin).Trim() -ne 40){
            throw 'TABLE_SCOPE'
        }
        $p=Join-Path $work 'initial-capture.tsv'
        Invoke-MySqlFile (Join-Path $work 'verification.sql') $admin $p 1800
        Publish-EvidenceFile $p ($m.role+'-initial-capture.tsv')
    }
    New-NetFirewallRule -DisplayName 'SalesStudyDatabase' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3306,33061 -RemoteAddress $m.private_cidr|Out-Null
    $r.status='DATABASE_INITIALIZED'
    $r.server_identity=Invoke-MySqlQuery 'SELECT @@server_uuid,@@version,@@server_id,@@innodb_buffer_pool_size;' $admin
}
catch{
    $r.status='FAILED'
    $r.failure=$_.Exception.Message -replace '[a-f0-9]{48}','REDACTED'
}
finally{
    $r.utc=[datetime]::UtcNow.ToString('o')
    $p=Join-Path $work 'setup-receipt.json'
    Write-JsonFile $r $p
    Publish-EvidenceFile $p ($m.role+'-setup.json')
}
