$work='C:\benchmark'
. 'C:\benchmark\common.ps1'
Initialize-ResourceCounters
$sw=[Diagnostics.Stopwatch]::StartNew()
$slot=0
$w=[IO.StreamWriter]::new('C:\benchmark\app-metrics.ndjson',$false,[Text.UTF8Encoding]::new($false))
try{
    while($sw.Elapsed.TotalSeconds -lt 7200){
        $o=Get-ResourceSample
        $o.slot=$slot
        $o.requested_period_ms=1000
        $w.WriteLine(($o|ConvertTo-Json -Compress -Depth 10))
        $w.Flush()
        $slot++
        $next=$slot*1000
        if($sw.ElapsedMilliseconds -gt $next){
            $slot=[int][math]::Floor($sw.ElapsedMilliseconds/1000)+1
        }
        else{
            Start-Sleep -Milliseconds ([int][math]::Max(0,$next-$sw.ElapsedMilliseconds))
        }
    }
}
finally{
    $w.Dispose()
}
