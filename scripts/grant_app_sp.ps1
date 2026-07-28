param(
  [string]$Profile = "Khadara",
  [string]$WarehouseId = "607eec0346978542",
  [string]$Sp = "f1146f27-bc61-4bd5-8993-6183ed8fe8cc"
)

$bt = [char]96  # backtick, for UC identifier quoting

function Invoke-DbxSql([string]$stmt) {
  $body = @{ warehouse_id = $WarehouseId; statement = $stmt; wait_timeout = "30s" }
  $tmp = Join-Path $env:TEMP "dbx_sql.json"
  [System.IO.File]::WriteAllText($tmp, ($body | ConvertTo-Json))
  $out = databricks api post /api/2.0/sql/statements --json "@$tmp" -p $Profile 2>&1
  return ($out | Out-String)
}

$tables = @(
  "file2edi_orders","file2edi_order_partners","file2edi_order_lines",
  "file2edi_order_anomalies","file2edi_conversions","file2edi_conversion_history",
  "file2edi_audit_events","file2edi_pdf_uploads","file2edi_settings"
)

foreach ($t in $tables) {
  $stmt = "GRANT SELECT, MODIFY ON TABLE hcdap_prod.silver_hcfrdashlog.$t TO $bt$Sp$bt"
  $raw = Invoke-DbxSql $stmt
  try { $r = $raw | ConvertFrom-Json } catch { $r = $null }
  if ($r -and $r.status) {
    $msg = if ($r.status.error) { $r.status.error.message } else { "OK" }
    "{0,-30} {1,-10} {2}" -f $t, $r.status.state, $msg
  } else {
    "{0,-30} {1}" -f $t, ("RAW: " + $raw.Trim())
  }
}
