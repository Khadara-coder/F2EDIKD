#!/usr/bin/env powershell
# Test RBAC endpoints

Write-Host "=== TEST 1: Master Data Search (ADV vs Admin) ===" -ForegroundColor Cyan

# Test ADV user
Write-Host "`n[ADV user - should see filtered sold-to]" -ForegroundColor Yellow
$advResponse = curl.exe -s -H "X-Forwarded-User: adv_user@bosch.com" -H "X-Forwarded-Role: adv" `
  "http://localhost:8000/api/masterdata/customers/search?q=1001"
Write-Host $advResponse

# Test Admin user
Write-Host "`n[Admin user - should see all sold-to]" -ForegroundColor Yellow
$adminResponse = curl.exe -s -H "X-Forwarded-User: admin@bosch.com" -H "X-Forwarded-Role: admin" `
  "http://localhost:8000/api/masterdata/customers/search?q=1001"
Write-Host $adminResponse

Write-Host "`nTests completed" -ForegroundColor Green
