param(
    [int]$SampleSize = 50,
    [int]$Seed = 0,
    [string]$BaseUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'

$root = Join-Path $PSScriptRoot '..\RAG Purchase Orders'
$root = (Resolve-Path $root).Path
$reports = Join-Path $PSScriptRoot '..\reports'
if (-not (Test-Path $reports)) { New-Item -ItemType Directory -Path $reports | Out-Null }

$allPdfs = Get-ChildItem $root -File | Where-Object { $_.Extension -match '^\.(pdf|PDF)$' }
if (-not $allPdfs -or $allPdfs.Count -eq 0) {
    throw "No PDF files found in $root"
}

if ($SampleSize -le 0) {
    $SampleSize = 50
}
if ($SampleSize -gt $allPdfs.Count) {
    $SampleSize = $allPdfs.Count
}

$effectiveSeed = $Seed
if ($effectiveSeed -le 0) {
    $effectiveSeed = Get-Random -Minimum 1 -Maximum 2147483646
}
$rng = [System.Random]::new($effectiveSeed)
$pdfs = $allPdfs | Sort-Object { $rng.Next() } | Select-Object -First $SampleSize | Sort-Object Name

Write-Output "Selected $($pdfs.Count) random PDF(s) out of $($allPdfs.Count)"
Write-Output "Seed=$effectiveSeed"
$rows = New-Object System.Collections.Generic.List[object]

$idx = 0
foreach ($f in $pdfs) {
    $idx++
    $pct = [int](($idx / [double]$pdfs.Count) * 100)
    Write-Progress -Activity 'RAG API evaluation' -Status ("{0}/{1} - {2}" -f $idx, $pdfs.Count, $f.Name) -PercentComplete $pct
    if (($idx % 25) -eq 0) {
        Write-Output "progress $idx/$($pdfs.Count)"
    }

    try {
        $upJson = curl.exe --noproxy "*" -s -F "pdf=@$($f.FullName)" "$BaseUrl/api/upload"
        $up = $upJson | ConvertFrom-Json
        $uploadId = $up.uploadId
        if (-not $uploadId) { throw 'uploadId missing' }

        $exJson = curl.exe --noproxy "*" -s -X POST "$BaseUrl/api/upload/$uploadId/extract"
        $ex = $exJson | ConvertFrom-Json
        $orderId = $ex.orderId
        if (-not $orderId) { throw 'orderId missing' }

        $rvJson = curl.exe --noproxy "*" -s "$BaseUrl/api/orders/$orderId/review"
        $rv = $rvJson | ConvertFrom-Json
        $o = $rv.order
        $sold = @($rv.partners | Where-Object { $_.partnerFunction -eq 'SOLDTO' } | Select-Object -First 1)
        $ship = @($rv.partners | Where-Object { $_.partnerFunction -eq 'SHIPTO' } | Select-Object -First 1)

        $rows.Add([pscustomobject]@{
            fileName = $f.Name
            orderId = $orderId
            status = $o.status
            confidence = $o.globalConfidence
            soldto = $sold.partnerCode
            shipto = $ship.partnerCode
            orderDate = $o.orderDate
            requestedDeliveryDate = $o.requestedDeliveryDate
            lineCount = $o.lineCount
            hasOrderDate = [bool]($o.orderDate)
            hasDeliveryDate = [bool]($o.requestedDeliveryDate)
            hasLines = [bool](($o.lineCount -as [int]) -gt 0)
        }) | Out-Null
    }
    catch {
        $rows.Add([pscustomobject]@{
            fileName = $f.Name
            orderId = ''
            status = 'ERROR'
            confidence = 0
            soldto = ''
            shipto = ''
            orderDate = ''
            requestedDeliveryDate = ''
            lineCount = 0
            hasOrderDate = $false
            hasDeliveryDate = $false
            hasLines = $false
        }) | Out-Null
    }
}

Write-Progress -Activity 'RAG API evaluation' -Completed

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$csv = Join-Path $reports "rag_api_eval_${SampleSize}_$ts.csv"
$json = Join-Path $reports "rag_api_eval_${SampleSize}_$ts.json"
$rows | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8
$rows | ConvertTo-Json -Depth 5 | Set-Content -Path $json -Encoding UTF8

$total = $rows.Count
$ok = ($rows | Where-Object { $_.status -ne 'ERROR' }).Count
$od = ($rows | Where-Object { $_.hasOrderDate }).Count
$dd = ($rows | Where-Object { $_.hasDeliveryDate }).Count
$ln = ($rows | Where-Object { $_.hasLines }).Count

Write-Output "TOTAL=$total OK=$ok ORDER_DATE=$od DELIVERY_DATE=$dd LINES=$ln"
Write-Output "CSV=$csv"
Write-Output "JSON=$json"
