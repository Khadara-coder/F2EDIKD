$ErrorActionPreference = "Stop"
$dir = "data\masterdata"
$p = Import-Csv (Join-Path $dir "10564_Partners.csv") -Delimiter ';'
$c = Import-Csv (Join-Path $dir "10564_Customers.csv") -Delimiter ';'

$pSold = $p.SOLDTO | Sort-Object -Unique
$cSold = $c.SOLDTO | Sort-Object -Unique
$cset = @{}; foreach ($x in $cSold) { $cset[$x] = $true }
$pset = @{}; foreach ($x in $pSold) { $pset[$x] = $true }

"Partners rows              : $($p.Count)"
"Partners SOLDTO uniques    : $($pSold.Count)"
"Customers SOLDTO uniques   : $($cSold.Count)"
"SOLDTO in Partners not in Customers : $((@($pSold | Where-Object { -not $cset[$_] })).Count)"
"SOLDTO in Customers not in Partners : $((@($cSold | Where-Object { -not $pset[$_] })).Count)"
""
"'Fonction Partenaire' == SHIPTO : $((@($p | Where-Object { $_.'Fonction Partenaire' -eq $_.SHIPTO })).Count) / $($p.Count)"
"'Gestionaire ADV'     == NAME   : $((@($p | Where-Object { $_.'Gestionaire ADV' -eq $_.NAME })).Count) / $($p.Count)"
""
"Rows with empty STRAS  : $((@($p | Where-Object { -not $_.STRAS })).Count)"
"Rows with empty PSTLZ  : $((@($p | Where-Object { -not $_.PSTLZ })).Count)"
"Rows with empty ORT01  : $((@($p | Where-Object { -not $_.ORT01 })).Count)"
""
"Sample where Gestionaire ADV != NAME:"
$p | Where-Object { $_.'Gestionaire ADV' -ne $_.NAME } | Select-Object -First 5 SOLDTO, NAME, 'Gestionaire ADV' | Format-Table -Auto | Out-String
