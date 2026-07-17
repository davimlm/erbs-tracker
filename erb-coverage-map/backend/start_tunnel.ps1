param([string]$CloudflaredPath)

Write-Host "Iniciando Cloudflare Tunnel..." -ForegroundColor Cyan

$logFile = "$env:TEMP\cloudflared_url.log"
if (Test-Path $logFile) { Remove-Item $logFile }

$proc = Start-Process -FilePath $CloudflaredPath `
    -ArgumentList "tunnel", "--protocol", "http2", "--url", "http://localhost:8000" `
    -RedirectStandardError $logFile `
    -RedirectStandardOutput "$env:TEMP\cloudflared_stdout.log" `
    -PassThru -WindowStyle Hidden

Write-Host "Aguardando URL (ate 15s)..." -ForegroundColor Yellow

$url = $null
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($content -match "https://[a-z0-9\-]+\.trycloudflare\.com") {
            $url = $matches[0]
            break
        }
    }
}

if ($url) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " URL DO TUNEL CLOUDFLARE:" -ForegroundColor Green
    Write-Host " $url" -ForegroundColor White
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    # Salva URL num arquivo para o bat ler
    $url | Out-File "$env:TEMP\cloudflared_tunnel_url.txt" -Encoding utf8
} else {
    Write-Host ""
    Write-Host "[AVISO] Nao foi possivel capturar a URL automaticamente." -ForegroundColor Yellow
    Write-Host "Verifique: $logFile" -ForegroundColor Yellow
}

# Mostra log em tempo real
Write-Host "--- Log do Cloudflare Tunnel (Ctrl+C para sair) ---" -ForegroundColor DarkGray
Get-Content $logFile -Wait
